import json
from pathlib import Path
from typing import List, Optional

from ..indexer.embedders.code_embedder import CodeEmbedder
from ..storage.vector_store import VectorStore
from ..storage.sparse_store import SparseStore
from ..indexer.parsers.tree_sitter_c import CodeChunk


class SearchResult:
    def __init__(self, chunk: CodeChunk, score: float, code: str = ""):
        self.chunk = chunk
        self.score = score
        self.code = code


class LineValidationResult:
    def __init__(self, is_valid: bool, actual_content: str = ""):
        self.is_valid = is_valid
        self.actual_content = actual_content


class HybridSearcher:
    def __init__(self, index_path: Optional[Path] = None, repo_path: Optional[Path] = None):
        self.index_path = Path(index_path) if index_path else None
        self.repo_path = repo_path
        
        if self.index_path:
            if repo_path is None:
                meta_file = self.index_path / "base" / "metadata.json"
                if meta_file.exists():
                    with open(meta_file) as f:
                        meta = json.load(f)
                    self.repo_path = Path(meta.get("repo_path", "."))
            
            self.vector_store = VectorStore(backend="qdrant", path=self.index_path / "base" / "qdrant")
            self.sparse_store = SparseStore(backend="meilisearch", path=self.index_path / "base" / "meili")
            self.chunks = self._load_chunks()
        else:
            self.vector_store = VectorStore(backend="memory")
            self.sparse_store = SparseStore(backend="memory")
            self.chunks = []
        
        self.embedder = CodeEmbedder()
    
    def _load_chunks(self) -> List[CodeChunk]:
        if not self.index_path:
            return []
        chunks_file = self.index_path / "base" / "chunks.json"
        if not chunks_file.exists():
            return []
        
        with open(chunks_file) as f:
            data = json.load(f)
        
        chunks = []
        for item in data:
            chunks.append(CodeChunk(
                name=item["name"],
                file_path=item["file_path"],
                start_line=item["start_line"],
                end_line=item["end_line"],
                chunk_type=item.get("chunk_type", "function"),
                subsys=item.get("subsys"),
            ))
        return chunks
    
    def _read_code(self, chunk: CodeChunk) -> str:
        if not self.repo_path:
            return ""
        
        file_path = self.repo_path / chunk.file_path
        if not file_path.exists():
            return ""
        
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                start = chunk.start_line - 1
                end = chunk.end_line
                if start < len(lines) and end <= len(lines):
                    return "".join(lines[start:end])
        except Exception:
            pass
        
        return ""
    
    def dense_search(self, query: str, top_k: int = 10) -> List[SearchResult]:
        query_emb = self.embedder.encode([query])[0]
        vector_results = self.vector_store.search(query_vector=query_emb, top_k=top_k)
        
        results = []
        for r in vector_results:
            chunk = self._find_chunk(r.id)
            if chunk:
                code = self._read_code(chunk)
                results.append(SearchResult(chunk, r.score, code))
        return results
    
    def sparse_search(self, query: str, top_k: int = 10) -> List[SearchResult]:
        sparse_results = self.sparse_store.search(query)
        
        results = []
        for sr in sparse_results[:top_k]:
            chunk = self._find_chunk(sr.symbol)
            if chunk:
                code = self._read_code(chunk)
                results.append(SearchResult(chunk, 0.5, code))
        return results
    
    def search(self, query: str, kconfig_filter=None, subsys=None, version=None, top_k: int = 10) -> List[SearchResult]:
        # Dense search (semantic)
        query_emb = self.embedder.encode([query])[0]
        vector_results = self.vector_store.search(
            query_vector=query_emb,
            top_k=top_k * 2,
        )
        
        # Sparse search (keyword)
        sparse_results = self.sparse_store.search(query)
        
        # RRF fusion
        fused = self._rrf_fusion(vector_results, sparse_results, k=60)
        
        results = []
        for r in fused[:top_k]:
            chunk_id = r.id
            chunk = self._find_chunk(chunk_id)
            
            if chunk and (not subsys or chunk.subsys == subsys):
                code = self._read_code(chunk)
                results.append(SearchResult(chunk, r.score, code))
        
        return results
    
    def _rrf_fusion(self, dense_results, sparse_results, k: int = 60):
        scores = {}
        
        # Dense results (semantic similarity)
        for rank, r in enumerate(dense_results):
            scores[r.id] = scores.get(r.id, 0) + 1.0 / (k + rank + 1)
        
        # Sparse results (keyword match)
        for rank, r in enumerate(sparse_results):
            scores[r.id] = scores.get(r.id, 0) + 1.0 / (k + rank + 1)
        
        fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        class FusedResult:
            def __init__(self, id, score):
                self.id = id
                self.score = score
        
        return [FusedResult(id, score) for id, score in fused]
    
    def _find_chunk(self, chunk_id: str) -> Optional[CodeChunk]:
        for c in self.chunks:
            if f"{c.file_path}:{c.name}" == chunk_id:
                return c
            if c.name == chunk_id:
                return c
        return None

    def validate_line_number(self, result: SearchResult) -> LineValidationResult:
        if not self.repo_path or not result.chunk:
            return LineValidationResult(is_valid=False)

        file_path = self.repo_path / result.chunk.file_path
        if not file_path.exists():
            return LineValidationResult(is_valid=False)

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                start = result.chunk.start_line - 1
                end = result.chunk.end_line - 1
                if 0 <= start < len(lines) and 0 <= end < len(lines):
                    content = "".join(lines[start:end + 1])
                    return LineValidationResult(is_valid=True, actual_content=content)
        except Exception:
            pass

        return LineValidationResult(is_valid=False)
