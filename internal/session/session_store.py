"""Session metadata persistence layer.

Follows the storage pattern established in internal/memory/storage/:
abstract base with JSON implementation. Sessions are stored as
individual JSON files keyed by session_id.
"""

import json
import logging
from pathlib import Path

from internal.session.types import Session

logger = logging.getLogger(__name__)


class SessionStore:
    """Persist and load Session metadata records.

    Stores one JSON file per session under <data_dir>/sessions/.
    This is session metadata only (topic, summary, etc.) —
    full message history stays in the Memory layer.
    """

    def __init__(self, data_dir: str = "./data/sessions"):
        self.data_dir = Path(data_dir)
        self._sessions_dir = self.data_dir / "sessions"

    async def init(self) -> None:
        """Initialize storage directories."""
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, session: Session) -> None:
        """Save a session record to disk."""
        filepath = self._sessions_dir / f"{session.session_id}.json"
        content = json.dumps(session.to_dict(), ensure_ascii=False, indent=2)
        filepath.write_text(content, encoding="utf-8")
        logger.debug("Saved session '%s' to %s", session.session_id, filepath)

    async def load(self, session_id: str) -> Session | None:
        """Load a single session by ID. Returns None if not found."""
        filepath = self._sessions_dir / f"{session_id}.json"
        if not filepath.exists():
            return None
        try:
            content = filepath.read_text(encoding="utf-8")
            data = json.loads(content)
            return Session.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load session '%s': %s", session_id, e)
            return None

    async def list_all(self) -> list[Session]:
        """List all stored sessions, sorted by last_active_at descending."""
        sessions: list[Session] = []
        if not self._sessions_dir.exists():
            return sessions

        for filepath in self._sessions_dir.glob("*.json"):
            try:
                content = filepath.read_text(encoding="utf-8")
                data = json.loads(content)
                sessions.append(Session.from_dict(data))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Skipping corrupt session file %s: %s", filepath, e)

        sessions.sort(key=lambda s: s.last_active_at, reverse=True)
        return sessions

    async def delete(self, session_id: str) -> bool:
        """Delete a session record. Returns True if deleted."""
        filepath = self._sessions_dir / f"{session_id}.json"
        if filepath.exists():
            filepath.unlink()
            logger.debug("Deleted session '%s'", session_id)
            return True
        return False
