"""Packaging contract: the plugin tree and skills ship with the executable."""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_FILE = REPO_ROOT / "live2d-agent.spec"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _spec_datas() -> list[tuple[str, str]]:
    module = ast.parse(SPEC_FILE.read_text(encoding="utf-8"), filename=str(SPEC_FILE))
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if "a" not in targets:
            continue
        if not isinstance(node.value, ast.Call):
            continue
        for keyword in node.value.keywords:
            if keyword.arg == "datas":
                return ast.literal_eval(keyword.value)
    raise AssertionError("Analysis(datas=...) not found in the spec")


def _spec_hiddenimports() -> list[str]:
    module = ast.parse(SPEC_FILE.read_text(encoding="utf-8"), filename=str(SPEC_FILE))
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if "a" not in targets or not isinstance(node.value, ast.Call):
            continue
        for keyword in node.value.keywords:
            if keyword.arg == "hiddenimports":
                return ast.literal_eval(keyword.value)
    raise AssertionError("Analysis(hiddenimports=...) not found in the spec")


def test_spec_ships_plugin_tree_and_skills() -> None:
    datas = dict(_spec_datas())

    assert "internal/plugins" in datas, "the plugin tree (cordis.yml + plugins) must be bundled"
    assert "skills" in datas, "skills must be bundled so self-evolution can ship its prompts"
    assert "prompt_modules" in datas

    for source in datas:
        assert (REPO_ROOT / source).exists(), f"packaging source missing: {source}"


def test_spec_bundles_cordis_hidden_imports() -> None:
    hidden = set(_spec_hiddenimports())

    required = {
        "internal.cordis",
        "internal.cordis.loader",
        "internal.plugins.app",
        "internal.plugins.agent.loop",
        "internal.plugins.outputs.typewriter",
        "internal.plugins.meta.self_evolution",
        "internal.plugins.meta.evolution_tools",
        "internal.plugins.core.tools",
        "internal.plugins.ui.bubble_widget",
    }
    missing = required - hidden
    assert not missing, f"spec is missing hidden imports: {sorted(missing)}"


def test_self_evolution_skill_is_shipped() -> None:
    skill_dir = REPO_ROOT / "skills" / "self-evolution"
    assert (skill_dir / "skill.yaml").is_file()
    prompts = list((skill_dir / "prompts").glob("*.md"))
    assert prompts, "the self-evolution skill needs at least one prompt module"
    assert "plugin_install" in (skill_dir / "skill.yaml").read_text(encoding="utf-8")


def test_pyyaml_is_a_declared_dependency() -> None:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]
    assert any(item.split()[0].startswith("pyyaml") for item in dependencies), (
        "cordis.yml needs PyYAML, so it must be an explicit project dependency"
    )


def test_plugin_tree_path_resolves_to_packaged_file() -> None:
    from internal.plugins.app import plugin_tree_path

    path = plugin_tree_path()
    assert path.is_file(), path
    text = path.read_text(encoding="utf-8")
    assert "internal.plugins.meta.self_evolution" in text
    assert "internal.plugins.outputs.typewriter" in text

    from internal.cordis import load_entries_from_file

    entries = load_entries_from_file(path)
    ids = {entry.id or entry.key for entry in entries}
    assert {"logger", "loop", "output", "self-evolution", "hmr"} <= ids


def test_example_configs_parse_with_the_current_schema() -> None:
    from internal.config.config import parse_config_content

    for name in ("config.example.json", "config.example-prompt-modules.json"):
        path = REPO_ROOT / name
        assert path.is_file(), name
        _raw, config = parse_config_content(name, path.read_text(encoding="utf-8"))
        assert config.session.enabled is True
        assert config.session.load_embeddings is False
        assert "session" in config.to_dict()


@pytest.mark.parametrize("entry_id", ["loop", "output"])
def test_replaceable_slots_are_declared_in_the_tree(entry_id: str) -> None:
    from internal.plugins.app import plugin_tree_path

    text = plugin_tree_path().read_text(encoding="utf-8")
    assert f"id: {entry_id}" in text
