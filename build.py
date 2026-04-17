#!/usr/bin/env python3
"""Live2D Agent packaging orchestrator for the PyInstaller spec build."""

from __future__ import annotations

import argparse
import ast
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path

PROJECT_NAME = "live2d-agent"
VERSION = "0.1.0"
SPEC_FILE = Path("live2d-agent.spec")
DIST_ROOT = Path("dist")
BUILD_ROOT = Path("build")
OUTPUT_DIR = DIST_ROOT / f"{PROJECT_NAME}-{VERSION}"
PYINSTALLER_DIST_DIR = DIST_ROOT


@dataclass(frozen=True)
class InventoryItem:
    label: str
    source: Path | None
    destination: Path
    required: bool = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build or verify the Live2D Agent packaging output."
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("build", "verify-inventory"),
        default="build",
        help="build the distributable output or verify an existing inventory",
    )
    return parser.parse_args()


def executable_name() -> str:
    suffix = ".exe" if platform.system() == "Windows" else ""
    return f"{PROJECT_NAME}{suffix}"


def parse_spec_datas() -> list[tuple[str, str]]:
    spec_source = SPEC_FILE.read_text(encoding="utf-8")
    module = ast.parse(spec_source, filename=str(SPEC_FILE))

    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue

        if not any(
            isinstance(target, ast.Name) and target.id == "a" for target in node.targets
        ):
            continue

        if not (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "Analysis"
        ):
            continue

        datas: list[tuple[str, str]] = []

        for keyword in node.value.keywords:
            if keyword.arg == "datas":
                datas = ast.literal_eval(keyword.value)

        return datas

    raise ValueError(f"Could not find Analysis(...) assignment in {SPEC_FILE}")


def spec_inventory_items() -> list[InventoryItem]:
    datas = parse_spec_datas()
    items: list[InventoryItem] = []

    for source_text, destination_text in datas:
        source = Path(source_text)
        destination = Path(destination_text)
        if source.name != destination.name:
            destination = destination / source.name
        items.append(InventoryItem(source.name, source, destination))

    return items


def distribution_inventory() -> list[InventoryItem]:
    executable = InventoryItem("executable", None, Path(executable_name()))
    return [executable, *spec_inventory_items()]


def ensure_pyinstaller_installed() -> None:
    if find_spec("PyInstaller") is not None:
        return

    raise RuntimeError(
        "PyInstaller is not installed in the active environment. "
        "Install it first (for example: `poetry add --group dev pyinstaller`) "
        "and rerun `poetry run python build.py`."
    )


def clean_build() -> None:
    print("=== Cleaning previous build outputs ===")
    for path in (OUTPUT_DIR, BUILD_ROOT, DIST_ROOT, Path("__pycache__")):
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            print(f"Removed: {path}")
    print()


def run_pyinstaller() -> None:
    ensure_pyinstaller_installed()

    print("=== Running PyInstaller from spec ===")
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(PYINSTALLER_DIST_DIR),
        "--workpath",
        str(BUILD_ROOT),
        str(SPEC_FILE),
    ]
    print("Command:", " ".join(command))
    print()
    subprocess.check_call(command)
    print()


def copy_directory(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def materialize_distribution() -> None:
    print("=== Materializing distribution inventory ===")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pyinstaller_executable = PYINSTALLER_DIST_DIR / executable_name()
    if not pyinstaller_executable.exists():
        raise FileNotFoundError(
            f"PyInstaller output not found: {pyinstaller_executable}"
        )

    final_executable = OUTPUT_DIR / executable_name()
    shutil.move(str(pyinstaller_executable), final_executable)
    print(f"Included executable: {final_executable}")

    for item in distribution_inventory()[1:]:
        if item.source is None:
            continue

        source = item.source
        destination = OUTPUT_DIR / item.destination

        if not source.exists():
            if item.required:
                raise FileNotFoundError(
                    f"Required packaging asset is missing: {source}"
                )
            print(f"Skipped optional asset: {source}")
            continue

        if source.is_dir():
            copy_directory(source, destination)
        else:
            copy_file(source, destination)
        print(f"Included {item.label}: {destination}")
    print()


def verify_inventory(output_dir: Path = OUTPUT_DIR) -> list[Path]:
    missing: list[Path] = []

    for item in distribution_inventory():
        path = output_dir / item.destination
        if not path.exists():
            missing.append(path)

    return missing


def show_result() -> None:
    print("=== Build complete ===")
    print(f"Output directory: {OUTPUT_DIR.resolve()}")
    print("Inventory:")
    for item in distribution_inventory():
        print(f"- {item.destination}")
    print()


def run_build() -> None:
    print(f"Live2D Agent packaging build v{VERSION}")
    print(f"System: {platform.system()} {platform.release()}")
    print(f"Python: {sys.version}")
    print()

    clean_build()
    run_pyinstaller()
    materialize_distribution()

    missing = verify_inventory()
    if missing:
        missing_paths = ", ".join(str(path) for path in missing)
        raise RuntimeError(
            f"Distribution inventory verification failed: {missing_paths}"
        )

    show_result()


def run_inventory_verification() -> None:
    missing = verify_inventory()
    if missing:
        print("Missing distribution artifacts:")
        for path in missing:
            print(f"- {path}")
        raise SystemExit(1)

    print(f"Inventory verified successfully: {OUTPUT_DIR.resolve()}")
    for item in distribution_inventory():
        print(f"- {item.destination}")


def main() -> None:
    args = parse_args()

    if args.command == "verify-inventory":
        run_inventory_verification()
        return

    run_build()


if __name__ == "__main__":
    main()
