# ingest

**职责**：订阅 MQTT → 校验 → 批量写 TimescaleDB；断网时写本地 spool，恢复后按 `(drive, ts, seq)` 幂等补传。

**不做**：不做业务计算，不直接服务前端。

## 关键参数（走环境变量）

| 变量 | 默认 | 说明 |
|---|---|---|
| `MQTT_HOST` / `MQTT_PORT` | mqtt / 1883 | 容器内地址 |
| `DB_DSN` | — | postgresql://... |
| `BATCH_ROWS` | 200 | 满 200 行或 1s 刷一次 |
| `SPOOL_DIR` | `/var/spool/ingest` | 断网缓冲 |

## 可观测

- `GET /healthz`（内部 8081）：`{lag_seconds, spool_rows, last_ts}`；
- 日志每 10s 一行：`ingested=N lag=0.4s spool=0`。
