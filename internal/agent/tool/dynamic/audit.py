"""Audit logging system for dynamic tool generation.

Records all tool generation requests, generated code content,
execution results, and errors for security auditing.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class AuditLogger:
    """Audit logger for dynamic tool generation operations.
    
    Logs:
    - All tool generation requests with timestamp and requester info
    - The full generated code content
    - Security validation results
    - Registration outcomes
    - Deletion events
    - Errors and exceptions
    """

    def __init__(
        self,
        log_dir: Optional[str] = None,
        enabled: bool = True,
    ):
        """Initialize the audit logger.
        
        Args:
            log_dir: Directory to store audit logs, defaults to module directory/logs
            enabled: Whether auditing is enabled
        """
        self.enabled = enabled

        if not enabled:
            self.log_path = None
            return

        if log_dir is None:
            base_path = Path(__file__).parent
            self.log_path = base_path / "audit_logs"
        else:
            self.log_path = Path(log_dir)

        self._ensure_log_dir()

    def _ensure_log_dir(self):
        """Ensure the log directory exists."""
        if self.log_path:
            self.log_path.mkdir(parents=True, exist_ok=True)

    def _get_current_iso(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now().isoformat()

    def _write_log(self, event_type: str, data: Dict) -> None:
        """Write a log entry to the audit log file."""
        if not self.enabled or not self.log_path:
            return

        # Create daily log file
        date_str = datetime.now().strftime("%Y-%m-%d")
        daily_log = self.log_path / f"audit_{date_str}.jsonl"

        entry = {
            "timestamp": self._get_current_iso(),
            "event_type": event_type,
            **data,
        }

        try:
            with open(daily_log, "a", encoding="utf-8") as f:
                json.dump(entry, f, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

    def log_generation_request(
        self,
        tool_name: str,
        description: str,
        requester: str = "agent",
        parameters: Optional[Dict] = None,
        template: Optional[str] = None,
        extra_imports: Optional[List[str]] = None,
    ) -> None:
        """Log a tool generation request.
        
        Args:
            tool_name: Name of the tool requested
            description: Natural language description
            requester: Who requested the generation (agent/user)
            parameters: Parameter schema provided
            template: Template name used
            extra_imports: Extra imports requested
        """
        data = {
            "tool_name": tool_name,
            "description": description,
            "requester": requester,
            "parameters": parameters,
            "template": template,
            "extra_imports": extra_imports,
        }
        self._write_log("generation_request", data)
        logger.info(f"Audit: Tool generation requested - {tool_name}")

    def log_generation_complete(
        self,
        tool_name: str,
        success: bool,
        code: Optional[str] = None,
        errors: Optional[List[str]] = None,
        security_passed: Optional[bool] = None,
        security_violations: Optional[List[str]] = None,
    ) -> None:
        """Log completion of tool generation.
        
        Args:
            tool_name: Name of the tool
            success: Whether generation succeeded
            code: The generated code if successful
            errors: List of error messages if failed
            security_passed: Whether security check passed
            security_violations: List of security violation messages
        """
        data = {
            "tool_name": tool_name,
            "success": success,
            "security_passed": security_passed,
            "security_violations": security_violations,
            "errors": errors,
        }
        # Include full code content for auditing
        if code is not None:
            data["code"] = code
            data["code_length"] = len(code)
            data["code_lines"] = len(code.splitlines())

        self._write_log("generation_complete", data)

        if success:
            logger.info(f"Audit: Tool generation completed successfully - {tool_name}")
        else:
            logger.warning(f"Audit: Tool generation failed - {tool_name}: {errors}")

    def log_registration(
        self,
        tool_name: str,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        """Log tool registration.
        
        Args:
            tool_name: Name of the tool
            success: Whether registration succeeded
            error: Error message if failed
        """
        data = {
            "tool_name": tool_name,
            "success": success,
            "error": error,
        }
        self._write_log("registration", data)

        if success:
            logger.info(f"Audit: Tool registered - {tool_name}")
        else:
            logger.warning(f"Audit: Tool registration failed - {tool_name}: {error}")

    def log_deletion(
        self,
        tool_name: str,
        success: bool,
        requester: str = "agent",
        error: Optional[str] = None,
    ) -> None:
        """Log tool deletion.
        
        Args:
            tool_name: Name of the tool deleted
            success: Whether deletion succeeded
            requester: Who requested the deletion
            error: Error message if failed
        """
        data = {
            "tool_name": tool_name,
            "success": success,
            "requester": requester,
            "error": error,
        }
        self._write_log("deletion", data)

        if success:
            logger.info(f"Audit: Tool deleted - {tool_name}")
        else:
            logger.warning(f"Audit: Tool deletion failed - {tool_name}: {error}")

    def log_execution(
        self,
        tool_name: str,
        success: bool,
        args: Optional[Dict] = None,
        result: Optional[str] = None,
        error: Optional[str] = None,
        execution_time_ms: Optional[float] = None,
    ) -> None:
        """Log execution of a dynamic tool.
        
        Args:
            tool_name: Name of the tool executed
            success: Whether execution succeeded
            args: Arguments passed to the tool
            result: Result summary (truncated if needed)
            error: Error message if failed
            execution_time_ms: Execution time in milliseconds
        """
        data = {
            "tool_name": tool_name,
            "success": success,
            "args": args,
            "result": result,
            "error": error,
            "execution_time_ms": execution_time_ms,
        }
        self._write_log("execution", data)

        if not success:
            logger.warning(f"Audit: Dynamic tool execution failed - {tool_name}: {error}")

    def log_error(
        self,
        error_type: str,
        message: str,
        tool_name: Optional[str] = None,
        exception: Optional[str] = None,
    ) -> None:
        """Log an error during dynamic tool operations.
        
        Args:
            error_type: Category of error
            message: Error message
            tool_name: Related tool name if available
            exception: Exception stack trace
        """
        data = {
            "error_type": error_type,
            "message": message,
            "tool_name": tool_name,
            "exception": exception,
        }
        self._write_log("error", data)
        logger.error(f"Audit: Error - {error_type}: {message}")

    def get_all_events(
        self,
        event_type: Optional[str] = None,
        tool_name: Optional[str] = None,
    ) -> List[Dict]:
        """Read all audit events from the logs.
        
        Args:
            event_type: Filter by event type
            tool_name: Filter by tool name
        
        Returns:
            List of matching audit events
        """
        if not self.enabled or not self.log_path:
            return []

        events = []
        if not self.log_path.exists():
            return events

        for log_file in self.log_path.glob("audit_*.jsonl"):
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                            if event_type and event.get("event_type") != event_type:
                                continue
                            if tool_name and event.get("tool_name") != tool_name:
                                continue
                            events.append(event)
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.error(f"Failed to read audit log {log_file}: {e}")
                continue

        # Sort by timestamp
        events.sort(key=lambda x: x.get("timestamp", ""))
        return events

    def get_events_for_tool(self, tool_name: str) -> List[Dict]:
        """Get all audit events for a specific tool."""
        return self.get_all_events(tool_name=tool_name)

    def clear_old_logs(self, days: int = 30) -> int:
        """Clear audit logs older than specified days.
        
        Args:
            days: Days to keep, logs older than this will be deleted
        
        Returns:
            Number of log files deleted
        """
        if not self.enabled or not self.log_path:
            return 0

        deleted = 0
        cutoff = datetime.now().timestamp() - (days * 24 * 60 * 60)

        for log_file in self.log_path.glob("audit_*.jsonl"):
            try:
                mtime = log_file.stat().st_mtime
                if mtime < cutoff:
                    log_file.unlink()
                    deleted += 1
            except Exception as e:
                logger.error(f"Failed to delete old log {log_file}: {e}")

        return deleted


# Global default instance
_default_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get the default global audit logger instance."""
    global _default_logger
    if _default_logger is None:
        _default_logger = AuditLogger()
    return _default_logger


def disable_audit() -> None:
    """Disable audit logging (for testing)."""
    global _default_logger
    _default_logger = AuditLogger(enabled=False)
