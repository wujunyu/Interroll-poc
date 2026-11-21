"""P9-2 多机重连风暴实验：N 台设备各自一条连接，随机相位接入，站点级断流后集中重连。

    python scripts/chaos_multi.py --devices 360 --duration 45 --outage 10 --stagger 10 --jitter 3

输出四个关键数：
- peak_reconnect_rate：恢复后每秒新增连接数的峰值（风暴强度）
- recover_s：从 broker 恢复到连接数回到基线 95% 的时间
- min_connected：断流期间最低连接数（应为 0）
- survived：broker 是否撑住（容器仍 running）

注意：fleet.py 不做本地缓存，断流期间的消息必然丢——本实验只测"连接恢复能力"，
数据不丢由 P9-1（设备侧 spool）覆盖。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import threading
import time

import paho.mqtt.client as mqtt

BROKER = "interroll-poc-mqtt-1"
PY_BIN = ".conda-env/bin/python"


def sh(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout.strip()


class Sampler:
    """订阅 $SYS，记录 (monotonic, connected)。"""

    def __init__(self, port: int) -> None:
        self.samples: list[tuple[float, int]] = []
        self._lock = threading.Lock()
        self.cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sys-sampler")
        self.cli.reconnect_delay_set(min_delay=1, max_delay=2)
        self.cli.on_message = self._on_message
        self.cli.on_connect = lambda c, u, f, rc, props=None: c.subscribe(
            "$SYS/broker/clients/connected", qos=0)
        self.cli.connect("127.0.0.1", port, keepalive=15)
        self.cli.loop_start()
        self._stop = threading.Event()

    def _on_message(self, c, u, msg) -> None:
        try:
            v = int(msg.payload)
        except ValueError:
            return
        with self._lock:
            self.samples.append((time.monotonic(), v))

    def stop(self) -> None:
        self._stop.set()
        self.cli.loop_stop()
        self.cli.disconnect()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--devices", type=int, default=360)
    ap.add_argument("--duration", type=float, default=45.0)
    ap.add_argument("--outage", type=float, default=10.0)
    ap.add_argument("--stagger", type=float, default=10.0)
    ap.add_argument("--jitter", type=float, default=3.0)
    ap.add_argument("--hz", type=float, default=10.0)
    ap.add_argument("--port", type=int, default=int(os.environ.get("MQTT_PORT", "1884")))
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    if args.seed is None:
        args.seed = random.randint(0, 10**6)
    random.seed(args.seed)

    sampler = Sampler(args.port)
    t0 = time.monotonic()
    fleet = subprocess.Popen(
        [PY_BIN, "code/simulator/fleet.py", "--devices", str(args.devices),
         "--duration", str(args.duration), "--stagger", str(args.stagger),
         "--jitter", str(args.jitter), "--hz", str(args.hz), "--port", str(args.port)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    time.sleep(args.stagger + 8)          # 等设备陆续接入
    before = sampler.samples[-1][1] if sampler.samples else 0
    at = time.monotonic() - t0
    print(f"[multi] devices={args.devices} 基线连接={before}  第 {at:.0f}s 停 broker", flush=True)
    sh(["docker", "stop", BROKER])
    time.sleep(args.outage)
    sh(["docker", "start", BROKER])
    recovered_at = time.monotonic()

    fleet_out, _ = fleet.communicate(timeout=args.duration + 120)
    time.sleep(3)
    sampler.stop()

    samples = sampler.samples
    after = [(t - recovered_at, v) for t, v in samples if t >= recovered_at]
    baseline = max((v for t, v in samples if t < recovered_at), default=before)
    min_after = min((v for _, v in after), default=0)
    peak_rate = 0.0
    for (t1, v1), (t2, v2) in zip(after, after[1:]):
        dt = max(t2 - t1, 0.001)
        peak_rate = max(peak_rate, max(0, v2 - v1) / dt)
    recover_s = next((round(t, 1) for t, v in after if v >= baseline * 0.95), None)

    sent_line = next((l for l in fleet_out.splitlines() if l.startswith("✓")), "")
    report = {
        "seed": args.seed,
        "devices": args.devices,
        "stagger_s": args.stagger,
        "jitter_s": args.jitter,
        "baseline_connected": baseline,
        "min_connected_after_restart": min_after,
        "peak_reconnect_per_s": round(peak_rate, 1),
        "recover_s": recover_s,
        "broker_running": "interroll-poc-mqtt-1" in sh(["docker", "ps", "--filter", f"name={BROKER}", "--format", "{{.Names}}"]),
        "fleet": sent_line,
    }
    print("[multi] " + json.dumps(report, ensure_ascii=False))
    ok = report["broker_running"] and (recover_s is not None)
    print("判定：" + ("✅ broker 撑住且连接恢复" if ok else "❌ 需要看日志"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
