"""Core plugin: skill packages (``ctx.skills``).

Bundled ``skills/*/skill.yaml`` packages contribute prompt snippets and tool
definitions. Skills that ship a ``plugin.py`` (or a ``Service`` subclass) are
mounted as cordis child plugins, which is how AI-authored skills reload without
restarting the app.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from internal.cordis import LoaderEntry, Schema, Service

plugin_name = "skills"

module_schema = Schema.object(
    {
        "dirs": Schema.array(Schema.string()).default([]),
        "enabled": Schema.array(Schema.string()).default([]),
    }
)


@dataclass(slots=True)
class LoadedSkill:
    """Bookkeeping for one skill package on disk."""

    name: str
    path: Path
    kind: str
    entry: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SkillsService(Service):
    """Discovers skill packages and mounts plugin-backed skills."""

    inject = ["loader"]

    def __init__(self, ctx: Any, name: str = "skills") -> None:
        super().__init__(ctx, name)
        self.root_dir = Path(__file__).resolve().parents[3] / "skills"
        self.extra_dirs: list[str] = []
        self.enabled: list[str] = []
        self.loaded: dict[str, LoadedSkill] = {}
        self.prompts: dict[str, str] = {}

    def directories(self) -> list[Path]:
        found = [self.root_dir]
        for entry in self.extra_dirs:
            found.append(Path(os.path.expanduser(entry)))
        return [path for path in found if path.exists()]

    def discover(self) -> list[LoadedSkill]:
        skills: list[LoadedSkill] = []
        for directory in self.directories():
            for child in sorted(directory.iterdir()):
                manifest = child / "skill.yaml"
                if not manifest.is_file():
                    continue
                skills.append(LoadedSkill(name=child.name, path=child, kind=self._kind(child)))
        return skills

    @staticmethod
    def _kind(path: Path) -> str:
        if (path / "plugin.py").is_file():
            return "plugin"
        if (path / "skill.py").is_file():
            return "plugin"
        return "prompt"

    async def mount_all(self) -> list[str]:
        """Register prompts and mount plugin-backed skills as child fibers."""
        mounted: list[str] = []
        for skill in self.discover():
            self.loaded[skill.name] = skill
            self._load_prompt(skill)
            if skill.kind == "plugin" and self._selected(skill.name):
                await self._mount_plugin(skill)
            mounted.append(skill.name)
        return mounted

    def _selected(self, name: str) -> bool:
        return not self.enabled or name in self.enabled

    def _load_prompt(self, skill: LoadedSkill) -> None:
        prompts_dir = skill.path / "prompts"
        if not prompts_dir.is_dir():
            return
        chunks: list[str] = []
        for prompt_file in sorted(prompts_dir.glob("*.md")):
            try:
                chunks.append(prompt_file.read_text(encoding="utf-8"))
            except OSError:
                continue
        if chunks:
            self.prompts[skill.name] = "\n\n".join(chunks)

    async def _mount_plugin(self, skill: LoadedSkill) -> Any:
        loader = self.ctx.get("loader")
        module_path = skill.path / "plugin.py"
        if not module_path.is_file():
            return None
        entry = LoaderEntry(name=str(module_path), id=f"skill:{skill.name}", config={})
        if loader is not None:
            skill.entry = await loader.mount_entry(entry, self.ctx)
            return skill.entry
        return None

    def prompt_text(self) -> str:
        return "\n\n".join(self.prompts.values())


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    service = SkillsService(ctx, "skills")
    if isinstance(config, dict):
        service.extra_dirs = [str(item) for item in config.get("dirs") or []]
        service.enabled = [str(item) for item in config.get("enabled") or []]
    ctx.service("skills", service)
    ctx.spawn(service.mount_all())
