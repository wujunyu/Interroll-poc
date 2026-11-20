"""连 /ws/live 数 3 秒，验证节流是否在 10fps 附近。"""
import asyncio, json, sys, time
import websockets

async def main(url: str = "ws://127.0.0.1:8080/ws/live", seconds: float = 3.0) -> None:
    n = 0
    first = None
    async with websockets.connect(url) as ws:
        t0 = time.monotonic()
        while time.monotonic() - t0 < seconds:
            frame = json.loads(await ws.recv())
            n += 1
            if first is None:
                first = frame
        dt = time.monotonic() - t0
    print(f"帧数 {n} / {dt:.1f}s → {n/dt:.1f} fps")
    pts = first.get("points", []) if first else []
    print(f"首帧点数 {len(pts)}，样例：{json.dumps(pts[:2], ensure_ascii=False)}")

asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8080/ws/live"))
