"""Git commit parser for extracting metadata and performance metrics."""

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PerformanceMetrics:
    improvement_percent: Optional[int] = None
    before_latency: Optional[str] = None
    after_latency: Optional[str] = None
    benchmark_tool: Optional[str] = None
    latency_before: Optional[str] = None
    latency_after: Optional[str] = None
    throughput_before: Optional[str] = None
    throughput_after: Optional[str] = None
    cpu_cycles_before: Optional[int] = None
    cpu_cycles_after: Optional[int] = None


@dataclass
class CommitParseResult:
    title: str = ""
    body: str = ""
    author: str = ""
    fixes: Optional[str] = None
    fixes_title: str = ""
    cc_stable: bool = False
    stable_versions: List[str] = field(default_factory=list)
    is_regression: bool = False
    patch_version: str = ""
    patch_number: int = 0
    patch_total: int = 0
    series_link: str = ""


class CommitParser:
    PERFORMANCE_KEYWORDS = [
        "optim", "speedup", "fast", "latency", "throughput", "performance",
        "scalability", "efficient", "improve", "reduce contention",
        "per-cpu", "per_cpu", "batch", "bulk", "lockless", "rcu",
    ]

    PERFORMANCE_EXPERTS = [
        "Peter Zijlstra", "Mel Gorman", "Eric Dumazet",
        "Ingo Molnar", "Thomas Gleixner",
    ]

    HOT_PATH_PATTERNS = [
        r"kernel/sched/.*",
        r"mm/page_alloc\.c", r"mm/slab\.c", r"mm/slub\.c",
        r"net/core/dev\.c", r"net/core/skbuff\.c",
        r"lib/radix-tree\.c", r"lib/rhashtable\.c",
        r"arch/x86/mm/.*", r"kernel/locking/.*",
    ]

    PERFORMANCE_CODE_PATTERNS = [
        r"\+\s*likely\(", r"\+\s*unlikely\(",
        r"\+\s*READ_ONCE\(", r"\+\s*WRITE_ONCE\(",
        r"\+\s*per_cpu\(", r"\+\s*this_cpu",
        r"\+\s*prefetch\(", r"\+\s*prefetchw\(",
        r"\+\s*static_branch_", r"\+\s*__always_inline",
        r"\+\s*alloc_pages_bulk", r"\+\s*kmalloc_array",
        r"\+\s*kfree_bulk", r"\+\s*__percpu",
        r"\+\s*NAPI", r"\+\s*busy_poll", r"\+\s*XDP",
        r"\+\s*this_cpu_add", r"\+\s*this_cpu_inc",
        r"\-\s*spin_lock",
    ]

    def parse(self, commit_msg: str) -> CommitParseResult:
        lines = commit_msg.split("\n")
        result = CommitParseResult()

        if lines:
            result.title = lines[0].strip()

        body_lines = []
        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith("Signed-off-by:"):
                author_match = re.search(r"Signed-off-by:\s*(.+?)\s+<", stripped)
                if author_match and not result.author:
                    result.author = author_match.group(1).strip()
            elif stripped.startswith("Fixes:"):
                fixes_match = re.search(r'Fixes:\s*(\w+)\s+\("(.+?)"\)', stripped)
                if fixes_match:
                    result.fixes = fixes_match.group(1)
                    result.fixes_title = fixes_match.group(2)
                else:
                    fixes_simple = re.search(r"Fixes:\s*(\w+)", stripped)
                    if fixes_simple:
                        result.fixes = fixes_simple.group(1)
            elif stripped.startswith("Cc: stable@vger.kernel.org"):
                result.cc_stable = True
                versions_match = re.search(r"#\s*(.+)", stripped)
                if versions_match:
                    result.stable_versions = [v.strip() for v in versions_match.group(1).split(",")]
            elif stripped.startswith("Link:"):
                result.series_link = stripped.split("Link:", 1)[1].strip()
            else:
                body_lines.append(line)

        result.body = "\n".join(body_lines).strip()

        if "regression" in result.title.lower():
            result.is_regression = True

        patch_match = re.match(r"\[PATCH\s+(v\d+)?\s*(\d+)/(\d+)\]\s*(.+)", result.title)
        if patch_match:
            result.patch_version = patch_match.group(1) or ""
            result.patch_number = int(patch_match.group(2))
            result.patch_total = int(patch_match.group(3))
            result.title = patch_match.group(4).strip()

        return result

    def extract_performance_metrics(self, body: str) -> Optional[PerformanceMetrics]:
        metrics = PerformanceMetrics()
        found = False

        improvement_match = re.search(r"(\d+)%\s*performance\s*improvement", body, re.IGNORECASE)
        if improvement_match:
            metrics.improvement_percent = int(improvement_match.group(1))
            found = True

        latency_match = re.search(r"(?:from|before)\s+(\d+\s*(?:us|ms|s|µs))\s+(?:to|after)\s+(\d+\s*(?:us|ms|s|µs))", body, re.IGNORECASE)
        if latency_match:
            metrics.latency_before = latency_match.group(1)
            metrics.latency_after = latency_match.group(2)
            found = True

        if not metrics.latency_before:
            w_o_match = re.search(r"W/o patch:\s*real\s+(\d+m[\d.]+s)", body)
            w_match = re.search(r"W/ patch:\s*real\s+(\d+m[\d.]+s)", body)
            if w_o_match and w_match:
                metrics.before_latency = w_o_match.group(1)
                metrics.after_latency = w_match.group(1)
                metrics.latency_before = metrics.before_latency
                metrics.latency_after = metrics.after_latency
                found = True

        if not metrics.improvement_percent:
            pct_match = re.search(r"(\d+)%\s+improvement", body, re.IGNORECASE)
            if pct_match:
                metrics.improvement_percent = int(pct_match.group(1))
                found = True

        throughput_match = re.search(r"(?:from|before)\s+(\d+\s*ops/s)\s+(?:to|after)\s+(\d+\s*ops/s)", body, re.IGNORECASE)
        if throughput_match:
            metrics.throughput_before = throughput_match.group(1)
            metrics.throughput_after = throughput_match.group(2)
            found = True

        cycles_match = re.search(r"Before:\s*(\d+)\s*cycles.*After:\s*(\d+)\s*cycles", body, re.IGNORECASE | re.DOTALL)
        if cycles_match:
            metrics.cpu_cycles_before = int(cycles_match.group(1))
            metrics.cpu_cycles_after = int(cycles_match.group(2))
            found = True

        benchmark_match = re.search(r"Benchmark:\s*(\S+)", body, re.IGNORECASE)
        if benchmark_match:
            metrics.benchmark_tool = benchmark_match.group(1)
        elif "hackbench" in body.lower():
            metrics.benchmark_tool = "hackbench"
        elif "fio" in body.lower():
            metrics.benchmark_tool = "fio"
        elif "memory.reclaim" in body:
            metrics.benchmark_tool = "memory.reclaim"

        return metrics if found else None

    def has_performance_keyword(self, title: str) -> bool:
        title_lower = title.lower()
        return any(kw in title_lower for kw in self.PERFORMANCE_KEYWORDS)

    def is_likely_performance(self, result: CommitParseResult) -> bool:
        body_lower = result.body.lower()
        if any(kw in body_lower for kw in ["scalability", "performance", "improve", "latency", "throughput"]):
            return True
        if "rhashtable" in result.title.lower() or "hashtable" in result.title.lower():
            return True
        return False

    def has_performance_claim(self, body: str) -> bool:
        return bool(re.search(r"improves? performance by\s*~?\d+%", body, re.IGNORECASE))

    def count_performance_patterns(self, diff: str) -> int:
        count = 0
        for pattern in self.PERFORMANCE_CODE_PATTERNS:
            count += len(re.findall(pattern, diff))
        return count

    def is_hot_path(self, file_path: str) -> bool:
        for pattern in self.HOT_PATH_PATTERNS:
            if re.match(pattern, file_path):
                return True
        return False

    def has_performance_expert(self, reviewers: List[str]) -> bool:
        for reviewer in reviewers:
            for expert in self.PERFORMANCE_EXPERTS:
                if expert in reviewer:
                    return True
        return False

    def calculate_performance_score(self, commit_msg: str, diff: str, files: List[str]) -> float:
        result = self.parse(commit_msg)
        score = 0.0

        if self.has_performance_keyword(result.title):
            score += 0.3

        if self.has_performance_claim(result.body):
            score += 0.2

        metrics = self.extract_performance_metrics(result.body)
        if metrics and metrics.improvement_percent:
            score += min(metrics.improvement_percent / 100.0 * 0.2, 0.2)

        patterns = self.count_performance_patterns(diff)
        score += min(patterns * 0.1, 0.2)

        if any(self.is_hot_path(f) for f in files):
            score += 0.1

        if "per-cpu" in result.title.lower() or "per_cpu" in result.title.lower():
            score += 0.1

        if "Reviewed-by" in commit_msg and any(expert in commit_msg for expert in self.PERFORMANCE_EXPERTS):
            score += 0.1

        return min(score, 1.0)
