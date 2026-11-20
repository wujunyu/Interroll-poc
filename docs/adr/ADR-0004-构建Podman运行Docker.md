# ADR-0004 构建用 Podman，运行用 Docker

- **状态**：已接受（2026-11-20 第二次修订；前一版「只用 Docker」作废）
- **日期**：2026-11-20

## 背景

最早一版写了「开发 Docker + 交付 Podman」，为了砍工作量又改成「只用 Docker」。
实际做到 P6 时遇到两件事：

1. 本机 Docker 的 buildx 在受限环境下写不了 `~/.docker/buildx`，构建直接失败；
2. 本机装了 Podman 5.4.2，构建不需要 daemon，且产物是标准 OCI 镜像。

## 决策

- **构建/发布**用 Podman（`deploy/scripts/build-images.sh`）；
- **运行**仍用 Docker Compose（`deploy/compose/compose.yaml`，`pull_policy: never` 用本地镜像）；
- 两边通过 `podman save | docker load` 衔接；镜像本身与运行时无关，将来整套搬走只需换掉这一步。

## 代价

- 多一步「导出再导入」，CI 里要显式写；
- 两个运行时各自占一份存储（`/var/lib/containers` 与 `/var/lib/docker`）；
- 构建要绕两处环境坑：buildah 要求 `--isolation=chroot --cgroup-manager=cgroupfs`（够不到宿主 systemd 的 cgroup），基础镜像要预置（`pull=never`）。

## 替代方案

| 方案 | 为什么没选 |
|---|---|
| 全用 Docker build | buildx 在受限环境不可用；构建失败无法推进 |
| 全用 Podman 跑 | compose 是既有的编排习惯，`podman-compose` 不在标准仓库 |
| 上 registry 再拉 | 演示是单机，registry 反而是额外故障点 |

## 事后回看

待补。若面试被问「为什么两个运行时」，答案就是上面那段：**构建与运行解耦，接口是 OCI 镜像**。
