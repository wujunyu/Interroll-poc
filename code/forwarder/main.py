"""边缘 → 中心：按水位把边缘库里的点推送到中心库（应用层 store-and-forward）。

为什么不用 MQTT bridge：WAN 断几小时很常见，broker 队列撑不住；落地库 + 水位重放才不怕断。
水位来源是中心库的 max(ts)，重启后自动续传；重复由 (site_id, zone_id, drive_id, ts, seq) 挡掉。
"""
from __future__ import annotations

import json
import os
import signal
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import psycopg

EDGE_DSN = os.environ["EDGE_DSN"]
CENTER_DSN = os.environ["CENTER_DSN"]
SITE_ID = os.environ.get("SITE_ID", "S1")
BATCH = int(os.environ.get("BATCH", "500"))
OVERLAP = int(os.environ.get("OVERLAP", "120"))   # 回扫窗口：秒
INTERVAL = float(os.environ.get("INTERVAL", "1"))
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "8082"))
VERSION = os.environ.get("APP_VERSION", "dev")

stop = threading.Event()
state = {"sent": 0, "watermark": None, "last_error": None, "lag_seconds": None}
lock = threading.Lock()

SELECT_EDGE = """
select ts, zone_id, drive_id, speed_mps, current_a, temp_c, state, seq
from telemetry where ts > %s order by ts limit %s
"""
# 重叠回扫：补"迟到但时间戳更早"的行（设备时钟抖动/批量落库顺序）
SELECT_GAP = """
select ts, zone_id, drive_id, speed_mps, current_a, temp_c, state, seq
from telemetry where ts > %s and ts <= %s order by ts limit %s
"""
INSERT_CENTER = """
insert into telemetry (site_id, ts, zone_id, drive_id, speed_mps, current_a, temp_c, state, seq)
values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
on conflict (site_id, zone_id, drive_id, ts, seq) do nothing
"""


def connect(dsn: str) -> psycopg.Connection:
    return psycopg.connect(dsn, connect_timeout=5)


def main() -> int:
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    center = connect(CENTER_DSN)
    with center.cursor() as cur:
        cur.execute("select max(ts) from telemetry where site_id = %s", (SITE_ID,))
        row = cur.fetchone()
    watermark = row[0]
    if watermark is None:
        # 首次启动：只回放最近 START_WINDOW 秒，避免把边缘历史全量拉到中心
        start_window = int(os.environ.get("START_WINDOW", "600"))
        watermark = datetime.fromtimestamp(time.time() - start_window, tz=timezone.utc)
    with lock:
        state["watermark"] = watermark.isoformat() if watermark else None

    class Health(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            with lock:
                body = json.dumps({"ok": True, "version": VERSION, "site": SITE_ID,
                                   "sent": state["sent"], "watermark": state["watermark"],
                                   "lag_seconds": state["lag_seconds"],
                                   "last_error": state["last_error"]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a) -> None:
            pass

    threading.Thread(target=lambda: HTTPServer(("0.0.0.0", HEALTH_PORT), Health).serve_forever(),
                     daemon=True).start()

    edge = connect(EDGE_DSN)
    gap_from = watermark - timedelta(seconds=OVERLAP) if watermark else None
    gap_to = watermark
    last_idle = time.monotonic()

    def push(rows) -> None:
        nonlocal center
        with center.cursor() as cur:
            cur.executemany(INSERT_CENTER, [(SITE_ID, *r) for r in rows])
        center.commit()

    while not stop.is_set():
        try:
            # 空闲时先补缺口（重叠窗口内重扫，重复由 ON CONFLICT 挡掉）
            if gap_from is not None and gap_from < gap_to:
                with edge.cursor() as cur:
                    cur.execute(SELECT_GAP, (gap_from, gap_to, BATCH))
                    gap_rows = cur.fetchall()
                if gap_rows:
                    push(gap_rows)
                    gap_from = gap_rows[-1][0]
                    with lock:
                        state["sent"] += len(gap_rows)
                    continue
                gap_from = None
            with edge.cursor() as cur:
                cur.execute(SELECT_EDGE, (watermark or datetime(1970, 1, 1, tzinfo=timezone.utc), BATCH))
                rows = cur.fetchall()
            if not rows:
                # 空闲超过一个周期就重新开一次回扫，兜住任意时刻迟到的行
                if gap_from is None and time.monotonic() - last_idle > 30:
                    gap_from, gap_to = watermark - timedelta(seconds=OVERLAP), watermark
                    last_idle = time.monotonic()
                time.sleep(INTERVAL)
                continue
            push(rows)
            watermark = rows[-1][0]
            last_idle = time.monotonic()
            with lock:
                state["sent"] += len(rows)
                state["watermark"] = watermark.isoformat()
                state["lag_seconds"] = round((datetime.now(timezone.utc) - watermark).total_seconds(), 1)
                state["last_error"] = None
        except Exception as exc:                      # 中心挂了：水位不动，等它回来
            with lock:
                state["last_error"] = str(exc)[:200]
            time.sleep(2)
            try:
                center = connect(CENTER_DSN)
            except Exception:
                pass
    edge.close()
    center.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
