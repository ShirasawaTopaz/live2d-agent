"""
Tool Result Offloader - Phase 2 Enhancement
Offloads large tool results to disk to reduce context size
"""

import os
import json
import logging
import hashlib
import uuid
from typing import Optional, Dict, Any

from internal.memory._types import Message


logger = logging.getLogger(__name__)


class ToolResultOffloader:
    """Tool result offloader - stores large tool outputs to disk

    Reduces context size by storing full tool results externally,
    injecting only a summary + reference into the context.
    """

    def __init__(self, data_dir: str = "./data/memory/tool_offload"):
        self.data_dir = data_dir
        self._offload_store: Dict[str, str] = {}
        os.makedirs(data_dir, exist_ok=True)

    def _get_file_path(self, tool_call_id: str) -> str:
        """Get file path for a tool call ID"""
        safe_id = hashlib.sha256(tool_call_id.encode()).hexdigest()[:16]
        return os.path.join(self.data_dir, f"{safe_id}.json")

    def should_offload(self, message: Message) -> bool:
        """Check if a tool result should be offloaded"""
        role = message.get("role", "")
        content = message.get("content", "")

        if role != "tool":
            return False

        if not isinstance(content, str):
            content = json.dumps(content) if isinstance(content, (dict, list)) else str(content)

        return len(content) > 2000

    def offload(self, message: Message) -> Message:
        """Offload tool result to disk, return modified message with reference"""
        tool_call_id = message.get("tool_call_id", "")
        if not tool_call_id:
            tool_call_id = str(uuid.uuid4())[:8]
            message["tool_call_id"] = tool_call_id

        content = message.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)

        file_path = self._get_file_path(tool_call_id)
        data = {
            "tool_call_id": tool_call_id,
            "tool_name": message.get("tool_name", "unknown"),
            "content": content,
            "original_size": len(content),
        }

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            self._offload_store[tool_call_id] = file_path
            logger.debug(f"Offloaded tool result to {file_path} ({len(content)} chars)")
        except Exception as e:
            logger.error(f"Failed to offload tool result: {e}")
            return message

        summary = content[:300] + "..." if len(content) > 300 else content
        summary += f"\n\n[完整结果已存储至磁盘，文件: {os.path.basename(file_path)}]"

        message["content"] = summary
        message["_offloaded"] = True
        message["_offload_file"] = file_path

        return message

    def retrieve(self, tool_call_id: str) -> Optional[str]:
        """Retrieve offloaded tool result"""
        file_path = self._get_file_path(tool_call_id)
        if not os.path.exists(file_path):
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("content", "")
        except Exception as e:
            logger.error(f"Failed to retrieve offloaded tool result: {e}")
            return None

    def cleanup_old_offloads(self, max_age_days: int = 30) -> int:
        """Clean up offloaded files older than max_age_days"""
        import time
        cutoff = time.time() - (max_age_days * 86400)
        count = 0

        for filename in os.listdir(self.data_dir):
            filepath = os.path.join(self.data_dir, filename)
            if os.path.isfile(filepath):
                if os.path.getmtime(filepath) < cutoff:
                    try:
                        os.remove(filepath)
                        count += 1
                    except Exception as e:
                        logger.warning(f"Failed to remove {filepath}: {e}")

        if count > 0:
            logger.info(f"Cleaned up {count} old offloaded tool results")
        return count