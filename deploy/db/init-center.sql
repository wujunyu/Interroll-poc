-- 中心库：多站点汇聚。与边缘库的唯一结构差异是主键含 site_id。
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS telemetry (
    site_id     text             NOT NULL,   -- 站点标识，边缘机上报时带上
    ts          timestamptz      NOT NULL,
    zone_id     text             NOT NULL,
    drive_id    text             NOT NULL,
    speed_mps   double precision,
    current_a   double precision,
    temp_c      double precision,
    state       text,
    seq         bigint           NOT NULL,
    forwarded_at timestamptz     NOT NULL DEFAULT now(),
    PRIMARY KEY (site_id, zone_id, drive_id, ts, seq)
);

SELECT create_hypertable('telemetry', 'ts', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);
