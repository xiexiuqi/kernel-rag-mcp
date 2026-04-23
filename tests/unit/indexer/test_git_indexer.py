import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from kernel_rag_mcp.indexer.git_indexer import GitIndexer
from kernel_rag_mcp.indexer.parsers.git_parser import CommitParser


class TestCommitParser:
    def test_parse_standard_commit(self):
        commit_msg = """mm: rmap: support batched unmapping for file large folios

Similar to folio_referenced_one(), we can apply batched unmapping for file
large folios to optimize the performance of file folios reclamation.

Performance testing:
Allocate 10G clean file-backed folios by mmap() in a memory cgroup, and
try to reclaim 8G file-backed folios via the memory.reclaim interface.  I
can observe 75% performance improvement on my Arm64 32-core server (and
50%+ improvement on my X86 machine) with this patch.

W/o patch:
real    0m1.018s
user    0m0.000s
sys     0m1.018s

W/ patch:
real    0m0.254s
user    0m0.000s
sys     0m0.254s

Signed-off-by: Baolin Wang <baolin.wang@linux.alibaba.com>
Reviewed-by: Barry Song <barry.song@linux.alibaba.com>
"""
        parser = CommitParser()
        result = parser.parse(commit_msg)

        assert result.title == "mm: rmap: support batched unmapping for file large folios"
        assert "batched unmapping" in result.body
        assert result.author == "Baolin Wang"
        assert "performance improvement" in result.body

    def test_extract_performance_metrics(self):
        body = """Performance testing:
Allocate 10G clean file-backed folios by mmap() in a memory cgroup, and
try to reclaim 8G file-backed folios via the memory.reclaim interface.  I
can observe 75% performance improvement on my Arm64 32-core server (and
50%+ improvement on my X86 machine) with this patch.

W/o patch:
real    0m1.018s
user    0m0.000s
sys     0m1.018s

W/ patch:
real    0m0.254s
user    0m0.000s
sys     0m0.254s
"""
        parser = CommitParser()
        metrics = parser.extract_performance_metrics(body)

        assert metrics is not None
        assert metrics.improvement_percent == 75
        assert metrics.before_latency == "0m1.018s"
        assert metrics.after_latency == "0m0.254s"
        assert metrics.benchmark_tool == "memory.reclaim"

    def test_extract_performance_metrics_latency(self):
        body = """This reduces latency from 100us to 20us on high-load systems.
Tested with hackbench -l 100000.
"""
        parser = CommitParser()
        metrics = parser.extract_performance_metrics(body)

        assert metrics is not None
        assert metrics.latency_before == "100us"
        assert metrics.latency_after == "20us"
        assert metrics.benchmark_tool == "hackbench"

    def test_extract_performance_metrics_throughput(self):
        body = """Increases throughput from 1000 ops/s to 1500 ops/s.
Benchmark: fio with 4k random read.
"""
        parser = CommitParser()
        metrics = parser.extract_performance_metrics(body)

        assert metrics is not None
        assert metrics.throughput_before == "1000 ops/s"
        assert metrics.throughput_after == "1500 ops/s"

    def test_no_performance_metrics(self):
        body = """Fixes null pointer dereference in tcp_cong.c.

The bug was introduced by commit abc123.
"""
        parser = CommitParser()
        metrics = parser.extract_performance_metrics(body)

        assert metrics is None

    def test_parse_fixes_tag(self):
        commit_msg = """tcp: fix inaccurate RTO for SACK retransmissions

Fixes: a1b2c3d ("tcp: optimize SACK processing")
Signed-off-by: Eric Dumazet <edumazet@google.com>
"""
        parser = CommitParser()
        result = parser.parse(commit_msg)

        assert result.fixes == "a1b2c3d"
        assert "tcp: optimize SACK processing" in result.fixes_title

    def test_parse_cc_stable(self):
        commit_msg = """mm: fix use-after-free in slab allocator

Cc: stable@vger.kernel.org # 5.15+, 6.1+
Signed-off-by: Author <author@example.com>
"""
        parser = CommitParser()
        result = parser.parse(commit_msg)

        assert result.cc_stable is True
        assert "5.15+" in result.stable_versions
        assert "6.1+" in result.stable_versions

    def test_parse_regression_mark(self):
        commit_msg = """sched: fix regression in scheduler load balance

Fixes: e4f5g6h ("sched: optimize load balance")
Signed-off-by: Author <author@example.com>
"""
        parser = CommitParser()
        result = parser.parse(commit_msg)

        assert result.is_regression is True
        assert result.fixes == "e4f5g6h"

    def test_parse_patch_series(self):
        commit_msg = """[PATCH v3 2/5] mm: rmap: support batched checks

This is patch 2 of 5 in the batched rmap series.

Link: https://lore.kernel.org/linux-mm/12345
Signed-off-by: Author <author@example.com>
"""
        parser = CommitParser()
        result = parser.parse(commit_msg)

        assert result.patch_version == "v3"
        assert result.patch_number == 2
        assert result.patch_total == 5
        assert result.series_link == "https://lore.kernel.org/linux-mm/12345"


