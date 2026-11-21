"""ingest：MQTT 订阅 → 预写日志 → 批量写 TimescaleDB。

- 每条先追加 WAL（fsync 后才入库），攒够 BATCH_ROWS 或到 BATCH_SECONDS 刷一次；
- 幂等键 (drive_id, ts, seq) 冲突即忽略，重放不增行；
- 自带 /healthz（默认 8091）报告 lag_seconds / wal_pending_bytes / last_ts / rows。

    DB_DSN=postgresql://poc:poc_dev_pw@127.0.0.1:5437/interroll_poc \
    MQTT_HOST=127.0.0.1 MQTT_PORT=1884 python code/ingest/main.py
"""
from __future__ import annotations

import json
import os
import signal
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import paho.mqtt.client as mqtt
import psycopg

from log_setup import setup as setup_log
from psycopg.rows import dict_row

DSN = os.environ["DB_DSN"]
VERSION = os.environ.get("APP_VERSION", "dev")
log = setup_log("ingest", os.environ.get("LOG_LEVEL", "INFO"))
MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USERNAME = os.environ.get("MQTT_USERNAME", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
TOPIC = os.environ.get("MQTT_TOPIC", "line/#")
BATCH_ROWS = int(os.environ.get("BATCH_ROWS", "200"))
BATCH_SECONDS = float(os.environ.get("BATCH_SECONDS", "1.0"))
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "8091"))
WAL_DIR = os.environ.get("WAL_DIR", "/tmp/interroll-ingest-wal")
REPLAY_STALE_SECONDS = float(os.environ.get("REPLAY_STALE_SECONDS", "60"))
os.makedirs(WAL_DIR, exist_ok=True)

INSERT_SQL = """
INSERT INTO telemetry (ts, zone_id, drive_id, speed_mps, current_a, temp_c, state, seq)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (zone_id, drive_id, ts, seq) DO NOTHING
"""

state_lock = threading.Lock()          # 保护 buffer 与 WAL 追加的原子性
flush_lock = threading.Lock()          # flush 与 replay 互斥，避免重复/竞争
buffer: list[tuple] = []
stats = {"rows_written": 0, "last_ts": None, "last_flush": 0.0, "batches": 0,
         "wal_pending_bytes": 0, "wal_committed": 0,
         "replay_tick": 0.0, "last_frame": 0.0}
_replay_thread: threading.Thread | None = None

def event(conn: psycopg.Connection, kind: str, severity: str = "info", **detail) -> None:
    """关键事件写库（不是日志流水）：启动/断库/恢复/补传完成。写失败不影响数据面。"""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO events (ts, kind, severity, detail) VALUES (now(), %s, %s, %s::jsonb)",
                (kind, severity, json.dumps({"version": VERSION, **detail}, ensure_ascii=False)),
            )
        conn.commit()
    except Exception:
        pass


WAL_PATH = os.path.join(WAL_DIR, "wal.ndjson")
WAL_COMMIT_PATH = os.path.join(WAL_DIR, "wal.commit")
wal_fh = None
wal_committed_bytes = 0


def wal_open() -> None:
    """打开预写日志，读取上次提交到的字节偏移。"""
    global wal_fh, wal_committed_bytes
    os.makedirs(WAL_DIR, exist_ok=True)
    wal_committed_bytes = 0
    if os.path.exists(WAL_COMMIT_PATH):
        try:
            wal_committed_bytes = int(open(WAL_COMMIT_PATH, encoding="utf-8").read().strip() or 0)
        except ValueError:
            wal_committed_bytes = 0
    wal_fh = open(WAL_PATH, "ab", buffering=0)   # 无缓冲：写入即进 page cache
    stats["wal_committed"] = wal_committed_bytes
    log.info("wal opened", extra={"detail": f"committed={wal_committed_bytes}B"})


def wal_append(line: str) -> None:
    """调用方必须持 state_lock：WAL 追加与 buffer 追加是同一个原子动作。"""
    wal_fh.write(line.encode())


def wal_sync() -> None:
    wal_fh.flush()
    os.fsync(wal_fh.fileno())


def wal_commit(offset: int) -> None:
    """把提交游标推进到 offset：之前的行已经落库，崩溃后不再重放。只许前进。"""
    global wal_committed_bytes
    offset = max(offset, wal_committed_bytes)
    with open(WAL_COMMIT_PATH, "w", encoding="utf-8") as f:
        f.write(str(offset))
        f.flush()
        os.fsync(f.fileno())
    wal_committed_bytes = offset
    stats["wal_committed"] = offset


def wal_pending() -> int:
    try:
        return max(0, os.path.getsize(WAL_PATH) - wal_committed_bytes)
    except OSError:
        return 0


