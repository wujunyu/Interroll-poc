"""产线遥测的造数与序列化：模拟器与 QoS 实验台共用。

一条消息 = 一台驱动在一个采样时刻的状态。seq 是设备侧自增，补传去重靠它。
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass

ZONES = ("Z1", "Z2", "Z3", "Z4", "Z5", "Z6")
DRIVES = tuple(f"D{i:02d}" for i in range(1, 7))


@dataclass(slots=True)
class Sample:
    ts: str
    zone: str
    drive: str
    seq: int
    speed_mps: float
    current_a: float
    temp_c: float
    state: str


def speed_at(t: float, phase: float = 0.0) -> float:
    """0.55±0.25 m/s 的慢波动 + 高频毛刺，模拟真实输送线。"""
    slow = 0.55 + 0.18 * math.sin(t * 0.55 + phase)
    ripple = 0.05 * math.sin(t * 9.0 + phase * 2)
    return round(max(0.0, min(1.2, slow + ripple)), 3)


def make_sample(zone: str, drive: str, seq: int, ts: str, t: float) -> Sample:
    phase = (hash((zone, drive)) % 100) / 100 * math.pi
    speed = speed_at(t, phase)
    return Sample(
        ts=ts,
        zone=zone,
        drive=drive,
        seq=seq,
        speed_mps=speed,
        current_a=round(1.8 + speed * 1.4, 2),
        temp_c=round(38 + speed * 6, 1),
        state="running" if speed > 0.05 else "idle",
    )


def to_payload(sample: Sample) -> bytes:
    return json.dumps(asdict(sample), separators=(",", ":")).encode()


def topic_for(zone: str, drive: str, prefix: str = "line") -> str:
    return f"{prefix}/{zone}/drive/{drive}"
