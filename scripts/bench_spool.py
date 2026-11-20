"""压一下 spool 补传的内存：生成 N 行 ndjson，走真实 replay_spool，打印峰值 RSS。

    python scripts/bench_spool.py 200000
"""
from __future__ import annotations

import importlib.util
import json
import os
import resource
import sys
import tempfile
import time
from pathlib import Path

N = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
os.environ.setdefault("DB_DSN", "postgresql://poc:poc_dev_pw@127.0.0.1:5437/interroll_poc")

spec = importlib.util.spec_from_file_location("ingest_main", Path("code/ingest/main.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)  # type: ignore[union-attr]

spool_dir = tempfile.mkdtemp(prefix="spool-bench-")
mod.SPOOL_DIR = spool_dir
path = os.path.join(spool_dir, "bench.ndjson")
ts = "2026-11-20T23:00:00.000+08:00"
t0 = time.monotonic()
with open(path, "w", encoding="utf-8") as fh:
    for i in range(N):
        fh.write(json.dumps([ts, "ZB", f"DB{i % 6:02d}", 0.5, 2.0, 40.0, "running", i]) + "\n")
size_mb = os.path.getsize(path) / 1024 / 1024
t1 = time.monotonic()

mod.replay_spool()
t2 = time.monotonic()
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

print(f"行数      : {N:,}")
print(f"文件大小  : {size_mb:.1f} MB")
print(f"写入耗时  : {t1 - t0:.2f}s")
print(f"补传耗时  : {t2 - t1:.2f}s")
print(f"峰值 RSS  : {peak:.0f} MB")
