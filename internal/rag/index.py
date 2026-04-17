import logging
import os
import pickle
from typing import List, Tuple, Optional
import torch

logger = logging.getLogger(__name__)

# Try to import faiss, handle gracefully if not available
faiss = None
try:
    # Try faiss-gpu first
    try:
        import faiss
        if faiss.get_num_gpus() > 0:
            logger.info("Using faiss-gpu")
        else:
            logger.info("Using faiss-cpu (no GPU detected)")
    except ImportError:
        import faiss_cpu as faiss
        logger.info("Using faiss-cpu")
except ImportError:
    faiss = None
    logger.warning("FAISS not available, RAG functionality will be disabled")

from internal.rag.document import Document


class FAISSIndex:
    """FAISS index for efficient similarity search."""
    
    def __init__(self, dimension: int = None):
        self._faiss_available = faiss is not None
        self._index = None
        self._documents: List[Document] = []
        self._dimension = dimension
        
    @property
    def is_available(self) -> bool:
        return self._faiss_available
        
    @property
    def size(self) -> int:
        if self._index is None:
            return 0
        return self._index.ntotal
        
    def build(self, embeddings: torch.Tensor, documents: List[Document]) -> None:
        """Build the FAISS index from embeddings and documents."""
        if not self._faiss_available:
            logger.warning("FAISS not available, cannot build index")
            return
            
        if len(embeddings) == 0:
            logger.warning("No embeddings provided, creating empty index")
            self._index = None
            self._documents = []
            return
            
        # Get dimension from embeddings if not set
        if self._dimension is None:
            self._dimension = embeddings.shape[1]
            
        # Create a flat L2 index (good for small to medium datasets)
        self._index = faiss.IndexFlatL2(self._dimension)
        
        # Add embeddings to index
        embeddings_np = embeddings.numpy()
        self._index.add(embeddings_np)
        self._documents = documents
        
        logger.info(f"Built FAISS index with {self.size} vectors of dimension {self._dimension}")
        
    def search(self, query_embedding: torch.Tensor, top_k: int = 3) -> List[Tuple[float, Document]]:
        """Search for similar documents given query embedding."""
        if not self._faiss_available or self._index is None or self.size == 0:
            return []
            
        query_np = query_embedding.unsqueeze(0).numpy()
        distances, indices = self._index.search(query_np, top_k)
        
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if 0 <= idx < len(self._documents):
                # Convert L2 distance to similarity score (lower distance = more similar)
                similarity = 1.0 / (1.0 + dist)
                results.append((similarity, self._documents[idx]))
                
        # Sort by similarity (higher = better)
        results.sort(reverse=True, key=lambda x: x[0])
        return results
        
    def save(self, path: str) -> None:
        """Save the index and documents to disk."""
        if not self._faiss_available:
            return
            
        if self._index is None:
            logger.warning("No index to save")
            return
            
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # Save FAISS index
        index_path = path + ".index"
        faiss.write_index(self._index, index_path)
        
        # Save documents
        docs_path = path + ".docs.pkl"
        with open(docs_path, "wb") as f:
            pickle.dump(self._documents, f)
            
        logger.info(f"Saved FAISS index to {path}")
        
    def load(self, path: str) -> bool:
        """Load index and documents from disk."""
        if not self._faiss_available:
            return False
            
        index_path = path + ".index"
        docs_path = path + ".docs.pkl"
        
        if not os.path.exists(index_path) or not os.path.exists(docs_path):
            logger.warning(f"Index files not found at {path}")
            return False
            
        try:
            self._index = faiss.read_index(index_path)
            with open(docs_path, "rb") as f:
                self._documents = pickle.load(f)
            logger.info(f"Loaded FAISS index with {self.size} documents")
            return True
        except Exception as e:
            logger.error(f"Failed to load index: {e}", exc_info=True)
            return False
            
    def clear(self) -> None:
        """Clear the index and documents."""
        self._index = None
        self._documents = []
