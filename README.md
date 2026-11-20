# Interroll PoC · 产线遥测最小闭环

模拟 6 区 × 6 台驱动（360 点/秒）→ MQTT → TimescaleDB → WebSocket → 看板。
断网本地续存、恢复幂等补传；`make rollback` 一键回上一版；`make diag` 导出诊断包。

> 这是面试现场用的 **PoC**，不是产品。目标只有三条：一条命令起得来、断网不丢数、每处取舍讲得清。

## 30 秒判断

| 你想看 | 就这条 |
|---|---|
| 起不起得来 | `make up-infra && make config` |
| 断网会不会丢 | `make demo-offline`（B 批） |
| 为什么聚合而不是逐点回传 | `docs/adr/ADR-0002-聚合与水位线.md` |
| 出问题谁救 | `docs/runbook/RB-03-排障.md`、`make diag` |

## 端口（避开宿主机已占用的 1883 / 5432 / 8000）

| 服务 | POC 端口 | 宿主已有 |
|---|---|---|
| MQTT | 1884 | 1883 mosquitto |
| TimescaleDB | 5433 | 5432 timescaledb |
| API | 8001 | 8000 |
| Web | 5174 | 5173 |

## 命令

```bash
make            # 列出所有目标
make config     # 校验 compose 与 .env（不启动）
make up-infra   # 只起 mqtt + db（B 批前唯一能起的）
make up         # 全栈（B 批完成后可用）
make down       # 停栈，保留数据卷
make verify     # 骨架期：config + 语法检查；B 批后加 smoke
```

## 目录

```
code/       按交付单元分（一个容器一个目录）：simulator / ingest / api / web
deploy/     Docker 编排与运维脚本：compose / db / scripts
docs/       文档：架构、ADR、runbook、kb（分层知识库）、design（看板设计）、WBS
tests/      unit / e2e
scripts/    开发辅助
```

## 当前状态

**骨架（A 批）**：目录、契约、编排、文档模板已就位；业务代码为空壳，见每个目录的 `README.md`。
下一步见 `docs/WBS/`。
