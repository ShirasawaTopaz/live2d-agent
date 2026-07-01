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


class TestFileSandboxGlobExpansion:
    def test_blocked_directories_glob_expanded(self, tmp_path):
        home_ssh = tmp_path / "home" / "user" / ".ssh"
        home_ssh.mkdir(parents=True)
        (home_ssh / "id_rsa").write_text("secret")

        allowed = tmp_path / "work"
        allowed.mkdir()

        config = FileSandboxConfig(
            enabled=True,
            default_policy="deny",
            allowed_directories=[str(allowed)],
            blocked_directories=[str(tmp_path / "home" / "*" / ".ssh")],
            allow_write=True,
        )
        sandbox = FileSandbox(config)

        is_allowed, msg, normalized = sandbox.validate_path(str(home_ssh / "id_rsa"))
        assert not is_allowed
        assert "blocked directory" in msg.lower()


class TestNetworkSandboxDnsRebinding:
    def test_allowed_domain_resolving_to_private_ip_is_blocked(self, monkeypatch):
        from internal.agent.sandbox.network_sandbox import NetworkSandbox
        from internal.agent.sandbox.sandbox_config import NetworkSandboxConfig

        config = NetworkSandboxConfig(
            enabled=True,
            block_private_ips=True,
            allowed_domains=["*.example.com"],
        )
        sandbox = NetworkSandbox(config)

        def fake_getaddrinfo(host, port, *args, **kwargs):
            return [(None, None, None, None, ("127.0.0.1", port))]

        monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)

        is_allowed, msg, _ = sandbox.validate_url("http://sub.example.com/path")
        assert not is_allowed
        assert "private" in msg.lower()
