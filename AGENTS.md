# AGENTS.md · Interroll PoC

## 这是什么

48 小时做出来的「产线遥测最小闭环」演示，用于面试现场。
**目标不是生产完备**，是「一条命令起、断网能续、能讲清每处取舍」。超出这个目标的功能一律不加。

## 硬边界

- 代码只写 `code/` 下；`deploy/` 只放编排与脚本；`docs/` 只放文档。
- 只用 `make` 入口。禁止 `docker run`、禁止手工改库（要改就改 `deploy/db/init.sql`）。
- 不引 GPL/AGPL 依赖；不提交 `.env`、不提交数据卷；日志不落明文密码。
- **不写 K8s 清单**：演示规模不需要，写了是减分。
- 改端口/表结构前，先改 `.env.example` 与 `deploy/db/init.sql`，再同步 README 的端口表。

## 目录约定

| 目录 | 放什么 | 不放什么 |
|---|---|---|
| `code/<svc>/` | 一个容器一个目录，`Containerfile` 就地在内 | 共享库（复制小段代码优于抽象） |
| `deploy/compose/` | `compose.yaml` + `compose.dev.yaml` / `compose.edge.yaml` | 业务代码、密钥 |
| `deploy/scripts/` | backup / restore / rollback / diag，全部幂等 | 交互式脚本 |
| `docs/adr/` | 一条决策一个文件，带「代价」一节 | 教程 |
| `docs/kb/` | 分层知识库（见 `docs/kb/_契约/SCHEMA.md`） | 大段复制的原文 |

## 知识库纪律

- 事实与取舍先查 `docs/kb/2-图/`，找不到再联网；查不到就写「待确认」，**不许填成事实**。
- AI 只能写 `docs/kb/1-卡/` 草案与 `0-源/` 的引用摘要；`2-图` / `3-稿` 由人确认后合入。
- 冲突不覆盖，新建 `C-*-CONFLICT`。

## 代码风格

- Python 3.12+：`ruff` + 全量类型标注；异步统一 `asyncio`，不混线程池。
- TypeScript：`eslint` + 严格模式；组件不写内联样式，色值只能来自 `docs/design/tokens.json`。
- 提交信息：`type(scope): 中文描述`，type ∈ feat/fix/docs/chore/test/deploy。

## 验收（改完必须自证）

```bash
make verify    # 骨架期：compose 校验 + 脚本语法；B 批后追加单元测试与 smoke
```

绿了才算完成。说不清的取舍，去写 ADR，别留在口头。
