# simulator（demo profile 专用）

**职责**：造数 + **QoS 实验台**。6 区 × 6 驱动 = 36 点，10Hz → 360 点/秒；可注入断网。

**不做**：不落库、不做聚合、不参与生产部署。

## 环境

本机用 conda（环境在仓库内，不入库）：

```bash
conda create -p .conda-env python=3.12 -y
.conda-env/bin/pip install -r code/simulator/requirements.txt
docker compose --env-file .env -f deploy/compose/compose.yaml up -d mqtt   # 1884
```

## 跑起来

```bash
# 10Hz 造数 10 秒，QoS1
.conda-env/bin/python code/simulator/main.py --duration 10 --qos 1

# 第 5 秒断网 8 秒（消息只进本地缓冲，只计数不重发）
.conda-env/bin/python code/simulator/main.py --duration 20 --offline-at 5 --offline-for 8

# QoS 实验：300 条 @100/s，中途把订阅端踢下线 1.5 秒
.conda-env/bin/python code/simulator/qos_lab.py --qos 1 --count 300 --rate 100 \
    --offline-at 1.0 --offline-for 1.5
```

实测吞吐：`--duration 6` 发出 2160 条，订阅端收到 2160 条，正好 360 条/秒。

## QoS 0/1/2 实测（2026-11-20，mosquitto 2.0）

条件：300 条、100 条/秒、第 1.0 秒订阅端断线 1.5 秒、订阅端 `clean_session=false`。

| # | pub QoS | sub QoS | 有效 QoS | 发送 | 唯一收到 | 丢失 | 重复 |
|---|---|---|---|---|---|---|---|
| A | 0 | 0 | 0 | 300 | 149 | **151** | 0 |
| B | 1 | 1 | 1 | 300 | 300 | 0 | 0 |
| C | 2 | 2 | 2 | 300 | 299 | **1** | 0 |
| D | 2 | 0 | 0 | 300 | 149 | **151** | 0 |

读法：

- **A vs D**：发布端用 QoS2 也没用，订阅端 QoS0 就把整条链降到 0——**实际 QoS = min(pub, sub)**。
- **B**：QoS1 在 1.5 秒断线里靠 Broker 排队补回 150 条，一条不丢（重复为 0 是因为链路干净；网络抖动时会重传，那时会出现重复）。
- **C**：丢的那 1 条是**断线瞬间正在四段握手里的消息**（seq=99，刚好在 1.0s）。这说明 QoS2 也只保「每一跳、每个会话」，断线瞬间仍有在途窗口——**所以数据面仍然需要应用层幂等**（我们靠 `drive_id + ts + seq`）。

## 两个坑（都踩过）

1. **paho 2.x 复用同一 `Client` 对象 `reconnect()`**：Broker 记 `session taken over`，`on_connect` 不触发，排队的消息一条都收不到（第一次跑出来 QoS1 也丢 200 条就是这个）。正确做法是**每次重连新建 `Client`，但 `client_id` 不变**，CONNACK 的 `session_present=true` 就是会话恢复的证据。
2. **固定 sleep 等补传**：QoS2 最后几条要走完 PUBLISH→PUBREC→PUBREL→PUBCOMP，固定等待会把在途消息误判成丢。实验台改成「轮询到 `unique == sent` 或超时」。

## 输出契约

Topic：`line/{zone}/drive/{drive}`（QoS 由 `--qos` 决定，不 retain）

```json
{"ts":"2026-11-20T21:36:12.345+08:00","zone":"Z3","drive":"D02","seq":184223,
 "speed_mps":0.78,"current_a":2.5,"temp_c":41.2,"state":"running"}
```

`seq` 设备侧自增，补传去重靠它。
