# RB-05 PG / TimescaleDB 性能排查

> 一条命令先跑体检：`make pg-perf`（只读，不锁表）。
> 本文是它的**逐段解释 + 可单独复制的 SQL**。

## 一、排查顺序（别乱猜）

```
1 写入是否卡住    → lag / spool / xact_commit
2 谁在等锁        → pg_blocking_pids
3 哪条 SQL 慢     → pg_stat_statements
4 数据量有没有失控 → chunk 数 / 表大小 / 死元组
5 时序特有        → chunk 裁剪 / 压缩 / 连续聚合滞后
6 配置是否离谱     → shared_buffers / work_mem / autovacuum
```

**先看 1 和 2**：大部分“系统慢”不是 SQL 慢，是锁或写入堆积。

## 二、会话与锁

```sql
-- 当前都在干什么
select pid, usename, state,
       round(extract(epoch from (now()-query_start))::numeric,1) as running_s,
       wait_event_type, wait_event,
       left(regexp_replace(query,'\s+',' ','g'),80) as query
from pg_stat_activity
where state <> 'idle' and pid <> pg_backend_pid()
order by running_s desc nulls last limit 10;

-- 阻塞链：谁堵了谁
select blocked.pid as blocked_pid, blocking.pid as blocking_pid,
       left(regexp_replace(blocked.query,'\s+',' ','g'),60) as blocked_query,
       left(regexp_replace(blocking.query,'\s+',' ','g'),60) as blocking_query
from pg_stat_activity blocked
join lateral unnest(pg_blocking_pids(blocked.pid)) as bp(pid) on true
join pg_stat_activity blocking on blocking.pid = bp.pid;

-- 空闲事务（连接池泄漏的典型症状）
select pid, state, round(extract(epoch from (now()-state_change))::numeric,1) idle_s,
       left(query,60) from pg_stat_activity
where state = 'idle in transaction' order by idle_s desc;
```

**处置**：`pg_cancel_backend(pid)` 取消查询；`pg_terminate_backend(pid)` 断连接（慎用）。
空闲事务要改连接池配置（`idle_in_transaction_session_timeout`）。

## 三、慢查询

```sql
-- TOP10：按总耗时（谁在拖垮系统）
select calls,
       round(total_exec_time::numeric,0) total_ms,
       round(mean_exec_time::numeric,2)  mean_ms,
       round((100.0*total_exec_time/sum(total_exec_time) over ())::numeric,1) pct,
       left(regexp_replace(query,'\s+',' ','g'),90) query
from pg_stat_statements
where query not like '%pg_stat_statements%'
order by total_exec_time desc limit 10;

-- 单条查询的真实计划（把 SQL 换成你要查的）
explain (analyze, buffers, costs off)
select count(*) from telemetry where ts > now() - interval '1 day';
```

**看什么**：

| 指标 | 含义 |
|---|---|
| `pct` 高 | 这条 SQL 占了大头，优先优化 |
| `mean_ms` 高但 `calls` 少 | 偶发慢查询，可能缺索引或缓存未命中 |
| `calls` 极高 | 调用次数问题（N+1），不是 SQL 问题 |

## 四、表与索引

```sql
-- 体积 TOP10（heap / index 分开看）
select relname,
       pg_size_pretty(pg_total_relation_size(relid)) total,
       pg_size_pretty(pg_relation_size(relid)) heap,
       pg_size_pretty(pg_total_relation_size(relid)-pg_relation_size(relid)) idx
from pg_stat_user_tables
order by pg_total_relation_size(relid) desc limit 10;

-- 死元组（delete 没 vacuum 的后果）
select relname, n_live_tup, n_dead_tup,
       round(100.0*n_dead_tup/greatest(n_live_tup+n_dead_tup,1),1) dead_pct,
       last_autovacuum
from pg_stat_user_tables
where n_dead_tup > 1000
order by n_dead_tup desc limit 10;

-- 顺序扫描最多的表（可能缺索引）
select relname, seq_scan, seq_tup_read, idx_scan,
       pg_size_pretty(pg_total_relation_size(relid)) size
from pg_stat_user_tables order by seq_scan desc limit 10;
```

**经验**：`dead_pct > 20%` 或 `seq_scan` 远大于 `idx_scan` 且表不大 → 该 vacuum / 补索引。
但 **hypertable 不要用 DELETE 清历史**，用 `drop_chunks`（见下）。

## 五、TimescaleDB 专属

