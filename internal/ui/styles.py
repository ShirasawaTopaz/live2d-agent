"""UI 样式定义 - 暗色/亮色主题"""

STYLES = {
    "dark": {
        "main": """
            QWidget {
                font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Microsoft YaHei", sans-serif;
                font-size: 13px;
            }

            #floatingInputBox {
                background-color: #1a1a1a;
                border: 1px solid #333333;
                border-radius: 10px;
            }

            /* Title bar - expanded */
            #titleBar {
                background-color: #242424;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                border-bottom: 1px solid #333333;
            }

            #titleBar[state="collapsed"] {
                background-color: #1a1a1a;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                border-bottom: none;
            }

            #modeTab {
                background-color: #1e1e1e;
                border-radius: 6px;
                padding: 2px;
            }

            QPushButton#modeTabBtn {
                background-color: transparent;
                color: #666666;
                border: none;
                border-radius: 4px;
                padding: 3px 12px;
                font-size: 11px;
                font-weight: 500;
            }

            QPushButton#modeTabBtn:hover {
                color: #999999;
            }

            QPushButton#modeTabBtn:checked {
                background-color: #0066cc;
                color: #ffffff;
            }

            #titleLabel {
                color: #888888;
                font-weight: 500;
                font-size: 11px;
                letter-spacing: 0.5px;
            }

            #windowBtn {
                background-color: transparent;
                border: none;
                color: #666666;
                font-size: 12px;
                border-radius: 4px;
                min-width: 24px;
                min-height: 24px;
            }

            #windowBtn:hover {
                background-color: #333333;
                color: #cccccc;
            }

            #closeBtn:hover {
                background-color: #e81123;
                color: #ffffff;
            }

            /* Content area */
            #contentWidget {
                background-color: #1a1a1a;
                border-bottom-left-radius: 10px;
                border-bottom-right-radius: 10px;
            }

            /* Text input */
            QTextEdit {
                background-color: #1e1e1e;
                color: #dddddd;
                border: 1px solid #333333;
                border-radius: 8px;
                padding: 8px 10px;
                selection-background-color: #0066cc;
                font-size: 12px;
                line-height: 1.5;
            }

            QTextEdit:focus {
                border-color: #0066cc;
            }

            QTextEdit::placeholder {
                color: #555555;
            }

            /* Tool buttons (icon + text hybrid) */
            QPushButton#toolBtn {
                background-color: transparent;
                border: none;
                border-radius: 4px;
                color: #999999;
                padding: 3px 10px;
                font-size: 11px;
                text-align: left;
            }

            QPushButton#toolBtn:hover {
                background-color: #2a2a2a;
                color: #cccccc;
            }

            QPushButton#toolBtn:pressed {
                background-color: #333333;
            }

            /* Send button */
            QPushButton#sendBtn {
                background-color: #0066cc;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 5px 16px;
                font-size: 12px;
                font-weight: 500;
            }

            QPushButton#sendBtn:hover {
                background-color: #0055aa;
            }

            QPushButton#sendBtn:pressed {
                background-color: #004488;
            }

            QPushButton#sendBtn:disabled {
                background-color: #333333;
                color: #555555;
            }

            /* Char count label */
            QLabel#charCount {
                color: #555555;
                font-size: 10px;
            }

            /* Image preview */
            #imagePreview {
                background-color: #1e1e1e;
                border: 1px dashed #333333;
                border-radius: 6px;
                padding: 4px;
            }

            /* Collapsed bar mini input */
            QLineEdit#collapsedInput {
                background-color: transparent;
                border: none;
                color: #555555;
                font-size: 11px;
                padding: 0;
            }

            QLineEdit#collapsedInput:focus {
                color: #dddddd;
            }

            /* Scrollbar */
            QScrollBar:vertical {
                background-color: #1a1a1a;
                width: 8px;
                border-radius: 4px;
            }

            QScrollBar::handle:vertical {
                background-color: #444444;
                border-radius: 4px;
                min-height: 20px;
            }

            QScrollBar::handle:vertical:hover {
                background-color: #555555;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }

            QScrollBar:horizontal {
                background-color: #1a1a1a;
                height: 8px;
                border-radius: 4px;
            }

            QScrollBar::handle:horizontal {
                background-color: #444444;
                border-radius: 4px;
                min-width: 20px;
            }

            QScrollBar::handle:horizontal:hover {
                background-color: #555555;
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

            #floatingInputBox {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 10px;
            }

            /* Title bar - expanded */
            #titleBar {
                background-color: #f5f5f5;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                border-bottom: 1px solid #e0e0e0;
            }

            #titleBar[state="collapsed"] {
                background-color: #ffffff;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                border-bottom: none;
            }

            #modeTab {
                background-color: #e8e8e8;
                border-radius: 6px;
                padding: 2px;
            }

            QPushButton#modeTabBtn {
                background-color: transparent;
                color: #999999;
                border: none;
                border-radius: 4px;
                padding: 3px 12px;
                font-size: 11px;
                font-weight: 500;
            }

            QPushButton#modeTabBtn:hover {
                color: #666666;
            }

            QPushButton#modeTabBtn:checked {
                background-color: #0078d4;
                color: #ffffff;
            }

            #titleLabel {
                color: #999999;
                font-weight: 500;
                font-size: 11px;
                letter-spacing: 0.5px;
            }

            #windowBtn {
                background-color: transparent;
                border: none;
                color: #999999;
                font-size: 12px;
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

            #contentWidget {
                background-color: #ffffff;
                border-bottom-left-radius: 10px;
                border-bottom-right-radius: 10px;
            }

            QTextEdit {
                background-color: #ffffff;
                color: #333333;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 8px 10px;
                selection-background-color: #0078d4;
                font-size: 12px;
                line-height: 1.5;
            }

            QTextEdit:focus {
                border-color: #0078d4;
            }

            QTextEdit::placeholder {
                color: #999999;
            }

            QPushButton#toolBtn {
                background-color: transparent;
                border: none;
                border-radius: 4px;
                color: #666666;
                padding: 3px 10px;
                font-size: 11px;
                text-align: left;
            }

            QPushButton#toolBtn:hover {
                background-color: #f0f0f0;
                color: #333333;
            }

            QPushButton#toolBtn:pressed {
                background-color: #e0e0e0;
            }

            QPushButton#sendBtn {
                background-color: #0078d4;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 5px 16px;
                font-size: 12px;
                font-weight: 500;
            }

            QPushButton#sendBtn:hover {
                background-color: #005a9e;
            }

            QPushButton#sendBtn:pressed {
                background-color: #004488;
            }

            QPushButton#sendBtn:disabled {
                background-color: #e0e0e0;
                color: #999999;
            }

            QLabel#charCount {
                color: #999999;
                font-size: 10px;
            }

            #imagePreview {
                background-color: #f9f9f9;
                border: 1px dashed #e0e0e0;
                border-radius: 6px;
                padding: 4px;
            }

            QLineEdit#collapsedInput {
                background-color: transparent;
                border: none;
                color: #999999;
                font-size: 11px;
                padding: 0;
            }

            QLineEdit#collapsedInput:focus {
                color: #333333;
            }

            QScrollBar:vertical {
                background-color: #f5f5f5;
                width: 8px;
                border-radius: 4px;
            }

            QScrollBar::handle:vertical {
                background-color: #c0c0c0;
                border-radius: 4px;
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
                height: 8px;
                border-radius: 4px;
            }

            QScrollBar::handle:horizontal {
                background-color: #c0c0c0;
                border-radius: 4px;
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
