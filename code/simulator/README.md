# simulator（只在 demo profile 里）

**职责**：造数。6 区 × 6 驱动 = 36 点，10Hz → 360 点/秒；可注入断网。

**不做**：不落库、不做聚合、不参与生产部署。

## 输出契约

Topic：`line/{zone}/drive/{drive}`（QoS 1，retain=false）

```json
{
  "ts": "2026-11-20T21:36:12.345+08:00",
  "zone": "Z3",
  "drive": "D02",
  "seq": 184223,
  "speed_mps": 0.78,
  "current_a": 2.5,
  "temp_c": 41.2,
  "state": "running"
}
```

`seq` 设备侧自增，补传去重靠它。

## 断网注入

`--offline 60`：期间只写本地 spool（`/tmp/spool.ndjson`），恢复后按 seq 补发。
