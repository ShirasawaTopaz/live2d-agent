"""Regression tests for memory storage backends after async I/O fixes."""

import tempfile
import pytest
from pathlib import Path
from datetime import datetime

from internal.memory.storage._json import JSONStorage
from internal.memory.storage._sqlite import SQLiteStorage
from internal.memory._types import SessionInfo, LongTermEntry


class TestJSONStorageAsync:
    """Test cases for JSONStorage with async non-blocking I/O."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = JSONStorage(self.temp_dir.name)

    def teardown_method(self):
        """Clean up after tests."""
        self.temp_dir.cleanup()

    @pytest.mark.asyncio
    async def test_init_creates_directories(self):
        """Test that init creates the required directory structure."""
        await self.storage.init()
        assert (Path(self.temp_dir.name) / "sessions").exists()
        assert (Path(self.temp_dir.name) / "long_term").exists()

    @pytest.mark.asyncio
    async def test_save_load_delete_session(self):
        """Test basic save/load/delete round trip for a session."""
        await self.storage.init()

        # Create test session data
        session_id = "test-session-001"
        test_data = {
            "info": {
                "session_id": session_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "title": "Test Session",
                "message_count": 5,
                "is_compressed": False,
            },
            "messages": [
                {"role": "user", "content": "Hello world"},
                {"role": "assistant", "content": "Hi there!"},
            ]
        }

        # Save
        await self.storage.save_session(session_id, test_data)

        # Load
        loaded = await self.storage.load_session(session_id)
        assert loaded is not None
        assert loaded["info"]["session_id"] == session_id
        assert loaded["messages"] == test_data["messages"]

        # List sessions
        sessions = await self.storage.list_sessions()
        assert len(sessions) == 1
        assert isinstance(sessions[0], SessionInfo)
        assert sessions[0].session_id == session_id

        # Delete
        deleted = await self.storage.delete_session(session_id)
        assert deleted is True
        loaded_after_delete = await self.storage.load_session(session_id)
        assert loaded_after_delete is None

        # List should be empty now
        sessions_after_delete = await self.storage.list_sessions()
        assert len(sessions_after_delete) == 0

    @pytest.mark.asyncio
    async def test_load_nonexistent_returns_none(self):
        """Test that loading a non-existent session returns None."""
        await self.storage.init()
        loaded = await self.storage.load_session("does-not-exist")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self):
        """Test that deleting a non-existent session returns False."""
        await self.storage.init()
        deleted = await self.storage.delete_session("does-not-exist")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_long_term_save_query_delete(self):
        """Test long-term memory save/query/delete operations."""
        await self.storage.init()

        # Create test long-term entries
        entry1 = LongTermEntry(
            id="lt-001",
            content="This is a test entry about Python programming",
            keywords=["python", "programming", "test"],
            source_session_id="session-001",
            created_at=datetime.now(),
            metadata={}
        )

        entry2 = LongTermEntry(
            id="lt-002",
            content="This entry talks about machine learning and AI",
            keywords=["ai", "machine-learning"],
            source_session_id="session-001",
            created_at=datetime.now(),
            metadata={}
        )

        entry3 = LongTermEntry(
            id="lt-003",
            content="Another Python related article",
            keywords=["python", "tutorial"],
            source_session_id="session-002",
            created_at=datetime.now(),
            metadata={}
        )

        # Save all three
        await self.storage.save_long_term(entry1)
        await self.storage.save_long_term(entry2)
        await self.storage.save_long_term(entry3)

        # Query for python
        results_python = await self.storage.query_long_term("python")
        assert len(results_python) == 2
        # Results should be sorted by created_at descending
        assert {entry.id for entry in results_python} == {"lt-001", "lt-003"}

        # Query for ai
        results_ai = await self.storage.query_long_term("ai")
        assert len(results_ai) == 1
        assert results_ai[0].id == "lt-002"

        # Delete entry1
        deleted = await self.storage.delete_long_term("lt-001")
        assert deleted is True

        # Query python again should only have entry3
        results_after_delete = await self.storage.query_long_term("python")
        assert len(results_after_delete) == 1
        assert results_after_delete[0].id == "lt-003"

        # Delete returns false for non-existent
        deleted_nonexistent = await self.storage.delete_long_term("lt-999")
        assert deleted_nonexistent is False

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self):
        """Test listing sessions when storage is empty."""
        await self.storage.init()
        sessions = await self.storage.list_sessions()
        assert len(sessions) == 0


class TestSQLiteStorageAsync:
    """Test cases for SQLiteStorage with async I/O and proper JSON serialization."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_file.close()
        self.storage = SQLiteStorage(self.temp_file.name)

    def teardown_method(self):
        """Clean up after tests."""
        import os
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)

    @pytest.mark.asyncio
    async def test_init_creates_tables(self):
        """Test that init creates the required tables."""
        await self.storage.init()
        await self.storage.close()
        assert Path(self.temp_file.name).exists()

    @pytest.mark.asyncio
    async def test_save_load_delete_session_json_serialization(self):
        """Test save/load/delete with proper JSON serialization (no string hack)."""
        await self.storage.init()

        # Create test session data with quotes and special characters
        session_id = "test-session-001"
        test_data = {
            "info": {
                "session_id": session_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "title": "Test Session with 'quotes' and \"double quotes\"",
                "message_count": 3,
                "is_compressed": False,
            },
            "messages": [
                {"role": "user", "content": "Hello world with 'single quotes'"},
                {"role": "assistant", "content": "Hi there with \"double quotes\""},
                {"role": "user", "content": "Special chars: '\"\\"},
            ]
        }

        # Save
        await self.storage.save_session(session_id, test_data)

        # Load - this verifies JSON serialization works correctly
        loaded = await self.storage.load_session(session_id)
        assert loaded is not None
        assert loaded["info"]["session_id"] == session_id
        assert loaded["info"]["title"] == test_data["info"]["title"]
        assert len(loaded["messages"]) == 3
        assert loaded["messages"][0]["content"] == test_data["messages"][0]["content"]
        assert loaded["messages"][1]["content"] == test_data["messages"][1]["content"]
        assert loaded["messages"][2]["content"] == test_data["messages"][2]["content"]

        # List sessions
        sessions = await self.storage.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].session_id == session_id

        # Delete
        deleted = await self.storage.delete_session(session_id)
        assert deleted is True
        loaded_after_delete = await self.storage.load_session(session_id)
        assert loaded_after_delete is None

        await self.storage.close()

    @pytest.mark.asyncio
    async def test_long_term_save_query_delete(self):
        """Test long-term memory operations with SQLite."""
        await self.storage.init()

        entry1 = LongTermEntry(
            id="lt-001",
            content="This is a test entry about Python programming",
            keywords=["python", "programming", "test"],
            source_session_id="session-001",
            created_at=datetime.now(),
            metadata={"author": "test", "version": 1}
        )

        entry2 = LongTermEntry(
            id="lt-002",
            content="This entry talks about machine learning and AI",
            keywords=["ai", "machine-learning"],
            source_session_id="session-001",
            created_at=datetime.now(),
            metadata={}
        )

        entry3 = LongTermEntry(
            id="lt-003",
            content="Another Python related article",
            keywords=["python", "tutorial"],
            source_session_id="session-002",
            created_at=datetime.now(),
            metadata={"source": "article"}
        )

        # Save all three
        await self.storage.save_long_term(entry1)
        await self.storage.save_long_term(entry2)
        await self.storage.save_long_term(entry3)

        # Query for python
        results_python = await self.storage.query_long_term("python")
        assert len(results_python) == 2
        assert {entry.id for entry in results_python} == {"lt-001", "lt-003"}

        # Query for ai
        results_ai = await self.storage.query_long_term("ai")
        assert len(results_ai) == 1
        assert results_ai[0].id == "lt-002"

        # Delete entry1
        deleted = await self.storage.delete_long_term("lt-001")
        assert deleted is True

        # Query python again should only have entry3
        results_after_delete = await self.storage.query_long_term("python")
        assert len(results_after_delete) == 1
        assert results_after_delete[0].id == "lt-003"

        await self.storage.close()

    @pytest.mark.asyncio
    async def test_load_nonexistent_returns_none(self):
        """Test loading non-existent session."""
        await self.storage.init()
        loaded = await self.storage.load_session("does-not-exist")
        assert loaded is None
        await self.storage.close()

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self):
        """Test listing sessions when empty."""
        await self.storage.init()
        sessions = await self.storage.list_sessions()
        assert len(sessions) == 0
        await self.storage.close()
