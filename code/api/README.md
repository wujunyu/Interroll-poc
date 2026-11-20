# api

**职责**：REST 查历史 + WebSocket 推实时（10fps 节流）+ `/healthz`。

## 分工（ADR-0003）

| 路径 | 数据源 | 为什么 |
|---|---|---|
| `/api/series?window≤5m` | `telemetry` 原始点 | 短窗口要精度，600~3000 点直绘 |
| `/api/series?window>5m` | `telemetry_1m` 连续聚合 | 长窗口不需要秒级细节，聚合把点数压到几十 |
| `/ws/live` | API 自己订 MQTT | 每帧回查数据库会把库压垮；实时帧走内存 |
| `/healthz` | 库 `max(ts)` + MQTT 连接状态 | 重启后水位自动恢复，不另存状态 |

点数超过 1,000 时上 **LTTB**（`lttb()`，36,000 → 1,000，首尾与尖峰都保留）。
LTTB 只影响「怎么画」，任何统计口径都不许拿抽样点算。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/healthz` | 版本、MQTT 连接/帧数、库水位 |
| GET | `/api/zones` | 六区：驱动数、在线数、平均速度、最后时间 |
| GET | `/api/series?zone=Z1&drive=D01&window=60s` | `window ∈ 60s/5m/1h/6h/24h` |
| WS | `/ws/live` | 每 100ms 一帧，36 个点 + 累计帧数 |

WS 帧：

```json
{"ts":"2026-11-20T22:31:48.015+08:00","frames":4320,
 "points":[{"zone":"Z1","drive":"D01","speed_mps":0.74,"current_a":2.84,"temp_c":42.4,"state":"running"}]}
```

## 跑起来

```bash
DB_DSN='postgresql://poc:poc_dev_pw@127.0.0.1:5437/interroll_poc' \
MQTT_HOST=127.0.0.1 MQTT_PORT=1883 MQTT_USERNAME=poc MQTT_PASSWORD=poc_dev_pw \
API_PORT=8090 .conda-env/bin/python code/api/main.py
```

> 8080/8088 在本机已被占，PoC 用 8090。

## 实测（2026-11-20）

| 项 | 结果 |
|---|---|
| `/healthz` | `mqtt.connected=true`、`frames=4320`、库水位正确 |
| `/api/zones` | 6 区 × 6 驱动，online=6 |
| `/api/series?window=60s` | `source=raw`，120 点（12 秒 × 10Hz）|
| `/api/series?window=1h` | `source=1m-agg`，2 点（两个分钟桶）|
| `/ws/live` | 3 秒 30 帧 → **9.9 fps**，每帧 36 点 |
| `lttb()` | 36,000 → 1,000 点，首尾保持、尖峰保留 |
