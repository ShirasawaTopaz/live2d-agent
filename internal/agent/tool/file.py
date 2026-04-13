from internal.agent.tool.base import Tool
import os
import glob
import aiofiles
import aiofiles.os
from typing import Any, Optional
from internal.agent.sandbox import SandboxMiddleware, default_sandbox


class SandboxedFileToolBase:
    """Base class that adds sandbox checking to file operations."""

    def __init__(self, sandbox: Optional[SandboxMiddleware] = None):
        self.sandbox = sandbox or default_sandbox

    def _check_path(self, path: str, is_write: bool) -> tuple[bool, str]:
        """Check if path access is allowed by sandbox.

        Returns:
            (allowed: bool, error_message: str)
        """
        if not self.sandbox.is_enabled():
            return True, ""

        allowed, reason, normalized = self.sandbox.check_file_access(path, is_write)

        if not allowed:
            if reason.startswith("APPROVAL_REQUIRED"):
                # Need to request approval
                if normalized is not None and self.sandbox.needs_file_approval(
                    normalized, is_write
                ):
                    approved = self.sandbox.request_file_approval(
                        normalized, is_write, reason
                    )
                    if approved:
                        return True, ""
                    else:
                        return False, "Operation was rejected by user approval"

            return False, f"Sandbox denied access: {reason}"

        # Check file size for reads
        if not is_write and normalized is not None:
            size_allowed, size_reason = self.sandbox.check_file_size(normalized)
            if not size_allowed:
                return False, size_reason

        return True, ""


class FileTool(Tool, SandboxedFileToolBase):
    def __init__(self, sandbox: Optional[SandboxMiddleware] = None):
        SandboxedFileToolBase.__init__(self, sandbox)

    @property
    def name(self) -> str:
        return "file"

    @property
    def description(self) -> str:
        return "文件工具，可以用于搜索文件，搜索文件夹，读取或写入文件。当需要读取或者写入文件时调用此工具。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search_files", "search_dirs", "read", "write"],
                    "description": "操作类型：search_files(搜索文件), search_dirs(搜索目录), read(读取文件), write(写入文件)",
                },
                "path": {"type": "string", "description": "文件或目录路径"},
                "pattern": {"type": "string", "description": "搜索模式（如 *.py）"},
                "content": {
                    "type": "string",
                    "description": "写入的内容（write 操作时需要）",
                },
                "write_mode": {
                    "type": "string",
                    "enum": ["append", "overwrite"],
                    "description": "写入模式：append(追加写入), overwrite(全部重新写入)",
                },
            },
            "required": ["action", "path"],
        }

    async def execute(self, **kwargs) -> Any:
        action = kwargs.get("action")
        path = kwargs.get("path")

        if not path:
            return "Path is required"

        is_write = action == "write"
        allowed, error = self._check_path(path, is_write)
        if not allowed:
            return error

        if action == "search_files":
            pattern = kwargs.get("pattern", "*")
            return glob.glob(os.path.join(path, pattern))

        elif action == "search_dirs":
            entries = await aiofiles.os.listdir(path)
            result = []
            for d in entries:
                full_path = os.path.join(path, d)
                if await aiofiles.os.path.isdir(full_path):
                    result.append(d)
            return result

        elif action == "read":
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                return await f.read()

        elif action == "write":
            content = kwargs.get("content", "")
            write_mode = kwargs.get("write_mode", "overwrite")

            mode = "a" if write_mode == "append" else "w"
            async with aiofiles.open(path, mode, encoding="utf-8") as f:
                await f.write(content)

            return "File written successfully"

        return "Unknown action"
