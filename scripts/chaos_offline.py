"""P9-1 断流压测：随机时刻停掉 broker N 秒，恢复后校验「零丢、零重、追平时间」。

    python scripts/chaos_offline.py --duration 40 --outage 10

做的事：
1. 起模拟器（设备角色，失联时自己落 spool）；
2. 随机时刻 docker stop broker，N 秒后 start；
3. 等模拟器跑完，比对：应有条数 / 库内行数 / 唯一键 / 重复 / 恢复耗时。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8))
PY_BIN = ".conda-env/bin/python"
BROKER = "interroll-poc-mqtt-1"
DB = "interroll-poc-db-1"


def sh(cmd: list[str], **kw) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kw).stdout.strip()


def psql(sql: str) -> str:
    return sh(["docker", "exec", "-e", "PGPASSWORD=change-me-in-.env", DB,
               "psql", "-U", "poc", "-d", "poc", "-tAc", sql])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=40.0)
    ap.add_argument("--outage", type=float, default=10.0)
    ap.add_argument("--hz", type=float, default=10.0)
    ap.add_argument("--port", default=os.environ.get("MQTT_PORT", "1884"))
    ap.add_argument("--replay-rate", default="800", help="补传限速（条/秒）")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    if args.seed is None:
        args.seed = random.randint(0, 10**6)
    random.seed(args.seed)
    # 随机时刻：留出前后各 8 秒，避免踩到启动/收尾
    at = random.uniform(8, max(9, args.duration - args.outage - 8))
    print(f"[chaos] seed={args.seed}  时长={args.duration}s  断流={args.outage}s  在第 {at:.1f}s 动手")

    t0 = datetime.now(CST)
    sim = subprocess.Popen(
        [PY_BIN, "code/simulator/main.py", "--duration", str(args.duration), "--hz", str(args.hz),
         "--port", str(args.port), "--spool", "/tmp/chaos-spool.ndjson",
         "--replay-rate", args.replay_rate],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    time.sleep(at)
    print(f"[chaos] +{at:.1f}s  docker stop {BROKER}")
    sh(["docker", "stop", BROKER])
    out1 = time.monotonic()
    time.sleep(args.outage)
    print(f"[chaos] +{at + args.outage:.1f}s  docker start {BROKER}")
    sh(["docker", "start", BROKER])
    recovered_at = time.monotonic()
    expected = round(36 * args.hz * args.duration)
    settle: float | None = None
    while time.monotonic() - recovered_at < 40:
        time.sleep(0.5)
        cur = int(psql(f"select count(*) from telemetry where ts between '{(t0 - timedelta(seconds=2)).isoformat()}' and '{(datetime.now(CST) + timedelta(seconds=2)).isoformat()}'") or 0)
        if cur >= expected:
            settle = time.monotonic() - recovered_at
            break

    sim_out, _ = sim.communicate(timeout=args.duration + 90)
    t1 = datetime.now(CST)

    sent_line = next((l for l in sim_out.splitlines() if l.startswith("✓")), "")
    sent = int(sent_line.split("发送")[1].split("条")[0].strip()) if "发送" in sent_line else 0

    lo = (t0 - timedelta(seconds=2)).isoformat()
    hi = (t1 + timedelta(seconds=2)).isoformat()
    rows = int(psql(f"select count(*) from telemetry where ts between '{lo}' and '{hi}'") or 0)
    uniq = int(psql(f"select count(distinct (zone_id, drive_id, ts, seq)) from telemetry where ts between '{lo}' and '{hi}'") or 0)


    report = {
        "seed": args.seed,
        "duration_s": args.duration,
        "outage_s": args.outage,
        "outage_at_s": round(at, 1),
        "sent": sent,
        "rows": rows,
        "unique": uniq,
        "duplicates": rows - uniq,
        "lost": sent - uniq,
        "recover_s": round(settle, 1) if settle is not None else None,
    }
    print("[chaos] " + json.dumps(report, ensure_ascii=False))
    print("判定：" + ("✅ 零丢零重" if report["lost"] == 0 and report["duplicates"] == 0 else "❌ 有丢失或重复"))
    return 0 if report["lost"] == 0 and report["duplicates"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
