"""api：REST 查历史 + WebSocket 推实时（10fps 节流）。

分工：
- 历史走库：≤5 分钟查原始点，更长查 1 分钟连续聚合（ADR-0003）；
- 实时走 MQTT：API 自己订一份，避免每帧回查数据库；
- 点数超过 1000 时上 LTTB，只影响「怎么画」，不影响任何统计口径。

    DB_DSN=... MQTT_HOST=127.0.0.1 MQTT_PORT=1883 MQTT_USERNAME=poc MQTT_PASSWORD=poc_dev_pw \
    .conda-env/bin/python code/api/main.py
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt
import psycopg
import uvicorn

from log_setup import setup as setup_log
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect

from alerts import AlertEngine, Rule
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row

DSN = os.environ["DB_DSN"]
MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USERNAME = os.environ.get("MQTT_USERNAME", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
TOPIC = os.environ.get("MQTT_TOPIC", "line/#")
WS_FPS = float(os.environ.get("WS_FPS", "10"))
VERSION = os.environ.get("APP_VERSION", "dev")
PORT = int(os.environ.get("API_PORT", "8000"))
ALERT_FOR = float(os.environ.get("ALERT_FOR_SECONDS", "30"))
ALERT_OFFLINE = float(os.environ.get("ALERT_OFFLINE_SECONDS", "15"))

engine = AlertEngine(
    rules=[
        Rule("电流过载", "current_a", float(os.environ.get("ALERT_CURRENT", "4.0")), "gt",
             ALERT_FOR, "critical", "{zone}/{drive} 电流 {value}A 超限"),
        Rule("速度掉零", "speed_mps", 0.05, "lt", ALERT_FOR, "warning",
             "{zone}/{drive} 速度 {value} m/s，疑似堵料"),
    ],
    offline_seconds=ALERT_OFFLINE,
)

WINDOWS = {"60s": 60, "5m": 300, "1h": 3600, "6h": 21600, "24h": 86400}

log = setup_log("api", os.environ.get("LOG_LEVEL", "INFO"))

app = FastAPI(title="Interroll PoC API", version=VERSION)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# ---- 实时缓存：paho 线程写，事件循环读 ----
live_lock = threading.Lock()
live: dict[tuple[str, str], dict[str, Any]] = {}
live_ts: dict[tuple[str, str], tuple[datetime, int]] = {}   # (事件时间, seq) 游标
mqtt_sys: dict[str, str] = {}   # $SYS 指标快照（连接数、丢弃数等）
live_meta = {"connected": False, "frames": 0, "last_ts": None}


def on_connect(client, userdata, flags, reason_code, properties=None) -> None:
    live_meta["connected"] = True
    client.subscribe([(TOPIC, 1), ("$SYS/#", 0)])


def on_disconnect(client, userdata, flags, reason_code, properties=None) -> None:
    live_meta["connected"] = False


def on_message(client, userdata, msg) -> None:
    if msg.topic.startswith("$SYS/"):
        mqtt_sys[msg.topic] = msg.payload.decode(errors="replace")[:64]
        return
    try:
        p = json.loads(msg.payload)
    except ValueError:
        return
    # 补传的消息 ts 是过去的；不能让旧值覆盖当前状态（到达顺序不可靠）
    try:
        ts = datetime.fromisoformat(p["ts"])
    except (KeyError, ValueError):
        return
    key = (p["zone"], p["drive"])
    seq = int(p.get("seq", 0))
    with live_lock:
        last = live_ts.get(key)
        # 用 (ts, seq) 做游标：同一秒内的多条靠 seq 区分，不会被误判成旧消息
        if last is not None and (ts, seq) <= last:
            return
        live_ts[key] = (ts, seq)
    try:
        for alert in engine.update(p):
            log.info("alert", extra={"detail": f"{alert.state} {alert.message}"})
    except Exception as exc:  # 规则写错不能把 MQTT 线程带走
        log.error("alert rule failed", extra={"detail": str(exc)[:200]})
    with live_lock:
        live[(p["zone"], p["drive"])] = {
            "zone": p["zone"], "drive": p["drive"],
            "speed_mps": p.get("speed_mps"), "current_a": p.get("current_a"),
            "temp_c": p.get("temp_c"), "state": p.get("state"), "ts": p["ts"],
        }
        live_meta["frames"] += 1
        live_meta["last_ts"] = p["ts"]


def start_mqtt() -> None:
    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"api-{os.getpid()}")
    cli.on_connect, cli.on_disconnect, cli.on_message = on_connect, on_disconnect, on_message
    if MQTT_USERNAME:
        cli.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    cli.reconnect_delay_set(min_delay=1, max_delay=2)
    cli.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    cli.loop_start()


def db() -> psycopg.Connection:
    return psycopg.connect(DSN, row_factory=dict_row)


def lttb(points: list[dict[str, Any]], threshold: int = 1000, x: str = "ts", y: str = "speed_mps") -> list[dict[str, Any]]:
    """Largest-Triangle-Three-Buckets：保形状的抽稀，只用于画线。"""
    n = len(points)
    if n <= threshold or threshold < 3:
        return points
    sampled = [points[0]]
    every = (n - 2) / (threshold - 2)
    a = 0
    for i in range(threshold - 2):
        start = int((i + 1) * every) + 1
        end = int((i + 2) * every) + 1
        end = min(end, n)
        avg_x = avg_y = 0.0
        for j in range(start, end):
            avg_x += points[j][x].timestamp()
            avg_y += points[j][y]
        span = max(1, end - start)
        avg_x /= span
        avg_y /= span
        ax, ay = points[a][x].timestamp(), points[a][y]
        best, best_area = start, -1.0
        for j in range(start, end):
            area = abs((ax - avg_x) * (points[j][y] - ay) - (ax - points[j][x].timestamp()) * (avg_y - ay)) / 2
            if area > best_area:
                best, best_area = j, area
        sampled.append(points[best])
        a = best
    sampled.append(points[-1])
    return sampled


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    out: dict[str, Any] = {
        "ok": True,
        "version": VERSION,
        "mqtt": {"connected": live_meta["connected"], "frames": live_meta["frames"], "last_ts": live_meta["last_ts"]},
        "ws_fps": WS_FPS,
    }
    try:
        with db() as conn, conn.cursor() as cur:
            cur.execute("select max(ts) as wm from telemetry")
            out["db"] = {"ok": True, "watermark": cur.fetchone()["wm"]}
    except Exception as exc:
        out["ok"] = False
        out["db"] = {"ok": False, "error": str(exc)[:120]}
    return out


@app.get("/api/zones")
def zones() -> list[dict[str, Any]]:
    """六区当前状态：在线驱动数、平均速度、最近 1 分钟吞吐。"""
    sql = """
    WITH recent AS (
        SELECT zone_id, drive_id, max(ts) AS last_ts, avg(speed_mps) AS v
        FROM telemetry
        WHERE ts > now() - interval '60 seconds'
        GROUP BY zone_id, drive_id
    )
    SELECT zone_id,
           count(*)                                   AS drives,
           count(*) FILTER (WHERE v > 0.05)           AS online,
           round(avg(v)::numeric, 3)                  AS speed_avg,
           max(last_ts)                               AS last_ts
    FROM recent
    GROUP BY zone_id
    ORDER BY zone_id
    """
    with db() as conn, conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    return [{"zone": r["zone_id"], "drives": r["drives"], "online": r["online"],
             "speed_avg": float(r["speed_avg"] or 0), "last_ts": r["last_ts"]} for r in rows]


@app.get("/api/series")
def series(
    zone: str = Query(..., min_length=1),
    drive: str = Query(..., min_length=1),
    window: str = Query("60s", pattern="^(60s|5m|1h|6h|24h)$"),
) -> dict[str, Any]:
    seconds = WINDOWS[window]
    use_raw = seconds <= 300
    with db() as conn, conn.cursor() as cur:
        if use_raw:
            cur.execute(
                """SELECT ts, speed_mps, current_a, temp_c FROM telemetry
                   WHERE zone_id=%s AND drive_id=%s AND ts > now() - make_interval(secs => %s)
                   ORDER BY ts""", (zone, drive, seconds))
            pts = [{"ts": r["ts"], "speed_mps": r["speed_mps"], "current_a": r["current_a"], "temp_c": r["temp_c"]} for r in cur.fetchall()]
            source = "raw"
        else:
            cur.execute(
                """SELECT bucket AS ts, speed_avg AS speed_mps, current_max AS current_a
                   FROM telemetry_1m
                   WHERE zone_id=%s AND drive_id=%s AND bucket > now() - make_interval(secs => %s)
                   ORDER BY bucket""", (zone, drive, seconds))
            pts = [{"ts": r["ts"], "speed_mps": float(r["speed_mps"] or 0), "current_a": float(r["current_a"] or 0)} for r in cur.fetchall()]
            source = "1m-agg"
    if not pts:
        raise HTTPException(status_code=404, detail=f"{zone}/{drive} 在 {window} 内没有数据")
    before = len(pts)
    pts = lttb(pts)
    return {"zone": zone, "drive": drive, "window": window, "source": source,
            "points": pts, "point_count": len(pts), "raw_count": before}


@app.get("/api/mqtt")
def mqtt_metrics() -> dict[str, Any]:
    """连接数与丢弃数的快照：峰值看 clients/maximum，速率看 load/connections。"""
    keys = [
        "clients/connected", "clients/maximum", "clients/total",
        "messages/received", "messages/sent", "publish/messages/dropped",
        "load/connections/1min",
    ]
    return {k.split("/")[-1]: mqtt_sys.get(f"$SYS/broker/{k}") for k in keys}


@app.get("/api/alerts")
def alerts(limit: int = Query(20, ge=1, le=200)) -> dict[str, Any]:
    """活动告警 + 最近历史。规则见 alerts.py（30 秒去抖，抖动不报）。"""
    return {"active": engine.active(), "history": engine.history(limit),
            "rules": {"for_seconds": ALERT_FOR, "offline_seconds": ALERT_OFFLINE}}


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket) -> None:
    await ws.accept()
    interval = 1.0 / WS_FPS
    try:
        while True:
            await asyncio.sleep(interval)
            with live_lock:
                snapshot = list(live.values())
                frames = live_meta["frames"]
            if not snapshot:
                await ws.send_json({"ts": datetime.now(timezone.utc).isoformat(), "points": []})
                continue
            # 按 (zone, drive) 排序，前端好做 diff
            snapshot.sort(key=lambda p: (p["zone"], p["drive"]))
            await ws.send_json({"ts": snapshot[-1]["ts"], "frames": frames, "points": snapshot})
    except WebSocketDisconnect:
        return


def sweeper() -> None:
    """离线规则靠扫：设备不再发消息时，update() 不会被调用。"""
    while True:
        time.sleep(1.0)
        try:
            for alert in engine.sweep():
                log.info("alert", extra={"detail": f"{alert.state} {alert.message}"})
        except Exception as exc:
            log.error("alert sweep failed", extra={"detail": str(exc)[:200]})


def main() -> int:
    log.info("api starting", extra={"detail": VERSION})
    threading.Thread(target=sweeper, daemon=True).start()
    start_mqtt()
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
