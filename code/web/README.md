# web

**职责**：Vite + React + ECharts 看板。已实现两屏：总览、单线详情。

## 跑起来

```bash
# 后端（另开两个终端）
.conda-env/bin/python code/ingest/main.py   # 需要 .env 里的 DB_DSN / MQTT_*
.conda-env/bin/python code/api/main.py      # API 在 8090

# 前端
cd code/web && npm install && npm run dev    # 5174
node scripts/gen-tokens.mjs                  # tokens.json -> src/styles/tokens.css
```

`vite.config.ts` 把 `/api`、`/healthz`、`/ws` 代理到 `127.0.0.1:8090`，所以前端只用相对路径。

## 两条硬约束

1. **色值只能来自 `tokens.css`**（由 `docs/design/tokens.json` 生成），组件里不许写 `#RRGGBB`；
2. **实时帧只保留最新一帧**，前端再按 90ms 节流一次；历史走 `/api/series`，不要拿实时帧攒长曲线。

## 屏幕

| 路由 | 屏 | 设计稿 |
|---|---|---|
| `/` | 总览：KPI + 六区 + 告警占位 + 实时速度 | `01-dashboard.png` |
| `/zone/:zone/:drive` | 单线详情：10Hz 曲线 + 缩放 + 点位表 + 水位 | `02-zone.png` |
| `/diagnostics` | 诊断包（P5-3，未做） | `03-diag.png` |
| `/m` | 移动端（P5-3，未做） | `04-mobile.png` |

## 缩放（对应 FR-10）

ECharts `dataZoom` 三件套一起上：

- `inside`：滚轮缩放 + 拖拽平移（拖选缩放由 toolbox 的 `dataZoom` 提供）；
- `slider`：底部概览条，拖动即平移；
- `toolbox.restore` + **canvas 双击**：复位到全量（ECharts 没有内置双击，绑在 zrender 上）。

## 实测截图

`docs/design/exports/web/overview.png`、`zone.png`（1440×900，真数据）。

## 已知没做

- 告警规则与告警流（当前是占位面板）；
- 诊断页与移动端（P5-3，P1 优先级）；
- 断网角标与「补传中」状态条（等 P3 的水位接到前端）。
