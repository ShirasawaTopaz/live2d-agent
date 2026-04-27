import pytest
import torch
from internal.rag.embeddings import EmbeddingGenerator


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA not available")
class TestEmbeddingGenerator:
    def test_load_model(self):
        # This will actually download the model first time
        generator = EmbeddingGenerator()
        generator.load()
        assert generator.is_loaded
        assert generator._model is not None
        assert generator._tokenizer is not None

    def test_embed_documents(self):
        generator = EmbeddingGenerator()
        generator.load()
        
        texts = ["Hello world", "Second test document"]
        embeddings = generator.embed_documents(texts)
        
        assert embeddings.shape[0] == 2
        # BGE small has dimension 384
        assert embeddings.shape[1] == 384
        assert isinstance(embeddings, torch.Tensor)

    def test_embed_query(self):
        generator = EmbeddingGenerator()
        generator.load()
        
        embedding = generator.embed_query("test query")
        
        assert embedding.shape[0] == 384
        assert isinstance(embedding, torch.Tensor)
