"""UI 样式定义 - 暗色/亮色主题"""

STYLES = {
    "dark": {
        "main": """
            QWidget {
                font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Microsoft YaHei", sans-serif;
                font-size: 13px;
            }

            /* 主窗口 */
            #floatingInputBox {
                background-color: #2d2d2d;
                border: 1px solid #505050;
                border-radius: 10px;
            }

            /* 标题栏 */
            #titleBar {
                background-color: #3d3d3d;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                border-bottom: 1px solid #505050;
            }

            #titleLabel {
                color: #ffffff;
                font-weight: 500;
                font-size: 14px;
            }

            /* 窗口按钮 */
            #windowBtn {
                background-color: transparent;
                border: none;
                color: #b0b0b0;
                font-size: 16px;
                font-weight: bold;
                border-radius: 4px;
                min-width: 24px;
                min-height: 24px;
            }

            #windowBtn:hover {
                background-color: #505050;
                color: #ffffff;
            }

            #closeBtn:hover {
                background-color: #e81123;
                color: #ffffff;
            }

            /* 文本输入框 */
            QTextEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #505050;
                border-radius: 6px;
                padding: 8px;
                selection-background-color: #4a9eff;
                line-height: 1.5;
            }

            QTextEdit:focus {
                border-color: #4a9eff;
            }

            QTextEdit::placeholder {
                color: #808080;
            }

            /* 按钮 */
            QPushButton {
                background-color: #4a9eff;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: 500;
            }

            QPushButton:hover {
                background-color: #357abd;
            }

            QPushButton:pressed {
                background-color: #2a5f8f;
            }

            QPushButton:disabled {
                background-color: #505050;
                color: #808080;
            }

            /* 工具按钮 */
            QPushButton#toolBtn {
                background-color: transparent;
                border: 1px solid #505050;
                color: #b0b0b0;
                padding: 4px 8px;
            }

            QPushButton#toolBtn:hover {
                background-color: #4a9eff;
                border-color: #4a9eff;
                color: #ffffff;
            }

            /* 标签 */
            QLabel {
                color: #b0b0b0;
            }

            QLabel#charCount {
                color: #808080;
                font-size: 11px;
            }

            /* 滚动条 */
            QScrollBar:vertical {
                background-color: #2d2d2d;
                width: 10px;
                border-radius: 5px;
            }

            QScrollBar::handle:vertical {
                background-color: #505050;
                border-radius: 5px;
                min-height: 20px;
            }

            QScrollBar::handle:vertical:hover {
                background-color: #606060;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }

            QScrollBar:horizontal {
                background-color: #2d2d2d;
                height: 10px;
                border-radius: 5px;
            }

            QScrollBar::handle:horizontal {
                background-color: #505050;
                border-radius: 5px;
                min-width: 20px;
            }

            QScrollBar::handle:horizontal:hover {
                background-color: #606060;
            }

            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                width: 0px;
            }
        """
    },
    "light": {
        "main": """
            QWidget {
                font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Microsoft YaHei", sans-serif;
                font-size: 13px;
            }

            /* 主窗口 */
            #floatingInputBox {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 10px;
            }

            /* 标题栏 */
            #titleBar {
                background-color: #f5f5f5;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                border-bottom: 1px solid #e0e0e0;
            }

            #titleLabel {
                color: #333333;
                font-weight: 500;
                font-size: 14px;
            }

            /* 窗口按钮 */
            #windowBtn {
                background-color: transparent;
                border: none;
                color: #666666;
                font-size: 16px;
                font-weight: bold;
                border-radius: 4px;
                min-width: 24px;
                min-height: 24px;
            }

            #windowBtn:hover {
                background-color: #e0e0e0;
                color: #333333;
            }

            #closeBtn:hover {
                background-color: #e81123;
                color: #ffffff;
            }

            /* 文本输入框 */
            QTextEdit {
                background-color: #ffffff;
                color: #333333;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                padding: 8px;
                selection-background-color: #0078d4;
                line-height: 1.5;
            }

            QTextEdit:focus {
                border-color: #0078d4;
            }

            QTextEdit::placeholder {
                color: #999999;
            }

            /* 按钮 */
            QPushButton {
                background-color: #0078d4;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: 500;
            }

            QPushButton:hover {
                background-color: #005a9e;
            }

            QPushButton:pressed {
                background-color: #004578;
            }

            QPushButton:disabled {
                background-color: #e0e0e0;
                color: #999999;
            }

            /* 工具按钮 */
            QPushButton#toolBtn {
                background-color: transparent;
                border: 1px solid #e0e0e0;
                color: #666666;
                padding: 4px 8px;
            }

            QPushButton#toolBtn:hover {
                background-color: #0078d4;
                border-color: #0078d4;
                color: #ffffff;
            }

            /* 标签 */
            QLabel {
                color: #666666;
            }

            QLabel#charCount {
                color: #999999;
                font-size: 11px;
            }

            /* 滚动条 */
            QScrollBar:vertical {
                background-color: #f5f5f5;
                width: 10px;
                border-radius: 5px;
            }

            QScrollBar::handle:vertical {
                background-color: #c0c0c0;
                border-radius: 5px;
                min-height: 20px;
            }

            QScrollBar::handle:vertical:hover {
                background-color: #a0a0a0;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }

            QScrollBar:horizontal {
                background-color: #f5f5f5;
                height: 10px;
                border-radius: 5px;
            }

            QScrollBar::handle:horizontal {
                background-color: #c0c0c0;
                border-radius: 5px;
                min-width: 20px;
            }

            QScrollBar::handle:horizontal:hover {
                background-color: #a0a0a0;
            }

            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                width: 0px;
            }
        """
    },
}


def get_styles(theme: str = "dark") -> dict:
    """获取指定主题的样式"""
    return STYLES.get(theme, STYLES["dark"])
