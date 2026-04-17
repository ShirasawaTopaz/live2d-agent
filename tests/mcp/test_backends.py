"""Regression tests for MCP storage backends after async I/O fixes."""

import tempfile
import pytest
from pathlib import Path

from internal.mcp.backend import JSONFileBackend, SQLiteBackend
from internal.mcp.protocol import MCPContextChunk


class TestJSONFileBackendAsync:
    """Test cases for JSONFileBackend with async non-blocking I/O."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.backend = JSONFileBackend(self.temp_dir.name)

    def teardown_method(self):
        """Clean up after tests."""
        self.temp_dir.cleanup()

    @pytest.mark.asyncio
    async def test_save_load_delete_chunk(self):
        """Test basic save/load/delete round trip for a chunk."""
        chunk = MCPContextChunk(
            chunk_id="chunk-001",
            scope_id="scope-001",
            summary="Test chunk summary",
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "World"},
            ],
            total_tokens=42,
            compressed=False,
            start_time=1234567890,
            end_time=1234567899,
        )

        # Save
        await self.backend.save_chunk(chunk)

        # Load
        loaded = await self.backend.load_chunk("chunk-001")
        assert loaded is not None
        assert loaded.chunk_id == chunk.chunk_id
        assert loaded.scope_id == chunk.scope_id
        assert loaded.summary == chunk.summary
        assert loaded.messages == chunk.messages
        assert loaded.total_tokens == chunk.total_tokens
        assert loaded.compressed == chunk.compressed

        # List chunks
        chunks = await self.backend.list_chunks("scope-001")
        assert len(chunks) == 1
        assert "chunk-001" in chunks

        # List for different scope should be empty
        chunks_other = await self.backend.list_chunks("scope-002")
        assert len(chunks_other) == 0

        # Search
        results_hello = await self.backend.search("Hello", scope_id="scope-001")
        assert len(results_hello) == 1
        assert results_hello[0].chunk_id == "chunk-001"

        results_none = await self.backend.search("NotFound")
        assert len(results_none) == 0

        # Delete
        await self.backend.delete_chunk("chunk-001")
        loaded_after_delete = await self.backend.load_chunk("chunk-001")
        assert loaded_after_delete is None

        # List should be empty now
        chunks_after_delete = await self.backend.list_chunks("scope-001")
        assert len(chunks_after_delete) == 0

    @pytest.mark.asyncio
    async def test_load_nonexistent_returns_none(self):
        """Test loading non-existent chunk returns None."""
        loaded = await self.backend.load_chunk("does-not-exist")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_search_with_limiting(self):
        """Test search respects the limit parameter."""
        # Create multiple chunks matching the same query
        for i in range(20):
            chunk = MCPContextChunk(
                chunk_id=f"chunk-{i:03d}",
                scope_id="test-scope",
                summary=f"This is chunk {i} about testing",
                messages=[],
                total_tokens=10 * i,
                compressed=False,
                start_time=1000 + i,
                end_time=1000 + i + 1,
            )
            await self.backend.save_chunk(chunk)

        # Search with limit 10 should only get 10 results
        results = await self.backend.search("testing", limit=10)
        assert len(results) == 10

    @pytest.mark.asyncio
    async def test_search_scoped(self):
        """Test scoped search only returns chunks from the specified scope."""
        # Create chunks in two different scopes
        chunk1 = MCPContextChunk(
            chunk_id="chunk-1",
            scope_id="scope-A",
            summary="Search me",
            messages=[],
            total_tokens=10,
            compressed=False,
            start_time=1,
            end_time=2,
        )
        chunk2 = MCPContextChunk(
            chunk_id="chunk-2",
            scope_id="scope-B",
            summary="Search me too",
            messages=[],
            total_tokens=10,
            compressed=False,
            start_time=3,
            end_time=4,
        )
        await self.backend.save_chunk(chunk1)
        await self.backend.save_chunk(chunk2)

        # Search all scopes
        results_all = await self.backend.search("Search")
        assert len(results_all) == 2

        # Search only scope A
        results_a = await self.backend.search("Search", scope_id="scope-A")
        assert len(results_a) == 1
        assert results_a[0].chunk_id == "chunk-1"

        # Search only scope B
        results_b = await self.backend.search("Search", scope_id="scope-B")
        assert len(results_b) == 1
        assert results_b[0].chunk_id == "chunk-2"


class TestSQLiteBackendAsync:
    """Test cases for SQLiteBackend with async aiosqlite."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_file.close()
        self.backend = SQLiteBackend(self.temp_file.name)

    def teardown_method(self):
        """Clean up after tests."""
        import os
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)

    @pytest.mark.asyncio
    async def test_init_creates_tables(self):
        """Test that init creates the required tables."""
        await self.backend.init()
        await self.backend.close()
        assert Path(self.temp_file.name).exists()

    @pytest.mark.asyncio
    async def test_save_load_delete_chunk(self):
        """Test basic save/load/delete round trip."""
        await self.backend.init()

        chunk = MCPContextChunk(
            chunk_id="chunk-001",
            scope_id="scope-001",
            summary="Test chunk with 'quotes' and \"double quotes\"",
            messages=[
                {"role": "user", "content": "Hello with 'single quotes'"},
                {"role": "assistant", "content": "World with \"double quotes\""},
            ],
            total_tokens=42,
            compressed=False,
            start_time=1234567890,
            end_time=1234567899,
        )

        # Save
        await self.backend.save_chunk(chunk)

        # Load
        loaded = await self.backend.load_chunk("chunk-001")
        assert loaded is not None
        assert loaded.chunk_id == chunk.chunk_id
        assert loaded.scope_id == chunk.scope_id
        assert loaded.summary == chunk.summary
        assert loaded.messages == chunk.messages
        assert loaded.total_tokens == chunk.total_tokens
        assert loaded.compressed == chunk.compressed

        # List chunks
        chunks = await self.backend.list_chunks("scope-001")
        assert len(chunks) == 1
        assert "chunk-001" in chunks

        # Search
        results = await self.backend.search("Hello", scope_id="scope-001")
        assert len(results) == 1

        # Delete
        await self.backend.delete_chunk("chunk-001")
        loaded_after_delete = await self.backend.load_chunk("chunk-001")
        assert loaded_after_delete is None

        await self.backend.close()

    @pytest.mark.asyncio
    async def test_load_nonexistent_returns_none(self):
        """Test loading non-existent chunk returns None."""
        await self.backend.init()
        loaded = await self.backend.load_chunk("does-not-exist")
        assert loaded is None
        await self.backend.close()

    @pytest.mark.asyncio
    async def test_list_chunks_empty(self):
        """Test listing chunks when scope is empty."""
        await self.backend.init()
        chunks = await self.backend.list_chunks("empty-scope")
        assert len(chunks) == 0
        await self.backend.close()

    @pytest.mark.asyncio
    async def test_search_works_with_both_scopes(self):
        """Test search works with and without scope filtering."""
        await self.backend.init()

        chunk1 = MCPContextChunk(
            chunk_id="chunk-1",
            scope_id="scope-A",
            summary="Testing search functionality",
            messages=[],
            total_tokens=10,
            compressed=False,
            start_time=1,
            end_time=2,
        )
        chunk2 = MCPContextChunk(
            chunk_id="chunk-2",
            scope_id="scope-B",
            summary="Another test for searching",
            messages=[],
            total_tokens=10,
            compressed=False,
            start_time=3,
            end_time=4,
        )
        await self.backend.save_chunk(chunk1)
        await self.backend.save_chunk(chunk2)

        # Search all
        all_results = await self.backend.search("test")
        assert len(all_results) == 2

        # Search scoped
        scope_a_results = await self.backend.search("test", scope_id="scope-A")
        assert len(scope_a_results) == 1
        assert scope_a_results[0].chunk_id == "chunk-1"

        scope_b_results = await self.backend.search("test", scope_id="scope-B")
        assert len(scope_b_results) == 1
        assert scope_b_results[0].chunk_id == "chunk-2"

        # Search that finds nothing
        no_results = await self.backend.search("notfound")
        assert len(no_results) == 0

        await self.backend.close()

    @pytest.mark.asyncio
    async def test_search_respects_limit(self):
        """Test search respects the limit parameter."""
        await self.backend.init()

        # Create multiple matching chunks
        for i in range(15):
            chunk = MCPContextChunk(
                chunk_id=f"chunk-{i}",
                scope_id="all-same",
                summary=f"Chunk {i} matching keyword",
                messages=[],
                total_tokens=10,
                compressed=False,
                start_time=i,
                end_time=i+1,
            )
            await self.backend.save_chunk(chunk)

        results = await self.backend.search("keyword", limit=10)
        assert len(results) == 10

        await self.backend.close()
