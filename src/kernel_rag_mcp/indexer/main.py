import json
from pathlib import Path
from typing import List

from .code_indexer import CodeIndexer
from .embedders.code_embedder import CodeEmbedder
from .embedders.siliconflow_embedder import SiliconFlowEmbedder
from ..storage.vector_store import VectorStore
from ..storage.sparse_store import SparseStore
from ..storage.metadata_store import MetadataStore
from ..config import Config
from .parsers.tree_sitter_c import CodeChunk


class Indexer:
    def __init__(self, config: Config = None):
        self.config = config or Config()
        self.repo_path = self.config.kernel_repo
        self.index_root = self.config.index_root
        self.code_indexer = CodeIndexer()
        
        # 优先使用 SiliconFlow 云端模型（有 API key 时）
        if self.config.siliconflow_api_key:
            self.embedder = SiliconFlowEmbedder(api_key=self.config.siliconflow_api_key)
            print(f"Using SiliconFlow embedder: {self.embedder.model} ({self.embedder.dim}d)")
        else:
            self.embedder = CodeEmbedder(
                model_name=self.config.embedding_model,
                dim=self.config.embedding_dim,
                model_path=self.config.model_path
            )

    def build_index(self, base: str, target: str, subsystems: List[str],
                    resume: bool = True):
        version_ns = self.config.get_version_ns(target)
        index_dir = self.index_root / version_ns / "base"
        index_dir.mkdir(parents=True, exist_ok=True)

        checkpoint_file = index_dir / "checkpoint.json"

        vector_store = VectorStore(
            backend=self.config.vector_backend,
            path=index_dir / "qdrant"
        )
        sparse_store = SparseStore(path=index_dir / "sparse")
        metadata_store = MetadataStore(path=index_dir)

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

        print(f"Total chunks: {len(all_chunks)}", flush=True)

        start_idx = 0
        completed_ids = set()
        if resume and checkpoint_file.exists():
            try:
                with open(checkpoint_file) as f:
                    checkpoint = json.load(f)
                start_idx = checkpoint.get("next_idx", 0)
                completed_ids = set(checkpoint.get("completed_ids", []))
                print(f"Resuming from {start_idx}/{len(all_chunks)}")
            except Exception:
                pass

        collection_name = "code_chunks"
        vector_store.create_collection(collection_name, self.embedder.dim)

        texts = [f"{c.name} {c.code[:200]}" for c in all_chunks]
        batch_size = self.config.batch_size

        print(f"Embedding in batches of {batch_size}...", flush=True)
        for i in range(start_idx, len(texts), batch_size):
            batch_end = min(i + batch_size, len(texts))
            batch = texts[i:batch_end]
            batch_chunks = all_chunks[i:batch_end]

            batch_embs = self.embedder.encode(batch)

            vector_chunks = []
            for j, chunk in enumerate(batch_chunks):
                rel_path = self._rel_path(chunk.file_path)
                chunk_id = f"{rel_path}:{chunk.name}"
                vector_chunks.append({
                    "id": chunk_id,
                    "vector": batch_embs[j],
                    "metadata": {
                        "name": chunk.name,
                        "file_path": rel_path,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "subsys": chunk.subsys,
                    }
                })
                completed_ids.add(chunk_id)

            vector_store.insert(vector_chunks)

            sparse_docs = []
            for chunk in batch_chunks:
                rel_path = self._rel_path(chunk.file_path)
                sparse_docs.append({
                    "id": f"{rel_path}:{chunk.name}",
                    "symbol": chunk.name,
                    "file": rel_path,
                    "subsys": chunk.subsys or "unknown",
                })

            sparse_store.index(sparse_docs)

            checkpoint = {
                "next_idx": batch_end,
                "total": len(all_chunks),
                "completed_ids": list(completed_ids),
                "base": base,
                "target": target,
                "subsystems": subsystems,
                "embedding_model": self.embedder.model_name,
                "embedding_dim": self.embedder.dim,
            }
            with open(checkpoint_file, "w") as f:
                json.dump(checkpoint, f, indent=2)

            if (i // batch_size) % 10 == 0 or batch_end >= len(all_chunks):
                print(f"  {batch_end}/{len(all_chunks)} ({100*batch_end//len(all_chunks)}%)", flush=True)

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

        self._save_chunks(index_dir, all_chunks)

        if checkpoint_file.exists():
            checkpoint_file.unlink()

        return index_dir

    def _rel_path(self, file_path: str) -> str:
        repo_str = str(self.repo_path)
        if file_path.startswith(repo_str + "/"):
            return file_path[len(repo_str) + 1:]
        return file_path

    def _save_chunks(self, index_dir: Path, chunks: List[CodeChunk]):
        chunks_file = index_dir / "chunks.json"
        chunks_data = []
        for chunk in chunks:
            chunks_data.append({
                "name": chunk.name,
                "file_path": self._rel_path(chunk.file_path),
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "chunk_type": chunk.chunk_type,
                "subsys": chunk.subsys,
            })
        with open(chunks_file, "w") as f:
            json.dump(chunks_data, f, indent=2)
