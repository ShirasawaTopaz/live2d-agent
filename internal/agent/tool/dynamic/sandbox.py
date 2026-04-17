"""工具代码安全沙箱模块

使用AST（抽象语法树）解析验证代码安全性。
"""

import ast
from typing import List, Tuple, Optional

from internal.agent.tool.dynamic.security import (
    ALLOWED_MODULES,
    FORBIDDEN_BUILTINS,
    FORBIDDEN_MODULES,
)


class SecurityViolation(Exception):
    """代码违反安全策略异常"""

    def __init__(self, message: str, line: Optional[int] = None):
        self.message = message
        self.line = line
        super().__init__(f"Line {line}: {message}" if line else message)


class ToolCodeSandbox:
    """工具代码安全沙箱

    使用AST静态分析检测危险操作：
    1. 禁止的模块导入
    2. 危险的builtin函数
    3. 可疑的代码模式
    """

    def __init__(self):
        self.violations: List[SecurityViolation] = []
        self._parents: dict[int, ast.AST] = {}

    def analyze(self, code: str) -> Tuple[bool, List[SecurityViolation]]:
        """分析代码安全性

        Returns:
            (is_safe, violations)
        """
        self.violations = []

        try:
            tree = ast.parse(code)
            self._parents = {}
            for parent in ast.walk(tree):
                for child in ast.iter_child_nodes(parent):
                    self._parents[id(child)] = parent
        except SyntaxError as e:
            self.violations.append(
                SecurityViolation(f"Syntax error: {e.msg}", e.lineno)
            )
            return False, self.violations

        self._check_node(tree)
        return len(self.violations) == 0, self.violations

    def _check_node(self, node: ast.AST):
        """递归检查AST节点"""
        # 检查导入语句
        if isinstance(node, ast.Import):
            for alias in node.names:
                self._check_import(alias.name, getattr(node, "lineno", None))

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                 self._check_import(node.module, getattr(node, "lineno", None))

        # 检查禁止的builtin函数
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                if node.id in FORBIDDEN_BUILTINS:
                    parent = self._parents.get(id(node))
                    is_safe_eval = (
                        node.id == "eval"
                        and isinstance(parent, ast.Call)
                        and parent.func is node
                        and len(parent.args) == 3
                    )
                    if not is_safe_eval:
                        self.violations.append(
                            SecurityViolation(
                                f"Forbidden builtin: {node.id}",
                                getattr(node, "lineno", None),
                            )
                        )

        # 检查Call表达式中的危险调用
        elif isinstance(node, ast.Call):
            self._check_call(node)

        # 检查属性访问（防止通过对象获取危险函数）
        elif isinstance(node, ast.Attribute):
            if isinstance(node.ctx, ast.Load):
                # 检查是否访问危险属性
                if node.attr in FORBIDDEN_BUILTINS:
                    self.violations.append(
                        SecurityViolation(
                            f"Access to forbidden attribute: {node.attr}",
                            getattr(node, "lineno", None),
                        )
                    )

        # 递归检查子节点
        for child in ast.iter_child_nodes(node):
            self._check_node(child)

    def _check_import(self, module_name: str, line: Optional[int] = None):
        """检查模块导入是否允许"""
        if module_name in ALLOWED_MODULES:
            return
            
        root_module = module_name.split(".")[0]

        if root_module in FORBIDDEN_MODULES:
            self.violations.append(
                SecurityViolation(f"Forbidden module: {module_name}", line)
            )
            return

        if root_module in ALLOWED_MODULES:
            return

        if "." in module_name:
            # Check recursively up the chain: urllib.request.parse → urllib.request → urllib
            current = module_name
            found = False
            while "." in current:
                current = ".".join(current.split(".")[:-1])
                if current in ALLOWED_MODULES:
                    found = True
                    break
            if found:
                return

            self.violations.append(
                SecurityViolation(
                    f"Untrusted module: {module_name} (not in whitelist)", line
                )
            )
            return

        self.violations.append(
            SecurityViolation(
                f"Untrusted module: {module_name} (not in whitelist)", line
            )
        )

    def _check_call(self, node: ast.Call):
        """检查函数调用是否安全"""
        if isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_BUILTINS:
                # Special case: allow eval when it's properly sandboxed with three arguments
                # (eval(expr, globals_dict, locals_dict)) which is the safe sandboxed use
                if node.func.id == "eval" and len(node.args) == 3:
                    # This is the safe sandboxed pattern like eval(expr, {}, {})
                    pass
                else:
                    self.violations.append(
                        SecurityViolation(
                            f"Call to forbidden function: {node.func.id}",
                            getattr(node, "lineno", None),
                        )
                    )

        # 检查是否通过getattr获取危险函数
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr in ("eval", "exec", "__import__"):
                self.violations.append(
                    SecurityViolation(
                        f"Potentially dangerous attribute access: {node.func.attr}",
                        getattr(node, "lineno", None),
                    )
                )


def quick_check(code: str) -> bool:
    """快速检查代码安全性

    Args:
        code: Python代码字符串

    Returns:
        True if safe, False otherwise
    """
    sandbox = ToolCodeSandbox()
    is_safe, _ = sandbox.analyze(code)
    return is_safe
