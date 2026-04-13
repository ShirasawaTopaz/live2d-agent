from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from internal.mcp.protocol import MCPMode, CompressionStrategyType


@dataclass(slots=True)
class RemoteMCPConfig:
    """远程MCP服务配置"""

    enabled: bool = False
    endpoint: str = ""
    api_key: str | None = None
    timeout: int = 30
    verify_ssl: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RemoteMCPConfig:
        return cls(
            enabled=data.get("enabled", False),
            endpoint=data.get("endpoint", ""),
            api_key=data.get("api_key"),
            timeout=data.get("timeout", 30),
            verify_ssl=data.get("verify_ssl", True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "endpoint": self.endpoint,
            "api_key": self.api_key,
            "timeout": self.timeout,
            "verify_ssl": self.verify_ssl,
        }


@dataclass(slots=True)
class MCPConfig:
    """MCP整体配置"""

    enabled: bool = False
    mode: MCPMode = MCPMode.LOCAL
    compression_strategy: CompressionStrategyType = CompressionStrategyType.SUMMARY
    max_working_messages: int = 10
    max_recent_tokens: int = 2048
    max_total_tokens: int = 4096
    enable_long_term: bool = True
    storage_type: str = "json"  # json / sqlite
    remote: RemoteMCPConfig = field(default_factory=RemoteMCPConfig)
    auto_compress: bool = True
    compression_threshold_messages: int = 15

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPConfig:
        """从字典创建配置"""
        remote_data = data.get("remote", {})
        return cls(
            enabled=data.get("enabled", data.get("use_mcp", False)),
            mode=MCPMode(data.get("mcp_mode", "local")),
            compression_strategy=CompressionStrategyType(
                data.get("compression_strategy", "summary")
            ),
            max_working_messages=data.get("max_working_messages", 10),
            max_recent_tokens=data.get("max_recent_tokens", 2048),
            max_total_tokens=data.get("max_total_tokens", 4096),
            enable_long_term=data.get("enable_long_term", True),
            storage_type=data.get("storage_type", "json"),
            remote=RemoteMCPConfig.from_dict(remote_data),
            auto_compress=data.get("auto_compress", True),
            compression_threshold_messages=data.get(
                "compression_threshold_messages", 15
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "mode": self.mode.value,
            "compression_strategy": self.compression_strategy.value,
            "max_working_messages": self.max_working_messages,
            "max_recent_tokens": self.max_recent_tokens,
            "max_total_tokens": self.max_total_tokens,
            "enable_long_term": self.enable_long_term,
            "storage_type": self.storage_type,
            "remote": self.remote.to_dict(),
            "auto_compress": self.auto_compress,
            "compression_threshold_messages": self.compression_threshold_messages,
        }

    @classmethod
    def default_disabled(cls) -> MCPConfig:
        """默认禁用配置"""
        return cls(enabled=False)
