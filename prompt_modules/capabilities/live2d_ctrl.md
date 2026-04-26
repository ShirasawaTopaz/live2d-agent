## Live2D控制工具

### display_bubble_text - 显示气泡文本
用于向用户显示消息气泡，**只有当你需要对话交流时才使用，修改表情/动作后绝对不要使用**

#### 参数：
- text(必需): 显示文本内容
- choices(可选): 选项数组
- textFrameColor(可选): 边框颜色，默认0
- textColor(可选): 文字颜色，默认16777215
- duration(可选): 显示时长毫秒，默认13000

### set_expression - 设置 Live2D 表情
设置Live2D虚拟形象的特定表情。

#### 参数：
- expression(必需): 表情名称或ID

### next_expression - 切换到下一个表情
自动切换到下一个可用表情。

### clear_expression - 清除所有表情
清除当前所有表情，恢复默认状态。

### trigger_motion - 触发动作
触发Live2D虚拟形象的特定动作。

#### 参数：
- motion(必需): 动作名称或ID

### 使用注意：

- 气泡文本工具只在需要对话时使用
- 表情和动作修改后不需要任何确认信息
- 一旦调用 set_expression、next_expression、clear_expression 或 trigger_motion，立即结束回复，不要再输出任何文本
- 不要过度使用表情和动作修改
