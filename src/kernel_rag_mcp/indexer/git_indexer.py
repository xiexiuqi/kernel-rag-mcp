"""Git indexer for extracting commit history and metadata."""

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .parsers.git_parser import CommitParser, CommitParseResult


@dataclass
class CommitEntry:
    hash: str
    title: str
    date: str
    author: str = ""
    body: str = ""
    type_tags: List[str] = field(default_factory=list)
    performance_data: Optional[dict] = None
    classification_score: float = 0.0


@dataclass
class ChangelogEntry:
    title: str
    hash: str
    author: str = ""
    date: str = ""


@dataclass
class ChangelogResult:
    entries: List[ChangelogEntry] = field(default_factory=list)


@dataclass
class BlameResult:
    commit_hash: str
    author: str
    date: str = ""


class GitIndexer:
    def __init__(self, repo_path: Path):
        self.repo_path = Path(repo_path)
        self.parser = CommitParser()

    def _run_git(self, args: List[str]) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.repo_path)] + args,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def index_range(self, base: str, target: str, subsystems: Optional[List[str]] = None, filter_performance: bool = False) -> List[CommitEntry]:
        log_output = self._run_git([
            "log", f"{base}..{target}",
            "--format=%H|%s|%an|%ad",
            "--date=short",
        ])
        commits = []
        for line in log_output.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 3)
            if len(parts) >= 3:
                commits.append(CommitEntry(
                    hash=parts[0],
                    title=parts[1],
                    author=parts[2],
                    date=parts[3] if len(parts) > 3 else "",
                ))
        
        if subsystems:
            filtered = []
            for c in commits:
                for subsys in subsystems:
                    if subsys.lower() in c.title.lower():
                        filtered.append(c)
                        break
            commits = filtered
        
        if filter_performance:
            filtered = []
            for c in commits:
                full_msg = self._run_git(["show", "--format=%B", "--no-patch", c.hash])
                parsed = self.parser.parse(full_msg)
                type_tags = []
                if self.parser.has_performance_keyword(parsed.title):
                    type_tags.append("performance")
                if self.parser.is_likely_performance(parsed):
                    type_tags.append("probably_performance")
                if self.parser.has_performance_claim(parsed.body):
                    type_tags.append("performance_claim")
                if type_tags:
                    c.type_tags = type_tags
                    filtered.append(c)
            commits = filtered
        
        return commits

    def get_commit_diff(self, commit_hash: str) -> str:
        return self._run_git(["show", commit_hash, "--format=", "-p"])

    def extract_modified_functions(self, diff: str) -> List[str]:
        functions = set()
        for match in re.finditer(r"^@@ .*?@@ .*?(\w+)\s*\(", diff, re.MULTILINE):
            functions.add(match.group(1))
        if not functions:
            for match in re.finditer(r"^[\+\-].*?(\w+)\s*\(", diff, re.MULTILINE):
                functions.add(match.group(1))
        return list(functions)

    def blame_line(self, file_path: str, line: int) -> BlameResult:
        output = self._run_git([
            "blame", "-L", f"{line},{line}",
            "--porcelain", file_path,
        ])
        commit_hash = output.split("\n")[0].split()[0] if output else ""
        author = ""
        date = ""
        for line_str in output.split("\n"):
            if line_str.startswith("author "):
                author = line_str[7:]
            elif line_str.startswith("author-time "):
                import time
                timestamp = int(line_str[12:])
                date = time.strftime("%Y-%m-%d", time.gmtime(timestamp))
        return BlameResult(commit_hash=commit_hash, author=author, date=date)

    def generate_changelog(self, subsys: str, since_tag: str, until_tag: str) -> ChangelogResult:
        commits = self.index_range(since_tag, until_tag)
        entries = [
            ChangelogEntry(title=c.title, hash=c.hash, author=c.author, date=c.date)
            for c in commits
        ]
        return ChangelogResult(entries=entries)

    def get_new_commits(self, old_head: str, new_head: str, subsystems: Optional[List[str]] = None) -> List[CommitEntry]:
        return self.index_range(old_head, new_head, subsystems)

    def get_commits_before(self, head: str) -> List[str]:
        output = self._run_git(["log", f"{head}~10..{head}", "--format=%H"])
        return [line.strip() for line in output.split("\n") if line.strip()]

    def index_commits_to_store(self, metadata_store, since: str = "v7.0", limit: int = 1000):
        log_output = self._run_git([
            "log", since + "..HEAD",
            "--format=%H|%s|%an|%ad|%b<END>",
            "--date=short",
            "-n", str(limit),
        ])

        commits = []
        entries = log_output.split("<END>")
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue
            lines = entry.split("\n", 4)
            if len(lines) < 4:
                continue
            header = lines[0]
            body = "\n".join(lines[4:]) if len(lines) > 4 else ""
            parts = header.split("|", 4)
            if len(parts) >= 4:
                commits.append({
                    "hash": parts[0],
                    "title": parts[1],
                    "author": parts[2],
                    "date": parts[3],
                    "message": body,
                })

        if commits:
            metadata_store.save_git_commits(commits)

        return len(commits)
