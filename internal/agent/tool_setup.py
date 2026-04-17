from internal.agent.register import ToolRegistry
from internal.agent.sandbox import SandboxMiddleware
from internal.agent.tool.dynamic.storage import DynamicToolStorage
from internal.agent.tool.file import FileTool
from internal.agent.tool.live2d.clear_expression import ClearExpressionTool
from internal.agent.tool.live2d.display_bubble_text import DisplayBubbleTextTool
from internal.agent.tool.live2d.next_expression import NextExpressionTool
from internal.agent.tool.live2d.play_sound import PlaySoundTool
from internal.agent.tool.live2d.set_background import SetBackgroundTool
from internal.agent.tool.live2d.set_expression import SetExpressionTool
from internal.agent.tool.live2d.set_model import SetModelTool
from internal.agent.tool.live2d.trigger_motion import TriggerMotionTool
from internal.agent.tool.meta.delete_tool import DeleteToolTool
from internal.agent.tool.meta.generate_tool import GenerateToolTool
from internal.agent.tool.meta.list_tools import ListToolsTool
from internal.agent.tool.meta.rollback_tool import RollbackTool
from internal.agent.tool.office import OfficeTool
from internal.agent.tool.web_search import WebSearchTool


def register_default_tools(
    tool_registry: ToolRegistry,
    sandbox: SandboxMiddleware,
    dynamic_tool_storage: DynamicToolStorage,
) -> None:
    """Register the built-in tool set used by Agent."""
    tool_registry.register(DisplayBubbleTextTool())
    tool_registry.register(FileTool(sandbox))
    tool_registry.register(OfficeTool(sandbox))
    tool_registry.register(WebSearchTool(sandbox))
    tool_registry.register(TriggerMotionTool())
    tool_registry.register(SetExpressionTool())
    tool_registry.register(NextExpressionTool())
    tool_registry.register(ClearExpressionTool())
    tool_registry.register(SetBackgroundTool())
    tool_registry.register(SetModelTool())
    tool_registry.register(PlaySoundTool())
    tool_registry.register(GenerateToolTool(tool_registry, dynamic_tool_storage))
    tool_registry.register(ListToolsTool(tool_registry, dynamic_tool_storage))
    tool_registry.register(DeleteToolTool(tool_registry, dynamic_tool_storage))
    tool_registry.register(RollbackTool(tool_registry, dynamic_tool_storage))
