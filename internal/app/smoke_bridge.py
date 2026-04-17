"""Startup bridge used to expose Live2DAgentApp for smoke imports."""

from __future__ import annotations

import sys
from typing import Any


def export_live2d_agent_app_to_main() -> None:
    try:
        from internal.app.live2d_agent_app import Live2DAgentApp
    except Exception:
        return

    main_module: Any = sys.modules.get("__main__")
    if main_module is not None and not hasattr(main_module, "Live2DAgentApp"):
        main_module.Live2DAgentApp = Live2DAgentApp
