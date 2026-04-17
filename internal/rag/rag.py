import logging
from typing import List, Tuple, Optional
from pathlib import Path

from internal.config.config import RAGConfig
from internal.rag.document import DocumentLoader, DocumentChunker, Document
from internal.rag.embeddings import EmbeddingGenerator
from internal.rag.index import FAISSIndex

logger = logging.getLogger(__name__)


class RAGManager:
    """Main RAG manager that ties together all components:
    - Load documents from configured directory
    - Chunk documents
    - Generate embeddings
    - Build FAISS index
    - Retrieve relevant documents for a query
    """
    
    def __init__(self, config: RAGConfig, index_cache_path: str = "data/rag/index"):
        self.config = config
        self.index_cache_path = index_cache_path
        
        # Initialize components
        self._loader = DocumentLoader(max_file_size_mb=10)
        self._chunker = DocumentChunker(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap
        )
        self._embeddings = EmbeddingGenerator()
        self._index = FAISSIndex()
        
        self._initialized = False
        
    @property
    def is_enabled(self) -> bool:
        return self.config.enabled and self._index.is_available
        
    def initialize(self) -> bool:
        """Initialize RAG: load documents, build index."""
        if not self.config.enabled:
            logger.info("RAG is disabled in config")
            return False
            
        if not self._index.is_available:
            logger.warning("FAISS is not available, cannot initialize RAG")
            return False
            
        logger.info(f"Initializing RAG from document directory: {self.config.document_dir}")
        
        # Check if document directory is empty
        if not self.config.document_dir or not Path(self.config.document_dir).exists():
            logger.warning(f"Document directory {self.config.document_dir} does not exist or is empty")
            self._index.clear()
            self._initialized = True
            return True
            
        # Load all documents
        documents = self._loader.load_from_directory(self.config.document_dir)
        if not documents:
            logger.warning("No documents loaded, RAG initialized with empty index")
            self._index.clear()
            self._initialized = True
            return True
            
        # Check if any documents have changed (mtime based deduplication)
        # For now, we just rebuild the index on each startup
        # This keeps it simple for this iteration
        
        # Chunk documents
        chunks = self._chunker.chunk_all(documents)
        if not chunks:
            logger.warning("No chunks created from documents, RAG initialized with empty index")
            self._index.clear()
            self._initialized = True
            return True
            
        # Generate embeddings for all chunks
        chunk_texts = [chunk.content for chunk in chunks]
        logger.info(f"Generating embeddings for {len(chunk_texts)} chunks")
        
        try:
            embeddings = self._embeddings.embed_documents(chunk_texts)
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}", exc_info=True)
            return False
            
        # Build the index
        self._index.build(embeddings, chunks)
        
        # Optionally save to cache
        if self.index_cache_path:
            self._index.save(self.index_cache_path)
            
        self._initialized = True
        logger.info(f"RAG initialization complete. Index size: {self._index.size}")
        return True
        
    def retrieve(self, query: str, top_k: int = None) -> List[Document]:
        """Retrieve relevant documents for a query."""
        if not self.is_enabled or not self._initialized:
            return []
            
        if self._index.size == 0:
            return []
            
        top_k = top_k or self.config.top_k
        
        try:
            # Generate query embedding
            query_embedding = self._embeddings.embed_query(query)
            
            # Search the index
            results = self._index.search(query_embedding, top_k)
            
            # Return just the documents
            return [doc for (score, doc) in results]
        except Exception as e:
            logger.error(f"Error during retrieval: {e}", exc_info=True)
            return []
            
    def format_retrieved_context(self, documents: List[Document]) -> str:
        """Format retrieved documents into a context string for prompt injection."""
        if not documents:
            return ""
            
        context_parts = ["## 参考文档\n\n"]
        
        for i, doc in enumerate(documents, 1):
            source = Path(doc.source).name
            context_parts.append(f"### 文档 {i} ({source})\n")
            context_parts.append(doc.content.strip())
            context_parts.append("\n\n")
            
        return "".join(context_parts)
