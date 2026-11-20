# api

**职责**：REST 查历史（走 1m 聚合）+ WebSocket 推实时（10fps 节流）+ `/healthz` + `/diag.zip`。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/healthz` | 版本、依赖状态、补传水位 |
| GET | `/api/zones` | 六区状态与 KPI |
| GET | `/api/series?zone=Z3&drive=D02&window=60s` | 原始点（≤5min） |
| GET | `/api/series?window=1h` | 走 `telemetry_1m` 聚合 |
| WS | `/ws/live` | 增量帧，10fps |
| GET | `/diag.zip` | 诊断包（RB-03） |

WS 帧：

```json
{ "ts": "...", "zone": "Z3", "drive": "D02", "speed_mps": 0.78, "current_a": 2.5 }
```
