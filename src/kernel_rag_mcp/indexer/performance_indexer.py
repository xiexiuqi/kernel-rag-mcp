"""Performance indexer for classifying and analyzing performance patches."""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any

from .parsers.git_parser import CommitParser


@dataclass
class ClassificationResult:
    is_performance: bool
    score: float
    type_tags: List[str] = field(default_factory=list)


@dataclass
class PerformanceData:
    latency_before: Optional[str] = None
    latency_after: Optional[str] = None
    throughput_before: Optional[str] = None
    throughput_after: Optional[str] = None
    improvement_percent: Optional[int] = None
    cpu_cycles_before: Optional[int] = None
    cpu_cycles_after: Optional[int] = None


@dataclass
class Feature:
    name: str
    commits: List[Dict[str, Any]] = field(default_factory=list)
    subsys: str = ""
    core_functions: List[str] = field(default_factory=list)


@dataclass
class EvolutionResult:
    status: str
    total_commits: int
    performance_commits: int
    bugfix_commits: int


class PerformanceIndexer:
    def __init__(self):
        self.parser = CommitParser()

    def classify(self, commit: Dict[str, Any]) -> ClassificationResult:
        title = commit.get("title", "")
        body = commit.get("body", "")
        diff = commit.get("diff", "")
        files = commit.get("files", [])
        reviewers = commit.get("reviewers", [])

        score = 0.0
        tags = []

        if self.parser.has_performance_keyword(title):
            score += 0.4
            tags.append("performance")

        if self.parser.has_performance_claim(body):
            score += 0.2
            tags.append("performance")

        metrics = self.parser.extract_performance_metrics(body)
        if metrics:
            score += 0.2
            tags.append("performance")

        patterns = self.parser.count_performance_patterns(diff)
        if patterns >= 2:
            score += 0.2

        if any(self.parser.is_hot_path(f) for f in files):
            score += 0.1

        if self.parser.has_performance_expert(reviewers):
            score += 0.1

        if "regression" in title.lower():
            tags.append("regression")
            tags.append("bugfix")
            score += 0.1

        if "fix" in title.lower():
            tags.append("bugfix")

        if "regression" in title.lower() and any(kw in body.lower() for kw in ["optimize", "performance", "scalability"]):
            tags.append("performance")
            score += 0.3

        # Hidden performance detection
        if "rhashtable" in title.lower() or "hashtable" in title.lower():
            score += 0.4
            tags.append("performance")

        is_performance = score >= 0.5
        tags = list(set(tags))

        return ClassificationResult(is_performance=is_performance, score=min(score, 1.0), type_tags=tags)

    def extract_performance_data(self, body: str) -> Optional[PerformanceData]:
        metrics = self.parser.extract_performance_metrics(body)
        if not metrics:
            return None
        return PerformanceData(
            latency_before=metrics.latency_before,
            latency_after=metrics.latency_after,
            throughput_before=metrics.throughput_before,
            throughput_after=metrics.throughput_after,
            improvement_percent=metrics.improvement_percent,
            cpu_cycles_before=metrics.cpu_cycles_before,
            cpu_cycles_after=metrics.cpu_cycles_after,
        )

    def associate_features(self, commits: List[Dict[str, Any]], method: str = "semantic") -> List[Feature]:
        if method == "semantic":
            return self._associate_by_semantic(commits)
        elif method == "code_fingerprint":
            return self._associate_by_code_fingerprint(commits)
        elif method == "series":
            return self._associate_by_series(commits)
        return []

    def _associate_by_semantic(self, commits: List[Dict[str, Any]]) -> List[Feature]:
        groups = []
        for commit in commits:
            title = commit.get("title", "")
            keywords = set(self._extract_keywords(title))

            found = False
            for group in groups:
                group_keywords = set(self._extract_keywords(group[0].get("title", "")))
                if keywords & group_keywords:
                    group.append(commit)
                    found = True
                    break

            if not found:
                groups.append([commit])

        features = []
        for group_commits in groups:
            name = self._feature_name_from_commits(group_commits)
            subsys = self._detect_subsys(group_commits)
            features.append(Feature(name=name, commits=group_commits, subsys=subsys))
        return features

    def _associate_by_code_fingerprint(self, commits: List[Dict[str, Any]]) -> List[Feature]:
        groups = defaultdict(list)
        for commit in commits:
            funcs = frozenset(commit.get("modified_functions", []))
            if funcs:
                # Group by intersection of functions
                found = False
                for key in list(groups.keys()):
                    if key != "other" and funcs & key:
                        groups[key].append(commit)
                        found = True
                        break
                if not found:
                    groups[funcs].append(commit)
            else:
                groups["other"].append(commit)

        features = []
        for key, group_commits in groups.items():
            if key != "other":
                name = self._feature_name_from_commits(group_commits)
                subsys = self._detect_subsys(group_commits)
                features.append(Feature(name=name, commits=group_commits, subsys=subsys, core_functions=list(key)))
        if "other" in groups:
            features.append(Feature(name="other", commits=groups["other"]))
        return features

    def _associate_by_series(self, commits: List[Dict[str, Any]]) -> List[Feature]:
        groups = defaultdict(list)
        for commit in commits:
            link = commit.get("series_link")
            if link:
                groups[link].append(commit)
            else:
                groups["standalone"].append(commit)

        features = []
        for key, group_commits in groups.items():
            name = self._feature_name_from_commits(group_commits)
            subsys = self._detect_subsys(group_commits)
            features.append(Feature(name=name, commits=group_commits, subsys=subsys))
        return features

    def _extract_keywords(self, title: str) -> List[str]:
        words = re.findall(r"\b\w+\b", title.lower())
        stopwords = {"sched", "mm", "net", "tcp", "fix", "add", "support", "for", "the", "a", "in", "to", "of", "and", "per-cpu", "per", "cpu"}
        return [w for w in words if len(w) > 3 and w not in stopwords]

    def _feature_name_from_commits(self, commits: List[Dict[str, Any]]) -> str:
        if not commits:
            return "unknown"
        words = []
        for commit in commits:
            title = commit.get("title", "")
            words.extend(self._extract_keywords(title))
        if words:
            from collections import Counter
            most_common = Counter(words).most_common(2)
            return " ".join([w[0] for w in most_common])
        return "feature"

    def _detect_subsys(self, commits: List[Dict[str, Any]]) -> str:
        for commit in commits:
            title = commit.get("title", "")
            if title.startswith("sched:"):
                return "sched"
            elif title.startswith("mm:"):
                return "mm"
            elif title.startswith("net:"):
                return "net"
        return ""

    def track_evolution(self, feature: Dict[str, Any]) -> EvolutionResult:
        commits = feature.get("commits", [])
        total = len(commits)
        perf_count = sum(1 for c in commits if c.get("type") == "performance")
        bugfix_count = sum(1 for c in commits if c.get("type") == "bugfix")
        return EvolutionResult(
            status="stable",
            total_commits=total,
            performance_commits=perf_count,
            bugfix_commits=bugfix_count,
        )

    def get_top_k(self, commits: List[Dict[str, Any]], k: int, metric: str = "improvement_percent") -> List[Dict[str, Any]]:
        def get_metric(c):
            pdata = c.get("performance_data", {})
            if pdata is None:
                return 0
            return pdata.get(metric, 0) if isinstance(pdata, dict) else getattr(pdata, metric, 0)
        sorted_commits = sorted(commits, key=get_metric, reverse=True)
        return sorted_commits[:k]

    def index_performance_commits(self, repo_path: Path, base: str, target: str, subsystems: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        from .git_indexer import GitIndexer
        indexer = GitIndexer(repo_path)
        commits = indexer.index_range(base, target, subsystems)
        results = []
        for commit in commits:
            cdict = {"title": commit.title, "hash": commit.hash, "body": commit.body, "files": [], "reviewers": []}
            result = self.classify(cdict)
            if result.is_performance:
                pdata = self.extract_performance_data(commit.body)
                results.append({
                    **cdict,
                    "performance_data": pdata if pdata is not None else {},
                    "classification_score": result.score,
                })
        return results

    def index_features(self, repo_path: Path, base: str, target: str, subsystems: Optional[List[str]] = None) -> List[Feature]:
        commits = self.index_performance_commits(repo_path, base, target, subsystems)
        return self.associate_features(commits, method="semantic")