class TestGitIndexer:
    def test_index_commit_range(self):
        from tests.conftest import KERNEL_REPO_PATH, BASE_VERSION, TARGET_VERSION

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        indexer = GitIndexer(KERNEL_REPO_PATH)
        commits = indexer.index_range(BASE_VERSION, TARGET_VERSION, subsystems=["mm"])

        assert len(commits) > 0
        assert all(c.hash for c in commits)
        assert all(c.title for c in commits)
        assert all(c.date for c in commits)

    def test_index_with_performance_filter(self):
        from tests.conftest import KERNEL_REPO_PATH, BASE_VERSION, TARGET_VERSION

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        indexer = GitIndexer(KERNEL_REPO_PATH)
        commits = indexer.index_range(
            BASE_VERSION, TARGET_VERSION,
            subsystems=["mm"],
            filter_performance=True
        )

        assert len(commits) >= 0
        for c in commits:
            assert "performance" in c.type_tags or "probably_performance" in c.type_tags

    def test_extract_diff_functions(self):
        from tests.conftest import KERNEL_REPO_PATH

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        indexer = GitIndexer(KERNEL_REPO_PATH)
        commit_hash = "a67fe41e214fcfd8b66dfb73d3abe4b7a4b3751d"

        diff = indexer.get_commit_diff(commit_hash)
        functions = indexer.extract_modified_functions(diff)

        assert len(functions) > 0
        assert all(f.isidentifier() for f in functions)

    def test_blame_line(self):
        from tests.conftest import KERNEL_REPO_PATH

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        indexer = GitIndexer(KERNEL_REPO_PATH)
        file_path = KERNEL_REPO_PATH / "kernel/sched/core.c"

        if not file_path.exists():
            pytest.skip("core.c not found")

        result = indexer.blame_line(str(file_path), line=100)

        assert result.commit_hash is not None
        assert result.author is not None
        assert result.date is not None

    def test_changelog_generation(self):
        from tests.conftest import KERNEL_REPO_PATH, BASE_VERSION, TARGET_VERSION

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        indexer = GitIndexer(KERNEL_REPO_PATH)
        changelog = indexer.generate_changelog("sched", BASE_VERSION, TARGET_VERSION)

        assert len(changelog.entries) > 0
        assert all(e.title for e in changelog.entries)
        assert all(e.hash for e in changelog.entries)

    def test_incremental_index(self):
        from tests.conftest import KERNEL_REPO_PATH

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        indexer = GitIndexer(KERNEL_REPO_PATH)
        old_head = "v6.19"
        new_head = "v7.0-rc6"

        new_commits = indexer.get_new_commits(old_head, new_head, subsystems=["mm"])

        assert len(new_commits) > 0
        assert all(c not in indexer.get_commits_before(old_head) for c in new_commits)


class TestPerformancePatchDetection:
    def test_explicit_performance_title(self):
        parser = CommitParser()
        result = parser.parse("sched: optimize vruntime update")

        assert parser.has_performance_keyword(result.title) is True

    def test_hidden_performance_title(self):
        parser = CommitParser()
        result = parser.parse("tcp: switch to rhashtable for ehash")

        assert parser.has_performance_keyword(result.title) is False
        assert parser.is_likely_performance(result) is True

    def test_performance_body_claim(self):
        body = "This improves performance by ~15% on the benchmark."
        parser = CommitParser()

        assert parser.has_performance_claim(body) is True

    def test_performance_diff_fingerprint(self):
        diff = """
+       if (likely(ptr))
+               return;
+       this_cpu_inc(stat);
"""
        parser = CommitParser()
        patterns = parser.count_performance_patterns(diff)

        assert patterns >= 2

    def test_hot_path_file_detection(self):
        parser = CommitParser()

        assert parser.is_hot_path("kernel/sched/core.c") is True
        assert parser.is_hot_path("mm/page_alloc.c") is True
        assert parser.is_hot_path("drivers/usb/core.c") is False

    def test_expert_reviewer_detection(self):
        parser = CommitParser()
        reviewers = ["Peter Zijlstra", "Alice Reviewer"]

        assert parser.has_performance_expert(reviewers) is True

        reviewers = ["Bob Reviewer", "Alice Reviewer"]
        assert parser.has_performance_expert(reviewers) is False

    def test_comprehensive_performance_score(self):
        commit_msg = """mm: use per-cpu list for page allocation

This reduces contention on zone->lock in high allocation rate workloads.
Benchmark: hackbench -l 100000 improves by 12%.

Signed-off-by: Author <author@example.com>
Reviewed-by: Mel Gorman <mgorman@techsingularity.net>
"""
        diff = """
+       this_cpu_add(zone->pages_allocated, 1);
-       spin_lock(&zone->lock);
"""
        parser = CommitParser()
        score = parser.calculate_performance_score(commit_msg, diff, ["mm/page_alloc.c"])

        assert score >= 0.5
        assert score <= 1.0

    def test_non_performance_score(self):
        commit_msg = """fix null pointer dereference in debugfs

Fixes: abc123 ("add debugfs support")

Signed-off-by: Author <author@example.com>
"""
        diff = """
+       if (!ptr)
+               return -EINVAL;
+       pr_err("debugfs error\\n");
"""
        parser = CommitParser()
        score = parser.calculate_performance_score(commit_msg, diff, ["fs/debugfs/inode.c"])

        assert score < 0.3
