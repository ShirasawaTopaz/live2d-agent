from types import SimpleNamespace

from internal.ui.input_box import FloatingInputBox


class DummyButton:
    def __init__(self) -> None:
        self.checked = None

    def setChecked(self, enabled: bool) -> None:
        self.checked = enabled


class DummyTextEdit:
    def __init__(self) -> None:
        self.placeholder = None

    def setPlaceholderText(self, text: str) -> None:
        self.placeholder = text


class DummyInputBox:
    EXPANDED_MAX_HEIGHT = FloatingInputBox.EXPANDED_MAX_HEIGHT

    def __init__(self) -> None:
        self._is_expanded = False
        self._plan_mode_enabled = False
        self._orchestration_mode_enabled = False
        self.plan_mode_checkbox = DummyButton()
        self.orchestration_mode_checkbox = DummyButton()
        self.text_edit = DummyTextEdit()
        self._max_height = None
        self._min_height = None
        self._resized = None
        self.content_widget = SimpleNamespace(show=lambda: None)

    def setMinimumHeight(self, value: int) -> None:
        self._min_height = value

    def setMaximumHeight(self, value: int) -> None:
        self._max_height = value

    def resize(self, width: int, height: int) -> None:
        self._resized = (width, height)

    def width(self) -> int:
        return 400

    def on_plan_mode_toggled(self, checked: bool) -> None:
        self._plan_mode_enabled = checked
        if checked:
            self.text_edit.setPlaceholderText("输入Plan模式指令... (Shift+Enter 换行, Ctrl+Enter 发送)")
        elif not self._orchestration_mode_enabled:
            self.text_edit.setPlaceholderText("输入消息... (Shift+Enter 换行, Ctrl+Enter 发送)")

    def on_orchestration_mode_toggled(self, checked: bool) -> None:
        self._orchestration_mode_enabled = checked
        if checked:
            self.text_edit.setPlaceholderText("输入编排模式指令... (Shift+Enter 换行, Ctrl+Enter 发送)")
        elif not self._plan_mode_enabled:
            self.text_edit.setPlaceholderText("输入消息... (Shift+Enter 换行, Ctrl+Enter 发送)")


def test_expand_clears_maximum_height_cap() -> None:
    box = DummyInputBox()

    FloatingInputBox.expand(box)

    assert box._max_height == FloatingInputBox.EXPANDED_MAX_HEIGHT
    assert box._min_height == 140
    assert box._resized == (400, 180)


def test_programmatic_mode_setters_update_state_and_placeholder() -> None:
    box = DummyInputBox()

    FloatingInputBox.set_plan_mode(box, True)
    assert box._plan_mode_enabled is True
    assert box.plan_mode_checkbox.checked is True
    assert box.text_edit.placeholder.startswith("输入Plan模式指令")

    FloatingInputBox.set_orchestration_mode(box, True)
    assert box._orchestration_mode_enabled is True
    assert box.orchestration_mode_checkbox.checked is True
    assert box.text_edit.placeholder.startswith("输入编排模式指令")
