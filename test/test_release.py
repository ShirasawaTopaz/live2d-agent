"""Release invariants: version and lock file stay consistent with pyproject."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _dependency_names() -> list[str]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    names: list[str] = []
    for item in pyproject["project"]["dependencies"]:
        name = re.split(r"[<>=!\[ ]", item, maxsplit=1)[0].strip()
        names.append(name.lower().replace("_", "-"))
    return names


def test_lock_file_locks_every_runtime_dependency() -> None:
    lock_text = (ROOT / "poetry.lock").read_text(encoding="utf-8")
    locked = set(re.findall(r'^name = "([^"]+)"', lock_text, flags=re.MULTILINE))

    missing = [name for name in _dependency_names() if name not in locked]
    assert not missing, f"poetry.lock is stale, missing: {missing}"


def test_package_version_is_release_version() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == "0.2.0"
