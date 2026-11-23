"""Logging helpers: put the request ID on every log line, and write logs as JSON."""

import json
import logging
from datetime import UTC, datetime

from apps.platform.core.request_id import get_request_id


class RequestIdFilter(logging.Filter):
    """Add ``request_id`` to every log record. It never hides a record."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Django attaches the request to its own log records ("Not Found: /x/").
        request = getattr(record, "request", None)
        record.request_id = getattr(request, "request_id", None) or get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """Write each log record as one line of JSON, which log tools can search."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", get_request_id()),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)
