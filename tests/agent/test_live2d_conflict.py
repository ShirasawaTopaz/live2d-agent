import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from internal.agent.chat_service import Live2DConflictController
from internal.config.config import Live2DExpressionsConfig


def test_live2d_conflict_orders_live2d_tools_deterministically():
    controller = Live2DConflictController(
        Live2DExpressionsConfig(cooldown_ms=1200)
    )

    tool_calls = [
        {"function": {"name": "display_bubble_text"}},
        {"function": {"name": "set_expression"}},
        {"function": {"name": "trigger_motion"}},
        {"function": {"name": "clear_expression"}},
    ]

    ordered = controller.order_tool_calls(tool_calls)

    assert [call[1]["function"]["name"] for call in ordered] == [
        "trigger_motion",
        "set_expression",
        "clear_expression",
        "display_bubble_text",
    ]


def test_live2d_conflict_orders_set_expression_before_next_expression():
    controller = Live2DConflictController(
        Live2DExpressionsConfig(cooldown_ms=1200)
    )

    tool_calls = [
        {"function": {"name": "next_expression"}},
        {"function": {"name": "set_expression"}},
    ]

    ordered = controller.order_tool_calls(tool_calls)

    assert [call[1]["function"]["name"] for call in ordered] == [
        "set_expression",
        "next_expression",
    ]


def test_live2d_conflict_suppresses_confirmation_bubble_after_expression_change():
    times = [100.0]

    def now() -> float:
        return times[0]

    controller = Live2DConflictController(
        Live2DExpressionsConfig(cooldown_ms=1200)
    )
    controller.set_time_provider(now)

    controller.begin_turn()
    controller.note_tool_execution("set_expression")

    assert controller.should_suppress_confirmation_bubble() is True
    assert controller.should_skip_bubble_tool("display_bubble_text") is True


def test_live2d_conflict_allows_bubble_after_cooldown_expires():
    times = [100.0]

    def now() -> float:
        return times[0]

    controller = Live2DConflictController(
        Live2DExpressionsConfig(cooldown_ms=1200)
    )
    controller.set_time_provider(now)

    controller.begin_turn()
    controller.note_tool_execution("trigger_motion")
    assert controller.should_suppress_confirmation_bubble() is True

    times[0] = 102.0
    controller.begin_turn()

    assert controller.should_suppress_confirmation_bubble() is False


def test_live2d_conflict_reports_non_blocker_tools_as_visible():
    controller = Live2DConflictController(Live2DExpressionsConfig(cooldown_ms=1200))

    assert controller.should_skip_bubble_tool("display_bubble_text") is False
