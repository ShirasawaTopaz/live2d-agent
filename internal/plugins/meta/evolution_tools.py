"""Tool plugins exposed by the self-evolution plugin."""

from __future__ import annotations

import json
from typing import Any

from internal.agent.tool.base import Tool
from internal.plugins.meta.self_evolution import EvolutionService

__all__ = ["build_tools", "register_evolution_tools"]


def _dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


class _EvolutionTool(Tool):
    """Base class wiring a tool to one evolution method."""

    method = ""
    tool_name = ""
    tool_description = ""

    def __init__(self, service: EvolutionService) -> None:
        self.service = service

    @property
    def name(self) -> str:
        return self.tool_name

    @property
    def description(self) -> str:
        return self.tool_description

    @property
    def parameters(self) -> dict:
        raise NotImplementedError

    def invoke(self, **kwargs: Any) -> Any:
        """Call the bound evolution method (sync or async result)."""
        method = getattr(self.service, self.method)
        return method(**kwargs)

    async def execute(self, **kwargs: Any) -> str:
        kwargs.pop("ws", None)
        kwargs.pop("bubble_widget", None)
        kwargs.pop("bubble_timing", None)
        result = self.invoke(**kwargs)
        if hasattr(result, "__await__"):
            result = await result
        return _dumps(result)


class PluginScaffoldTool(_EvolutionTool):
    method = "scaffold"
    tool_name = "plugin_scaffold"
    tool_description = (
        "为一个新 cordis 插件生成骨架代码（不写盘）。kind 可选 tool/service/loop/output/prompt；"
        "loop 用于替换 Agent 对话循环，output 用于替换滚动字输出模块。"
    )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "插件名（lower_snake_case）"},
                "kind": {"type": "string", "enum": ["tool", "service", "loop", "output", "prompt"]},
                "description": {"type": "string", "description": "插件用途说明"},
                "service": {"type": "string", "description": "可选：注册的服务名"},
            },
            "required": ["name"],
        }


class PluginInstallTool(_EvolutionTool):
    method = "install"
    tool_name = "plugin_install"
    tool_description = (
        "安装（或改写）cordis 插件源码：AST 安全校验 → 版本快照 → 写入用户插件目录 → "
        "在插件树追加条目 → 挂载生效。写入核心目录需显式开启并审批。"
    )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "code": {"type": "string", "description": "完整插件源码（需含 apply(ctx, config)）"},
                "kind": {"type": "string"},
                "config": {"type": "object", "description": "插件 config 段"},
                "mount": {"type": "boolean", "description": "是否立即挂载，默认 true"},
            },
            "required": ["name", "code"],
        }


class PluginReloadTool(_EvolutionTool):
    method = "reload"
    tool_name = "plugin_reload"
    tool_description = "热重载插件树中的一个条目（卸载旧 fiber 后按新代码重新挂载）。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {"entry_id": {"type": "string", "description": "如 user:my_plugin"}},
            "required": ["entry_id"],
        }


class PluginRollbackTool(_EvolutionTool):
    method = "rollback"
    tool_name = "plugin_rollback"
    tool_description = "把插件回滚到某个历史版本（不传 version 则回到上一个版本）并重新挂载。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "version": {"type": "string", "description": "如 1.0.0；省略则回到上一版"},
            },
            "required": ["name"],
        }


class PluginToggleTool(_EvolutionTool):
    tool_name = "plugin_toggle"
    tool_description = "启用或禁用一个插件条目（禁止会卸载 fiber，启用会重新挂载）。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "entry_id": {"type": "string"},
                "enabled": {"type": "boolean"},
            },
            "required": ["entry_id", "enabled"],
        }

    def invoke(self, **kwargs: Any) -> Any:
        return self.service.set_enabled(kwargs["entry_id"], kwargs["enabled"])


class PluginStatusTool(_EvolutionTool):
    method = "status"
    tool_name = "plugin_status"
    tool_description = "查看插件树状态：fiber 状态机、已注册服务、已安装的自进化插件与当前 rev。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {"entry_id": {"type": "string", "description": "可选：只看某个条目"}},
        }


class PluginDiagnoseTool(_EvolutionTool):
    method = "diagnose"
    tool_name = "plugin_diagnose"
    tool_description = "诊断所有非 ACTIVE 的插件：处于 PENDING 说明缺少 inject 的服务。"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}


class PluginAuditTool(_EvolutionTool):
    method = "audit"
    tool_name = "plugin_audit"
    tool_description = "读取插件自进化审计日志（安装/重载/回滚/拒绝等事件）。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "可选：install/reload/rollback/..."},
                "limit": {"type": "integer"},
            },
        }


TOOL_CLASSES = (
    PluginScaffoldTool,
    PluginInstallTool,
    PluginReloadTool,
    PluginRollbackTool,
    PluginToggleTool,
    PluginStatusTool,
    PluginDiagnoseTool,
    PluginAuditTool,
)


def build_tools(service: EvolutionService) -> list[Tool]:
    return [tool_class(service) for tool_class in TOOL_CLASSES]


def register_evolution_tools(service: EvolutionService, owner: Any = None) -> int:
    """Register every evolution tool through the tools plugin as an effect."""
    tools = service.ctx.get("tools")
    if tools is None:
        return 0
    for tool in build_tools(service):
        tools.register(tool, owner=owner if owner is not None else service.ctx)
    return len(TOOL_CLASSES)
