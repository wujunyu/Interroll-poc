"""多设备集群模拟器：每台设备一条独立 MQTT 连接（不是一条连接发多个 topic）。

    python code/simulator/fleet.py --devices 360 --hz 10 --stagger 10 --jitter 3 --duration 40

与 main.py 的区别：
- main.py 模拟"一台网关聚合 36 台驱动"（1 条连接、36 个 topic）；
- fleet.py 模拟"N 台设备各自连 broker"（N 条连接），才能制造重连风暴。

抖动三处：
1. 启动相位 --stagger：第 i 台延迟 uniform(0, stagger) 秒再连；
2. 重连退避 --jitter：每台 min_delay = 1 + uniform(0, jitter)，避免同时重试；
3. 发布相位：每台按自己的相位对齐，避免同一毫秒发同一条。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import signal
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt

CST = timezone(timedelta(hours=8))
DRIVES = [f"D{i:02d}" for i in range(1, 37)]
stop = threading.Event()


def make_device(idx: int, args: argparse.Namespace, sent: list[int], lock: threading.Lock) -> None:
    zone = f"Z{idx // 36 + 1}"
    drive = DRIVES[idx % 36]
    topic = f"line/{zone}/drive/{drive}"
    time.sleep(random.uniform(0, args.stagger))   # 启动抖动

    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"dev-{idx}")
    min_delay = 1 + random.uniform(0, args.jitter)  # 重连抖动
    cli.reconnect_delay_set(min_delay=min_delay, max_delay=min_delay * 2)
    cli.max_inflight_messages_set(50)
    try:
        cli.connect(args.host, args.port, keepalive=30)
    except OSError:
        return
    cli.loop_start()

    period = 1.0 / args.hz
    next_tick = time.monotonic() + random.uniform(0, period)   # 发布相位
    seq = 0
    while not stop.is_set():
        seq += 1
        payload = json.dumps({
            "ts": datetime.now(CST).isoformat(timespec="milliseconds"),
            "zone": zone, "drive": drive, "seq": seq,
            "speed_mps": 0.5, "current_a": 2.0, "temp_c": 40, "state": "running",
        }, separators=(",", ":"))
        cli.publish(topic, payload, qos=1)
        with lock:
            sent[0] += 1
        next_tick += period
        time.sleep(max(0.0, next_tick - time.monotonic()))

    cli.loop_stop()
    cli.disconnect()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--devices", type=int, default=36)
    ap.add_argument("--hz", type=float, default=10.0)
    ap.add_argument("--duration", type=float, default=40.0)
    ap.add_argument("--host", default=os.environ.get("MQTT_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("MQTT_PORT", "1884")))
    ap.add_argument("--stagger", type=float, default=5.0)
    ap.add_argument("--jitter", type=float, default=3.0)
    args = ap.parse_args()

    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    sent = [0]
    lock = threading.Lock()
    threads = [threading.Thread(target=make_device, args=(i, args, sent, lock), daemon=True)
               for i in range(args.devices)]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    time.sleep(args.duration)
    stop.set()
    for t in threads:
        t.join(timeout=5)
    elapsed = time.monotonic() - t0
    print(f"✓ devices={args.devices} sent={sent[0]} elapsed={elapsed:.1f}s "
          f"rate={sent[0] / max(elapsed, 0.001):.0f}/s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
