"""Exception types raised by the cordis kernel."""

from __future__ import annotations

from typing import Any


class CordisError(Exception):
    """Base class for every cordis kernel error."""


class ValidationError(CordisError):
    """Raised when a plugin config does not match its schema."""

    def __init__(self, path: str, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}" if path else message)


class ConfigError(CordisError):
    """Raised when a schema is built incorrectly."""


class LoaderError(CordisError):
    """Raised when a plugin module cannot be resolved or mounted."""


class ServiceError(CordisError):
    """Raised for invalid service registrations."""

    def __init__(self, name: str, message: str) -> None:
        self.name = name
        super().__init__(f"service '{name}': {message}")


class DisposedError(CordisError):
    """Raised when an operation targets a disposed context or fiber."""

    def __init__(self, target: Any = None) -> None:
        super().__init__(f"{target!r} is already disposed")
