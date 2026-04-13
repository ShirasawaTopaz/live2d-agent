import logging
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
from threading import Event, Lock
from .sandbox_config import ApprovalConfig

logger = logging.getLogger(__name__)


@dataclass
class ApprovalRequest:
    """Represents a request for user approval."""

    operation_type: str  # "read", "write"
    path: str
    reason: str
    request_id: int


class ApprovalManager:
    """Manages user approval requests for dangerous operations."""

    def __init__(self, config: ApprovalConfig):
        self.config = config
        self._pending_request: Optional[ApprovalRequest] = None
        self._response: Optional[bool] = None
        self._event = Event()
        self._lock = Lock()
        self._request_counter = 0
        # Cache of remembered decisions (path -> decision)
        self._cache: Dict[str, bool] = {}
        self._cache_enabled = config.remember_choice

    def _get_cache_key(self, operation_type: str, path: str) -> str:
        """Get cache key for a decision."""
        return f"{operation_type}:{path}"

    def check_cached_decision(self, operation_type: str, path: str) -> Optional[bool]:
        """Check if we have a remembered decision for this path.

        Returns:
            None if no cached decision, cached boolean decision otherwise.
        """
        if not self._cache_enabled:
            return None
        key = self._get_cache_key(operation_type, path)
        return self._cache.get(key)

    def request_approval_sync(
        self, operation_type: str, path: str, reason: str
    ) -> Tuple[bool, str]:
        """
        Request approval from user synchronously.

        This method should be called from a background thread. It will
        block until the user responds or timeout occurs.

        Args:
            operation_type: Type of operation ("read" or "write")
            path: The path that needs approval
            reason: Why approval is needed

        Returns:
            (approved: bool, message: str)
        """
        if not self.config.enabled:
            return True, "Approval disabled"

        # Check cache
        cached = self.check_cached_decision(operation_type, path)
        if cached is not None:
            logger.info(f"Using cached decision {cached} for {path}")
            return cached, "Using cached decision"

        with self._lock:
            self._request_counter += 1
            request_id = self._request_counter
            self._pending_request = ApprovalRequest(
                operation_type=operation_type,
                path=path,
                reason=reason,
                request_id=request_id,
            )
            self._response = None
            self._event.clear()

        # Wait for response or timeout
        logger.info(f"Waiting for user approval: {operation_type} on {path}")
        signaled = self._event.wait(timeout=self.config.timeout_seconds)

        with self._lock:
            if not signaled or self._response is None:
                # Timeout - default to reject
                self._pending_request = None
                return False, "Approval timed out, operation rejected"

            response = self._response
            self._pending_request = None

            # Cache decision if enabled
            if self._cache_enabled and response is not None:
                key = self._get_cache_key(operation_type, path)
                self._cache[key] = response

            return response, "User responded"

    def get_pending_request(self) -> Optional[ApprovalRequest]:
        """Get the current pending approval request."""
        with self._lock:
            return self._pending_request

    def respond(self, request_id: int, approved: bool) -> bool:
        """
        Respond to a pending approval request.

        Called by the UI when user approves or rejects.

        Args:
            request_id: Request ID to respond to
            approved: Whether the request was approved

        Returns:
            True if response was accepted, False if request doesn't match
        """
        with self._lock:
            if (
                self._pending_request is None
                or self._pending_request.request_id != request_id
            ):
                return False
            self._response = approved
            self._event.set()
            return True

    def clear_cache(self) -> None:
        """Clear all cached decisions."""
        with self._lock:
            self._cache.clear()
        logger.info("Approval cache cleared")
