import pytest
import torch
from internal.rag.index import FAISSIndex
from internal.rag.document import Document


@pytest.mark.skipif(
    not pytest.importorskip("faiss"),
    reason="FAISS not installed"
)
class TestFAISSIndex:
    def test_build_empty_index(self):
        index = FAISSIndex(dimension=384)
        assert index.is_available
        index.build(torch.empty((0, 384)), [])
        assert index.size == 0

    def test_build_index_with_embeddings(self):
        index = FAISSIndex(dimension=3)
        embeddings = torch.tensor([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ])
        docs = [
            Document(content="doc 1", source="test1.txt"),
            Document(content="doc 2", source="test2.txt"),
            Document(content="doc 3", source="test3.txt"),
        ]
        
        index.build(embeddings, docs)
        assert index.size == 3

    def test_search(self):
        index = FAISSIndex(dimension=3)
        embeddings = torch.tensor([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ])
        docs = [
            Document(content="doc 1", source="test1.txt"),
            Document(content="doc 2", source="test2.txt"),
            Document(content="doc 3", source="test3.txt"),
        ]
        index.build(embeddings, docs)
        
        # Search for a vector closest to first document
        query = torch.tensor([0.9, 0.1, 0.0])
        results = index.search(query, top_k=2)
        
        assert len(results) == 2
        # First result should be the first document
        assert results[0][1].source == "test1.txt"
        # Similarity should be higher than second
        assert results[0][0] > results[1][0]

    def test_search_empty_index_returns_empty(self):
        index = FAISSIndex(dimension=3)
        index.build(torch.empty((0, 3)), [])
        
        query = torch.tensor([1.0, 0.0, 0.0])
        results = index.search(query, top_k=3)
        assert len(results) == 0
