---
type: 事实卡
id: C-PIPE-008
confidence: 原文事实
source: "[[SRC-20261121-insert-bench]]"
verified: 2026-11-21
tags: [英特诺, PoC, PostgreSQL, 写入]
---
**主张**：PostgreSQL 插入的瓶颈是**提交次数**，不是 SQL 本身；把 3 万行拆成 3 万次 commit，比批量慢 **89 倍**。

**实测**（同一张表、3 万行，脚本 `scripts/bench_insert.py`）：

| 方式 | 耗时 | 吞吐 |
|---|---|---|
| 逐条 execute + 逐条 commit | 59.9 s | **501 行/秒** |
| `executemany`，200 行/批，每批一次 commit | 0.67 s | **44,521 行/秒** |
| `COPY` 进临时表 → `INSERT … SELECT … ON CONFLICT` | 0.53 s | **56,682 行/秒** |

**原因**：每次 commit 触发 WAL fsync（约 2ms），单行提交的开销全在刷盘上，不在解析。

**边界**：`COPY` 不能直接做 `ON CONFLICT`，要先进临时表再去重，失败处理更复杂；
我们的量级 360 行/秒，`executemany` 有 100 倍以上余量，不值得上 COPY。

**反例**：历史数据导入（百万行、可接受短暂锁）用 COPY 更快；在线高频写入要求幂等时优先批量 INSERT。
