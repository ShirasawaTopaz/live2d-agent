"""Integration tests for SessionManager."""

import time
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from internal.session.types import Session, ClassificationResult
from internal.session.topic_classifier import TopicClassifier
from internal.session.router import RouteAction
from internal.session.session_store import SessionStore


class TestSessionManagerBasic:
    """Tests for SessionManager lifecycle operations."""

    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = SessionStore(data_dir=self.temp_dir.name)

    def teardown_method(self):
        self.temp_dir.cleanup()

    @pytest.mark.asyncio
    async def test_init_creates_session(self):
        from internal.session.session_manager import SessionManager

        await self.store.init()
        mgr = SessionManager(
            session_store=self.store,
            classifier=TopicClassifier(embedding_model=None),
            router=None,
            memory_manager=None,
        )
        await mgr.initialize()

        assert mgr.current_session is not None
        assert mgr.current_session.topic == "general"
        sessions = await mgr.list_sessions()
        assert len(sessions) == 1

    @pytest.mark.asyncio
    async def test_new_session_creates_with_topic(self):
        from internal.session.session_manager import SessionManager

        await self.store.init()
        mgr = SessionManager(
            session_store=self.store,
            classifier=TopicClassifier(embedding_model=None),
            router=None,
            memory_manager=None,
        )
        await mgr.initialize()

        session = await mgr.create_session(topic="coding", inherit_from=None)
        assert session.topic == "coding"
        assert session.session_id is not None

    @pytest.mark.asyncio
    async def test_list_sessions_returns_all(self):
        from internal.session.session_manager import SessionManager

        await self.store.init()
        mgr = SessionManager(
            session_store=self.store,
            classifier=TopicClassifier(embedding_model=None),
            router=None,
            memory_manager=None,
        )
        await mgr.initialize()
        await mgr.create_session(topic="coding")
        await mgr.create_session(topic="translation")

        sessions = await mgr.list_sessions()
        assert len(sessions) == 3  # default + coding + translation

    @pytest.mark.asyncio
    async def test_switch_session_updates_current(self):
        from internal.session.session_manager import SessionManager

        await self.store.init()
        mgr = SessionManager(
            session_store=self.store,
            classifier=TopicClassifier(embedding_model=None),
            router=None,
            memory_manager=None,
        )
        await mgr.initialize()
        coding = await mgr.create_session(topic="coding")

        switched = await mgr.switch_to(coding.session_id)
        assert switched is True
        assert mgr.current_session.session_id == coding.session_id


class TestSessionManagerRouting:
    """Tests for auto-routing on message input."""

    @pytest.mark.asyncio
    async def test_route_message_switches_when_classifier_matches(self):
        from internal.session.session_manager import SessionManager

        mock_memory = MagicMock()
        mock_memory.switch_session = AsyncMock(return_value=True)
        mock_memory.new_session = AsyncMock()
        mock_memory.list_sessions = MagicMock(return_value=[])
        mock_memory.current_session_info = MagicMock(return_value=None)

        temp_dir = tempfile.TemporaryDirectory()
        store = SessionStore(data_dir=temp_dir.name)
        await store.init()
        mgr = SessionManager(
            session_store=store,
            classifier=TopicClassifier(embedding_model=None),
            router=None,
            memory_manager=mock_memory,
        )
        await mgr.initialize()

        await mgr.create_session(topic="coding")

        action, _ = await mgr.route_message("帮我写一段代码")
        assert action in (RouteAction.SWITCH, RouteAction.CREATE)
        temp_dir.cleanup()

    @pytest.mark.asyncio
    async def test_route_message_stays_when_no_match(self):
        from internal.session.session_manager import SessionManager

        mock_memory = MagicMock()
        mock_memory.switch_session = AsyncMock(return_value=True)
        mock_memory.new_session = AsyncMock()
        mock_memory.list_sessions = MagicMock(return_value=[])
        mock_memory.current_session_info = MagicMock(return_value=None)

        temp_dir = tempfile.TemporaryDirectory()
        store = SessionStore(data_dir=temp_dir.name)
        await store.init()
        mgr = SessionManager(
            session_store=store,
            classifier=TopicClassifier(embedding_model=None),
            router=None,
            memory_manager=mock_memory,
        )
        await mgr.initialize()

        action, _ = await mgr.route_message("你好")
        assert action == RouteAction.STAY
        temp_dir.cleanup()
