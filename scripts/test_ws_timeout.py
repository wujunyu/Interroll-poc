"""验证 WS 发送超时：客户端握手后不读数据 → 服务端应判定假死并关闭。

用法：python scripts/test_ws_timeout.py
"""
import base64
import json
import os
import socket
import time
import urllib.request

HOST, PORT = "127.0.0.1", int(os.environ.get("API_PORT", "8001"))


def health() -> dict:
    with urllib.request.urlopen(f"http://{HOST}:{PORT}/healthz", timeout=3) as r:
        return json.load(r)["ws"]


def handshake() -> socket.socket:
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)   # 让接收窗口很快关闭
    s.connect((HOST, PORT))
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall(
        f"GET /ws/live HTTP/1.1\r\nHost: {HOST}:{PORT}\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode()
    )
    time.sleep(0.3)
    return s


def main() -> int:
    before = health()
    print("连接前:", before)

    s = handshake()
    time.sleep(1.0)
    during = health()
    print("连接后:", during)

    # 不读数据，等服务端发送超时
    for _ in range(20):
        time.sleep(1)
        after = health()
        if after["clients"] == 0:
            break
    print("超时后:", after)
    try:
        data = s.recv(64)
        closed = data == b"" or b"\x88" in data   # EOF 或 close 帧
    except OSError:
        closed = True
    s.close()

    ok = during["clients"] >= 1 and after["clients"] == 0 and after["timeouts"] > before["timeouts"]
    print("结论：" + ("✅ 服务端识别假死并断开" if ok else "❌ 未按预期关闭"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
