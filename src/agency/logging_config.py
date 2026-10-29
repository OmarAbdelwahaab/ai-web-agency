"""Structured logging configuration for development and production."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from agency.config import Settings, get_settings


class JSONFormatter(logging.Formatter):
    """Serialize log records to a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        # Include custom extra fields if attached
        standard_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message",
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in standard_attrs and not k.startswith("_")}
        if extras:
            log_entry["extra"] = extras

        return json.dumps(log_entry)


def setup_logging(settings: Settings | None = None, level: int = logging.INFO) -> None:
    s = settings or get_settings()
    root = logging.getLogger()
    root.setLevel(level)

    # Remove existing handlers to avoid duplicates
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if (s.log_format or "text").lower() == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    root.addHandler(handler)
