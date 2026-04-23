import json
import subprocess
from pathlib import Path
from typing import List

from .main import Indexer


class DeltaIndexer:
    def __init__(self, repo_path: Path, index_root: Path):
        self.repo_path = repo_path
        self.index_root = index_root
    
    def get_changed_files(self, old_commit: str, new_commit: str) -> List[str]:
        result = subprocess.run(
            ["git", "-C", str(self.repo_path), "diff", "--name-only", f"{old_commit}..{new_commit}"],
            capture_output=True,
            text=True,
            check=True,
        )
        
        return [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
    
    def get_new_commits(self, old_commit: str, new_commit: str) -> List[dict]:
        result = subprocess.run(
            ["git", "-C", str(self.repo_path), "log", "--format=%H|%s|%an|%ad", "--date=short", f"{old_commit}..{new_commit}"],
            capture_output=True,
            text=True,
            check=True,
        )
        
        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 3)
            if len(parts) >= 3:
                commits.append({
                    "hash": parts[0],
                    "title": parts[1],
                    "author": parts[2],
                    "date": parts[3] if len(parts) > 3 else "",
                })
        
        return commits
    
    def build_delta(self, base_version: str, old_commit: str, new_commit: str, subsystems: List[str]):
        version_ns = self._get_version_namespace(base_version)
        
        # Get changed files
        changed_files = self.get_changed_files(old_commit, new_commit)
        
        # Filter by subsystems
        relevant_files = []
        for file_path in changed_files:
            for subsys in subsystems:
                if file_path.startswith(subsys):
                    relevant_files.append(file_path)
                    break
        
        if not relevant_files:
            return None
        
        # Create delta index
        delta_name = f"delta-{new_commit[:8]}"
        delta_dir = self.index_root / version_ns / delta_name
        delta_dir.mkdir(parents=True, exist_ok=True)
        
        # Index only changed files
        indexer = Indexer(self.repo_path, self.index_root)
        
        # Parse changed files
        from ..indexer.parsers.tree_sitter_c import TreeSitterCParser
        parser = TreeSitterCParser()
        
        delta_chunks = []
        for file_path in relevant_files:
            file_full_path = self.repo_path / file_path
            if not file_full_path.exists():
                continue
            
            try:
                with open(file_full_path, "r", encoding="utf-8", errors="replace") as f:
                    code = f.read()
                
                chunks = parser.parse_functions(code, file_path)
                chunks.extend(parser.parse_structs(code, file_path))
                chunks.extend(parser.parse_macros(code, file_path))
                
                delta_chunks.extend(chunks)
            except Exception:
                pass
        
        # Save delta chunks
        chunks_file = delta_dir / "chunks.json"
        chunks_data = []
        for chunk in delta_chunks:
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
        
        # Save delta metadata
        metadata = {
            "base_version": base_version,
            "old_commit": old_commit,
            "new_commit": new_commit,
            "changed_files": relevant_files,
            "chunk_count": len(delta_chunks),
        }
        
        with open(delta_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)
        
        return delta_dir
    
    def _get_version_namespace(self, target: str) -> str:
        if target.startswith("v"):
            parts = target.split(".")
            if len(parts) >= 2:
                return f"v{parts[0][1:]}.{parts[1]}"
        return "v6.12"
