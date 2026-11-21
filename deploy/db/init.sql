-- TimescaleDB 初始化：超表 / 连续聚合 / 保留策略 / 压缩
-- 只跑一次（docker-entrypoint-initdb.d），改这里要 `make clean` 重来。

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 原始点：每秒 360 行（36 驱动 × 10Hz），这是 PoC 的量级
CREATE TABLE IF NOT EXISTS telemetry (
    ts          timestamptz      NOT NULL,
    zone_id     text             NOT NULL,
    drive_id    text             NOT NULL,
    speed_mps   double precision,
    current_a   double precision,
    temp_c      double precision,
    state       text,
    seq         bigint           NOT NULL,   -- 设备侧自增，补传去重用
    -- 设备身份是 (zone_id, drive_id)：六个区里都有 D01..D06，只用 drive_id 会撞
    PRIMARY KEY (zone_id, drive_id, ts, seq)
);

SELECT create_hypertable('telemetry', 'ts', chunk_time_interval => INTERVAL '1 hour', if_not_exists => TRUE);

-- 幂等键与主键一致：同一批补传重放不会写两遍
-- （保留这条显式索引，是为了让「幂等键是哪几列」在文档里可见，不被主键细节掩盖）

-- 1 分钟聚合：看板长窗口只查这里
CREATE MATERIALIZED VIEW IF NOT EXISTS telemetry_1m
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 minute', ts) AS bucket,
       zone_id,
       drive_id,
       avg(speed_mps)   AS speed_avg,
       max(current_a)   AS current_max,
       avg(temp_c)      AS temp_avg,
       count(*)         AS samples
FROM telemetry
GROUP BY bucket, zone_id, drive_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy('telemetry_1m',
       start_offset => INTERVAL '3 days',
       end_offset   => INTERVAL '1 minute',
       schedule_interval => INTERVAL '1 minute',
       if_not_exists => TRUE);

-- 慢查询统计（compose 已把 pg_stat_statements 加进 shared_preload_libraries）
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- 事件表：只记「发生了什么」，不记日志流水（审计 / 诊断包时间线）
CREATE TABLE IF NOT EXISTS events (
    ts       timestamptz NOT NULL DEFAULT now(),
    kind     text        NOT NULL,          -- ingest_start / db_recovered / spool_replayed / ingest_stop
    severity text        NOT NULL DEFAULT 'info',
    detail   jsonb       NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_events_ts ON events (ts DESC);

-- 保留：原始 7 天、聚合 90 天
SELECT add_retention_policy('telemetry',    INTERVAL '7 days',  if_not_exists => TRUE);
SELECT add_retention_policy('telemetry_1m', INTERVAL '90 days', if_not_exists => TRUE);

-- 压缩：7 天前的块
-- segmentby 必须包含 zone_id：D01..D06 在 6 个区里都存在，只按 drive_id 分段会把 6 个区混在一段里
-- orderby 用 ts DESC：时间近的先出，范围查询少解压
ALTER TABLE telemetry SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'zone_id, drive_id',
    timescaledb.compress_orderby   = 'ts DESC'
);
SELECT add_compression_policy('telemetry', INTERVAL '7 days', if_not_exists => TRUE);
