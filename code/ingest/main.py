"""ingest：MQTT 订阅 → 批量写 TimescaleDB。

- 攒够 BATCH_ROWS 或到 BATCH_SECONDS 就刷一次；
- 幂等键 (drive_id, ts, seq) 冲突即忽略，重放不增行；
- 自带 /healthz（默认 8091）报告 lag_seconds / spool_rows / last_ts / rows。

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
SPOOL_DIR = os.environ.get("SPOOL_DIR", "/tmp/interroll-ingest-spool")
os.makedirs(SPOOL_DIR, exist_ok=True)

INSERT_SQL = """
INSERT INTO telemetry (ts, zone_id, drive_id, speed_mps, current_a, temp_c, state, seq)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (zone_id, drive_id, ts, seq) DO NOTHING
"""

state_lock = threading.Lock()
buffer: list[tuple] = []
stats = {"rows_written": 0, "last_ts": None, "last_flush": 0.0, "batches": 0, "spooled": 0}


def spool_rows(rows: list[tuple]) -> None:
    """写库失败时兜底：整批落本地文件，等库恢复再补。"""
    path = os.path.join(SPOOL_DIR, f"{int(time.time() * 1000)}.ndjson")
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps([row[0].isoformat(), *row[1:]], ensure_ascii=False) + "\n")
    with state_lock:
        stats["spooled"] += len(rows)
    log.warning("flush failed, spooled", extra={"rows": len(rows), "detail": path})


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


def spool_pending() -> int:
    n = 0
    for name in os.listdir(SPOOL_DIR):
        if name.endswith(".ndjson"):
            with open(os.path.join(SPOOL_DIR, name), encoding="utf-8") as fh:
                n += sum(1 for _ in fh)
    return n


def replay_spool() -> None:
    """独立线程 + 独立连接：库恢复后把 spool 文件补回。

    流式分块，内存 O(chunk) 而不是 O(file)：
      断网 1 小时 = 360 条/秒 × 3600 ≈ 130 万行 / 160MB，读成整表会直接吃掉内存。
    崩溃语义：不记游标，从头重读；重复行由主键 (zone_id, drive_id, ts, seq) 挡掉。
    """
    files = sorted(f for f in os.listdir(SPOOL_DIR) if f.endswith(".ndjson"))
    if not files:
        return
    conn = psycopg.connect(DSN)
    try:
        for name in files:
            path = os.path.join(SPOOL_DIR, name)
            total = 0
            chunk: list[tuple] = []
            with open(path, encoding="utf-8") as fh:
                for line in fh:  # 逐行：文件对象自己就是游标
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ts, zone, drive, speed, current, temp, state, seq = json.loads(line)
                    except (ValueError, TypeError):
                        continue  # 崩溃留下的半行，跳过而不是整批失败
                    chunk.append((datetime.fromisoformat(ts), zone, drive, speed, current, temp, state, seq))
                    if len(chunk) >= 500:
                        with conn.cursor() as cur:
                            cur.executemany(INSERT_SQL, chunk)
                        conn.commit()
                        total += len(chunk)
                        chunk.clear()
            if chunk:
                with conn.cursor() as cur:
                    cur.executemany(INSERT_SQL, chunk)
                conn.commit()
                total += len(chunk)
            os.remove(path)
            with state_lock:
                stats["spooled"] = max(0, stats["spooled"] - total)
                stats["rows_written"] += total
            log.info("spool replayed", extra={"rows": total, "detail": name})
            event(conn, "spool_replayed", rows=total, file=name)
    finally:
        conn.close()


_conn: psycopg.Connection | None = None
_conn_lock = threading.Lock()
_db_down = False   # 用于在恢复时补一条事件，而不是在断库时（那时也写不进去）


def get_conn(force_new: bool = False) -> psycopg.Connection:
    """连接断了就重连；重连失败抛给调用方，由调用方落 spool。"""
    global _conn
    with _conn_lock:
        if force_new or _conn is None or _conn.closed:
            _conn = psycopg.connect(DSN)
        return _conn


def flush() -> int:
    with state_lock:
        if not buffer:
            return 0
        rows, buffer[:] = list(buffer), []
    global _db_down
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.executemany(INSERT_SQL, rows)
        conn.commit()
        if _db_down:
            _db_down = False
            event(conn, "db_recovered", "warning")
    except Exception as exc:  # 库挂了：不丢数据，整批落 spool
        try:
            if conn is not None:
                conn.rollback()
        except Exception:
            pass
        spool_rows(rows)
        _db_down = True
        log.error("flush failed", extra={"detail": str(exc)[:200]})
        return 0
    with state_lock:
        stats["rows_written"] += len(rows)
        stats["batches"] += 1
        stats["last_flush"] = time.time()
        stats["last_ts"] = rows[-1][0]
    log.debug("flush", extra={"rows": len(rows)})
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
    with state_lock:
        buffer.append(row)


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
            "spool_rows": spool_pending(),
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

    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"ingest-{os.getpid()}")
    cli.on_message = on_message
    if MQTT_USERNAME:
        cli.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    cli.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    cli.subscribe(TOPIC, qos=1)
    cli.loop_start()
    log.info("subscribed", extra={"detail": f"{TOPIC} @ {MQTT_HOST}:{MQTT_PORT}"})

    def replay_loop() -> None:
        while True:
            time.sleep(2.0)
            try:
                replay_spool()
            except Exception:
                pass  # 库还没好，下一轮再试

    threading.Thread(target=replay_loop, daemon=True).start()

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