```sql
-- chunk 概况：数量、压缩数、总大小
select count(*) chunks, count(*) filter (where is_compressed) compressed
from timescaledb_information.chunks where hypertable_name = 'telemetry';

-- 最近 6 个 chunk 的时间范围与大小（看 chunk 是否过大/过小）
select c.chunk_name, c.range_start, c.range_end,
       pg_size_pretty(d.total_bytes) size, c.is_compressed
from timescaledb_information.chunks c
join chunks_detailed_size('telemetry') d on d.chunk_name = c.chunk_name
where c.hypertable_name = 'telemetry'
order by c.range_start desc limit 6;

-- 压缩效果（只列已压缩的）
select chunk_name,
       pg_size_pretty(before_compression_total_bytes) before,
       pg_size_pretty(after_compression_total_bytes)  after,
       round(100.0*after_compression_total_bytes/nullif(before_compression_total_bytes,0),1) pct
from chunk_compression_stats('telemetry')
where before_compression_total_bytes is not null
order by chunk_name desc limit 6;

-- 策略是否在跑：刷新 / 保留 / 压缩
select j.job_id, j.application_name, j.schedule_interval,
       s.last_run_status, s.last_successful_finish
from timescaledb_information.jobs j
join timescaledb_information.job_stats s using (job_id)
order by j.job_id;
```

### 验证 chunk 裁剪是否生效

```sql
explain (costs off)
select count(*) from telemetry where ts > now() - interval '5 minutes';
```

期望看到 `ChunkAppend` + 只列出一个 chunk。若出现全表扫描，检查：

- 时间条件是不是**常量/可折叠**（`now()` 可以，`$1` 参数在某些驱动下会关掉裁剪）；
- 有没有对 `ts` 做函数运算（`date_trunc('hour', ts) = ...` 会失去裁剪）。

### 三个高频坑

| 现象 | 原因 | 处置 |
|---|---|---|
| 压缩卡住几分钟 | `compress_chunk` 要强锁，和全表 `max(ts)` 互锁 | 只压冷 chunk；水位查询带时间谓词 |
| 连续聚合查询很慢 | 物化窗口没刷新到最新（`end_offset`） | 看 `continuous_aggregates` 与 job 状态 |
| 删历史删不动 | 用 `DELETE`，产生大量死元组 | 改 `drop_chunks` / 保留策略 |

## 六、配置体检

```sql
select name, setting, unit from pg_settings
where name in ('shared_buffers','work_mem','maintenance_work_mem','max_connections',
               'autovacuum','autovacuum_naptime','checkpoint_timeout','max_wal_size',
               'synchronous_commit','effective_cache_size','random_page_cost')
order by name;
```

参考值（本机 62GB 内存的 PoC）：

| 参数 | 当前 | 说明 |
|---|---|---|
| `shared_buffers` | 15.5 GB | 通常设物理内存 25% |
| `work_mem` | 31 MB | 排序/哈希每个操作可用，不是全局 |
| `maintenance_work_mem` | 2 GB | vacuum/建索引用 |
| `max_wal_size` | 1 GB | 太小会导致频繁 checkpoint |
| `random_page_cost` | 1.1 | SSD 上正常 |

### 一个类型坑（脚本里踩过）

`pg_stat_statements` 的 `total_exec_time` 是 **double precision**，而 PostgreSQL **没有** `round(double precision, int)`：

```
ERROR: function round(double precision, integer) does not exist
```

必须显式转 numeric：

```sql
round((100.0*total_exec_time/sum(total_exec_time) over ())::numeric, 1)
```

`bigint` 参与 `100.0 * x` 会先变 numeric，所以 `round(100.0*n_dead_tup/...)` 没问题——
**只有 double precision 需要手动转**。

## 七、一键脚本

```bash
make pg-perf                 # 终端输出
bash deploy/scripts/pg-perf.sh > perf.txt   # 存档
```

脚本是**只读**的（全是 `select` / `explain`），可以在生产跑；
不进诊断包（`make diag` 已有精简版 db-stats），因为输出较长。

## 八、症状 → 查询对照

| 症状 | 先看 | 常见原因 |
|---|---|---|
| 写入 lag 上涨 | `pg_stat_activity` 的 active/锁 | 锁等待、autovacuum、磁盘满 |
| 查询突然变慢 | `pg_stat_statements` TOP | 计划变化、缺索引、缓存失效 |
| 磁盘只增不减 | 表大小 + 死元组 | 用 DELETE 清历史，没 vacuum |
| chunk 数量暴涨 | chunk 概况 | `chunk_time_interval` 设太小 |
| 压缩后查询更慢 | 压缩统计 + `explain` | 只查单列却解压整行？看 segmentby |
| 连续聚合不更新 | job 状态 | 策略被停、`end_offset` 太大 |
