"""Startup bridge used to expose Live2oderApp for smoke imports."""

from __future__ import annotations

import sys
from typing import Any


def export_live2oder_app_to_main() -> None:
    try:
        from internal.app.live2oder_app import Live2oderApp
    except Exception:
        return

    main_module: Any = sys.modules.get("__main__")
    if main_module is not None and not hasattr(main_module, "Live2oderApp"):
        main_module.Live2oderApp = Live2oderApp
