import pytest
from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace
from importlib.util import find_spec
from internal.config.config import RAGConfig
from internal.rag.rag import RAGManager


@pytest.mark.skipif(
    find_spec("faiss") is None,
    reason="FAISS not installed"
)
class TestRAGManager:
    def test_rag_disabled_returns_no_docs(self):
        config = RAGConfig(enabled=False)
        rag = RAGManager(config)
        assert not rag.is_enabled
        assert rag.initialize() is False
        docs = rag.retrieve("test query")
        assert len(docs) == 0

    def test_rag_enabled_empty_dir(self):
        with TemporaryDirectory() as tmpdir:
            config = RAGConfig(enabled=True, document_dir=tmpdir)
            rag = RAGManager(config)
            success = rag.initialize()
            assert success is True
            assert rag.is_enabled
            assert rag._index.size == 0
            docs = rag.retrieve("test query")
            assert len(docs) == 0

    def test_rag_with_documents(self):
        with TemporaryDirectory() as tmpdir:
            # Create three documents with distinct topics
            (Path(tmpdir) / "python.txt").write_text(
                "Python is a high-level programming language created by Guido van Rossum. "
                "It is widely used for web development, data science, machine learning, and automation."
            )
            (Path(tmpdir) / "javascript.txt").write_text(
                "JavaScript, often abbreviated as JS, is a programming language that conforms "
                "to the ECMAScript specification. It is primarily used for web development "
                "and client-side scripting in web browsers."
            )
            (Path(tmpdir) / "ai.txt").write_text(
                "Artificial intelligence (AI) is intelligence demonstrated by machines, "
                "contrary to the natural intelligence displayed by humans and animals. "
                "Machine learning is a subfield of AI focused on training models from data."
            )
            
            config = RAGConfig(
                enabled=True, 
                document_dir=tmpdir,
                chunk_size=200, 
                chunk_overlap=20,
                top_k=2
            )
            rag = RAGManager(config)
            success = rag.initialize()
            assert success is True
            assert rag._index.size > 0

    def test_retrieval_finds_relevant_document(self):
        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "python.txt").write_text(
                "Python is a high-level programming language created by Guido van Rossum. "
                "It is widely used for web development, data science, machine learning, and automation."
            )
            (Path(tmpdir) / "javascript.txt").write_text(
                "JavaScript, often abbreviated as JS, is a programming language that conforms "
                "to the ECMAScript specification. It is primarily used for web development "
                "and client-side scripting in web browsers."
            )
            
            config = RAGConfig(enabled=True, document_dir=tmpdir, chunk_size=200, top_k=1)
            rag = RAGManager(config)
            rag.initialize()
            
            # Query about Python should retrieve the Python document
            results = rag.retrieve("What programming language was created by Guido van Rossum?")
            assert len(results) == 1
            assert "python.txt" in results[0].source
            assert "Guido" in results[0].content

    def test_format_retrieved_context(self):
        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test1.txt").write_text("First test content")
            (Path(tmpdir) / "test2.txt").write_text("Second test content")
            
            config = RAGConfig(enabled=True, document_dir=tmpdir, top_k=2)
            rag = RAGManager(config)
            rag.initialize()
            
            # Search and format
            docs = rag.retrieve("test")
            context = rag.format_retrieved_context(docs)
            
            assert "## 参考文档" in context
            assert "### 文档 1" in context
            assert "First test content" in context
            assert "### 文档 2" in context
            assert "Second test content" in context

    def test_initialize_uses_fresh_cache(self):
        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "doc.txt").write_text("cacheable content")
            config = RAGConfig(enabled=True, document_dir=tmpdir, top_k=1)
            rag = RAGManager(config, index_cache_path=str(Path(tmpdir) / "cache"))
            rag._index._faiss_available = True
            rag._document_signature = lambda: {"digest": "abc"}

            calls: list[str] = []

            def fake_load(path: str) -> bool:
                calls.append(f"load:{path}")
                rag._index._index = SimpleNamespace(ntotal=1)
                rag._index._documents = []
                return True

            def fake_build(*_args, **_kwargs) -> None:
                calls.append("build")

            def fake_save(*_args, **_kwargs) -> None:
                calls.append("save")

            rag._index.load = fake_load
            rag._index.build = fake_build
            rag._index.save = fake_save

            manifest_path = Path(f"{rag.index_cache_path}.manifest.json")
            manifest_path.write_text(
                '{"document_dir": "x", "digest": "abc", "entries": []}',
                encoding="utf-8",
            )

            assert rag.initialize() is True
            assert calls == [f"load:{rag.index_cache_path}"]


def test_initialize_uses_fresh_cache_without_faiss():
    with TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "doc.txt").write_text("cacheable content")
        config = RAGConfig(enabled=True, document_dir=tmpdir, top_k=1)
        rag = RAGManager(config, index_cache_path=str(Path(tmpdir) / "cache"))
        rag._index._faiss_available = True
        rag._document_signature = lambda: {"digest": "abc"}

        calls: list[str] = []

        def fake_load(path: str) -> bool:
            calls.append(f"load:{path}")
            rag._index._index = SimpleNamespace(ntotal=1)
            rag._index._documents = []
            return True

        def fake_build(*_args, **_kwargs) -> None:
            calls.append("build")

        def fake_save(*_args, **_kwargs) -> None:
            calls.append("save")

        rag._index.load = fake_load
        rag._index.build = fake_build
        rag._index.save = fake_save

        manifest_path = Path(f"{rag.index_cache_path}.manifest.json")
        manifest_path.write_text(
            '{"document_dir": "x", "digest": "abc", "entries": []}',
            encoding="utf-8",
        )

        assert rag.initialize() is True
        assert calls == [f"load:{rag.index_cache_path}"]
