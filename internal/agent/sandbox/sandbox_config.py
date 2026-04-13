from dataclasses import dataclass, field
from typing import List


@dataclass
class FileSandboxConfig:
    enabled: bool = True
    """Enable file system sandboxing"""

    default_policy: str = "deny"  # "allow" or "deny"
    """Default policy: deny (whitelist mode) or allow (blacklist mode)"""

    allowed_directories: List[str] = field(default_factory=lambda: ["./"])
    """List of directories allowed to be accessed (whitelist mode)"""

    blocked_directories: List[str] = field(
        default_factory=lambda: [
            "/etc",
            "~/.ssh",
            "~/.git",
            "%APPDATA%",
            "%USERPROFILE%\\.ssh",
            "%LOCALAPPDATA%",
            "/root",
            "/home/*/.ssh",
            "/proc",
            "/sys",
        ]
    )
    """List of directories that are always blocked"""

    blocked_extensions: List[str] = field(
        default_factory=lambda: [
            ".pem",
            ".key",
            ".priv",
            ".id_rsa",
            ".env",
            ".env.*",
            ".json",  # Note: blocks config.json with secrets, user can override
            ".sqlite",
            ".db",
            ".dll",
            ".exe",
            ".sys",
            ".bat",
            ".cmd",
            ".ps1",
            ".sh",
        ]
    )
    """List of file extensions that are always blocked"""

    blocked_files: List[str] = field(
        default_factory=lambda: [
            "config.json",
            "credentials",
            "id_rsa",
            "id_dsa",
            "known_hosts",
            ".git/config",
            ".git/credentials",
        ]
    )
    """List of specific filenames that are always blocked"""

    max_file_size: int = 10 * 1024 * 1024  # 10MB
    """Maximum file size that can be read"""

    allow_write: bool = True
    """Allow file write operations. If False, all writes are blocked."""

    require_approval_for_write: bool = True
    """Require user approval before writing files"""

    require_approval_for_read_outside_allowed: bool = True
    """Require user approval when reading outside allowed directories"""


@dataclass
class NetworkSandboxConfig:
    enabled: bool = True
    """Enable network sandboxing (SSRF protection)"""

    block_private_ips: bool = True
    """Block requests to private IP address ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8)"""

    allowed_domains: List[str] = field(
        default_factory=lambda: [
            "*.baidu.com",
            "*.bing.com",
            "*.duckduckgo.com",
            "*.google.com",
            "*.githubusercontent.com",
            "*.github.com",
        ]
    )
    """Allowed domains (suffix matching, * allowed as wildcard)"""

    blocked_ports: List[int] = field(
        default_factory=lambda: [
            21,
            22,
            23,
            25,
            135,
            139,
            445,
            3306,
            5432,
            27017,
            6379,
            9200,
        ]
    )
    """Blocked ports that are commonly used for internal services"""


@dataclass
class ApprovalConfig:
    enabled: bool = True
    """Enable user approval for dangerous operations"""

    timeout_seconds: int = 30
    """Automatically reject if user doesn't respond within this timeout"""

    remember_choice: bool = True
    """Remember user's choice for similar paths"""


@dataclass
class SandboxConfig:
    enabled: bool = True
    """Master switch: if False, all sandbox checks are disabled"""

    file: FileSandboxConfig = field(default_factory=FileSandboxConfig)
    network: NetworkSandboxConfig = field(default_factory=NetworkSandboxConfig)
    approval: ApprovalConfig = field(default_factory=ApprovalConfig)

    @staticmethod
    def from_dict(data: dict) -> "SandboxConfig":
        """Load sandbox configuration from dictionary."""
        config = SandboxConfig()

        if "enabled" in data:
            config.enabled = bool(data["enabled"])

        if "file" in data and isinstance(data["file"], dict):
            file_data = data["file"]
            config.file.enabled = file_data.get("enabled", config.file.enabled)
            config.file.default_policy = file_data.get(
                "default_policy", config.file.default_policy
            )
            config.file.allowed_directories = file_data.get(
                "allowed_directories", config.file.allowed_directories
            )
            config.file.blocked_directories = file_data.get(
                "blocked_directories", config.file.blocked_directories
            )
            config.file.blocked_extensions = file_data.get(
                "blocked_extensions", config.file.blocked_extensions
            )
            config.file.blocked_files = file_data.get(
                "blocked_files", config.file.blocked_files
            )
            if "max_file_size" in file_data:
                config.file.max_file_size = int(file_data["max_file_size"])
            config.file.allow_write = file_data.get(
                "allow_write", config.file.allow_write
            )
            config.file.require_approval_for_write = file_data.get(
                "require_approval_for_write", config.file.require_approval_for_write
            )
            config.file.require_approval_for_read_outside_allowed = file_data.get(
                "require_approval_for_read_outside_allowed",
                config.file.require_approval_for_read_outside_allowed,
            )

        if "network" in data and isinstance(data["network"], dict):
            net_data = data["network"]
            config.network.enabled = net_data.get("enabled", config.network.enabled)
            config.network.block_private_ips = net_data.get(
                "block_private_ips", config.network.block_private_ips
            )
            config.network.allowed_domains = net_data.get(
                "allowed_domains", config.network.allowed_domains
            )
            config.network.blocked_ports = net_data.get(
                "blocked_ports", config.network.blocked_ports
            )

        if "approval" in data and isinstance(data["approval"], dict):
            approv_data = data["approval"]
            config.approval.enabled = approv_data.get(
                "enabled", config.approval.enabled
            )
            if "timeout_seconds" in approv_data:
                config.approval.timeout_seconds = int(approv_data["timeout_seconds"])
            config.approval.remember_choice = approv_data.get(
                "remember_choice", config.approval.remember_choice
            )

        return config

    def to_dict(self) -> dict:
        """Convert configuration to dictionary for saving."""
        return {
            "enabled": self.enabled,
            "file": {
                "enabled": self.file.enabled,
                "default_policy": self.file.default_policy,
                "allowed_directories": self.file.allowed_directories,
                "blocked_directories": self.file.blocked_directories,
                "blocked_extensions": self.file.blocked_extensions,
                "blocked_files": self.file.blocked_files,
                "max_file_size": self.file.max_file_size,
                "allow_write": self.file.allow_write,
                "require_approval_for_write": self.file.require_approval_for_write,
                "require_approval_for_read_outside_allowed": self.file.require_approval_for_read_outside_allowed,
            },
            "network": {
                "enabled": self.network.enabled,
                "block_private_ips": self.network.block_private_ips,
                "allowed_domains": self.network.allowed_domains,
                "blocked_ports": self.network.blocked_ports,
            },
            "approval": {
                "enabled": self.approval.enabled,
                "timeout_seconds": self.approval.timeout_seconds,
                "remember_choice": self.approval.remember_choice,
            },
        }
