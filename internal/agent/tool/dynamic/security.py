"""安全策略配置模块

定义动态工具生成系统的安全边界。
采用白名单机制，只允许已知安全的操作。
"""

# 允许导入的标准库模块白名单
ALLOWED_MODULES = {
    "json",
    "re",
    "math",
    "random",
    "datetime",
    "typing",
    "urllib.request",
    "urllib.parse",
    "hashlib",
    "base64",
    "collections",
    "itertools",
    "functools",
    "string",
    "time",
    "uuid",
    "copy",
    "enum",
    "dataclasses",
    "pathlib",
    "decimal",
    "fractions",
    "statistics",
    "inspect",
    "textwrap",
    "html",
    "html.parser",
    "internal",  # Allow importing from our own internal package
}

# 禁止使用的内置函数
FORBIDDEN_BUILTINS = {
    "eval",
    "exec",
    "__import__",
    "open",
    "compile",
    "exit",
    "quit",
}

# 禁止导入的模块
FORBIDDEN_MODULES = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "requests",
    "ftplib",
    "http.client",
    "pickle",
    "ctypes",
    "multiprocessing",
    "threading",
    "asyncio",  # 禁止直接使用asyncio，只允许通过框架提供的事件循环
    "concurrent",
    "sqlite3",  # 禁止直接数据库操作
    "urllib3",
    "certifi",
}
