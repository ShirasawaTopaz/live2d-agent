"""Logging service, mirroring the cordis logger contract used by DSH."""

from __future__ import annotations

import logging
from typing import Any

from .plugin import Service

__all__ = ["LoggerService", "LEVELS"]

LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "fatal": logging.CRITICAL,
}

_LOG = logging.getLogger("live2oder.cordis")


class LoggerService(Service):
    """Provides ``ctx.logger`` with a small cordis-shaped API."""

    def __init__(self, ctx: Any, name: str = "logger", *, base: str = "live2oder") -> None:
        super().__init__(ctx, name)
        self._base = base

    def _logger(self, scope: str = "") -> logging.Logger:
        return logging.getLogger(f"{self._base}.{scope}" if scope else self._base)

    def log(self, level: str, message: str, scope: str = "", **fields: Any) -> None:
        record = _format(message, fields)
        self._logger(scope).log(LEVELS.get(level, logging.INFO), record)

    def debug(self, message: str, scope: str = "", **fields: Any) -> None:
        self.log("debug", message, scope, **fields)

    def info(self, message: str, scope: str = "", **fields: Any) -> None:
        self.log("info", message, scope, **fields)

    def warn(self, message: str, scope: str = "", **fields: Any) -> None:
        self.log("warn", message, scope, **fields)

    warning = warn

    def error(self, message: str, scope: str = "", **fields: Any) -> None:
        self.log("error", message, scope, **fields)

    def fatal(self, message: str, scope: str = "", **fields: Any) -> None:
        self.log("fatal", message, scope, **fields)


def _format(message: str, fields: dict[str, Any]) -> str:
    if not fields:
        return message
    extras = " ".join(f"{key}={value}" for key, value in fields.items())
    return f"{message} {extras}"


def apply(ctx: Any, config: Any = None) -> None:
    """Function-shaped entry point for the ``core/logger`` plugin slot."""
    base = "live2oder"
    if isinstance(config, dict):
        base = str(config.get("base", base))
    service = LoggerService(ctx, "logger", base=base)
    ctx.service("logger", service)
    stop = getattr(service, "stop", None)
    if callable(stop):
        ctx.effect(stop)


_ = _LOG
