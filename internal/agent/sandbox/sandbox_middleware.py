import logging
from typing import Tuple, Optional
from .sandbox_config import SandboxConfig
from .file_sandbox import FileSandbox
from .network_sandbox import NetworkSandbox
from .approval import ApprovalManager, ApprovalRequest

logger = logging.getLogger(__name__)


class SandboxMiddleware:
    """
    Sandbox middleware that integrates security checking into the tool
    execution flow.
    """

    def __init__(self, config: SandboxConfig):
        self.config = config
        self.file_sandbox = FileSandbox(config.file)
        self.network_sandbox = NetworkSandbox(config.network)
        self.approval_manager = ApprovalManager(config.approval)

    def is_enabled(self) -> bool:
        """Check if sandbox is globally enabled."""
        return self.config.enabled

    def check_file_access(
        self, path: str, is_write: bool = False
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Check if file access is allowed.

        Returns:
            (allowed: bool, reason: str, normalized_path: Optional[str])
            - If allowed=True: access is permitted, normalized_path contains validated path
            - If allowed=False and reason starts with "APPROVAL_REQUIRED": needs user approval
            - If allowed=False and other reason: access denied permanently
        """
        if not self.config.enabled or not self.config.file.enabled:
            # Sandbox disabled - normalize path but allow access
            from .file_sandbox import FileSandbox

            # Need to normalize anyway for safety
            temp_sandbox = FileSandbox(self.config.file)
            normalized = temp_sandbox._normalize_path(path)
            return True, "", normalized

        return self.file_sandbox.validate_path(path, is_write)

    def check_file_size(self, normalized_path: str) -> Tuple[bool, str]:
        """Check if file size is within allowed limits."""
        if not self.config.enabled or not self.config.file.enabled:
            return True, ""
        return self.file_sandbox.check_file_size(normalized_path)

    def check_url_access(self, url: str) -> Tuple[bool, str]:
        """
        Check if URL access is allowed.

        Returns:
            (allowed: bool, reason: str)
        """
        if not self.config.enabled or not self.config.network.enabled:
            return True, ""
        allowed, msg, _ = self.network_sandbox.validate_url(url)
        return allowed, msg

    def needs_file_approval(self, normalized_path: str, is_write: bool) -> bool:
        """Check if this file operation needs user approval."""
        if not self.config.enabled:
            return False
        if not self.config.approval.enabled:
            return False
        return self.file_sandbox.needs_approval(normalized_path, is_write)

    def request_file_approval(self, path: str, is_write: bool, reason: str) -> bool:
        """
        Request user approval for a file operation.

        Blocks until user responds or timeout.

        Returns:
            True if approved, False otherwise
        """
        op_type = "write" if is_write else "read"
        approved, msg = self.approval_manager.request_approval_sync(
            op_type, path, reason
        )
        logger.info(f"Approval result: {approved} - {msg}")
        return approved

    def check_host_port_access(self, host: str, port: int) -> Tuple[bool, str]:
        """
        Check if direct host:port access is allowed.

        Returns:
            (allowed: bool, reason: str)
        """
        if not self.config.enabled or not self.config.network.enabled:
            return True, ""
        return self.network_sandbox.validate_host_port(host, port)

    def get_pending_approval(self) -> Optional[ApprovalRequest]:
        """Get the current pending approval request for UI display."""
        return self.approval_manager.get_pending_request()

    def respond_approval(self, request_id: int, approved: bool) -> bool:
        """Respond to a pending approval request from the UI."""
        return self.approval_manager.respond(request_id, approved)


# Create default sandbox instance with default configuration
default_sandbox = SandboxMiddleware(SandboxConfig())
