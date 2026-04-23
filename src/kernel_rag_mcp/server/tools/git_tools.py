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
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.indexer = GitIndexer(repo_path)
    
    def git_search_commits(self, query: str, since: Optional[str] = None, until: Optional[str] = None) -> List[CommitInfo]:
        # Search git log for commits matching query
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
    
    def git_changelog(self, subsys: str, since_tag: Optional[str] = None, until_tag: Optional[str] = None) -> ChangelogResult:
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
