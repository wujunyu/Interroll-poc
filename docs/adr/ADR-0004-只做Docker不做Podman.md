# ADR-0004 只用 Docker，不做 Podman / quadlet / 边缘交付形态

- **状态**：已接受（2026-11-20 修订：原方案「开发 Docker + 交付 Podman」作废）
- **日期**：2026-11-20

## 背景

原计划给现场交付留一套 Podman quadlet（无 daemon、rootless、systemd 直管）。
但本次目标是**面试演示**，交付形态不是考点；同时 Podman 会带来两套启动路径、
两套日志、两份需要同步的服务定义——纯增成本，不增演示效果。

## 决策

1. 运行时只有 **Docker Compose**，一份 `deploy/compose/compose.yaml` + 一份 `compose.dev.yaml`；
2. 不做 Podman、不做 quadlet、不做 K8s、不做「边缘机交付包」；
3. 「可移交」靠**诊断包 + 回滚脚本 + runbook** 证明，而不是靠第二套运行时。

## 代价

- 面试若被问「现场为什么不用 Podman」，只能讲取舍（本 ADR），不能现场演示；
- 少了 rootless、开机自启、无 daemon 这三个可以展开的话题；
- 未来真要交付，得补一层 quadlet，本 ADR 需翻案。

## 替代方案

| 方案 | 为什么没选 |
|---|---|
| Docker + Podman 双形态 | 两套启动方式要各自验证，工期不够；演示看不出差别 |
| 只写 Podman | 开发机没装，compose 生态在开发期更顺 |
| K8s / k3s | 一台机器上跑控制面纯亏，见 ADR-0001 |

## 事后回看

待补。若面试明确问「交付形态」，就用本 ADR 的「代价」一节正面回答。
