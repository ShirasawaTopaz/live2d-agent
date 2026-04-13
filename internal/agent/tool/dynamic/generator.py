"""工具代码生成器模块

将自然语言描述转换为符合安全规范的Python Tool类代码。
"""

import json
from typing import Dict, Optional
from datetime import datetime

from internal.agent.tool.dynamic.templates import (
    to_pascal_case,
    render_tool_class,
    get_template,
)
from internal.agent.tool.dynamic.sandbox import ToolCodeSandbox


class ToolGenerationError(Exception):
    """工具代码生成错误"""

    pass


class ToolGenerator:
    """工具代码生成器

    将自然语言描述转换为符合安全规范的Python Tool类代码。

    使用方法：
        generator = ToolGenerator()
        code = generator.generate(
            name="my_tool",
            description="A simple tool",
            parameters={...},
            template="simple"
        )
    """

    def __init__(self):
        self.sandbox = ToolCodeSandbox()

    def generate(
        self,
        name: str,
        description: str,
        parameters: Optional[Dict] = None,
        implementation: Optional[str] = None,
        template: str = "simple",
        extra_imports: Optional[list] = None,
    ) -> str:
        """生成完整的工具类代码

        Args:
            name: 工具名称 (snake_case)
            description: 功能描述
            parameters: JSON Schema参数字典，默认为简单input参数
            implementation: 自定义实现代码（可选）
            template: 使用的模板名称 ('simple', 'http', 'calc')
            extra_imports: 额外需要的导入模块列表

        Returns:
            完整的Python代码字符串

        Raises:
            ToolGenerationError: 生成失败或安全验证未通过
        """

        # 参数名验证
        if not name.isidentifier():
            raise ToolGenerationError(f"Invalid tool name: {name}")

        # 默认参数schema
        if parameters is None:
            parameters = {
                "type": "object",
                "properties": {"input": {"type": "string", "description": "输入参数"}},
                "required": ["input"],
            }

        # 使用模板实现或自定义实现
        if implementation is None:
            impl_code = get_template(template)
        else:
            impl_code = implementation

        # 生成导入语句
        imports = self._generate_imports(extra_imports or [])

        try:
            # Extract parameter names from the schema to unpack them into local variables
            param_names = list(parameters.get("properties", {}).keys())
            unpacking_code = "\n".join([f"        {name} = kwargs.get('{name}')" for name in param_names])
            # Add the unpacking code to the beginning of the implementation
            if impl_code:
                full_impl = unpacking_code + "\n" + impl_code
            else:
                full_impl = unpacking_code
            # 渲染完整代码
            code = render_tool_class(
                tool_name=name,
                class_name=to_pascal_case(name),
                description=description,
                parameters_schema=json.dumps(parameters, indent=4, ensure_ascii=False),
                implementation=full_impl,
                imports=imports,
                timestamp=datetime.now().isoformat(),
            )

            # 安全验证
            is_safe, violations = self.sandbox.analyze(code)
            if not is_safe:
                errors = [v.message for v in violations]
                raise ToolGenerationError(f"Security check failed: {'; '.join(errors)}")

            return code

        except ToolGenerationError:
            raise
        except Exception as e:
            raise ToolGenerationError(f"Generation failed: {e}")

    def _generate_imports(self, extra_imports: list) -> str:
        """生成模板所需的import语句"""
        if not extra_imports:
            return ""

        # 验证所有额外导入都在白名单中
        from internal.agent.tool.dynamic.security import ALLOWED_MODULES

        for module in extra_imports:
            if module in ALLOWED_MODULES:
                continue
            root_module = module.split(".")[0]
            if root_module in ALLOWED_MODULES:
                continue
            # Allow submodules if any ancestor is in allowed modules
            if "." in module:
                # Check if any of the ancestor parts are allowed
                current = module
                found = False
                while "." in current:
                    current = ".".join(current.split(".")[:-1])
                    if current in ALLOWED_MODULES:
                        found = True
                        break
                if not found:
                    # No ancestor is allowed, reject
                    raise ToolGenerationError(f"Unauthorized import: {module}")
            else:
                # No dots and root module not allowed, reject
                raise ToolGenerationError(f"Unauthorized import: {module}")

        return "\n" + "\n".join(f"import {m}" for m in extra_imports)

    def validate(self, code: str) -> tuple[bool, Optional[list]]:
        """验证代码安全性

        Args:
            code: Python代码字符串

        Returns:
            (is_valid, errors) 元组
        """
        is_safe, violations = self.sandbox.analyze(code)
        if is_safe:
            return True, None
        return False, [v.message for v in violations]


# 便捷函数
def generate_tool_code(name: str, description: str, **kwargs) -> str:
    """快速生成工具代码

    这是ToolGenerator.generate()的便捷包装。

    Args:
        name: 工具名称
        description: 功能描述
        **kwargs: 传递给ToolGenerator.generate()的其他参数

    Returns:
        生成的Python代码字符串

    Example:
        >>> code = generate_tool_code(
        ...     name="greet",
        ...     description="Greet someone",
        ...     template="simple"
        ... )
    """
    gen = ToolGenerator()
    return gen.generate(name=name, description=description, **kwargs)
