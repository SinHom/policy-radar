"""JSON 结构化日志配置。

设计：
- 默认输出 JSON（含 ts/level/logger/msg/module + 任意 extra 字段）
- Windows console 不支持 emoji / GBK 编码问题：用 errors='replace' 兜底
- 通过 LOG_FORMAT=json|text 环境变量切换（text 用于本地开发，json 用于生产/聚合）
- correlation_id 通过 contextvar 跨函数传递（webhook push / MCP tool 调用时打 tag）

用法：
    from python.app.logging_config import setup_logging
    setup_logging()  # 入口调用一次

    # 业务日志里加 extra：
    logger.info("push ok", extra={"subscription_id": 1, "matches": 4})
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Any

# correlation_id 跨函数传递
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def new_correlation_id() -> str:
    """生成新 correlation_id 并设到 context。"""
    cid = uuid.uuid4().hex[:16]
    _correlation_id.set(cid)
    return cid


def get_correlation_id() -> str | None:
    return _correlation_id.get()


class JsonFormatter(logging.Formatter):
    """JSON formatter：每条日志输出单行 JSON。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Windows console 容错
        self._encoding = sys.stdout.encoding or "utf-8"

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        # correlation_id
        cid = _correlation_id.get()
        if cid:
            payload["correlation_id"] = cid
        # exception
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # 任意 extra 字段（exclude 标准 LogRecord 属性）
        std = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "asctime",
        }
        for k, v in record.__dict__.items():
            if k not in std and not k.startswith("_"):
                try:
                    json.dumps(v)
                    payload[k] = v
                except (TypeError, ValueError):
                    payload[k] = str(v)
        # 编码安全
        try:
            return json.dumps(payload, ensure_ascii=False)
        except (TypeError, ValueError):
            payload["msg"] = str(record.getMessage())
            return json.dumps(payload, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """本地开发用：彩色 / 人类可读（但 Windows console 不支持 emoji 时降级）。"""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        # Windows GBK 容错
        try:
            msg.encode(sys.stdout.encoding or "utf-8")
        except UnicodeEncodeError:
            msg = msg.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
                sys.stdout.encoding or "utf-8", errors="replace"
            )
        return msg


def setup_logging(
    level: str | None = None,
    fmt: str | None = None,
    log_file: str | None = None,
) -> None:
    """初始化全局 logging。

    参数：
        level:  DEBUG/INFO/WARNING/ERROR，从环境变量 LOG_LEVEL 读
        fmt:   json/text，从 LOG_FORMAT 读，默认 text
        log_file: 可选，写日志到文件（不影响 console）
    """
    level = level or os.environ.get("LOG_LEVEL", "INFO").upper()
    fmt = fmt or os.environ.get("LOG_FORMAT", "text").lower()

    root = logging.getLogger()
    # 清掉已有 handler（避免重复调用 setup_logging 时叠加）
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(level)

    if fmt == "json":
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = TextFormatter()

    # console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    # file handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(JsonFormatter())  # 文件总是 JSON
        root.addHandler(fh)

    # 抑制过吵的 logger
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "logging initialized: level=%s format=%s file=%s",
        level, fmt, log_file or "none",
    )
