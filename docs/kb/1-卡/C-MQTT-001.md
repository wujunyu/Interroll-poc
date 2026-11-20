---
type: 事实卡
id: C-MQTT-001
confidence: 原文事实
source: "[[SRC-20261120-qos实验]]"
verified: 2026-11-20
tags: [英特诺, PoC, MQTT, QoS]
---
**主张**：一条链路的实际 QoS = min(发布端 QoS, 订阅端 QoS)；发布端用 QoS2 也会被订阅端的 QoS0 拉平。
**原文**：实验 D 组（pub 2 / sub 0）丢失 151 条，与 A 组（0/0）完全一致。
**边界**：MQTT 3.1.1 与 5.0 都按此规则；Broker 侧的策略不改变这条语义。
**冲突/反例**：无。
