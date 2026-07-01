"""Tests for file sandbox path traversal and symlink protection."""

import os
import pytest
from internal.agent.sandbox.file_sandbox import FileSandbox
from internal.agent.sandbox.sandbox_config import FileSandboxConfig


def _can_symlink() -> bool:
    """Check if the OS supports creating symlinks."""
    try:
        import tempfile
        tmp = tempfile.mkstemp()
        os.close(tmp[0])
        link = tmp[1] + "_link"
        os.symlink(tmp[1], link)
        os.remove(link)
        os.remove(tmp[1])
        return True
    except OSError:
        return False


class TestFileSandboxPathTraversal:
    def test_traversal_outside_allowed_denied(self, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        config = FileSandboxConfig(
            enabled=True,
            default_policy="deny",
            allowed_directories=[str(allowed)],
            blocked_directories=[],
            allow_write=True,
        )
        sandbox = FileSandbox(config)

        is_allowed, msg, normalized = sandbox.validate_path(
            str(allowed / ".." / "secret.txt")
        )
        assert not is_allowed
        assert "outside" in msg.lower() or "traversal" in msg.lower()

    @pytest.mark.skipif(not _can_symlink(), reason="OS does not support symlinks")
    def test_symlink_to_outside_blocked(self, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret")

        allowed = tmp_path / "allowed"
        allowed.mkdir()
        symlink = allowed / "link_to_secret"
        symlink.symlink_to(outside / "secret.txt")

        config = FileSandboxConfig(
            enabled=True,
            default_policy="deny",
            allowed_directories=[str(allowed)],
            blocked_directories=[],
            blocked_files=["secret.txt"],
            allow_write=True,
        )
        sandbox = FileSandbox(config)

        is_allowed, msg, normalized = sandbox.validate_path(str(symlink))
        assert not is_allowed
