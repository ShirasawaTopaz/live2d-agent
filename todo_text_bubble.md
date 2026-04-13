# 实现方案：Qt 本地悬浮气泡窗口（推荐）

## Context

用户需求：
- 在屏幕中央靠下位置显示 AI 回复文字（类似浮动歌词位置）
- 需要支持**流式输出**（逐字实时显示）
- 显示一定时间后自动消失
- **完全不依赖 Live2DViewerEx 内置气泡功能**，完全由 Qt 本地绘制
- 支持 Markdown 格式直接显示

为什么改用 Qt 方案：
- 项目已有 PySide6 Qt 框架和悬浮输入框，可直接复用
- 完全控制样式、位置、动画，不需要依赖 Live2D 模型做背景
- 原生支持流式输出，不需要重复加载模型
- 实现更简单，性能更好

## 实现方案

### 核心思路

1. **新增 `BubbleWidget`**：在 Qt 中创建一个独立的悬浮气泡窗口
2. **始终置顶**：和输入框一样使用 `WindowStaysOnTopHint`
3. **无边框透明背景**：只有圆角气泡框和文字，没有标题栏
4. **初始位置**：屏幕中央靠下（类似浮动歌词）
5. **支持流式输出**：提供 `append_text()` 方法，支持逐字追加
6. **自动消失**：显示指定毫秒后自动淡出并隐藏
7. **支持 Markdown**：直接显示 Markdown 原文，保持格式可读性

### 1. 新增文件：`internal/ui/bubble_widget.py`

**类名**：`BubbleWidget` 继承 `QWidget`

**特性**：
- 无边框窗口，始终置顶
- 半透明背景，圆角气泡框
- 文字自动换行，左对齐
- 支持流式追加文字
- 显示 duration 毫秒后自动淡出消失
- 可拖动调整位置
- 透明背景支持鼠标穿透（可选）
- 使用等宽字体显示，保持 Markdown 格式对齐

**公开方法**：
```python
class BubbleWidget(QWidget):
    def __init__(self, parent=None):
    def set_text(self, text: str): ...        # 设置完整文字
    def append_text(self, text: str): ...    # 追加文字（流式用）
    def clear(self): ...                      # 清空内容
    def show_with_duration(self, duration_ms: int = 10000): ...  # 显示并定时消失
    def fade_out_and_hide(self): ...  # 淡出隐藏
```

### 2. 修改现有文件：`internal/ui/__init__.py`

- 导出 `BubbleWidget`

### 3. 修改现有文件：`__main__.py`

- 在 `Live2oderApp` 中添加 `bubble_widget: BubbleWidget | None` 成员
- 在 `initialize()` 中创建 `BubbleWidget` 实例
- 在 `cleanup()` 中正确销毁

### 4. 修改现有文件：`internal/agent/agent.py`

在 `_try_parse_and_send_bubble()` 方法中：
- 如果 `bubble_widget` 存在，使用 Qt 气泡显示
- 否则 fallback 到原来的 WebSocket 方式
- 流式响应支持：在流式输出循环中逐字调用 `append_text()`
- 直接输出原始 Markdown，保持格式不变

### 5. 样式设计

- **背景**：半透明磨砂效果（`WA_TranslucentBackground` + `setWindowOpacity`）
- **气泡框**：圆角矩形，浅色半透明背景
- **文字**：黑色/白色根据主题，自动换行，居中对齐。流式输出时靠左对齐，并且启动换行，被换的那一行颜色变淡，上两行自动消失
- **字体**：等宽字体（如 Consolas 或系统默认等宽字体），保持 `代码块` 对齐
- **大小**：自动适应文字内容，最大宽度限制，超出自动换行
- **位置**：默认屏幕水平居中，垂直靠下（Y = 屏幕高度 - 200），支持拖动保存位置

### 6. 流式输出集成

复用现有流式输出机制 (`agent.py:98-121`):
- 在流式循环中，每得到一个 chunk 就调用 `bubble_widget.append_text()`
- Qt 自动重绘，实现逐字实时显示
- 流式完成后，启动定时器，duration 到了自动消失

### 7. 自动消失

- `show_with_duration()` 调用 `QTimer.singleShot(duration_ms, self.fade_out_and_hide)`
- 淡出动画：使用 `QPropertyAnimation` 渐变透明度到 0，然后 hide()

### 目录结构

```
internal/ui/
├── __init__.py          # 更新，导出 BubbleWidget
├── bubble_widget.py     # 新增：悬浮气泡组件
├── input_box.py         # 现有：悬浮输入框
├── title_bar.py         # 现有：标题栏（可复用拖动逻辑）
├── styles.py            # 现有：样式
├── history_manager.py   # 现有：历史记录
└── styles.py            # 现有：主题样式
```

### 对话流程

1. **初始化**：程序启动 → 创建悬浮输入框 → 创建气泡窗口 → 气泡窗口默认隐藏
2. **用户输入** → AI 流式响应 → 每块文字调用 `append_text()` → 气泡逐字显示
3. **流式完成** → 定时器启动 → 等待 duration → 淡出消失
4. **下一轮回复** → 清空文字重新显示
5. **如果输出文本多，要多轮输出** -> 尽量一次输出不超过20个字词

### 优点对比

| 特性 | Qt 本地方案 | Live2D 背景方案 |
|------|-------------|-----------------|
| 流式输出 | ✅ 原生支持，流畅 | ⚠️ 可行但需要重复加载模型 |
| Markdown 支持 | ✅ 直接显示原文，等宽字体对齐 | ⚠️ 几乎不支持，只能纯文本 |
| 实现难度 | ✅ 简单，复用现有框架 | ⚠️ 复杂 |
| 性能 | ✅ 好，无额外加载 | ⚠️ 每次回复重新加载模型 |
| 样式控制 | ✅ 完全控制 | ⚠️ 受限于 Live2D 模型 |
| 自动消失 | ✅ 容易实现 | ✅ 可行 |
| 依赖 | ✅ 项目已有 Qt | 需要 bubble_text 模型 |

### 验证测试

1. 启动程序，验证：
   - ✅ 悬浮输入框正常显示
   - ✅ 气泡窗口正确创建，默认隐藏
   - ✅ 发送消息后，AI 流式回复，气泡逐字显示在底部
   - ✅ 气泡背景半透明圆角，文字正确换行
   - ✅ Markdown 格式保持可读性（`代码块`、**粗体**、列表缩进都能看清）
   - ✅ 显示指定时间后自动淡出消失
   - ✅ 可以拖动气泡到其他位置，重启后保存位置
   - ✅ 下一次回复正常重新显示
   - ✅ 能够完全替代现有的display_bubble_text使用
