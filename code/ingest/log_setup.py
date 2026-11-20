"""结构化日志：一行一条 JSON 到 stdout；崩溃留栈。

刻意在 ingest / api 各放一份（AGENTS.md：复制小段代码优于抽公共库）。
字段约定：ts / level / svc / msg，外加 zone / drive / trace_id / rows / spool。
"""
from __future__ import annotations

import faulthandler
import json
import logging
import sys
import time

_EXTRA = ("zone", "drive", "trace_id", "rows", "spool", "detail")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(record.created)),
            "level": record.levelname.lower(),
            "svc": getattr(record, "svc", "-"),
            "msg": record.getMessage(),
        }
        for key in _EXTRA:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup(svc: str, level: str = "INFO") -> logging.Logger:
    faulthandler.enable()  # 段错误 / 死锁时把栈打到 stderr（容器日志里能看到）
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    logger = logging.getLogger(svc)
    logger = logging.LoggerAdapter(logger, {"svc": svc})
    return logger  # type: ignore[return-value]
