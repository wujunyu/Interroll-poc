#!/usr/bin/env bash
# PG / TimescaleDB 性能体检（只读）。用法：
#   bash deploy/scripts/pg-perf.sh            # 打印到终端
#   bash deploy/scripts/pg-perf.sh > perf.txt # 存文件
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENGINE="${ENGINE:-docker}"
CT="${DB_CONTAINER:-interroll-poc-db-1}"
DB_USER="$(grep -E '^DB_USER=' "$ROOT/.env" | cut -d= -f2)"
DB_NAME="$(grep -E '^DB_NAME=' "$ROOT/.env" | cut -d= -f2)"
DB_PW="$(grep -E '^DB_PASSWORD=' "$ROOT/.env" | cut -d= -f2)"

out=$($ENGINE exec -i -e PGPASSWORD="$DB_PW" "$CT" psql -P pager=off -U "$DB_USER" -d "$DB_NAME" <<'SQL'
\echo '== 1. 版本与关键参数 =='
select version();
select name, setting, unit
from pg_settings
where name in ('shared_buffers','work_mem','maintenance_work_mem','max_connections',
               'autovacuum','autovacuum_naptime','checkpoint_timeout','max_wal_size',
               'synchronous_commit','effective_cache_size','random_page_cost')
order by name;

\echo '== 2. 会话与锁 =='
select state, count(*) from pg_stat_activity group by 1 order by 2 desc;
select pid, usename, state,
       round(extract(epoch from (now()-query_start))::numeric,1) as running_s,
       wait_event_type, wait_event,
       left(regexp_replace(query,'\s+',' ','g'),80) as query
from pg_stat_activity
where state <> 'idle' and pid <> pg_backend_pid()
order by running_s desc nulls last limit 10;
select blocked.pid as blocked_pid, blocking.pid as blocking_pid,
       left(regexp_replace(blocked.query,'\s+',' ','g'),60) as blocked_query,
       left(regexp_replace(blocking.query,'\s+',' ','g'),60) as blocking_query
from pg_stat_activity blocked
join lateral unnest(pg_blocking_pids(blocked.pid)) as bp(pid) on true
join pg_stat_activity blocking on blocking.pid = bp.pid
limit 10;

\echo '== 3. 慢查询 TOP10（pg_stat_statements）=='
select calls, round(total_exec_time::numeric,0) total_ms, round(mean_exec_time::numeric,2) mean_ms,
       round((100.0*total_exec_time/sum(total_exec_time) over ())::numeric,1) pct,
       left(regexp_replace(query,'\s+',' ','g'),90) query
from pg_stat_statements
where query not like '%pg_stat_statements%'
order by total_exec_time desc limit 10;

\echo '== 4. 表/索引体积 TOP10 =='
select relname, pg_size_pretty(pg_total_relation_size(relid)) total,
       pg_size_pretty(pg_relation_size(relid)) heap,
       pg_size_pretty(pg_total_relation_size(relid)-pg_relation_size(relid)) idx
from pg_stat_user_tables
order by pg_total_relation_size(relid) desc limit 10;

\echo '== 5. 死元组与 autovacuum =='
select relname, n_live_tup, n_dead_tup,
       round(100.0*n_dead_tup/greatest(n_live_tup+n_dead_tup,1),1) dead_pct,
       last_vacuum, last_autovacuum
from pg_stat_user_tables
where n_dead_tup > 1000
order by n_dead_tup desc limit 10;

\echo '== 6. 索引使用情况（未使用 / 全表扫描）=='
select relname, seq_scan, seq_tup_read, idx_scan,
       pg_size_pretty(pg_total_relation_size(relid)) size
from pg_stat_user_tables
order by seq_scan desc limit 10;

\echo '== 7. TimescaleDB：chunk 概况 =='
select count(*) chunks, count(*) filter (where is_compressed) compressed,
       pg_size_pretty(sum(total_bytes)) total_size
from timescaledb_information.chunks c
join chunks_detailed_size('telemetry') d on d.chunk_name = c.chunk_name
where c.hypertable_name = 'telemetry';
select c.chunk_name, c.range_start, c.range_end, pg_size_pretty(d.total_bytes) size, c.is_compressed
from timescaledb_information.chunks c
join chunks_detailed_size('telemetry') d on d.chunk_name = c.chunk_name
where c.hypertable_name = 'telemetry'
order by c.range_start desc limit 6;

\echo '== 8. 压缩效果 =='
select chunk_name, pg_size_pretty(before_compression_total_bytes) before,
       pg_size_pretty(after_compression_total_bytes) after,
       round(100.0*after_compression_total_bytes/nullif(before_compression_total_bytes,0),1) pct
from chunk_compression_stats('telemetry')
where before_compression_total_bytes is not null   -- 未压缩 chunk 没有这组统计
order by chunk_name desc limit 6;

\echo '== 9. 连续聚合与策略 =='
select view_name, materialized_only, compression_enabled from timescaledb_information.continuous_aggregates;
select job_id, application_name, schedule_interval, last_run_status, last_successful_finish
from timescaledb_information.job_stats js
join timescaledb_information.jobs j using (job_id)
order by job_id;

\echo '== 10. 写入速率（近 5 分钟快照）=='
select datname, xact_commit, tup_inserted, tup_updated,
       pg_size_pretty(pg_database_size(datname)) size
from pg_stat_database where datname = current_database();
SQL
)
printf '%s\n' "$out"
errs=$(printf '%s\n' "$out" | grep -c '^ERROR' || true)
if [ "${errs:-0}" -gt 0 ]; then
  echo "⚠ 有 $errs 条查询失败（见上方 ERROR）" >&2
  exit 1
fi
echo "✓ 体检完成，无 SQL 错误"
