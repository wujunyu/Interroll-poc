"""告警状态机：去抖（持续 N 秒才算一条）、恢复、抑制。

设计要点：
- 每条规则对每个设备是独立的 pending → firing → resolved 状态机；
- 抖动只让 pending 清零，不产生告警（FR-09 的「10 秒抖动不报警」）；
- 条件消失就 resolved，状态被清掉，下次超限重新计 30 秒；
- 纯函数式喂样本（update/sweep），不碰数据库，方便单测。

没做的：抑制窗口（同 key 恢复后 N 分钟内不重复通知）。FR-09 只要求去抖，抑制属于告警治理的下一层。
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(slots=True)
class Rule:
    name: str
    metric: str
    threshold: float
    compare: str          # "gt" | "lt"
    for_seconds: float    # 去抖窗口：条件持续这么久才算一条
    level: str            # warning | critical
    message: str          # 可带 {zone} {drive} {value}

    def violated(self, value: float | None) -> bool:
        if value is None:
            return False
        return value > self.threshold if self.compare == "gt" else value < self.threshold


@dataclass
class _State:
    since: float
    firing: bool = False
    resolved_at: float | None = None


@dataclass
class Alert:
    key: str
    rule: str
    zone: str
    drive: str
    level: str
    state: str            # firing | resolved
    since: float
    value: float | None
    message: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "key": self.key, "rule": self.rule, "zone": self.zone,
            "drive": self.drive, "level": self.level, "state": self.state,
            "since": time.strftime("%H:%M:%S", time.localtime(self.since)),
            "value": None if self.value is None else round(self.value, 2),
            "message": self.message,
        }


DEFAULT_RULES = [
    Rule("电流过载", "current_a", 4.0, "gt", 30.0, "critical", "{zone}/{drive} 电流 {value}A 超限，持续 30s"),
    Rule("速度掉零", "speed_mps", 0.05, "lt", 30.0, "warning", "{zone}/{drive} 速度 {value} m/s，疑似堵料"),
]


class AlertEngine:
    def __init__(self, rules: list[Rule] | None = None, offline_seconds: float = 15.0) -> None:
        self.rules = rules if rules is not None else DEFAULT_RULES
        self.offline_seconds = offline_seconds
        self._state: dict[tuple[str, str], _State] = {}
        self._last_seen: dict[tuple[str, str], float] = {}
        self._active: dict[str, Alert] = {}
        self._history: list[Alert] = []

    # ---------- 样本驱动 ----------
    def update(self, point: dict[str, Any], now: float | None = None) -> list[Alert]:
        now = now if now is not None else time.time()
        zone, drive = point["zone"], point["drive"]
        self._last_seen[(zone, drive)] = now
        out: list[Alert] = []
        for rule in self.rules:
            st_key = (f"{zone}/{drive}", rule.name)
            value = point.get(rule.metric)
            st = self._state.get(st_key)
            if rule.violated(value):
                if st is None:
                    self._state[st_key] = _State(since=now)      # 开始计时，还不报
                elif not st.firing and now - st.since >= rule.for_seconds:
                    st.firing = True                              # 持续够久，报一条
                    out.append(self._emit(zone, drive, rule, value, st.since))
            elif st is not None:
                if st.firing:
                    out.append(self._resolve(zone, drive, rule, st, value, now))
                self._state.pop(st_key, None)                    # 清零：下次重新计时
        return out

    def sweep(self, now: float | None = None) -> list[Alert]:
        """离线规则：看最后一次见到该设备是多久以前。"""
        now = now if now is not None else time.time()
        out: list[Alert] = []
        for (zone, drive), seen in list(self._last_seen.items()):
            st_key = (f"{zone}/{drive}", "离线")
            st = self._state.get(st_key)
            gap = now - seen
            if gap >= self.offline_seconds:
                if st is None:
                    self._state[st_key] = _State(since=seen, firing=True)
                    rule = Rule("离线", "", 0, "gt", self.offline_seconds, "critical", "{zone}/{drive} 已 {value}s 无数据")
                    out.append(self._emit(zone, drive, rule, gap, seen))
            elif st and st.firing:
                rule = Rule("离线", "", 0, "gt", self.offline_seconds, "critical", "")
                out.append(self._resolve(zone, drive, rule, st, gap, now))
                self._state.pop(st_key, None)
        return out

    # ---------- 内部 ----------
    def _emit(self, zone: str, drive: str, rule: Rule, value: float | None, since: float) -> Alert:
        key = f"{zone}/{drive}/{rule.name}"
        try:  # 模板写错（少一个占位参数）不该让告警丢失
            text = rule.message.format(zone=zone, drive=drive, value=value)
        except (KeyError, IndexError):
            text = f"{zone}/{drive} {rule.name}"
        alert = Alert(key=key, rule=rule.name, zone=zone, drive=drive, level=rule.level,
                      state="firing", since=since, value=value, message=text)
        self._active[key] = alert
        self._history.append(alert)
        return alert

    def _resolve(self, zone: str, drive: str, rule: Rule, st: _State, value: float | None, now: float) -> Alert:
        key = f"{zone}/{drive}/{rule.name}"
        prev = self._active.pop(key, None)
        st.firing = False
        st.resolved_at = now
        alert = Alert(key=key, rule=rule.name, zone=zone, drive=drive, level=rule.level,
                      state="resolved", since=prev.since if prev else now, value=value,
                      message=f"{zone}/{drive} {rule.name} 已恢复")
        self._history.append(alert)
        return alert

    # ---------- 查询 ----------
    def active(self) -> list[dict[str, Any]]:
        return [a.as_dict() for a in sorted(self._active.values(), key=lambda a: -a.since)]

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        return [a.as_dict() for a in self._history[-limit:]]
