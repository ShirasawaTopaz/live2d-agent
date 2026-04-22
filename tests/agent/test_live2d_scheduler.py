import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from internal.agent.chat_service import (
    Live2DConflictController,
    Live2DExpressionPlan,
    Live2DExpressionScheduler,
)
from internal.config.config import Live2DExpressionsConfig


def test_live2d_scheduler_builds_deterministic_tool_call_sequence():
    scheduler = Live2DExpressionScheduler(
        Live2DConflictController(Live2DExpressionsConfig(cooldown_ms=1200)),
        Live2DExpressionsConfig(cooldown_ms=1200),
    )

    contract = {
        "main_emotion": "happy",
        "stage_sequence": [
            {
                "tool_calls": [
                    {"tool": "display_bubble_text", "text": "hello"},
                    {"tool": "set_expression", "expression_id": 7},
                    {"tool": "trigger_motion", "motion_name": "wave"},
                ]
            }
        ],
    }

    tool_calls = scheduler.build_tool_calls(contract)
    plan = scheduler.build_plan(contract, tool_calls)

    assert [call["function"]["name"] for call in tool_calls] == [
        "trigger_motion",
        "set_expression",
    ]
    assert isinstance(plan, Live2DExpressionPlan)
    assert plan.tool_calls == tool_calls
    assert plan.consumes_assistant_content is True
    assert plan.has_confirmation_blocker is True


def test_live2d_scheduler_preserves_stage_order_across_multiple_stages():
    scheduler = Live2DExpressionScheduler(
        Live2DConflictController(Live2DExpressionsConfig(cooldown_ms=1200)),
        Live2DExpressionsConfig(cooldown_ms=1200),
    )

    contract = {
        "main_emotion": "happy",
        "stage_sequence": [
            {"tool": "set_expression", "expression_id": 1},
            {"tool": "trigger_motion", "motion_name": "wave"},
        ],
    }

    tool_calls = scheduler.build_tool_calls(contract)

    assert [call["function"]["name"] for call in tool_calls] == [
        "set_expression",
        "trigger_motion",
    ]


def test_live2d_scheduler_falls_back_to_clear_expression_for_invalid_sequence():
    scheduler = Live2DExpressionScheduler(
        Live2DConflictController(Live2DExpressionsConfig(cooldown_ms=1200)),
        Live2DExpressionsConfig(cooldown_ms=1200, fallback_policy="neutral"),
    )

    tool_calls = scheduler.build_tool_calls({"main_emotion": "sad", "stage_sequence": []})
    plan = scheduler.build_plan({"main_emotion": "sad", "stage_sequence": []}, tool_calls)

    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "clear_expression"
    assert plan.tool_calls == tool_calls


def test_live2d_scheduler_falls_back_to_noop_when_configured():
    scheduler = Live2DExpressionScheduler(
        Live2DConflictController(Live2DExpressionsConfig(cooldown_ms=1200)),
        Live2DExpressionsConfig(cooldown_ms=1200, fallback_policy="no-op"),
    )

    tool_calls = scheduler.build_tool_calls({"main_emotion": "sad", "stage_sequence": []})
    plan = scheduler.build_plan({"main_emotion": "sad", "stage_sequence": []}, tool_calls)

    assert tool_calls == []
    assert plan.tool_calls == []
