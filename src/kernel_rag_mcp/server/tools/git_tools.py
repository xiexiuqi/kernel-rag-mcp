from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import subprocess

from ...indexer.git_indexer import GitIndexer


@dataclass
class CommitInfo:
    hash: str
    title: str
    author: str = ""
    date: str = ""


@dataclass
class BlameResult:
    commit_hash: str
    author: str
    line: int = 0
    date: str = ""


@dataclass
class ChangelogResult:
    entries: List[dict]


@dataclass
class CommitContext:
    hash: str
    title: str
    diff: str
    author: str = ""
    date: str = ""


class GitTools:
    def __init__(self, repo_path: Path, index_path: Optional[Path] = None):
        self.repo_path = repo_path
        self.index_path = index_path
        self.indexer = GitIndexer(repo_path)
        self._embedder = None
        self._vector_store = None
        self._metadata_store = None

    def _init_semantic_search(self):
        if self._embedder is not None:
            return

        if not self.index_path:
            return

        base_path = self.index_path / "base"
        if not base_path.exists():
            return

        from ...storage.metadata_store import MetadataStore
        from ...storage.vector_store import VectorStore
        from ...indexer.embedders.siliconflow_embedder import SiliconFlowEmbedder

        store = MetadataStore(base_path)
        model = store.get_metadata("embedding_model")
        dim = store.get_metadata("embedding_dim")

        if model and dim:
            if "siliconflow" in model or "bge-m3" in model:
                self._embedder = SiliconFlowEmbedder()
            else:
                from ...indexer.embedders.code_embedder import CodeEmbedder
                self._embedder = CodeEmbedder(model_name=model, dim=int(dim))

        qdrant_path = base_path / "qdrant"
        if qdrant_path.exists():
            self._vector_store = VectorStore(backend="qdrant", path=qdrant_path)
            self._vector_store.create_collection("git_commits", int(dim) if dim else 768)

        self._metadata_store = MetadataStore(base_path)

    def git_search_commits(self, query: str, since: Optional[str] = None, until: Optional[str] = None, top_k: int = 10) -> List[CommitInfo]:
        self._init_semantic_search()

        if self._embedder and self._vector_store and self._metadata_store:
            try:
                query_emb = self._embedder.encode([query])[0]
                vector_results = self._vector_store.search(query_vector=query_emb, top_k=top_k)

                if vector_results:
                    hashes = []
                    for r in vector_results:
                        h = r.metadata.get("hash") if hasattr(r, "metadata") else None
                        if h:
                            hashes.append(h)

                    if hashes:
                        commits_data = self._metadata_store.get_git_commits_by_hashes(hashes)
                        return [
                            CommitInfo(
                                hash=c["hash"],
                                title=c.get("title", ""),
                                author=c.get("author", ""),
                                date=c.get("date", ""),
                            )
                            for c in commits_data
                        ]
            except Exception:
                pass

        cmd = ["git", "-C", str(self.repo_path), "log", "--format=%H|%s|%an|%ad", "--date=short", "--grep", query]
        if since:
            cmd.extend(["--since", since])
        if until:
            cmd.extend(["--until", until])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            commits = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("|", 3)
                if len(parts) >= 3:
                    commits.append(CommitInfo(
                        hash=parts[0],
                        title=parts[1],
                        author=parts[2],
                        date=parts[3] if len(parts) > 3 else "",
                    ))
            return commits
        except subprocess.CalledProcessError:
            return []
    
    def git_blame_line(self, file: str, line: int) -> BlameResult:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo_path), "blame", "-L", f"{line},{line}", "--porcelain", file],
                capture_output=True, text=True, check=True
            )
            
            commit_hash = ""
            author = ""
            date = ""
            
            for line_str in result.stdout.split("\n"):
                if line_str.startswith("author "):
                    author = line_str[7:]
                elif line_str.startswith("author-time "):
                    import time
                    timestamp = int(line_str[12:])
                    date = time.strftime("%Y-%m-%d", time.gmtime(timestamp))
            
            if result.stdout:
                commit_hash = result.stdout.split("\n")[0].split()[0]
            
            return BlameResult(commit_hash=commit_hash, author=author, line=line, date=date)
        except subprocess.CalledProcessError:
            return BlameResult(commit_hash="", author="", line=line)
    
    SUBSYS_ALIASES = {
        "sched": "kernel/sched",
        "mm": "mm",
        "net": "net",
        "ext4": "fs/ext4",
        "fs": "fs",
        "block": "block",
        "usb": "drivers/usb",
        "x86": "arch/x86",
        "locking": "kernel/locking",
    }

    def _resolve_subsys(self, subsys: str) -> str:
        if not subsys:
            return subsys
        subsys = subsys.lower().strip()
        return self.SUBSYS_ALIASES.get(subsys, subsys)

    def git_changelog(self, subsys: str, since_tag: Optional[str] = None, until_tag: Optional[str] = None) -> ChangelogResult:
        subsys = self._resolve_subsys(subsys)
        range_str = f"{since_tag}..{until_tag}" if since_tag and until_tag else "HEAD~100..HEAD"
        
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo_path), "log", range_str, "--format=%H|%s|%an|%ad", "--date=short", "--", subsys],
                capture_output=True, text=True, check=True
            )
            
            entries = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("|", 3)
                if len(parts) >= 3:
                    entries.append({
                        "hash": parts[0],
                        "title": parts[1],
                        "author": parts[2],
                        "date": parts[3] if len(parts) > 3 else "",
                    })
            
            return ChangelogResult(entries=entries)
        except subprocess.CalledProcessError:
            return ChangelogResult(entries=[])
    
    def git_commit_context(self, hash: str) -> CommitContext:
        try:
            # Get commit info
            result = subprocess.run(
                ["git", "-C", str(self.repo_path), "show", "--format=%H|%s|%an|%ad", "--date=short", "--no-patch", hash],
                capture_output=True, text=True, check=True
            )
            
            parts = result.stdout.strip().split("|", 3)
            commit_hash = parts[0] if len(parts) > 0 else hash
            title = parts[1] if len(parts) > 1 else ""
            author = parts[2] if len(parts) > 2 else ""
            date = parts[3] if len(parts) > 3 else ""
            
            # Get diff
            diff_result = subprocess.run(
                ["git", "-C", str(self.repo_path), "show", "--format=", hash],
                capture_output=True, text=True, check=True
            )
            
            return CommitContext(
                hash=commit_hash,
                title=title,
                diff=diff_result.stdout[:2000],
                author=author,
                date=date,
            )
        except subprocess.CalledProcessError:
            return CommitContext(hash=hash, title="", diff="")
