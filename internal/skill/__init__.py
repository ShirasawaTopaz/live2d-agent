"""Skill system for Live2oder.

A Skill is a functional unit that bundles related Tools and Prompts
to provide cohesive capabilities to the AI Agent.
"""

from .base import (
    Skill,
    SkillMetadata,
    SkillPrompt,
    SkillTool,
)
from .registry import SkillRegistry
from .manager import SkillManager
from .external import ExternalSkill
from .integration import SkillSystemIntegration, integrate_skill_system
from .dynamic_loader import (
    DynamicSkillLoader,
    SkillDirectoryWatcher,
    PollingSkillWatcher,
    HotReloadManager,
    SkillReloader,
)

__all__ = [
    # Base classes
    "Skill",
    "SkillMetadata",
    "SkillPrompt",
    "SkillTool",
    # Registry
    "SkillRegistry",
    # Manager
    "SkillManager",
    # External
    "ExternalSkill",
    # Integration
    "SkillSystemIntegration",
    "integrate_skill_system",
    # Dynamic loading
    "DynamicSkillLoader",
    "SkillDirectoryWatcher",
    "PollingSkillWatcher",
    "HotReloadManager",
    "SkillReloader",
]
