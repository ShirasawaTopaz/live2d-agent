"""工具代码模板系统

提供工具类代码的模板和渲染功能。
"""

from string import Template


def to_pascal_case(snake_str: str) -> str:
    """将snake_case转换为PascalCase

    Example:
        >>> to_pascal_case("my_tool")
        'MyTool'
    """
    return "".join(word.capitalize() for word in snake_str.split("_"))


def to_snake_case(pascal_str: str) -> str:
    """将PascalCase转换为snake_case

    Example:
        >>> to_snake_case("MyTool")
        'my_tool'
        >>> to_snake_case("HTTPRequestTool")
        'http_request_tool'
    """
    import re
    # Add underscore before capital letters, then lowercase everything
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', pascal_str)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


# 基础工具类模板
TOOL_CLASS_TEMPLATE = Template('''
# Auto-generated Tool: $tool_name
# Generated at: $timestamp
# This file is auto-generated. Do not edit manually.

from internal.agent.tool.base import Tool, ToolResult
from typing import Any$imports


class $class_name(Tool):
    """$description"""
    
    @property
    def name(self) -> str:
        return "$tool_name"
    
    @property
    def description(self) -> str:
        return """$description"""
    
    @property
    def parameters(self) -> dict:
        return $parameters_schema
    
    async def execute(self, **kwargs) -> ToolResult:
        try:
            # Unpack parameters into local scope for easy access by name
$unpacking_code
$implementation
            result = result
            
            return ToolResult(
                name=self.name,
                success=True,
                result=result,
                error=None
            )
        except Exception as e:
            return ToolResult(
                name=self.name,
                success=False,
                result=None,
                error=str(e)
            )
''')


# 简单实现模板
SIMPLE_IMPLEMENTATION_TEMPLATE = """
            # 实现逻辑
            result = f"Processed: {kwargs}"
"""

# HTTP请求实现模板
HTTP_IMPLEMENTATION_TEMPLATE = """
            import urllib.request
            import json
            
            url = kwargs.get("url")
            method = kwargs.get("method", "GET")
            headers = kwargs.get("headers", {})
            data = kwargs.get("data")
            
            req = urllib.request.Request(url, method=method)
            
            for key, value in headers.items():
                req.add_header(key, value)
            
            if data and isinstance(data, dict):
                req.data = json.dumps(data).encode('utf-8')
                req.add_header('Content-Type', 'application/json')
            
            with urllib.request.urlopen(req, timeout=30) as response:
                result = {
                    "status": response.status,
                    "body": response.read().decode('utf-8')
                }
"""

# 计算实现模板
CALC_IMPLEMENTATION_TEMPLATE = """
            expression = kwargs.get("expression", "")
            
            # 安全的数学运算环境
            safe_dict = {
                "abs": abs,
                "max": max,
                "min": min,
                "sum": sum,
                "pow": pow,
                "round": round,
                "int": int,
                "float": float,
                "len": len,
            }
            
            result = eval(expression, {"__builtins__": {}}, safe_dict)
"""


def render_tool_class(
    tool_name: str,
    class_name: str,
    description: str,
    parameters_schema: str,
    implementation: str,
    imports: str = "",
    timestamp: str | None = None,
) -> str:
    """渲染完整的工具类代码

    Args:
        tool_name: 工具名称 (snake_case)
        class_name: 类名 (PascalCase)
        description: 工具描述
        parameters_schema: JSON Schema参数字符串
        implementation: 实现代码
        imports: 额外导入语句
        timestamp: 生成时间戳

    Returns:
        完整的Python代码字符串
    """
    import textwrap
    if timestamp is None:
        from datetime import datetime

        timestamp = datetime.now().isoformat()

    # Dedent first to remove any leading indentation then add correct indentation
    # 16 spaces = 4 for execute + 4 for try + 4 for def user_code + 4 for the actual content
    dedented = textwrap.dedent(implementation)
    lines = dedented.strip().split("\n")
    indented_impl = "\n".join(
        f"                {line}" if line.strip() else line for line in lines
    )

    return TOOL_CLASS_TEMPLATE.substitute(
        tool_name=tool_name,
        class_name=class_name,
        description=description,
        parameters_schema=parameters_schema,
        implementation=indented_impl,
        imports=imports,
        timestamp=timestamp,
    )


# 模板注册表
IMPLEMENTATION_TEMPLATES = {
    "simple": SIMPLE_IMPLEMENTATION_TEMPLATE,
    "http": HTTP_IMPLEMENTATION_TEMPLATE,
    "calc": CALC_IMPLEMENTATION_TEMPLATE,
}


def get_template(name: str) -> str:
    """获取实现模板"""
    return IMPLEMENTATION_TEMPLATES.get(name, SIMPLE_IMPLEMENTATION_TEMPLATE)
