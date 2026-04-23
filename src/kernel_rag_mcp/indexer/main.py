import json
from pathlib import Path
from typing import List

from .code_indexer import CodeIndexer
from .embedders.code_embedder import CodeEmbedder
from ..storage.vector_store import VectorStore
from ..storage.sparse_store import SparseStore
from ..storage.metadata_store import MetadataStore
from .parsers.tree_sitter_c import CodeChunk


class Indexer:
    def __init__(self, repo_path: Path, index_root: Path, model_name: str = "simple"):
        self.repo_path = repo_path
        self.index_root = index_root
        self.code_indexer = CodeIndexer()
        self.embedder = CodeEmbedder(model_name=model_name)
    
    def build_index(self, base: str, target: str, subsystems: List[str]):
        version_ns = self._get_version_namespace(target)
        index_dir = self.index_root / version_ns / "base"
        index_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize stores
        vector_store = VectorStore(backend="qdrant", path=index_dir / "qdrant")
        sparse_store = SparseStore(backend="meilisearch", path=index_dir / "meili")
        metadata_store = MetadataStore(path=index_dir)
        
        # Parse code
        all_chunks = []
        for subsys in subsystems:
            subsys_path = self.repo_path / subsys
            if not subsys_path.exists():
                continue
            
            results = self.code_indexer.index_directory(subsys_path)
            for result in results:
                for chunk in result.chunks:
                    chunk.set_subsystem(subsys)
                all_chunks.extend(result.chunks)
        
        print(f"Total chunks to index: {len(all_chunks)}")
        for subsys in subsystems:
            count = sum(1 for c in all_chunks if c.subsys == subsys)
            print(f"  {subsys}: {count} chunks")
        
        # Generate embeddings
        texts = [f"{c.name} {c.code[:200]}" for c in all_chunks]
        embeddings = self.embedder.encode(texts)
        
        # Store in Qdrant
        collection_name = "code_chunks"
        vector_store.create_collection(collection_name, self.embedder.dim)
        
        vector_chunks = []
        for i, chunk in enumerate(all_chunks):
            chunk_id = f"{chunk.file_path}:{chunk.name}"
            vector_chunks.append({
                "id": chunk_id,
                "vector": embeddings[i],
                "metadata": {
                    "name": chunk.name,
                    "file_path": chunk.file_path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "subsys": chunk.subsys,
                }
            })
        
        vector_store.insert(vector_chunks)
        
        # Store in sparse index
        sparse_docs = []
        for chunk in all_chunks:
            sparse_docs.append({
                "id": f"{chunk.file_path}:{chunk.name}",
                "symbol": chunk.name,
                "file": chunk.file_path,
                "subsys": chunk.subsys or "unknown",
            })
        
        sparse_store.index(sparse_docs)
        
        # Save metadata
        metadata = {
            "repo_path": str(self.repo_path),
            "base": base,
            "target": target,
            "subsystems": subsystems,
            "chunk_count": len(all_chunks),
            "embedding_model": self.embedder.model_name,
            "embedding_dim": self.embedder.dim,
        }
        metadata_store.save(metadata)
        
        # Save chunk pointers (no code)
        self._save_chunks(index_dir, all_chunks)
        
        return index_dir
    
    def _get_version_namespace(self, target: str) -> str:
        if target.startswith("v"):
            parts = target.split(".")
            if len(parts) >= 2:
                major = parts[0][1:] if parts[0].startswith("v") else parts[0]
                minor = parts[1]
                if "-rc" in minor:
                    minor = minor.split("-")[0]
                return f"v{major}.{minor}"
        return "v7.0-rc6"
    
    def _save_chunks(self, index_dir: Path, chunks: List[CodeChunk]):
        chunks_file = index_dir / "chunks.json"
        chunks_data = []
        for chunk in chunks:
            chunks_data.append({
                "name": chunk.name,
                "file_path": chunk.file_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "chunk_type": chunk.chunk_type,
                "subsys": chunk.subsys,
            })
        with open(chunks_file, "w") as f:
            json.dump(chunks_data, f, indent=2)
