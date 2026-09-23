"""Static safety checks for AI-authored cordis plugins.

Plugin source is validated with the same AST approach as dynamic tools, but with
a whitelist that also covers what a cordis plugin legitimately needs
(``asyncio``, ``dataclasses``, ``typing``, ``internal.cordis``, ...). The check
runs *before* anything is written to disk and again before mounting.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

from internal.agent.tool.dynamic.sandbox import ToolCodeSandbox

__all__ = [
    "PLUGIN_ALLOWED_MODULES",
    "PluginCodeSandbox",
    "PluginPolicy",
    "ValidationResult",
]

PLUGIN_ALLOWED_MODULES: frozenset[str] = frozenset(
    {
        "internal.cordis",
        "internal.plugins",
        "__future__",
        "asyncio",
        "collections",
        "contextlib",
        "dataclasses",
        "datetime",
        "enum",
        "functools",
        "itertools",
        "json",
        "logging",
        "math",
        "pathlib",
        "random",
        "re",
        "statistics",
        "string",
        "textwrap",
        "time",
        "types",
        "typing",
        "uuid",
    }
)

_FORBIDDEN_ATTRS = frozenset({"__globals__", "__code__", "__subclasses__", "__bases__", "__mro__"})
_FORBIDDEN_CALLS = frozenset({"exec", "eval", "compile", "__import__", "globals", "vars", "breakpoint"})


@dataclass(slots=True)
class ValidationResult:
    """Outcome of validating one plugin source file."""

    ok: bool
    errors: list[str] = field(default_factory=list)

    @property
    def message(self) -> str:
        return "; ".join(self.errors) if self.errors else "ok"


class PluginPolicy:
    """Where AI-authored plugins may be written."""

    def __init__(self, *, allow_core_writes: bool = False) -> None:
        self.allow_core_writes = allow_core_writes

    def check_target(self, path: Any, *, user_root: Any, core_root: Any) -> ValidationResult:
        """Allow the user plugin directory; core writes need an explicit opt-in."""
        resolved = str(path)
        user = str(user_root)
        core = str(core_root)
        if resolved.startswith(user):
            return ValidationResult(True)
        if resolved.startswith(core):
            if self.allow_core_writes:
                return ValidationResult(True)
            return ValidationResult(
                False,
                [
                    "writing into the shipped plugin directory requires "
                    "config.allow_core_writes = true"
                ],
            )
        return ValidationResult(
            False,
            [f"refusing to write outside the plugin directories: {resolved}"],
        )


class PluginCodeSandbox(ToolCodeSandbox):
    """AST validator tuned for plugin modules."""

    def __init__(self, *, allow_core_imports: bool = False) -> None:
        super().__init__()
        self.allow_core_imports = allow_core_imports

    def validate(self, code: str) -> ValidationResult:
        is_safe, violations = self.analyze(code)
        errors = [violation.message for violation in violations]
        self._check_plugin_specific(code, errors)
        return ValidationResult(is_safe and not errors, errors)

    def _check_import(self, module_name: str, line: int | None = None) -> None:
        if module_name in PLUGIN_ALLOWED_MODULES:
            return
        if self.allow_core_imports:
            root = module_name.split(".")[0]
            if root == "internal":
                return
        super()._check_import(module_name, line)

    def _check_plugin_specific(self, code: str, errors: list[str]) -> None:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_ATTRS:
                errors.append(f"forbidden attribute access: {node.attr}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in _FORBIDDEN_CALLS:
                    errors.append(f"forbidden call: {node.func.id}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("internal.") and not self.allow_core_imports:
                        if not alias.name.startswith("internal.cordis") and not alias.name.startswith(
                            "internal.plugins"
                        ):
                            errors.append(f"forbidden internal import: {alias.name}")