def wal_replay() -> int:
    """从提交游标回放未提交的尾部（崩溃恢复 / 库恢复都走这条）。"""
    with flush_lock:
        try:
            size = os.path.getsize(WAL_PATH)
        except OSError:
            return 0
        if size <= wal_committed_bytes:
            return 0
        total = 0
        offset = wal_committed_bytes
        conn = psycopg.connect(DSN, connect_timeout=5)
        try:
            with open(WAL_PATH, "rb") as fh:
                fh.seek(wal_committed_bytes)
                chunk: list[tuple] = []
                for raw in fh:
                    offset += len(raw)
                    if raw.strip():
                        try:
                            ts, zone, drive, speed, current, temp, state, seq = json.loads(raw)
                            chunk.append((datetime.fromisoformat(ts), zone, drive, speed, current, temp, state, seq))
                        except (ValueError, TypeError):
                            continue          # 崩溃留下的半行，跳过
                    if len(chunk) >= 500:
                        with conn.cursor() as cur:
                            cur.executemany(INSERT_SQL, chunk)
                        conn.commit()
                        wal_commit(offset)
                        total += len(chunk)
                        chunk.clear()
                if chunk:
                    with conn.cursor() as cur:
                        cur.executemany(INSERT_SQL, chunk)
                    conn.commit()
                    wal_commit(offset)
                    total += len(chunk)
        finally:
            conn.close()
        if total:
            with state_lock:
                stats["rows_written"] += total
            log.info("wal replayed", extra={"rows": total})
            try:
                event(psycopg.connect(DSN, connect_timeout=5), "wal_replayed", rows=total)
            except Exception:
                pass
        return total


def wal_compact(threshold: int = 64 * 1024 * 1024) -> None:
    """已提交部分超过阈值就把文件重写一遍，只留未提交尾部。"""
    global wal_fh
    if wal_committed_bytes < threshold:
        return
    with state_lock:
        keep = b""
        try:
            size = os.path.getsize(WAL_PATH)
            if size > wal_committed_bytes:
                with open(WAL_PATH, "rb") as fh:
                    fh.seek(wal_committed_bytes)
                    keep = fh.read()
        except OSError:
            return
        wal_fh.close()
        with open(WAL_PATH, "wb") as fh:
            fh.write(keep)
            fh.flush()
            os.fsync(fh.fileno())
        wal_fh = open(WAL_PATH, "ab", buffering=0)
    wal_commit(len(keep))
    log.info("wal compacted", extra={"detail": f"keep={len(keep)}B"})


_conn: psycopg.Connection | None = None
_conn_lock = threading.Lock()
_db_down = False   # 用于在恢复时补一条事件，而不是在断库时（那时也写不进去）


def get_conn(force_new: bool = False) -> psycopg.Connection:
    """连接断了就重连；重连失败抛给调用方，由调用方保留 WAL 不推进游标。"""
    global _conn
    with _conn_lock:
        if force_new or _conn is None or _conn.closed:
            _conn = psycopg.connect(DSN, connect_timeout=5)
        return _conn


def flush() -> int:
    with flush_lock:
        with state_lock:
            if not buffer:
                return 0
            rows, buffer[:] = list(buffer), []
            end = wal_fh.tell()          # 这批数据在 WAL 中的结束偏移
        global _db_down
        conn = None
        try:
            wal_sync()                   # ① 先落盘（write-ahead）
            conn = get_conn()
            with conn.cursor() as cur:
                cur.executemany(INSERT_SQL, rows)
            conn.commit()                # ② 再入库
            wal_commit(end)              # ③ 最后推进游标
            if _db_down:
                _db_down = False
                event(conn, "db_recovered", "warning")
        except Exception as exc:         # 库挂了：不推进游标，WAL 就是缓冲
            try:
                if conn is not None:
                    conn.rollback()
            except Exception:
                pass
            _db_down = True
            log.error("flush failed, kept in WAL", extra={"detail": str(exc)[:200]})
            return 0
        with state_lock:
            stats["rows_written"] += len(rows)
            stats["batches"] += 1
            stats["last_flush"] = time.time()
            stats["last_ts"] = rows[-1][0]
        log.debug("flush", extra={"rows": len(rows)})
    wal_compact()
    return len(rows)


def on_message(client, userdata, msg) -> None:
    try:
        p = json.loads(msg.payload)
        row = (
            datetime.fromisoformat(p["ts"]),
            p["zone"],
            p["drive"],
            p.get("speed_mps"),
            p.get("current_a"),
            p.get("temp_c"),
            p.get("state"),
            int(p["seq"]),
        )
    except Exception:
        return
    line = json.dumps([row[0].isoformat(), *row[1:]], ensure_ascii=False) + "\n"
    with state_lock:
        wal_append(line)
        buffer.append(row)
        stats["last_frame"] = time.time()


