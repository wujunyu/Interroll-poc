# web

**职责**：Vite + React + ECharts 看板，四屏见 `docs/design/00-设计说明.md`。

## 约束

- **色值只能来自** `docs/design/tokens.json`（构建时生成 CSS 变量，禁止硬编码）；
- 实时窗口直绘，长窗口走聚合 + LTTB（ADR-0003）；
- WS 断线要有可见提示，不能静默白屏。

## 页面

| 路由 | 屏 | 设计稿 |
|---|---|---|
| `/` | 总览 | `01-dashboard.png` |
| `/zone/:id` | 单线详情 | `02-zone.png` |
| `/diagnostics` | 诊断包 | `03-diag.png` |
| `/m` | 移动端 | `04-mobile.png` |
