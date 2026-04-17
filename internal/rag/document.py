import os
import logging
from dataclasses import dataclass
from typing import List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Document:
    """Represents a document with content and metadata."""
    content: str
    source: str
    chunk_id: int = 0


class DocumentLoader:
    """Loads documents from a directory, supports .txt and .md files."""
    
    def __init__(self, max_file_size_mb: int = 10):
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        
    def load_from_directory(self, directory: str) -> List[Document]:
        """Load all supported documents from the directory."""
        documents = []
        dir_path = Path(directory)
        
        if not dir_path.exists():
            logger.warning(f"Document directory {directory} does not exist")
            return documents
            
        for file_path in dir_path.glob("**/*"):
            if not file_path.is_file():
                continue
                
            if file_path.suffix.lower() not in [".txt", ".md"]:
                continue
                
            file_size = file_path.stat().st_size
            if file_size > self.max_file_size_bytes:
                logger.warning(
                    f"Skipping large file {file_path}: {file_size/(1024*1024):.1f}MB "
                    f"(max {self.max_file_size_bytes/(1024*1024):.1f}MB)"
                )
                continue
                
            try:
                content = self._load_file(file_path)
                content = self._preprocess(content)
                if not content.strip():
                    logger.warning(f"Skipping empty file {file_path}")
                    continue
                    
                documents.append(Document(content=content, source=str(file_path)))
                logger.debug(f"Loaded document: {file_path}")
            except Exception as e:
                logger.error(f"Error loading {file_path}: {e}", exc_info=True)
                continue
                
        logger.info(f"Loaded {len(documents)} documents from {directory}")
        return documents
        
    def _load_file(self, file_path: Path) -> str:
        """Load file content with encoding handling."""
        for encoding in ["utf-8", "gbk", "gb2312", "latin1"]:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        # If all decodings fail, try with latin1 (always succeeds)
        with open(file_path, "r", encoding="latin1") as f:
            return f.read()
            
    def _preprocess(self, content: str) -> str:
        """Preprocess content: normalize whitespace and line endings."""
        # Normalize line endings
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        # Remove excessive blank lines (keep max 2 consecutive)
        lines = content.split("\n")
        processed_lines = []
        consecutive_blanks = 0
        for line in lines:
            stripped = line.rstrip()
            if not stripped:
                consecutive_blanks += 1
                if consecutive_blanks <= 2:
                    processed_lines.append(stripped)
            else:
                consecutive_blanks = 0
                processed_lines.append(stripped)
        content = "\n".join(processed_lines)
        # Strip leading/trailing whitespace
        return content.strip()


class DocumentChunker:
    """Splits documents into fixed-size chunks with overlap."""
    
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
    def chunk_document(self, document: Document) -> List[Document]:
        """Split a single document into overlapping chunks."""
        content = document.content
        words = content.split()
        
        if len(words) <= self.chunk_size:
            return [document]
            
        chunks = []
        start = 0
        chunk_id = 0
        
        while start < len(words):
            end = min(start + self.chunk_size, len(words))
            chunk_words = words[start:end]
            chunk_content = " ".join(chunk_words)
            
            chunks.append(Document(
                content=chunk_content,
                source=document.source,
                chunk_id=chunk_id
            ))
            chunk_id += 1
            
            # Move start forward by chunk_size - overlap
            start += self.chunk_size - self.chunk_overlap
            if start >= len(words):
                break
                
        logger.debug(f"Split document {document.source} into {len(chunks)} chunks")
        return chunks
        
    def chunk_all(self, documents: List[Document]) -> List[Document]:
        """Split all documents into chunks."""
        all_chunks = []
        for doc in documents:
            chunks = self.chunk_document(doc)
            all_chunks.extend(chunks)
        logger.info(f"Created {len(all_chunks)} chunks from {len(documents)} documents")
        return all_chunks
