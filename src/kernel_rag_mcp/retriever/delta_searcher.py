from pathlib import Path
from typing import List, Optional

from ..indexer.embedders.code_embedder import CodeEmbedder
from ..indexer.parsers.tree_sitter_c import CodeChunk
from ..storage.metadata_store import MetadataStore
from ..storage.vector_store import VectorStore
from ..storage.sparse_store import SparseStore


class SearchResult:
    def __init__(self, chunk: CodeChunk, score: float, code: str = ""):
        self.chunk = chunk
        self.score = score
        self.code = code


class DeltaSearcher:
    def __init__(
        self,
        base_path: Path,
        delta_paths: List[Path],
        repo_path: Optional[Path] = None
    ):
        self.base_path = Path(base_path)
        self.delta_paths = [Path(d) for d in delta_paths]
        self.repo_path = repo_path
        self.embedder = self._load_embedder()

    def _load_embedder(self):
        base_store = MetadataStore(self.base_path)
        model = base_store.get_metadata("embedding_model")
        dim = base_store.get_metadata("embedding_dim")

        if model and dim:
            from ..indexer.embedders.siliconflow_embedder import SiliconFlowEmbedder
            if "siliconflow" in model or "bge-m3" in model:
                return SiliconFlowEmbedder()
            return CodeEmbedder(model_name=model, dim=int(dim))

        return CodeEmbedder(model_name="local", dim=768)

    def _load_dim(self):
        base_store = MetadataStore(self.base_path)
        dim = base_store.get_metadata("embedding_dim")
        return int(dim) if dim else 768

    def _load_all_chunks(self) -> List[CodeChunk]:
        chunk_map = {}

        base_store = MetadataStore(self.base_path)
        base_rows = base_store.search_chunks_by_subsys("", limit=1000000)
        for item in base_rows:
            key = item["file_path"]
            chunk_map[key] = CodeChunk(
                name=item["name"],
                file_path=item["file_path"],
                start_line=item["start_line"],
                end_line=item["end_line"],
                chunk_type=item.get("chunk_type", "function"),
                subsys=item.get("subsys"),
            )

        for delta_path in self.delta_paths:
            delta_store = MetadataStore(delta_path)
            delta_rows = delta_store.search_chunks_by_subsys("", limit=1000000)
            for item in delta_rows:
                key = item["file_path"]
                chunk_map[key] = CodeChunk(
                    name=item["name"],
                    file_path=item["file_path"],
                    start_line=item["start_line"],
                    end_line=item["end_line"],
                    chunk_type=item.get("chunk_type", "function"),
                    subsys=item.get("subsys"),
                )

        return list(chunk_map.values())

    def _find_chunk(self, chunk_id: str, all_chunks: List[CodeChunk]) -> Optional[CodeChunk]:
        for c in all_chunks:
            if f"{c.file_path}:{c.name}" == chunk_id:
                return c
            if c.name == chunk_id:
                return c
        return None

    def _read_code(self, chunk: CodeChunk) -> str:
        if not self.repo_path:
            return ""

        file_path = Path(self.repo_path) / chunk.file_path
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
        all_results = []

        base_vec = VectorStore(backend="qdrant", path=self.base_path / "qdrant")
        base_vec.create_collection("code_chunks", self._load_dim())
        base_results = base_vec.search(query_vector=query_emb, top_k=top_k)
        all_results.extend([(r, "base") for r in base_results])
        if base_vec._qdrant_client:
            base_vec._qdrant_client.close()

        for delta_path in self.delta_paths:
            delta_vec = VectorStore(backend="qdrant", path=delta_path / "qdrant")
            delta_vec.create_collection("code_chunks", self._load_dim())
            delta_results = delta_vec.search(query_vector=query_emb, top_k=top_k)
            all_results.extend([(r, "delta") for r in delta_results])
            if delta_vec._qdrant_client:
                delta_vec._qdrant_client.close()

        all_chunks = self._load_all_chunks()

        seen = set()
        results = []
        for r, source in sorted(all_results, key=lambda x: x[0].score, reverse=True):
            chunk = self._find_chunk(r.id, all_chunks)
            if chunk and chunk.file_path not in seen:
                seen.add(chunk.file_path)
                code = self._read_code(chunk)
                results.append(SearchResult(chunk, r.score, code))

        return results[:top_k]

    def search(self, query: str, subsys=None, top_k: int = 10) -> List[SearchResult]:
        results = self.dense_search(query, top_k=top_k * 2)

        if subsys:
            results = [r for r in results if r.chunk.subsys == subsys]

        return results[:top_k]
