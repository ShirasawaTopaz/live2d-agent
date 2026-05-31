"""Session Manager — orchestrator for auto-routing.

Wires TopicClassifier + Router + SessionStore + MemoryManager together.
Called at the start of each user message to determine session routing.

Flow:
  User message -> route_message(text) -> classify -> Router.decide ->
    - STAY: continue in current session, return empty context injection
    - SWITCH: MemoryManager.switch_session(), inject old summary
    - CREATE: MemoryManager.new_session(), inherit context
"""

import logging
import time
import uuid
from typing import TYPE_CHECKING

from internal.session.types import ClassificationResult, Session
from internal.session.router import Router, RouteAction
from internal.session.topic_classifier import TopicClassifier
from internal.session.session_store import SessionStore

if TYPE_CHECKING:
    from internal.memory._manager import MemoryManager
    from internal.rag.embeddings import EmbeddingGenerator

logger = logging.getLogger(__name__)


class SessionManager:
    """Orchestrates session auto-routing.

    Dependencies:
    - TopicClassifier: detects topic from user text
    - Router: makes STAY/SWITCH/CREATE decisions
    - SessionStore: persists session metadata
    - MemoryManager: manages actual message history per session
    """

    def __init__(
        self,
        session_store: SessionStore,
        classifier: TopicClassifier,
        router: Router | None = None,
        memory_manager: "MemoryManager | None" = None,
    ):
        self._store = session_store
        self._classifier = classifier
        self._router = router or Router()
        self._memory: "MemoryManager | None" = memory_manager
        self._sessions: dict[str, Session] = {}
        self._current_session_id: str | None = None

    # -- Properties -----------------------------------------------

    @property
    def current_session(self) -> Session | None:
        if self._current_session_id is None:
            return None
        return self._sessions.get(self._current_session_id)

    # -- Lifecycle -------------------------------------------------

    async def initialize(self) -> None:
        """Load existing sessions from store, create default if none."""
        await self._store.init()

        loaded = await self._store.list_all()
        self._sessions = {s.session_id: s for s in loaded}
        logger.info("Loaded %d sessions from store", len(self._sessions))

        if not self._sessions:
            session = await self.create_session(topic="general", inherit_from=None)
            self._current_session_id = session.session_id
        else:
            # Restore the most recently active session
            self._current_session_id = loaded[0].session_id
            if self._memory is not None and self._current_session_id is not None:
                await self._memory.switch_session(self._current_session_id)

    async def create_session(
        self,
        topic: str,
        inherit_from: Session | None = None,
    ) -> Session:
        """Create a new session with the given topic."""
        session_id = str(uuid.uuid4())[:8]
        now = time.time()

        snapshot: dict[str, object] = {}
        if inherit_from is not None:
            snapshot = self._router.generate_new_session_inheritance(inherit_from)

        session = Session(
            session_id=session_id,
            topic=topic,
            display_name=topic,
            summary="",
            created_at=now,
            last_active_at=now,
            message_count=0,
            context_snapshot=snapshot,
        )

        self._sessions[session_id] = session
        await self._store.save(session)

        if self._memory is not None:
            await self._memory.new_session(topic)

        logger.info(
            "Created session '%s' topic='%s' (inherited from %s)",
            session_id,
            topic,
            inherit_from.session_id if inherit_from else "none",
        )
        return session

    async def switch_to(self, session_id: str) -> bool:
        """Switch to an existing session. Returns True if succeeded."""
        if session_id not in self._sessions:
            logger.warning("Session '%s' not found", session_id)
            return False

        if session_id == self._current_session_id:
            return True

        # Mark the current session as inactive before switching
        if self._current_session_id and self._current_session_id in self._sessions:
            old = self._sessions[self._current_session_id]
            old.last_active_at = time.time()
            await self._store.save(old)

        self._current_session_id = session_id
        session = self._sessions[session_id]
        session.last_active_at = time.time()
        await self._store.save(session)

        if self._memory is not None:
            await self._memory.switch_session(session_id)

        logger.info("Switched to session '%s'", session_id)
        return True

    async def list_sessions(self) -> list[Session]:
        """List all sessions sorted by last_active_at descending."""
        return sorted(
            self._sessions.values(),
            key=lambda s: s.last_active_at,
            reverse=True,
        )

    async def update_summary(self, session_id: str, summary: str) -> None:
        """Update a session's summary (called after compression)."""
        if session_id in self._sessions:
            self._sessions[session_id].summary = summary
            await self._store.save(self._sessions[session_id])

    # -- Core routing ----------------------------------------------

    async def route_message(
        self,
        text: str,
    ) -> tuple[RouteAction, str]:
        """Route an incoming user message to the appropriate session.

        Called at the start of every user message processing flow.

        Returns:
            (RouteAction, context_injection_string)
        """
        session_list = list(self._sessions.values())
        classification = self._classifier.classify(text, session_list)

        action = self._router.decide(classification, self._current_session_id)

        context_injection = ""

        if action == RouteAction.STAY:
            pass

        elif action == RouteAction.SWITCH:
            target_id = self._router.target_session_id
            if target_id is not None and target_id != self._current_session_id:
                prev = self.current_session
                target = self._sessions.get(target_id)
                if prev is not None and target is not None:
                    context_injection = self._router.generate_switch_context(prev, target)
                await self.switch_to(target_id)

        elif action == RouteAction.CREATE:
            prev = self.current_session
            new_session = await self.create_session(
                topic=classification.topic,
                inherit_from=prev,
            )

            if prev is not None:
                context_injection = (
                    f"[新会话已创建] 主题: {classification.topic}。"
                    f"上一会话摘要: {prev.summary}"
                )

            self._current_session_id = new_session.session_id

        return action, context_injection
