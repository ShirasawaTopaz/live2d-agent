"""Regression tests for headless-safe imports."""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_bubble_timing_import_does_not_load_ui_input_box():
    sys.modules.pop("internal.agent.bubble_timing", None)
    sys.modules.pop("internal.agent.agent", None)
    sys.modules.pop("internal.agent", None)
    sys.modules.pop("internal.ui.input_box", None)
    sys.modules.pop("internal.ui", None)

    module = importlib.import_module("internal.agent.bubble_timing")

    assert module.__name__ == "internal.agent.bubble_timing"
    assert "internal.ui.input_box" not in sys.modules


def test_internal_agent_package_import_stays_headless_safe():
    sys.modules.pop("internal.agent", None)
    sys.modules.pop("internal.ui", None)
    sys.modules.pop("internal.ui.input_box", None)
    sys.modules.pop("PySide6", None)

    module = importlib.import_module("internal.agent")

    assert module.__name__ == "internal.agent"
    assert "internal.ui" not in sys.modules
    assert "internal.ui.input_box" not in sys.modules
    assert "PySide6" not in sys.modules


def test_internal_agent_register_import_stays_headless_safe():
    sys.modules.pop("internal.agent.register", None)
    sys.modules.pop("internal.agent", None)
    sys.modules.pop("internal.ui", None)
    sys.modules.pop("internal.ui.input_box", None)
    sys.modules.pop("PySide6", None)

    module = importlib.import_module("internal.agent.register")

    assert module.__name__ == "internal.agent.register"
    assert "internal.ui" not in sys.modules
    assert "internal.ui.input_box" not in sys.modules
    assert "PySide6" not in sys.modules
