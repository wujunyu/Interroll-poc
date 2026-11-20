"""FR-09 验收：10 秒抖动不报警，持续 30 秒才报一条；恢复后 resolved。"""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("alerts", Path("code/api/alerts.py"))
m = importlib.util.module_from_spec(spec)
sys.modules["alerts"] = m          # dataclass 需要模块已注册，否则取 __module__ 会炸
spec.loader.exec_module(m)

rule = m.Rule("电流过载", "current_a", 4.0, "gt", 30.0, "critical", "{zone}/{drive} {value}A")
eng = m.AlertEngine(rules=[rule], offline_seconds=999)

def feed(seconds: int, amps: float, start: float) -> list:
    out = []
    for t in range(seconds):
        out += eng.update({"zone": "Z1", "drive": "D01", "current_a": amps}, now=start + t)
    return out

# 1) 抖动 10 秒（超限但不满 30 秒）→ 不应有告警
a = feed(10, 4.8, start=0)
print(f"抖动 10s：告警 {len(a)} 条  → {'通过' if not a else '失败'}")

# 2) 恢复 5 秒，再持续超限 35 秒 → 只报 1 条
a = feed(5, 2.0, start=10)
print(f"恢复 5s：告警 {len(a)} 条（清除态）")
a = feed(35, 4.8, start=15)
print(f"持续 35s：告警 {len(a)} 条 → {'通过' if len(a) == 1 else '失败'}")
active = eng.active()
print(f"当前活动告警 {len(active)} 条：{active[0]['message'] if active else '—'}")

# 3) 恢复 → resolved
a = feed(2, 2.0, start=50)
print(f"恢复 2s：告警 {len(a)} 条，状态 {a[0].state if a else '—'} → {'通过' if a and a[0].state == 'resolved' else '失败'}")
print(f"活动告警剩 {len(eng.active())} 条，历史 {len(eng.history())} 条")
