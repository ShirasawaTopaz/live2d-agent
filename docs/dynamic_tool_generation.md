# Agent 自我工具生成系统 - 开发者文档

## 概述

Agent 自我工具生成系统允许 AI Agent 根据自然语言描述动态创建新工具。这个系统包括：

1. **ToolGenerator** - 将自然语言转换为 Python Tool 类代码
2. **ToolCodeSandbox** - AST 静态安全分析检测危险操作
3. **DynamicToolStorage** - 持久化存储动态生成的工具
4. **版本管理** - 保存版本历史，支持回滚
5. **审计日志** - 记录所有操作用于安全审计
6. **元工具** - Agent 可以通过这些 meta 工具自我管理工具：
   - `generate_tool` - 生成新工具
   - `list_tools` - 列出所有工具
   - `delete_tool` - 删除动态工具
   - `rollback_tool` - 回滚到先前版本

## 架构

```
internal/agent/tool/
├── base.py                 # 基础 Tool 抽象类
├── dynamic/
│   ├── __init__.py         # 模块导出
│   ├── security.py         # 安全策略白名单/黑名单
│   ├── templates.py        # 代码模板系统
│   ├── sandbox.py         # AST 安全沙箱
│   ├── generator.py       # 工具代码生成器
│   ├── storage.py         # 持久化存储管理
│   ├── audit.py           # 审计日志系统
│   ├── versioning.py      # 版本管理
│   └── tools/             # 动态生成工具存储
│       ├── __init__.py
│       ├── .tools_index.json
│       └── versions/       # 版本历史
├── meta/
│   ├── __init__.py
│   ├── generate_tool.py   # generate_tool 元工具
│   ├── list_tools.py      # list_tools 元工具
│   ├── delete_tool.py     # delete_tool 元工具
│   └── rollback_tool.py   # rollback_tool 元工具
```

## 安全策略

### 允许的模块

只有以下标准库模块允许导入：

- `json` - JSON 处理
- `re` - 正则表达式
- `math` - 数学函数
- `random` - 随机数
- `datetime` - 日期时间
- `urllib.request` - HTTP 请求
- `urllib.parse` - URL 解析
- `hashlib` - 哈希函数
- `base64` - Base64 编码
- `collections` - 容器数据类型
- `itertools` - 迭代工具
- `functools` - 高阶函数

### 禁止的内置函数

这些函数永远不允许使用，因为它们可以执行任意代码：

- `eval` - 执行任意代码
- `exec` - 执行任意代码
- `__import__` - 动态导入禁止模块
- `open` - 文件系统访问
- `input` - 交互式输入
- `compile` - 动态编译代码
- `exit` / `quit` - 退出程序

### 禁止的模块

这些模块永远不允许导入，因为它们可以访问文件系统、网络、子进程：

- `os` - 操作系统接口
- `sys` - 系统参数
- `subprocess` - 子进程
- `socket` - 网络通信
- `requests` - HTTP 客户端
- `ftplib` - FTP
- `http.client` - HTTP 客户端
- `socketserver` - 网络服务器

## API 使用

### 基本使用示例

```python
from internal.agent.tool.dynamic.generator import ToolGenerator
from internal.agent.tool.dynamic.storage import DynamicToolStorage
from internal.agent.register import ToolRegistry

# 创建组件
generator = ToolGenerator()
storage = DynamicToolStorage()
registry = ToolRegistry()

# 生成工具代码
code = generator.generate(
    name="add_two_numbers",
    description="Add two numbers together",
    parameters={
        "type": "object",
        "properties": {
            "a": {"type": "number", "description": "First number"},
            "b": {"type": "number", "description": "Second number"},
        },
        "required": ["a", "b"],
    },
    implementation="    result = a + b\n    return result",
)

# 保存并注册
tool = registry.create_and_register_dynamic_tool(
    name="add_two_numbers",
    code=code,
    storage=storage,
)

# 现在可以使用了
result = await tool.execute(a=5, b=3)
# result = 8
```

