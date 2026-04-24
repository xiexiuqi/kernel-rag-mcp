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
        raw_path = Path(index_path) if index_path else None
        self.index_path = self._resolve_index_path(raw_path)
        self.repo_path = repo_path
        
        if self.index_path:
            if repo_path is None:
                meta_file = self.index_path / "metadata.json"
                if meta_file.exists():
                    with open(meta_file) as f:
                        meta = json.load(f)
                    self.repo_path = Path(meta.get("repo_path", "."))
            
            self.vector_store = VectorStore(backend="qdrant", path=self.index_path / "qdrant")
            self.vector_store.create_collection("code_chunks", self._load_dim())
            self.sparse_store = SparseStore(path=self.index_path / "sparse")
            self.chunks = self._load_chunks()
            self._build_sparse_index()
        else:
            self.vector_store = VectorStore(backend="memory")
            self.sparse_store = SparseStore(backend="memory")
            self.chunks = []
        
        self.embedder = self._load_embedder()

    def _resolve_index_path(self, raw_path: Optional[Path]) -> Optional[Path]:
        if not raw_path:
            return None
        nested_base = raw_path / "base"
        if (nested_base / "qdrant").exists():
            return nested_base
        if (raw_path / "qdrant").exists():
            return raw_path
        if (nested_base / "metadata.db").exists():
            return nested_base
        if (raw_path / "metadata.db").exists():
            return raw_path
        return raw_path
    
    def _load_embedder(self):
        if self.index_path:
            from ..storage.metadata_store import MetadataStore
            store = MetadataStore(self.index_path)
            model = store.get_metadata("embedding_model")
            dim = store.get_metadata("embedding_dim")
            if model and dim:
                from ..indexer.embedders.siliconflow_embedder import SiliconFlowEmbedder
                if "siliconflow" in model or "bge-m3" in model:
                    return SiliconFlowEmbedder()
                return CodeEmbedder(model_name=model, dim=int(dim))
        return CodeEmbedder(model_name="local", dim=768)

    def _load_dim(self):
        if self.index_path:
            from ..storage.metadata_store import MetadataStore
            store = MetadataStore(self.index_path)
            dim = store.get_metadata("embedding_dim")
            if dim:
                return int(dim)
        return 768
    
    def _load_chunks(self) -> List[CodeChunk]:
        if not self.index_path:
            return []
        
        from ..storage.metadata_store import MetadataStore
        store = MetadataStore(self.index_path)
        rows = store.search_chunks_by_subsys("", limit=1000000)
        
        chunks = []
        for item in rows:
            chunks.append(CodeChunk(
                name=item["name"],
                file_path=item["file_path"],
                start_line=item["start_line"],
                end_line=item["end_line"],
                chunk_type=item.get("chunk_type", "function"),
                subsys=item.get("subsys"),
            ))
        return chunks
    
    def _build_sparse_index(self):
        docs = []
        for chunk in self.chunks:
            docs.append({
                "id": f"{chunk.file_path}:{chunk.name}",
                "symbol": chunk.name,
                "file": chunk.file_path,
                "subsys": chunk.subsys,
            })
        self.sparse_store.index(docs)
    
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
            
            if chunk and (not subsys or self._subsys_match(chunk.subsys, subsys)):
                code = self._read_code(chunk)
                results.append(SearchResult(chunk, r.score, code))
        
        return results
    
    def _rrf_fusion(self, dense_results, sparse_results, k: int = 60):
        scores = {}

        def _get_id(r):
            if hasattr(r, 'id'):
                return r.id
            if hasattr(r, 'symbol'):
                return r.symbol
            if isinstance(r, dict):
                return r.get('id') or r.get('symbol') or r.get('chunk', {}).get('name', '')
            return str(r)

        for rank, r in enumerate(dense_results):
            scores[_get_id(r)] = scores.get(_get_id(r), 0) + 1.0 / (k + rank + 1)

        for rank, r in enumerate(sparse_results):
            scores[_get_id(r)] = scores.get(_get_id(r), 0) + 1.0 / (k + rank + 1)

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

    def _subsys_match(self, chunk_subsys: str, filter_subsys: str) -> bool:
        if not chunk_subsys or not filter_subsys:
            return False
        return (
            chunk_subsys == filter_subsys
            or chunk_subsys.endswith(f"/{filter_subsys}")
            or filter_subsys.endswith(f"/{chunk_subsys}")
        )

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
