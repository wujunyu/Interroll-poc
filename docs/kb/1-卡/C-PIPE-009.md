---
type: 事实卡
id: C-PIPE-009
confidence: 原文事实
source: "[[SRC-20261121-wal-kill9]]"
verified: 2026-11-21
tags: [英特诺, PoC, WAL, 崩溃恢复]
---
**主张**：把"失败才落盘"改成"先落盘再入库"，进程崩溃就不再丢数据；代价只是每批一次 fsync（本机 0.93ms）。

**实测**（500 条消息，kill -9 ingest）：

| 阶段 | 行数 |
|---|---|
| 发送前 | 0 |
| kill -9 时（已 flush） | 315 |
| 重启回放后 | **500** |

日志出现 `crash tail recovered`，WAL 游标从最后提交位置继续。

**机制**：WAL 追加 → flush 时 fsync → 入库 → 推进 `wal.commit` 字节偏移；
崩溃后从偏移回放，重复由 `(zone_id, drive_id, ts, seq)` 挡掉。

**边界**：进程崩溃（page cache 存活）不丢；**断电仍可能丢最后 ≤1 秒**，
因为 fsync 在 flush 时做，不是每条追加时做。

**反例**：若每秒消息量很大（>5 万），每批 fsync 的成本会明显，需要改成组提交或异步刷盘。
