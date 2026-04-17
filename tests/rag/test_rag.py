import pytest
from tempfile import TemporaryDirectory
from pathlib import Path
from internal.config.config import RAGConfig
from internal.rag.rag import RAGManager


@pytest.mark.skipif(
    not pytest.importorskip("faiss"),
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
