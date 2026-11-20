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
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import paho.mqtt.client as mqtt
import psycopg
from psycopg.rows import dict_row

DSN = os.environ["DB_DSN"]
MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USERNAME = os.environ.get("MQTT_USERNAME", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
TOPIC = os.environ.get("MQTT_TOPIC", "line/#")
BATCH_ROWS = int(os.environ.get("BATCH_ROWS", "200"))
BATCH_SECONDS = float(os.environ.get("BATCH_SECONDS", "1.0"))
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "8091"))

INSERT_SQL = """
INSERT INTO telemetry (ts, zone_id, drive_id, speed_mps, current_a, temp_c, state, seq)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (zone_id, drive_id, ts, seq) DO NOTHING
"""

state_lock = threading.Lock()
buffer: list[tuple] = []
stats = {"rows_written": 0, "last_ts": None, "last_flush": 0.0, "batches": 0}


def flush(conn: psycopg.Connection) -> int:
    with state_lock:
        if not buffer:
            return 0
        rows, buffer[:] = list(buffer), []
    with conn.cursor() as cur:
        cur.executemany(INSERT_SQL, rows)
    conn.commit()
    with state_lock:
        stats["rows_written"] += len(rows)
        stats["batches"] += 1
        stats["last_flush"] = time.time()
        stats["last_ts"] = rows[-1][0]
    print(f"· flush {len(rows)} 行 (累计 {stats['rows_written']})", flush=True)
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
            "spool_rows": 0,
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


def main() -> int:
    conn = psycopg.connect(DSN, autocommit=False)
    with conn.cursor() as cur:
        cur.execute("select 1")
    print(f"✓ 已连库 {DSN.split('@')[-1]}", flush=True)

    srv = ThreadingHTTPServer(("0.0.0.0", HEALTH_PORT), Health)
    srv.conn = conn
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"· /healthz 监听 :{HEALTH_PORT}", flush=True)

    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"ingest-{os.getpid()}")
    cli.on_message = on_message
    if MQTT_USERNAME:
        cli.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    cli.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    cli.subscribe(TOPIC, qos=1)
    cli.loop_start()
    print(f"· 已订阅 {TOPIC} @ {MQTT_HOST}:{MQTT_PORT}", flush=True)

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
                flush(conn)
                last_flush = time.time()
    except KeyboardInterrupt:
        flush(conn)
        print("\n· 已停止", flush=True)
    finally:
        cli.loop_stop()
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
