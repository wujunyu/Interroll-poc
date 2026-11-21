# .NET NativeAOT 探针

**目的**：在一台 **x86_64 Linux** 上交叉编译出 **linux-arm64** 的 NativeAOT 二进制，
拿到三个真实数字——体积、启动时间、是否真的 arm64——用来判断"边缘机换 .NET 值不值"。

## 为什么放这里

不属于交付栈（`code/` 下唯一一个非服务目录），只为验证技术假设。
不参与 compose、不进 bundle、不影响 `make up`。

## 怎么跑

```bash
docker build -t dotnet-aot-probe . -f code/dotnet-aot-probe/Containerfile
docker run --rm dotnet-aot-probe sh -c 'ls -l /out/arm64 /out/x64; file /out/arm64/aotprobe'
docker run --rm dotnet-aot-probe /out/x64/aotprobe      # x64 可直接跑（本机就是 x64）
```

## 交叉编译的前提

| 需要 | 作用 |
|---|---|
| `clang` + `lld` | NativeAOT 用它做链接（不是 gcc） |
| `binutils-aarch64-linux-gnu` | 目标架构的 ld/objcopy |
| `libc6-dev-arm64-cross` | 目标架构的 glibc 头与库（sysroot） |

**不需要 QEMU**：交叉编译产出的是真二进制，不是模拟。
但反过来，**没有 QEMU 就跑不起来 arm64 产物**——本机没有 binfmt，`docker run --platform linux/arm64` 会 `exec format error`。
所以这里只能验证"能产出"，要验证"能运行"得在 ARM 机器或 CI 的 arm64 runner 上。

## 实测结果（x86_64 主机，.NET 10.0.15）

| 产物 | 体积 | 验证方式 | 结果 |
|---|---|---|---|
| `linux-arm64` AOT | **1,385,904 B ≈ 1.32 MB** | `aarch64-linux-gnu-readelf -h` | ELF64 / **AArch64** / PIE |
| `linux-x64` AOT | **1,341,016 B ≈ 1.28 MB** | 本机直接运行 | `arch = X64`，正常输出 |
| 启动耗时（x64，20 次均值） | **≈ 1.7 ms** | 容器内 `date +%s%N` 取差 | 符合 AOT 预期 |
| arm64 产物在 x64 上运行 | —— | `exec format error` | 证明是真交叉产物，不是模拟 |
| 交叉编译总耗时 | ≈ 4 分钟（SDK 已缓存） | 构建日志 | 可进 CI |

> 参考：带 ASP.NET Core 的最小 API，AOT 产物通常 10–15 MB；体积主要来自框架程序集。

## 踩过的三个坑（都会卡住流水线）

| 现象 | 原因 | 解法 |
|---|---|---|
| `cannot find crtbeginS.o` | 只装了 binutils，没有 cross-gcc | 装 `gcc-aarch64-linux-gnu` |
| `objcopy: Unable to recognise the format` | ILCompiler 调**裸名** `objcopy`，用的是宿主 x86 版本 | 建 `/opt/arm64bin` 符号链接，只在该步 `PATH` 前置 |
| `CS0103: Console 不存在` | 没开 `ImplicitUsings` | csproj 加 `<ImplicitUsings>enable</ImplicitUsings>` |
