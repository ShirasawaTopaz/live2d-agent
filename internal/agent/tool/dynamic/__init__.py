"""动态工具生成系统 - 让Agent能够自我生成工具

核心组件：
- Security: 安全策略配置（白名单/黑名单）
- Templates: 代码模板系统
- Sandbox: AST安全沙箱验证
- Generator: 工具代码生成器
- Storage: 动态工具存储管理
- Audit: 审计日志系统
- Versioning: 工具版本管理和回滚
"""

from internal.agent.tool.dynamic.security import (
    ALLOWED_MODULES,
    FORBIDDEN_BUILTINS,
    FORBIDDEN_MODULES,
)
from internal.agent.tool.dynamic.templates import (
    TOOL_CLASS_TEMPLATE,
    render_tool_class,
    to_pascal_case,
    to_snake_case,
    get_template,
    IMPLEMENTATION_TEMPLATES,
)
from internal.agent.tool.dynamic.sandbox import (
    ToolCodeSandbox,
    SecurityViolation,
    quick_check,
)
from internal.agent.tool.dynamic.generator import (
    ToolGenerator,
    ToolGenerationError,
    generate_tool_code,
)
from internal.agent.tool.dynamic.storage import (
    DynamicToolStorage,
)
from internal.agent.tool.dynamic.audit import (
    AuditLogger,
    get_audit_logger,
    disable_audit,
)
from internal.agent.tool.dynamic.versioning import (
    VersionManager,
    VersionInfo,
)

__all__ = [
    # Security
    "ALLOWED_MODULES",
    "FORBIDDEN_BUILTINS",
    "FORBIDDEN_MODULES",
    # Templates
    "TOOL_CLASS_TEMPLATE",
    "render_tool_class",
    "to_pascal_case",
    "to_snake_case",
    "get_template",
    "IMPLEMENTATION_TEMPLATES",
    # Sandbox
    "ToolCodeSandbox",
    "SecurityViolation",
    "quick_check",
    # Generator
    "ToolGenerator",
    "ToolGenerationError",
    "generate_tool_code",
    # Storage
    "DynamicToolStorage",
    # Audit
    "AuditLogger",
    "get_audit_logger",
    "disable_audit",
    # Versioning
    "VersionManager",
    "VersionInfo",
]

__version__ = "1.0.0"
