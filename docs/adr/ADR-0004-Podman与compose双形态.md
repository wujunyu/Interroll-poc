# ADR-0004 开发用 Docker，交付用 Podman

- **状态**：已接受
- **日期**：2026-11-20

## 背景

开发机是 Docker（29.x + compose v5）；客户现场倾向无 daemon、可 rootless 的运行时。
两边镜像格式都是 OCI，编排文件也能复用。

## 决策

- 仓库里只有**一份 compose**（`deploy/compose/`），开发与演示都用它；
- 现场交付额外提供 `deploy/podman/quadlet/*.container`，由 systemd 直接拉起；
- **不引入 podman-compose 依赖**：compose 只用于开发/演示，现场用 quadlet。

## 代价

- 两套启动方式要各自验证（quadlet 的日志进 journald，与 compose logs 不同）；
- quadlet 的 `.container` 与 compose 的服务定义会漂移，需要人工同步；
- Podman rootless 下端口 < 1024 需要额外配置，本项目全用高位端口规避。

## 替代方案

| 方案 | 为什么没选 |
|---|---|
| 全用 Podman | 开发机没装，且 compose 生态在开发期更顺 |
| 全用 Docker + restart | Docker Desktop 商用要订阅；现场也不喜欢常驻 daemon |
| K8s/k3s | 见 ADR-0001 |

## 事后回看

待补。
