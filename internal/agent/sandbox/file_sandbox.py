import os
import re
from typing import Tuple, Optional, List
from .sandbox_config import FileSandboxConfig


class FileSandbox:
    """File system sandbox that enforces security restrictions on file operations."""

    def __init__(self, config: FileSandboxConfig):
        self.config = config
        self._expand_user_vars_in_config()

    def _expand_user_vars_in_config(self):
        """Expand user home directory and environment variables in paths."""
        expanded_allowed = []
        for path in self.config.allowed_directories:
            expanded = os.path.expanduser(os.path.expandvars(path))
            expanded_allowed.append(os.path.abspath(expanded))
        self.config.allowed_directories = expanded_allowed

        expanded_blocked = []
        for path in self.config.blocked_directories:
            expanded = os.path.expanduser(os.path.expandvars(path))
            expanded_blocked.append(os.path.abspath(expanded))
        self.config.blocked_directories = expanded_blocked

    def _normalize_path(self, path: str) -> Optional[str]:
        """Normalize and resolve path, detect path traversal attempts.

        Returns None if path traversal is detected, normalized absolute path otherwise.
        """
        try:
            # Expand user and environment variables
            expanded = os.path.expanduser(os.path.expandvars(path))
            # Get absolute path
            abs_path = os.path.abspath(expanded)
            # Resolve symlinks (important security step)
            real_path = os.path.realpath(abs_path)

            # Check for path traversal: if after resolution the path doesn't start
            # with the original expanded path's prefix, traversal occurred
            if not real_path.startswith(os.path.commonprefix([abs_path, real_path])):
                return None

            return real_path
        except Exception:
            return None

    def _is_path_in_any_prefix(self, path: str, prefixes: List[str]) -> bool:
        """Check if path starts with any of the given prefixes."""
        path_lower = path.lower()
        for prefix in prefixes:
            prefix_abs = os.path.abspath(prefix)
            prefix_lower = prefix_abs.lower()
            if (
                path_lower.startswith(prefix_lower + os.sep)
                or path_lower == prefix_lower
            ):
                return True
        return False

    def _matches_blocked_filename(self, filename: str) -> bool:
        """Check if filename matches any of the blocked filenames."""
        filename_lower = filename.lower()
        for blocked in self.config.blocked_files:
            blocked_lower = blocked.lower()
            # Exact match or filename ends with blocked pattern
            if filename_lower == blocked_lower or filename_lower.endswith(
                "/" + blocked_lower
            ):
                return True
            # Support simple wildcards
            if "*" in blocked_lower:
                pattern = re.escape(blocked_lower).replace(r"\*", ".*")
                if re.match(pattern, filename_lower):
                    return True
        return False

    def _has_blocked_extension(self, path: str) -> bool:
        """Check if file has a blocked extension."""
        _, ext = os.path.splitext(path)
        ext_lower = ext.lower()
        blocked_lower = [e.lower() for e in self.config.blocked_extensions]
        return ext_lower in blocked_lower

    def _is_in_allowed_directory(self, normalized_path: str) -> bool:
        """Check if path is within any allowed directory."""
        return self._is_path_in_any_prefix(
            normalized_path, self.config.allowed_directories
        )

    def _is_in_blocked_directory(self, normalized_path: str) -> bool:
        """Check if path is within any blocked directory."""
        return self._is_path_in_any_prefix(
            normalized_path, self.config.blocked_directories
        )

    def validate_path(
        self, requested_path: str, is_write: bool = False
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Validate a file path against sandbox security rules.

        Args:
            requested_path: The path requested by the tool
            is_write: Whether this is a write operation

        Returns:
            (is_allowed: bool, error_message: str, normalized_path: Optional[str])
            - If is_allowed is True, normalized_path contains the validated absolute path
            - If is_allowed is False, error_message contains the reason
        """
        if not self.config.enabled:
            # Sandbox disabled for file operations - everything allowed
            normalized = self._normalize_path(requested_path)
            return True, "", normalized

        # Normalize and check for path traversal
        normalized = self._normalize_path(requested_path)
        if normalized is None:
            return False, "Path traversal detected: invalid path", None

        # Check blocked writes
        if is_write and not self.config.allow_write:
            return False, "File writes are disabled by sandbox configuration", None

        # Check if in blocked directory (always blocked regardless of policy)
        if self._is_in_blocked_directory(normalized):
            return False, "Access to blocked directory denied", None

        # Check blocked filename
        filename = os.path.basename(normalized)
        if self._matches_blocked_filename(filename):
            return False, "Access to blocked file denied", None

        # Check blocked extension
        if self._has_blocked_extension(normalized):
            return False, "Access to file type with blocked extension denied", None

        # Check against policy
        if self.config.default_policy == "deny":
            # Whitelist mode: only allowed directories are allowed
            if not self._is_in_allowed_directory(normalized):
                if self.config.require_approval_for_read_outside_allowed or is_write:
                    # Need approval, return special status indicating approval needed
                    return (
                        False,
                        "APPROVAL_REQUIRED: Access outside allowed directory requires approval",
                        None,
                    )
                else:
                    return (
                        False,
                        "Access denied: path outside allowed directories",
                        None,
                    )

        # If we get here, path is allowed
        return True, "", normalized

    def check_file_size(self, path: str) -> Tuple[bool, str]:
        """
        Check if file size is within allowed limits.

        Returns:
            (is_allowed: bool, error_message: str)
        """
        try:
            size = os.path.getsize(path)
            if size > self.config.max_file_size:
                return (
                    False,
                    f"File too large: {size} bytes exceeds limit of {self.config.max_file_size} bytes",
                )
            return True, ""
        except OSError:
            # File doesn't exist or can't be accessed - let the caller handle it
            return True, ""

    def needs_approval(self, normalized_path: str, is_write: bool) -> bool:
        """
        Determine if this operation requires user approval.

        The caller should have already checked that the path is not
        in the always-blocked lists. This method checks whether
        approval is required based on configuration.
        """
        if is_write and self.config.require_approval_for_write:
            return True

        if not self._is_in_allowed_directory(normalized_path):
            if self.config.require_approval_for_read_outside_allowed:
                return True

        return False


class SandboxFileAccessError(Exception):
    """Exception raised when file access is denied by sandbox."""

    pass
