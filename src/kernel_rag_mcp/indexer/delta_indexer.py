import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

from .code_indexer import CodeIndexer
from .parsers.tree_sitter_c import CodeChunk
from ..storage.metadata_store import MetadataStore
from ..storage.vector_store import VectorStore


@dataclass
class DeltaMetadata:
    from_commit: str
    to_commit: str
    changed_files: List[str]
    timestamp: str
    chunk_count: int = 0


class DeltaIndexer:
    def __init__(
        self,
        repo_path: Path,
        index_root: Path,
        version: str,
        subsystems: Optional[List[str]] = None,
        repo_name: str = "linux"
    ):
        self.repo_path = Path(repo_path)
        self.index_root = Path(index_root)
        self.version = version
        self.subsystems = subsystems or ["kernel/sched", "mm", "net"]
        self.repo_name = repo_name
        self.version_dir = self.index_root / self.repo_name / version
        self.code_indexer = CodeIndexer()

    def detect_changes(self, from_ref: str, to_ref: str) -> List[str]:
        result = subprocess.run(
            ["git", "-C", str(self.repo_path), "diff", "--name-only", from_ref, to_ref],
            capture_output=True,
            text=True,
            check=True
        )
        all_files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
        return self._filter_by_subsystems(all_files)

    def _filter_by_subsystems(self, files: List[str]) -> List[str]:
        filtered = []
        for f in files:
            for subsys in self.subsystems:
                if f.startswith(subsys):
                    filtered.append(f)
                    break
        return filtered

    def get_delta_dir(self, delta_name: str) -> Path:
        return self.version_dir / f"delta-{delta_name}"

    def list_deltas(self) -> List[Path]:
        if not self.version_dir.exists():
            return []
        deltas = []
        for item in self.version_dir.iterdir():
            if item.is_dir() and item.name.startswith("delta-"):
                deltas.append(item)
        return sorted(deltas)

    def build_delta(
        self,
        changed_files: List[str],
        from_commit: str,
        to_commit: str,
        embedder,
        delta_name: Optional[str] = None
    ) -> Path:
        if delta_name is None:
            delta_name = to_commit[:8]

        delta_dir = self.get_delta_dir(delta_name)
        delta_dir.mkdir(parents=True, exist_ok=True)

        metadata_store = MetadataStore(delta_dir)
        vector_store = VectorStore(backend="qdrant", path=delta_dir / "qdrant")
        vector_store.create_collection("code_chunks", embedder.dim)

        all_chunks = []
        batch_size = 10

        for file_path in changed_files:
            full_path = self.repo_path / file_path
            if not full_path.exists():
                continue

            try:
                result = self.code_indexer.index_file(full_path)
                for chunk in result.chunks:
                    chunk.set_subsystem(self.code_indexer.get_subsystem(file_path))
                all_chunks.extend(result.chunks)
            except Exception:
                continue

        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i:i + batch_size]
            texts = [f"{c.name} {c.code[:200]}" for c in batch]
            embeddings = embedder.encode(texts)

            vector_chunks = []
            sqlite_chunks = []

            for j, chunk in enumerate(batch):
                rel_path = str(chunk.file_path).replace(str(self.repo_path) + "/", "")
                chunk_id = f"{rel_path}:{chunk.name}"

                vector_chunks.append({
                    "id": chunk_id,
                    "vector": embeddings[j],
                    "metadata": {
                        "name": chunk.name,
                        "file_path": rel_path,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "subsys": chunk.subsys,
                    }
                })

                sqlite_chunks.append({
                    "id": chunk_id,
                    "name": chunk.name,
                    "file_path": rel_path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "chunk_type": chunk.chunk_type,
                    "subsys": chunk.subsys,
                    "code_snippet": chunk.code[:500],
                })

            vector_store.insert(vector_chunks)
            metadata_store.save_chunks(sqlite_chunks)

        metadata_store.save_metadata({
            "from_commit": from_commit,
            "to_commit": to_commit,
            "changed_files": ",".join(changed_files),
            "chunk_count": str(len(all_chunks)),
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "version": self.version,
            "delta_name": delta_name,
        })

        if vector_store._qdrant_client:
            vector_store._qdrant_client.close()

        return delta_dir
