import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from internal.agent.sandbox import default_sandbox
from internal.agent.tool.dynamic.storage import DynamicToolStorage
from internal.agent.tool_setup import register_default_tools
from internal.agent.register import ToolRegistry


def test_register_default_tools_populates_registry_and_definitions(tmp_path):
    registry = ToolRegistry()
    storage = DynamicToolStorage(storage_path=str(tmp_path / "dynamic_tools"))

    register_default_tools(registry, default_sandbox, storage)

    expected_names = {
        "display_bubble_text",
        "file",
        "office",
        "web_search",
        "trigger_motion",
        "set_expression",
        "next_expression",
        "clear_expression",
        "set_background",
        "set_model",
        "play_sound",
        "generate_tool",
        "list_tools",
        "delete_tool",
        "rollback_tool",
    }

    assert registry.is_none is False
    assert expected_names.issubset(registry.tools.keys())

    definition_names = {
        definition["function"]["name"] for definition in registry.get_definitions()
    }
    assert expected_names.issubset(definition_names)
