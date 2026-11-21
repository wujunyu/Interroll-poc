"""验证：补传的旧消息不会覆盖 api 的当前状态（V1 边界）。"""
import asyncio, json, os, time
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt
import websockets

CST = timezone(timedelta(hours=8))

def pub_old(seconds_ago: int = 3600) -> str:
    ts = (datetime.now(CST) - timedelta(seconds=seconds_ago)).isoformat(timespec="milliseconds")
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="stale-test")
    c.connect("127.0.0.1", int(os.environ.get("MQTT_PORT", "1884"))); c.loop_start()
    c.publish("line/Z1/drive/D01", json.dumps({
        "ts": ts, "zone": "Z1", "drive": "D01", "seq": 999999,
        "speed_mps": 9.99, "current_a": 9.99, "temp_c": 99, "state": "running"}), qos=1)
    time.sleep(1); c.loop_stop(); c.disconnect()
    return ts

def pub_now() -> None:
    ts = datetime.now(CST).isoformat(timespec="milliseconds")
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="seed-test")
    c.connect("127.0.0.1", int(os.environ.get("MQTT_PORT", "1884"))); c.loop_start()
    c.publish("line/Z1/drive/D01", json.dumps({
        "ts": ts, "zone": "Z1", "drive": "D01", "seq": 888888,
        "speed_mps": 0.55, "current_a": 2.1, "temp_c": 41, "state": "running"}), qos=1)
    time.sleep(1); c.loop_stop(); c.disconnect()


async def main() -> None:
    pub_now()          # 先播一条"当前"数据，保证 Z1/D01 在实时字典里
    await asyncio.sleep(0.8)
    async with websockets.connect("ws://127.0.0.1:8001/ws/live") as ws:
        f1 = json.loads(await ws.recv())
        p1 = next(p for p in f1["points"] if p["zone"] == "Z1" and p["drive"] == "D01")
        old_ts = pub_old()
        await asyncio.sleep(1.2)
        f2 = json.loads(await ws.recv())
        p2 = next(p for p in f2["points"] if p["zone"] == "Z1" and p["drive"] == "D01")
    print(f"注入的旧消息 ts : {old_ts}")
    print(f"帧1 Z1/D01 speed: {p1['speed_mps']}  ts={p1['ts']}")
    print(f"帧2 同一设备     : {p2['speed_mps']}  ts={p2['ts']}")
    print("结论：" + ("旧值被丢弃 ✅" if p2["speed_mps"] != 9.99 and p2["ts"] == p1["ts"] else "旧值覆盖了当前状态 ❌"))

asyncio.run(main())
