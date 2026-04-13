import ipaddress
from typing import Tuple, Optional
from urllib.parse import urlparse
from .sandbox_config import NetworkSandboxConfig


class NetworkSandbox:
    """Network sandbox that provides SSRF protection and domain restrictions."""

    # Private IP address ranges (RFC 1918, loopback, link-local)
    PRIVATE_RANGES = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("fc00::/7"),  # Unique local addresses (IPv6)
        ipaddress.ip_network("fe80::/10"),  # Link-local addresses (IPv6)
        ipaddress.ip_network("::1/128"),  # Loopback (IPv6)
    ]

    def __init__(self, config: NetworkSandboxConfig):
        self.config = config

    def _is_private_ip(self, ip_str: str) -> bool:
        """Check if an IP address is in a private/unroutable range."""
        try:
            ip = ipaddress.ip_address(ip_str.strip())
            for private_range in self.PRIVATE_RANGES:
                if ip in private_range:
                    return True
            return False
        except ValueError:
            # Not a valid IP address - could be a domain name
            return False

    def _domain_matches_pattern(self, domain: str, pattern: str) -> bool:
        """Check if domain matches a pattern with optional wildcard prefix."""
        domain = domain.lower()
        pattern = pattern.lower()

        # Exact match
        if domain == pattern:
            return True

        # Wildcard match (e.g., *.example.com matches sub.example.com)
        if pattern.startswith("*."):
            suffix = pattern[1:]  # .example.com
            if domain.endswith(suffix):
                return True

        return False

    def _domain_is_allowed(self, domain: str) -> bool:
        """Check if domain is allowed by the configured whitelist."""
        if not self.config.allowed_domains:
            # Empty whitelist means all domains allowed
            return True

        domain_clean = domain.strip().lower()
        for pattern in self.config.allowed_domains:
            if self._domain_matches_pattern(domain_clean, pattern):
                return True

        return False

    def _port_is_blocked(self, port: int) -> bool:
        """Check if a port is in the blocked ports list."""
        return port in self.config.blocked_ports

    def validate_url(self, url: str) -> Tuple[bool, str, Optional[str]]:
        """
        Validate a URL against network security rules.

        Args:
            url: The URL to validate

        Returns:
            (is_allowed: bool, error_message: str, resolved_domain: Optional[str])
        """
        if not self.config.enabled:
            return True, "", None

        try:
            parsed = urlparse(url)
        except ValueError as e:
            return False, f"Invalid URL: {e}", None

        # Only allow http/https schemes
        if parsed.scheme not in ("http", "https"):
            return False, f"Scheme '{parsed.scheme}' not allowed", None

        domain = parsed.netloc.split(":")[0]
        port_str = parsed.netloc.split(":")[1] if ":" in parsed.netloc else None
        port = int(port_str) if port_str else (443 if parsed.scheme == "https" else 80)

        # Check if port is blocked
        if self._port_is_blocked(port):
            return False, f"Port {port} is blocked", None

        # Check for private IPs directly accessed
        if self._is_private_ip(domain):
            if self.config.block_private_ips:
                return False, "Access to private IP addresses blocked", domain
            return True, "", domain

        # Check domain whitelist
        if not self._domain_is_allowed(domain):
            return False, f"Domain '{domain}' not in allowed domains list", domain

        return True, "", domain

    def validate_host_port(self, host: str, port: int) -> Tuple[bool, str]:
        """
        Validate a direct host:port connection.

        Args:
            host: Hostname or IP address
            port: Port number

        Returns:
            (is_allowed: bool, error_message: str)
        """
        if not self.config.enabled:
            return True, ""

        # Check blocked port
        if self._port_is_blocked(port):
            return False, f"Port {port} is blocked"

        # Check if host is a private IP
        try:
            if self._is_private_ip(host):
                if self.config.block_private_ips:
                    return False, "Access to private IP addresses blocked"
        except ValueError:
            pass

        # Check domain whitelist if it's a domain
        if not ipaddress.ip_address(host):
            if not self._domain_is_allowed(host):
                return False, f"Domain '{host}' not in allowed domains list"

        return True, ""


class SandboxNetworkAccessError(Exception):
    """Exception raised when network access is denied by sandbox."""

    pass
