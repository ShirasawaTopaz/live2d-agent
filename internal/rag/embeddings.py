import logging
from typing import List
import torch

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generate embeddings using a local lightweight embedding model.
    Uses BAAI/bge-small-zh-v1.5 optimized for Chinese RAG."""
    
    DEFAULT_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
    
    _model_cache = None
    _tokenizer_cache = None
    
    def __init__(self, model_name: str = None, device: str = None):
        self.model_name = model_name or self.DEFAULT_MODEL_NAME
        self._device = device
        self._model = None
        self._tokenizer = None
        
    @property
    def is_loaded(self) -> bool:
        return self._model is not None and self._tokenizer is not None
        
    def load(self) -> None:
        """Lazy load the embedding model."""
        if self.is_loaded:
            return
            
        if self._model_cache is not None:
            # Use cached model if already loaded
            self._model = self._model_cache
            self._tokenizer = self._tokenizer_cache
            logger.info(f"Using cached embedding model: {self.model_name}")
            return
            
        logger.info(f"Loading embedding model: {self.model_name}")
        
        try:
            from transformers import AutoTokenizer, AutoModel
        except ImportError:
            logger.error("transformers not available, cannot load embeddings")
            raise
            
        if self._device is None:
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModel.from_pretrained(self.model_name).to(self._device)
            # Cache for future use
            EmbeddingGenerator._model_cache = self._model
            EmbeddingGenerator._tokenizer_cache = self._tokenizer
            logger.info(f"Embedding model {self.model_name} loaded successfully on {self._device}")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}", exc_info=True)
            raise
            
    def _mean_pooling(self, model_output, attention_mask):
        """Mean pooling to get sentence embeddings."""
        token_embeddings = model_output[0]
        input_mask = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * input_mask, 1) / torch.clamp(input_mask.sum(1), min=1e-9)
        
    @torch.no_grad()
    def embed_documents(self, texts: List[str]) -> torch.Tensor:
        """Generate embeddings for a list of documents."""
        if not self.is_loaded:
            self.load()
            
        encoded_input = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt"
        ).to(self._device)
        
        model_output = self._model(**encoded_input)
        embeddings = self._mean_pooling(model_output, encoded_input["attention_mask"])
        
        # Normalize embeddings
        embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
        
        return embeddings.cpu()
        
    @torch.no_grad()
    def embed_query(self, query: str) -> torch.Tensor:
        """Generate embedding for a single query."""
        # For BGE models, instructions are added for queries
        query = f"Represent this sentence for searching relevant passages: {query}"
        return self.embed_documents([query])[0]
