---
type: 事实卡
id: C-MQTT-003
confidence: 原文事实
source: "[[SRC-20261120-qos实验]]"
verified: 2026-11-20
tags: [英特诺, PoC, MQTT, paho]
---
**主张**：paho-mqtt 2.x 复用同一个 `Client` 对象调 `reconnect()`，会话会被 Broker 标记 `session taken over`，
`on_connect` 不再触发，排队的消息一条也收不到。
**原文**：第一次跑 QoS1 时丢失 200 条；改用「新建 Client + 同一 client_id」后 300/300。
**边界**：mosquitto 2.0 + paho 2.2.0 实测；其他组合未验证。判断会话是否恢复看 CONNACK 的 `session_present`。
**冲突/反例**：待确认（paho 1.x 行为不同）。
