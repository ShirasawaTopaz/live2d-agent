import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from internal.rag.document import DocumentLoader, DocumentChunker, Document


@pytest.fixture
def loader():
    return DocumentLoader(max_file_size_mb=1)


@pytest.fixture
def chunker():
    return DocumentChunker(chunk_size=100, chunk_overlap=20)


class TestDocumentLoader:
    def test_load_empty_directory(self, loader):
        with TemporaryDirectory() as tmpdir:
            docs = loader.load_from_directory(tmpdir)
            assert len(docs) == 0

    def test_load_single_txt_file(self, loader):
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            content = "This is a test document content.\nIt has multiple lines.\n\nSome empty lines here.\nEnd of content."
            file_path.write_text(content, encoding="utf-8")
            
            docs = loader.load_from_directory(tmpdir)
            assert len(docs) == 1
            assert docs[0].content.strip() == content.strip()
            assert str(file_path) in docs[0].source

    def test_skip_large_file(self, loader):
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "large.txt"
            # Create 2MB file which exceeds the 1MB limit
            content = "x" * (2 * 1024 * 1024 + 100)
            file_path.write_text(content, encoding="utf-8")
            
            docs = loader.load_from_directory(tmpdir)
            assert len(docs) == 0  # Should be skipped

    def test_skip_empty_file(self, loader):
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "empty.txt"
            file_path.write_text("", encoding="utf-8")
            
            docs = loader.load_from_directory(tmpdir)
            assert len(docs) == 0  # Should be skipped

    def test_load_multiple_files(self, loader):
        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "file1.txt").write_text("Content 1", encoding="utf-8")
            (Path(tmpdir) / "file2.md").write_text("## Content 2\nmarkdown content", encoding="utf-8")
            (Path(tmpdir) / "ignore.me").write_text("This should not load", encoding="utf-8")
            
            docs = loader.load_from_directory(tmpdir)
            assert len(docs) == 2


class TestDocumentChunker:
    def test_chunk_small_document(self, chunker):
        doc = Document(content="Short document", source="test.txt")
        chunks = chunker.chunk_document(doc)
        assert len(chunks) == 1
        assert chunks[0].content == doc.content

    def test_chunk_large_document(self, chunker):
        # Create a document with 200 words
        words = ["word"] * 200
        content = " ".join(words)
        doc = Document(content=content, source="test.txt")
        
        chunks = chunker.chunk_document(doc)
        # With chunk_size=100 and overlap=20, we expect ~3 chunks:
        # 0-100, 80-180, 160-200 = 3 chunks
        assert len(chunks) == 3
        # Each chunk should have at most 100 words
        for chunk in chunks:
            assert len(chunk.content.split()) <= 100

    def test_chunk_overlap(self, chunker):
        words = [str(i) for i in range(100)]
        content = " ".join(words)
        doc = Document(content=content, source="test.txt")
        
        chunks = chunker.chunk_document(doc)
        # 0-100 would be one chunk if no overlap, but with 100/20:
        # 0-100, 80-100 = 2 chunks
        assert len(chunks) == 2
        # Second chunk should start at word 80, so overlap of 20 words
        first_words = set(chunks[0].content.split()[-20:])
        second_words = set(chunks[1].content.split()[:20])
        overlap = first_words & second_words
        assert len(overlap) == 20
