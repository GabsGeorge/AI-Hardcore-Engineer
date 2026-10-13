"""Structured JSON logs with trace_id; every string value is PII-masked before any sink
(constitution VII and X)."""

import logging
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

from app.guardrails.pii import mask


def _mask_value(value: Any) -> Any:
    if isinstance(value, str):
        return mask(value)[0]
    if isinstance(value, dict):
        return {k: _mask_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_mask_value(v) for v in value]
    return value


def _mask_pii(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> Mapping[str, Any]:
    return {k: _mask_value(v) for k, v in event_dict.items()}


def configure_logging(level: int = logging.INFO) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _mask_pii,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )


def get_logger() -> Any:
    return structlog.get_logger()
