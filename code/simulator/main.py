"""产线模拟器：6 区 × 6 驱动，默认 10Hz，共 360 点/秒。

    python code/simulator/main.py --duration 10 --qos 1
    python code/simulator/main.py --duration 20 --offline-at 5 --offline-for 8
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone, timedelta

import paho.mqtt.client as mqtt

from telemetry import DRIVES, ZONES, make_sample, to_payload, topic_for

CST = timezone(timedelta(hours=8))


def main() -> int:
    ap = argparse.ArgumentParser(description="产线遥测模拟器")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("MQTT_PORT", "1883")))
    ap.add_argument("--user", default=os.environ.get("MQTT_USERNAME", ""))
    ap.add_argument("--password", default=os.environ.get("MQTT_PASSWORD", ""))
    ap.add_argument("--hz", type=float, default=10.0)
    ap.add_argument("--duration", type=float, default=10.0, help="秒；0 表示一直跑")
    ap.add_argument("--qos", type=int, choices=(0, 1, 2), default=1)
    ap.add_argument("--prefix", default="line")
    ap.add_argument("--zones", default=",".join(ZONES))
    ap.add_argument("--offline-at", type=float, default=None, help="第几秒开始断网")
    ap.add_argument("--offline-for", type=float, default=0.0, help="断网持续秒数")
    ap.add_argument("--spool", default="/tmp/interroll-sim-spool.ndjson",
                    help="断网期间落盘的文件，恢复后按原顺序补发")
    ap.add_argument("--replay-rate", type=float, default=400.0,
                    help="补传速率（条/秒）。不限速会把 Broker 的客户端队列打爆丢消息")
    args = ap.parse_args()

    zones = tuple(z for z in args.zones.split(",") if z)
    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sim-{int(time.time())}")
    if args.user:
        cli.username_pw_set(args.user, args.password)
    cli.connect(args.host, args.port, keepalive=30)
    cli.loop_start()

    seq = 0
    sent = 0
    buffered = 0
    replayed = 0
    started = time.monotonic()
    period = 1.0 / args.hz
    next_tick = started
    offline_until = None
    offline_done = False
    replay_thread: threading.Thread | None = None

    print(f"· 目标 {args.host}:{args.port}  qos={args.qos}  {len(zones)}区 × {len(DRIVES)}驱动 @ {args.hz}Hz", flush=True)
    try:
        while True:
            now = time.monotonic()
            elapsed = now - started
            if args.duration and elapsed >= args.duration:
                break
            if (args.offline_at is not None and not offline_done
                    and elapsed >= args.offline_at and offline_until is None):
                offline_until = now + args.offline_for
                offline_done = True
                print(f"· [{elapsed:5.1f}s] 断网 {args.offline_for}s（消息只进本地缓冲）", flush=True)
            if offline_until and now >= offline_until:
                offline_until = None
                print(f"· [{elapsed:5.1f}s] 网络恢复，开始补传 spool 里的 {buffered} 条", flush=True)
                if os.path.exists(args.spool):
                    def replay(path: str) -> None:
                        # 后台限速补传：真实设备不会把 8 秒欠账一次性喷完，
                        # 一次性喷会打爆 Broker 的客户端队列（默认 1000 条）造成丢消息。
                        nonlocal sent, replayed
                        chunk = 0
                        t0 = time.monotonic()
                        with open(path, encoding="utf-8") as fh:
                            for line in fh:
                                rec = json.loads(line)
                                cli.publish(rec["topic"], json.dumps(rec["payload"], separators=(",", ":")), qos=args.qos)
                                sent += 1
                                replayed += 1
                                chunk += 1
                                if chunk % 50 == 0:
                                    ahead = chunk / args.replay_rate - (time.monotonic() - t0)
                                    if ahead > 0:
                                        time.sleep(ahead)
                        os.remove(path)
                        print(f"· 后台补传完成 {chunk} 条", flush=True)

                    replay_thread = threading.Thread(target=replay, args=(args.spool,), daemon=True)
                    replay_thread.start()
                print(f"· [{elapsed:5.1f}s] 补传完成 {replayed} 条", flush=True)

            ts = datetime.now(CST).isoformat(timespec="milliseconds")
            if offline_until is None:
                for zone in zones:
                    for drive in DRIVES:
                        seq += 1
                        payload = to_payload(make_sample(zone, drive, seq, ts, elapsed))
                        cli.publish(topic_for(zone, drive, args.prefix), payload, qos=args.qos)
                        sent += 1
            else:
                # 断网：不丢，落本地 spool（真实设备上是 edge 机的本地库）
                with open(args.spool, "a", encoding="utf-8") as fh:
                    for zone in zones:
                        for drive in DRIVES:
                            seq += 1
                            rec = {"topic": topic_for(zone, drive, args.prefix),
                                   "payload": json.loads(to_payload(make_sample(zone, drive, seq, ts, elapsed)))}
                            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                            buffered += 1

            next_tick += period
            time.sleep(max(0.0, next_tick - time.monotonic()))
    except KeyboardInterrupt:
        print("\n· 手动停止", flush=True)
    finally:
        if replay_thread is not None and replay_thread.is_alive():
            print("· 等待后台补传收尾…", flush=True)
            replay_thread.join(timeout=60)
        cli.loop_stop()
        cli.disconnect()

    rate = sent / max(elapsed, 0.001)
    print(f"✓ 发送 {sent} 条（其中断网缓冲补传 {replayed} 条）/ 平均 {rate:.0f} 条/秒", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
