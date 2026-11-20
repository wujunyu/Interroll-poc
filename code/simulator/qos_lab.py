"""QoS 实验台：在「订阅端断线再重连」这一次故障里，量出 QoS 0/1/2 的差别。

只做一件事：发布 N 条带 seq 的消息，中途把订阅端踢下线一段时间，再看最后收到多少、
多少重复、丢了多少。输出一行 JSON，方便脚本聚合。

    python code/simulator/qos_lab.py --qos 1 --count 300 --rate 100 \
        --offline-at 1.0 --offline-for 1.5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone, timedelta

import paho.mqtt.client as mqtt

CST = timezone(timedelta(hours=8))


class Collector:
    """订阅端：记录收到的 seq，用来算「唯一 / 重复 / 丢」。

    坑（2026-11-20 实测）：paho 2.x 里复用同一个 Client 对象调 `reconnect()`，
    Broker 会记 "session taken over"，on_connect 不再触发，排队的消息一条都收不到。
    正确做法是**每次重连新建 Client 对象，client_id 保持不变**，会话才会被恢复
    （CONNACK 的 session_present=True 就是证据）。
    """

    def __init__(self, host: str, port: int, topic: str, sub_qos: int, client_id: str,
                 user: str = "", password: str = "") -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.topic = topic
        self.sub_qos = sub_qos
        self.client_id = client_id
        self.seqs: list[int] = []
        self.session_flags: list[bool] = []
        self.lock = threading.Lock()
        self.connected = threading.Event()
        self.client: mqtt.Client | None = None
        self.start()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        with self.lock:
            self.session_flags.append(bool(getattr(flags, "session_present", False)))
        client.subscribe(self.topic, qos=self.sub_qos)
        self.connected.set()

    def _on_message(self, client, userdata, msg) -> None:
        try:
            seq = json.loads(msg.payload)["seq"]
        except Exception:
            return
        with self.lock:
            self.seqs.append(int(seq))

    def start(self) -> None:
        self.connected.clear()
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            clean_session=False,  # 保留会话：断线期间的 QoS1/2 消息由 Broker 排队
        )
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        if self.user:
            client.username_pw_set(self.user, self.password)
        client.connect(self.host, self.port, keepalive=30)
        client.loop_start()
        self.client = client
        self.connected.wait(timeout=10)

    def offline(self) -> None:
        self.connected.clear()
        if self.client is not None:
            self.client.disconnect()
            self.client.loop_stop()

    def online(self) -> None:
        self.start()

    def close(self) -> None:
        if self.client is not None:
            self.client.loop_stop()
            try:
                self.client.disconnect()
            except Exception:
                pass

    def stats(self, sent: int) -> dict[str, int]:
        with self.lock:
            got = list(self.seqs)
        uniq = len(set(got))
        return {
            "sent": sent,
            "received": len(got),
            "unique": uniq,
            "duplicates": len(got) - uniq,
            "lost": sent - uniq,
            "missing_preview": sorted(set(range(sent)) - set(got))[:5],
        }


def main() -> int:
    ap = argparse.ArgumentParser(description="QoS 故障注入实验")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("MQTT_PORT", "1883")))
    ap.add_argument("--user", default=os.environ.get("MQTT_USERNAME", ""))
    ap.add_argument("--password", default=os.environ.get("MQTT_PASSWORD", ""))
    ap.add_argument("--qos", type=int, choices=(0, 1, 2), default=1)
    ap.add_argument("--sub-qos", type=int, choices=(0, 1, 2), default=None,
                    help="不给则与 --qos 相同；用来验证「实际 QoS = min(pub, sub)」")
    ap.add_argument("--count", type=int, default=300)
    ap.add_argument("--rate", type=float, default=100.0)
    ap.add_argument("--offline-at", type=float, default=1.0)
    ap.add_argument("--offline-for", type=float, default=1.5)
    ap.add_argument("--drain", type=float, default=2.0)
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    sub_qos = args.qos if args.sub_qos is None else args.sub_qos
    run_id = f"{int(time.time() * 1000)}"
    topic = f"lab/qos/{run_id}"

    sub = Collector(args.host, args.port, topic, sub_qos, client_id=f"lab-sub-{run_id}",
                    user=args.user, password=args.password)
    if not sub.connected.is_set():
        print("订阅端连不上 Broker", file=sys.stderr)
        return 2

    pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"lab-pub-{run_id}")
    if args.user:
        pub.username_pw_set(args.user, args.password)
    pub.connect(args.host, args.port, keepalive=30)
    pub.loop_start()

    def inject_fault() -> None:
        time.sleep(args.offline_at)
        sub.offline()
        time.sleep(args.offline_for)
        sub.online()

    fault = threading.Thread(target=inject_fault, daemon=True)
    fault.start()

    period = 1.0 / args.rate
    started = time.monotonic()
    sent = 0
    for i in range(args.count):
        ts = datetime.now(CST).isoformat(timespec="milliseconds")
        pub.publish(topic, json.dumps({"seq": i, "ts": ts}), qos=args.qos)
        sent += 1
        target = started + (i + 1) * period
        time.sleep(max(0.0, target - time.monotonic()))

    fault.join(timeout=args.offline_for + 15)
    # 收敛等待：QoS2 的最后一两条要走完四段握手，固定 sleep 会把它算成「丢」
    deadline = time.monotonic() + args.drain
    while time.monotonic() < deadline:
        if sub.stats(sent)["unique"] >= sent:
            break
        time.sleep(0.1)
    time.sleep(0.2)

    result = {
        "label": args.label or f"pub qos{args.qos} / sub qos{sub_qos}",
        "pub_qos": args.qos,
        "sub_qos": sub_qos,
        "effective_qos": min(args.qos, sub_qos),
        **sub.stats(sent),
        "offline_seconds": args.offline_for,
        "session_restored": sub.session_flags,
    }
    sub.close()
    pub.loop_stop()
    pub.disconnect()

    print("RESULT " + json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
