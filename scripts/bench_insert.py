"""对比三种插入方式：逐条提交 / executemany 批量 / COPY 进临时表再 ON CONFLICT。"""
import time
from datetime import datetime, timedelta, timezone

import psycopg

DSN = "postgresql://poc:change-me-in-.env@127.0.0.1:5433/poc"
N = 30000
BASE = datetime.now(timezone.utc)
ROWS = [(BASE + timedelta(milliseconds=i), f"Z{i%6+1}", f"D{i%36+1:02d}", 0.5, 2.0, 40.0, "run", i)
        for i in range(N)]


def reset(conn):
    with conn.cursor() as cur:
        cur.execute("drop table if exists bench_ins")
        cur.execute("""create table bench_ins (ts timestamptz, zone_id text, drive_id text,
                       speed_mps float8, current_a float8, temp_c float8, state text, seq bigint,
                       primary key (zone_id, drive_id, ts, seq))""")
    conn.commit()


def mode_single(conn):
    t0 = time.monotonic()
    for r in ROWS:
        with conn.cursor() as cur:
            cur.execute("insert into bench_ins values (%s,%s,%s,%s,%s,%s,%s,%s)", r)
        conn.commit()
    return time.monotonic() - t0


def mode_batch(conn, size=200):
    t0 = time.monotonic()
    for i in range(0, len(ROWS), size):
        with conn.cursor() as cur:
            cur.executemany("insert into bench_ins values (%s,%s,%s,%s,%s,%s,%s,%s)", ROWS[i:i + size])
        conn.commit()
    return time.monotonic() - t0


def mode_copy(conn):
    t0 = time.monotonic()
    with conn.cursor() as cur:
        cur.execute("create temp table stage (like bench_ins) on commit drop")
        with cur.copy("copy stage from stdin") as cp:
            for r in ROWS:
                cp.write_row(r)
        cur.execute("insert into bench_ins select * from stage on conflict do nothing")
    conn.commit()
    return time.monotonic() - t0


with psycopg.connect(DSN) as conn:
    for name, fn in (("逐条提交", mode_single), ("executemany(200)", mode_batch), ("COPY 临时表", mode_copy)):
        reset(conn)
        secs = fn(conn)
        print(f"{name:18s} {secs:6.2f}s  {N/secs:8.0f} 行/秒")
    reset(conn)
print("done")
