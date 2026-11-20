# ingest

**职责**：订阅 MQTT → 校验 → 批量写 TimescaleDB；断网时写本地 spool（P3 补），恢复后按 `(zone_id, drive_id, ts, seq)` 幂等补传。

**不做**：不做业务计算，不直接服务前端。

## 跑起来（本机复用宿主服务，不另起容器）

宿主已有 `mosquitto:1883`（账号 `poc`）与 `timescaledb:5437`（5432 被 immichPG 占了）。

```bash
DB_DSN='postgresql://poc:poc_dev_pw@127.0.0.1:5437/interroll_poc' \
MQTT_HOST=127.0.0.1 MQTT_PORT=1883 MQTT_USERNAME=poc MQTT_PASSWORD=poc_dev_pw \
HEALTH_PORT=8091 .conda-env/bin/python code/ingest/main.py
```

> 8091 而不是 8081：宿主 8081 是 Penpot。

## 关键参数（环境变量）

| 变量 | 默认 | 说明 |
|---|---|---|
| `MQTT_HOST` / `MQTT_PORT` | 127.0.0.1 / 1883 | |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | 空 | 宿主 broker 关了匿名，必须带 |
| `DB_DSN` | — | 必填 |
| `BATCH_ROWS` | 200 | 满 200 行刷一次 |
| `BATCH_SECONDS` | 1.0 | 或每 1 秒刷一次 |
| `HEALTH_PORT` | 8091 | `/healthz` |

## 实测（2026-11-20）

| 项 | 结果 |
|---|---|
| 10 秒造数 | 3600 条，17 个批次，全部落库 |
| 稳态延迟 | lag < 0.2s；停发 3 秒后 lag ≈ 4s（正常，因为没有新数据） |
| 1 分钟连续聚合 | 36 行（36 台驱动各 1 行），`samples=100` 与 10s×10Hz 对得上 |
| 幂等重放 | 同 `ts+seq` 发两轮共 100 条 → 表里仍是 **50 行** |

## 断网/断库两条兜底

| 故障 | 谁兜 | 怎么兜 |
|---|---|---|
| 设备 → Broker 断 | 模拟器（真实世界里是 edge 机） | 期间落 `*.ndjson`，恢复后**限速**回放 |
| ingest → 数据库断 | ingest | flush 失败整批落 spool，后台线程每 2s 重试补回 |

实测（2026-11-20）：

| 场景 | 结果 |
|---|---|
| 断网 8 秒（20 秒窗口） | 发 7200 条 / 落库 **7200 行** / 重复 0 / 每秒 360 行无空洞 |
| 掐断数据库连接（12 秒窗口） | 发 4320 条 / 落库 **4320 行**，spool 触发 6 次后自动补回 |
| 补传不限速 | **丢 66 条**（Broker 逐客户端队列上限 1000 被瞬间打爆）|
| 补传限速 400 条/秒 | 0 丢 |

> 最后两行是这次最值钱的一条：**补传必须限速**，否则「恢复瞬间的洪水」会把队列打爆，
> 反而比断网时丢得更多。

## 水位线

不单独存表：库里 `max(ts)` 就是水位，重启自动恢复，少一份可能写歪的状态。

## 表结构要点

```sql
PRIMARY KEY (zone_id, drive_id, ts, seq)
```

**设备身份是 `(zone_id, drive_id)`**——六个区里都有 `D01..D06`，只用 `drive_id` 会撞主键（第一版就是这么挂的）。
幂等键与主键一致，`ON CONFLICT ... DO NOTHING` 直接挡掉补传重放。