### 通过 Agent 使用（元工具）

Agent 已经注册了以下 meta 工具：

1. **generate_tool** - 生成新工具

参数：
- `tool_name` (required): 工具名称，必须是有效的 snake_case Python 标识符
- `description` (required): 工具功能的自然语言描述
- `parameters` (optional): JSON Schema 参数定义
- `implementation` (optional): 自定义实现代码，如果提供则不自动生成
- `template` (optional, default: `simple`): 使用的模板，可选 `simple`/`http`/`calc`
- `extra_imports` (optional): 额外需要导入的允许模块列表

2. **list_tools** - 列出所有工具

参数：
- `include_dynamic` (default: `True`): 包含动态工具
- `include_builtin` (default: `True`): 包含内置工具
- `detailed` (default: `False`): 包含完整参数 schema

3. **delete_tool** - 删除动态工具

参数：
- `tool_name` (required): 要删除的工具名称
- `confirm` (default: `False`): 必须设置为 `True` 确认删除

4. **rollback_tool** - 回滚到先前版本

参数：
- `tool_name` (required): 工具名称
- `version` (optional): 版本号，如果不提供则列出可用版本
- `confirm` (default: `False`): 必须设置为 `True` 确认回滚

## 版本管理

每个动态工具自动保留版本历史：

- 首次创建 → 版本 `1.0.0`
- 每次修改 → 补丁版本自动递增 (`1.0.0` → `1.0.1` → `1.0.2`)
- 回滚 → 创建新版本，其代码等于回滚目标版本的代码

回滚后不会删除任何历史，旧版本仍然保留。

## 审计日志

默认启用审计日志，记录所有操作：

- 日志位置: `internal/agent/tool/dynamic/audit_logs/`
- 按日期分文件: `audit_YYYY-MM-DD.jsonl`
- 每一行是一个 JSON 事件

日志事件类型：

- `generation_request` - 工具生成请求
- `generation_complete` - 工具生成完成（包含完整代码）
- `registration` - 注册完成
- `deletion` - 删除工具
- `execution` - 执行动态工具
- `error` - 错误发生

## 限制

- **最大动态工具数量**: 默认 20 个。可以在 `DynamicToolStorage` 构造函数修改 `max_dynamic_tools` 参数
- 达到上限后必须删除一些工具才能创建新工具
- 每个工具代码都经过 AST 静态安全分析，不允许危险操作

## 扩展

### 添加新模板

在 `internal/agent/tool/dynamic/templates.py` 的 `IMPLEMENTATION_TEMPLATES` 字典添加新模板：

```python
IMPLEMENTATION_TEMPLATES = {
    # ... 现有模板
    "my_new_template": """    # Your template implementation here
    result = do_something(input)
    return result""",
}
```

### 调整安全策略

修改 `internal/agent/tool/dynamic/security.py`：

- `ALLOWED_MODULES` - 添加允许的模块
- `FORBIDDEN_BUILTINS` - 添加禁止的内置函数
- `FORBIDDEN_MODULES` - 添加禁止的模块

## 故障排查

### 生成失败常见原因

1. **名称无效** - 必须是有效的 Python 标识符（字母数字下划线，不能以数字开头）
2. **安全检查失败** - 包含禁止的导入或函数
3. **语法错误** - 生成的代码有语法错误
4. **达到上限** - 已经创建了太多动态工具，需要删除一些

### 回滚失败常见原因

1. **版本不存在** - 检查可用版本使用 `rollback_tool tool_name="X"`
2. **代码文件丢失** - 版本文件被删除

## 最佳实践

1. **每次生成后测试** - 生成工具后立即测试确保功能正确
2. **使用描述性名称** - 工具名称清晰表达功能
3. **不要绕过安全检查** - 永远不要手动修改安全策略允许危险操作
4. **定期清理** - 删除不再使用的工具保持在限制以下
5. **审计日志** - 定期检查审计日志了解生成了哪些工具
