# ADR-0006 技术栈与 AOT 边界

- **状态**：已接受
- **日期**：2026-11-21
- **相关**：ADR-0004（构建/交付）、`code/dotnet-aot-probe/`

## 背景

团队是 .NET 栈（历史项目用 log4net），本项目用 Python（FastAPI + paho + psycopg）。
需要回答三个问题：

1. PoC 用 Python 是否站得住？
2. 产品化若换 .NET，边缘机（ARM64、2–4GB）能不能扛？
3. 32 位 x86 老工控机怎么办？

## 决策

| 场景 | 选择 | 依据 |
|---|---|---|
| PoC / 48 小时闭环 | **Python**（现状） | I/O 密集型，实测两服务共 70MB，单进程 1.3 万行/秒 |
| 产品化、团队 .NET | **ASP.NET Core + MQTTnet + Npgsql**，镜像用 Alpine 或 AOT | 见下"实测" |
| ARM64 交付 | 两者都可，**.NET 可直接交叉发布** | `dotnet publish -r linux-arm64 -p:PublishAot=true` |
| 32 位 x86 目标 | **Go / C**，.NET 与 Python 都不合适 | NativeAOT 不支持 32 位 x86；Linux 32 位运行时已停 |

## 实测（`code/dotnet-aot-probe`，x86_64 主机交叉编译）

| 指标 | 结果 |
|---|---|
| linux-arm64 AOT 体积 | **1.32 MB**（Hello 级） |
| linux-x64 AOT 体积 | 1.28 MB |
| 启动耗时 | **≈ 1.7 ms** |
| arm64 产物在 x64 运行 | `exec format error`（说明是真交叉产物） |
| 交叉编译耗时 | ≈ 4 分钟（SDK 缓存后） |

对照：我们的 Python 镜像 api 310MB / ingest 224MB，空载内存 44MB / 25MB。

## 代价

| 项 | 说明 |
|---|---|
| 镜像基线 | Alpine 约 130MB；AOT 可到 15MB 级，但失去部分反射能力 |
| 生态限制 | EF Core / Dapper 基本不可 AOT；`System.Text.Json` 必须源生成；Npgsql 需核版本 |
| 工具链 | 交叉编译要 clang + cross-gcc + aarch64 objcopy（已踩坑，见探针 README） |
| 调试 | AOT 没有 JIT，现场只能靠日志与 core dump；开发期建议先框架依赖发布 |
| 迁移成本 | MQTT 协议无关，ingest/api 重写不改变架构（批量、幂等、spool、健康检查） |

## 不做什么

- 不在 PoC 里重写为 .NET（48 小时目标已完成，重写无收益）；
- 不为 32 位 x86 做兼容（占不到场景，且两边都不支持）；
- 不把探针纳入 compose / bundle（`make up` 不受影响）。

## 面试口径

> "PoC 用 Python 是 I/O 密集 + 交付速度的取舍，实测内存 70MB、吞吐 1.3 万行/秒。
> 产品化如果按团队栈走 .NET，我在 x64 上交叉编译过 ARM64 的 NativeAOT：1.32MB、启动 1.7ms，
> 说明边缘机扛得住；代价是 EF Core 这类反射重的库不能用，JSON 要走源生成。
> 32 位 x86 老机器两边都不合适，该换 Go。"
