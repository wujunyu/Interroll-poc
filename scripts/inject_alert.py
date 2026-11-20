"""往一个驱动注入过流：前 3 秒抖动、中间 8 秒持续、最后 3 秒恢复。

    python scripts/inject_alert.py --host 127.0.0.1 --port 1883 --user poc --pass poc_dev_pw
"""
import argparse, json, time
from datetime import datetime, timezone, timedelta

import paho.mqtt.client as mqtt

CST = timezone(timedelta(hours=8))
ap = argparse.ArgumentParser()
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, default=1883)
ap.add_argument("--user", default="poc")
ap.add_argument("--pass", dest="password", default="poc_dev_pw")
ap.add_argument("--zone", default="Z1")
ap.add_argument("--drive", default="D01")
ap.add_argument("--sustain", type=float, default=8.0, help="持续过流秒数")
ap.add_argument("--fill-zone", action="store_true", default=True,
                help="同区其余驱动补正常值，避免只看得到 1 台（默认开）")
args = ap.parse_args()

cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="inject-alert")
if args.user:
    cli.username_pw_set(args.user, args.password)
cli.connect(args.host, args.port)
cli.loop_start()

seq = 900000
def send(seconds: float, amps: float) -> None:
    global seq
    t0 = time.monotonic()
    others = [f"D{i:02d}" for i in range(1, 7) if f"D{i:02d}" != args.drive]
    while time.monotonic() - t0 < seconds:
        ts = datetime.now(CST).isoformat(timespec="milliseconds")
        seq += 1
        cli.publish(f"line/{args.zone}/drive/{args.drive}", json.dumps({
            "ts": ts, "zone": args.zone, "drive": args.drive, "seq": seq,
            "speed_mps": 0.6, "current_a": amps,
            "temp_c": 41.0, "state": "running",
        }, separators=(",", ":")), qos=1)
        if args.fill_zone:
            for d in others:
                seq += 1
                cli.publish(f"line/{args.zone}/drive/{d}", json.dumps({
                    "ts": ts, "zone": args.zone, "drive": d, "seq": seq,
                    "speed_mps": 0.58, "current_a": 2.4,
                    "temp_c": 40.5, "state": "running",
                }, separators=(",", ":")), qos=1)
        time.sleep(0.1)

print("phase1 抖动 3s @4.8A", flush=True); send(3, 4.8)
print(f"phase2 持续 {args.sustain}s @4.8A", flush=True); send(args.sustain, 4.8)
print("phase3 恢复 3s @2.2A", flush=True); send(3, 2.2)
time.sleep(1); cli.loop_stop(); cli.disconnect()
print("done", flush=True)
