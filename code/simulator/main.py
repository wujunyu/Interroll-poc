"""产线模拟器：6 区 × 6 驱动，默认 10Hz，共 360 点/秒。

    python code/simulator/main.py --duration 10 --qos 1
    python code/simulator/main.py --duration 20 --offline-at 5 --offline-for 8
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone, timedelta

import paho.mqtt.client as mqtt

from telemetry import DRIVES, ZONES, make_sample, to_payload, topic_for

CST = timezone(timedelta(hours=8))


def main() -> int:
    ap = argparse.ArgumentParser(description="产线遥测模拟器")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1884)
    ap.add_argument("--hz", type=float, default=10.0)
    ap.add_argument("--duration", type=float, default=10.0, help="秒；0 表示一直跑")
    ap.add_argument("--qos", type=int, choices=(0, 1, 2), default=1)
    ap.add_argument("--prefix", default="line")
    ap.add_argument("--zones", default=",".join(ZONES))
    ap.add_argument("--offline-at", type=float, default=None, help="第几秒开始断网")
    ap.add_argument("--offline-for", type=float, default=0.0, help="断网持续秒数")
    args = ap.parse_args()

    zones = tuple(z for z in args.zones.split(",") if z)
    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sim-{int(time.time())}")
    cli.connect(args.host, args.port, keepalive=30)
    cli.loop_start()

    seq = 0
    sent = 0
    dropped = 0
    started = time.monotonic()
    period = 1.0 / args.hz
    next_tick = started
    offline_until = None

    print(f"· 目标 {args.host}:{args.port}  qos={args.qos}  {len(zones)}区 × {len(DRIVES)}驱动 @ {args.hz}Hz", flush=True)
    try:
        while True:
            now = time.monotonic()
            elapsed = now - started
            if args.duration and elapsed >= args.duration:
                break
            if args.offline_at is not None and elapsed >= args.offline_at and offline_until is None:
                offline_until = now + args.offline_for
                print(f"· [{elapsed:5.1f}s] 断网 {args.offline_for}s（消息只进本地缓冲）", flush=True)
            if offline_until and now >= offline_until:
                offline_until = None
                print(f"· [{elapsed:5.1f}s] 网络恢复，开始补传（本演示只计数，不重发）", flush=True)

            if offline_until is None:
                ts = datetime.now(CST).isoformat(timespec="milliseconds")
                for zone in zones:
                    for drive in DRIVES:
                        seq += 1
                        cli.publish(topic_for(zone, drive, args.prefix),
                                    to_payload(make_sample(zone, drive, seq, ts, elapsed)),
                                    qos=args.qos)
                        sent += 1
            else:
                dropped += len(zones) * len(DRIVES)

            next_tick += period
            time.sleep(max(0.0, next_tick - time.monotonic()))
    except KeyboardInterrupt:
        print("\n· 手动停止", flush=True)
    finally:
        cli.loop_stop()
        cli.disconnect()

    rate = sent / max(elapsed, 0.001)
    print(f"✓ 发送 {sent} 条 / 断网期间丢弃 {dropped} 条 / 平均 {rate:.0f} 条/秒", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