class Health(BaseHTTPRequestHandler):
    conn: psycopg.Connection

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/healthz":
            self.send_response(404)
            self.end_headers()
            return
        with state_lock:
            pending = len(buffer)
            last_ts = stats["last_ts"]
            written = stats["rows_written"]
        lag = None
        if last_ts is not None:
            lag = round((datetime.now(timezone.utc) - last_ts.astimezone(timezone.utc)).total_seconds(), 2)
        body = json.dumps({
            "ok": True,
            "version": os.environ.get("APP_VERSION", "dev"),
            "rows_written": written,
            "pending_in_buffer": pending,
            "wal_pending_bytes": wal_pending(),
            "replay_thread_alive": bool(_replay_thread and _replay_thread.is_alive()),
            "replay_tick_age_s": round(time.time() - stats["replay_tick"], 1) if stats["replay_tick"] else None,
            "wal_stuck": bool(stats["replay_tick"] and
                              time.time() - stats["replay_tick"] > REPLAY_STALE_SECONDS),
            "frame_age_s": round(time.time() - stats["last_frame"], 1) if stats["last_frame"] else None,
            "lag_seconds": lag,
            "batches": stats["batches"],
        }, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args) -> None:  # 静默访问日志
        return


def _on_sigterm(signum, frame):  # docker stop / systemd stop 发的是 SIGTERM
    raise KeyboardInterrupt


def main() -> int:
    global _conn
    signal.signal(signal.SIGTERM, _on_sigterm)
    wal_open()
    try:
        replayed = wal_replay()
        if replayed:
            log.info("crash tail recovered", extra={"rows": replayed})
    except Exception as exc:
        log.error("wal replay at startup failed", extra={"detail": str(exc)[:200]})
    get_conn(force_new=True)
    conn = _conn
    with conn.cursor() as cur:
        cur.execute("select 1")
        # 水位线不单独存表：库里 max(ts) 就是水位，重启后自动恢复，少一份可能写歪的状态
        cur.execute("select max(ts) from telemetry")
        row = cur.fetchone()
        if row and row[0]:
            stats["last_ts"] = row[0]
            log.info("watermark restored", extra={"detail": row[0].isoformat()})
    log.info("db connected")

    srv = ThreadingHTTPServer(("0.0.0.0", HEALTH_PORT), Health)
    srv.conn = conn
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log.info("healthz listening", extra={"detail": HEALTH_PORT})
    event(_conn, "ingest_start")

    # clean_session=False + 固定 client_id：ingest 重启期间 broker 替它排队（QoS1），
    # 重连后补投；重复由 (zone_id, drive_id, ts, seq) 幂等键挡掉。
    cli = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=os.environ.get("MQTT_CLIENT_ID", "ingest-1"),
        clean_session=False,
    )
    cli.on_message = on_message
    # broker 重启后要尽快复连，否则排队的数据要等几十秒才被取走
    cli.reconnect_delay_set(min_delay=1, max_delay=2)
    cli.max_inflight_messages_set(500)
    cli.on_connect = lambda c, u, flags, rc, props=None: log.info(
        "mqtt connected", extra={"detail": f"session_present={getattr(flags, 'session_present', None)}"})
    if MQTT_USERNAME:
        cli.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    cli.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    cli.subscribe(TOPIC, qos=1)
    cli.loop_start()
    log.info("subscribed", extra={"detail": f"{TOPIC} @ {MQTT_HOST}:{MQTT_PORT}"})

    def replay_loop() -> None:
        while True:
            time.sleep(2.0)
            stats["replay_tick"] = time.time()
            if not _db_down:
                continue          # 正常运行时由 flush 推进游标，回放只在库故障时接管
            try:
                wal_replay()
            except Exception:
                pass              # 库还没好，下一轮再试

    global _replay_thread
    _replay_thread = threading.Thread(target=replay_loop, daemon=True)
    _replay_thread.start()

    last_flush = time.time()
    try:
        while True:
            time.sleep(min(0.2, BATCH_SECONDS / 2))
            due_rows = False
            due_time = False
            with state_lock:
                due_rows = len(buffer) >= BATCH_ROWS
            due_time = (time.time() - last_flush) >= BATCH_SECONDS
            if due_rows or due_time:
                flush()
                last_flush = time.time()
            # 看门狗 ①：线程死了 → 新建一个（Thread 不能 restart）
            if _replay_thread is not None and not _replay_thread.is_alive():
                log.error("replay thread died, restarting")
                _replay_thread = threading.Thread(target=replay_loop, daemon=True)
                _replay_thread.start()

            # 看门狗 ②：线程活着但心跳停了（卡在 IO）→ Python 杀不了线程，只能退出进程
            # WAL 已落盘，退出后由 docker restart 拉起并回放，不会丢数据
            tick_age = time.time() - stats["replay_tick"] if stats["replay_tick"] else 0.0
            if _db_down and tick_age > REPLAY_STALE_SECONDS and wal_pending() > 0:
                log.critical("replay stuck, exiting for supervisor restart",
                             extra={"detail": f"tick_age={tick_age:.0f}s pending={wal_pending()}B"})
                os._exit(3)
    except KeyboardInterrupt:
        flush()
        try:
            event(get_conn(), "ingest_stop")
        except Exception:
            pass
        log.info("stopped")
    finally:
        cli.loop_stop()
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
