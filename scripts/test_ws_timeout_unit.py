"""直接验证 ws_live 的超时分支：用假连接模拟"发不出去"的客户端。

不依赖网络缓冲，3 秒出结果；网络层的慢测见 test_ws_timeout.py。
"""
import asyncio
import sys

sys.path.insert(0, "code/api")
import main as api  # noqa: E402


class SlowWS:
    """accept 正常、send 永远卡住、close 记录 code。"""

    def __init__(self) -> None:
        self.closed_with: int | None = None

    async def accept(self) -> None:
        return None

    async def send_json(self, payload) -> None:
        await asyncio.sleep(30)          # 模拟客户端不读，send 卡住

    async def close(self, code: int = 1000) -> None:
        self.closed_with = code


async def run() -> int:
    ws = SlowWS()
    before = api.ws_stats["timeouts"]
    await asyncio.wait_for(api.ws_live(ws), timeout=10)
    after = api.ws_stats["timeouts"]
    print(f"close code = {ws.closed_with}, timeouts {before} → {after}, clients = {api.ws_clients}")
    ok = ws.closed_with == 1013 and after == before + 1 and api.ws_clients == 0
    print("结论：" + ("✅ 超时后以 1013 关闭并归零" if ok else "❌ 未按预期关闭"))
    return 0 if ok else 1


raise SystemExit(asyncio.run(run()))
