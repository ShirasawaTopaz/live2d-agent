import os

import pytest

from internal.ui.input_box import FloatingInputBox, EXPANDED_MAX_HEIGHT


class DummyTextEdit:
    def __init__(self) -> None:
        self.placeholder = None

    def setPlaceholderText(self, text: str) -> None:
        self.placeholder = text

    def setFocus(self) -> None:
        pass


class DummyTitleBar:
    def __init__(self) -> None:
        self._current_mode = "chat"
        self.collapsed_input = DummyTextEdit()
        self._expanded = True

    def set_mode(self, mode_id: str) -> None:
        self._current_mode = mode_id

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded


class DummyInputBox:
    def __init__(self) -> None:
        self._is_expanded = False
        self._plan_mode_enabled = False
        self._orchestration_mode_enabled = False
        self.title_bar = DummyTitleBar()
        self.text_edit = DummyTextEdit()
        self._max_height = None
        self._min_height = None
        self._resized = None
        self._target_expanded_height = 180
        self._expand_animation = type("obj", (object,), {"stop": lambda s: None, "setStartValue": lambda s, v: None, "setEndValue": lambda s, v: None, "start": lambda s: None})()
        self._collapse_animation = type("obj", (object,), {"stop": lambda s: None, "setStartValue": lambda s, v: None, "setEndValue": lambda s, v: None, "start": lambda s: None, "finished": type("sig", (object,), {"connect": lambda s, c: None, "disconnect": lambda s, c: None})()})()
        self.content_widget = type("obj", (object,), {"show": lambda s: None, "hide": lambda s: None})()

    def setMinimumHeight(self, value: int) -> None:
        self._min_height = value

    def setMaximumHeight(self, value: int) -> None:
        self._max_height = value

    def resize(self, width: int, height: int) -> None:
        self._resized = (width, height)

    def width(self) -> int:
        return 400

    def height(self) -> int:
        return self._target_expanded_height


def test_expand_sets_maximum_height() -> None:
    box = DummyInputBox()

    FloatingInputBox.expand(box)

    assert box._max_height == EXPANDED_MAX_HEIGHT


def test_programmatic_mode_setters_update_state_and_placeholder() -> None:
    box = DummyInputBox()

    FloatingInputBox.set_plan_mode(box, True)
    assert box._plan_mode_enabled is True
    assert box.title_bar._current_mode == "plan"
    assert box.text_edit.placeholder.startswith("输入Plan模式指令")

    FloatingInputBox.set_orchestration_mode(box, True)
    assert box._orchestration_mode_enabled is True
    assert box.title_bar._current_mode == "orchestration"
    assert box.text_edit.placeholder.startswith("输入编排模式指令")


def test_on_mode_changed_sets_flags() -> None:
    box = DummyInputBox()

    FloatingInputBox.on_mode_changed(box, "plan")
    assert box._plan_mode_enabled is True
    assert box._orchestration_mode_enabled is False
    assert box.text_edit.placeholder.startswith("输入Plan模式指令")

    FloatingInputBox.on_mode_changed(box, "orchestration")
    assert box._plan_mode_enabled is False
    assert box._orchestration_mode_enabled is True
    assert box.text_edit.placeholder.startswith("输入编排模式指令")

    FloatingInputBox.on_mode_changed(box, "chat")
    assert box._plan_mode_enabled is False
    assert box._orchestration_mode_enabled is False
    assert "输入消息" in (box.text_edit.placeholder or "")


pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def qt_app():
    from PySide6.QtWidgets import QApplication
    import sys
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_input_box_has_image_support():
    assert hasattr(FloatingInputBox, "dragEnterEvent")
    assert hasattr(FloatingInputBox, "dropEvent")
    assert hasattr(FloatingInputBox, "_add_image_file")
    assert hasattr(FloatingInputBox, "cleanup_images")


def test_input_box_creates_image_preview_label(qt_app):
    box = FloatingInputBox()
    assert box._image_preview is not None


def test_input_box_handles_empty_cleanup(qt_app):
    box = FloatingInputBox()
    box.cleanup_images()
    assert len(box._image_files) == 0
