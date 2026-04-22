import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from kernel_rag_mcp.indexer.performance_indexer import PerformanceIndexer
from kernel_rag_mcp.indexer.parsers.git_parser import CommitParser


class TestPerformanceIndexer:
    def test_classify_performance_patch_explicit(self):
        commit = {
            "title": "sched: optimize vruntime update",
            "body": "This improves performance by 15%.",
            "diff": "+       if (likely(ptr))\n+               return;",
            "files": ["kernel/sched/fair.c"],
            "reviewers": ["Peter Zijlstra"],
        }
        indexer = PerformanceIndexer()
        result = indexer.classify(commit)

        assert result.is_performance is True
        assert result.score >= 0.5
        assert "performance" in result.type_tags

    def test_classify_performance_patch_hidden(self):
        commit = {
            "title": "tcp: switch to rhashtable for ehash",
            "body": "Use rhashtable for better scalability.",
            "diff": "+       struct rhashtable ht;\n-       struct hlist_head *table;",
            "files": ["net/ipv4/tcp.c"],
            "reviewers": ["Eric Dumazet"],
        }
        indexer = PerformanceIndexer()
        result = indexer.classify(commit)

        assert result.is_performance is True
        assert result.score >= 0.5

    def test_classify_non_performance_patch(self):
        commit = {
            "title": "fix null pointer dereference in debugfs",
            "body": "Fixes: abc123",
            "diff": "+       if (!ptr)\n+               return -EINVAL;",
            "files": ["fs/debugfs/inode.c"],
            "reviewers": [],
        }
        indexer = PerformanceIndexer()
        result = indexer.classify(commit)

        assert result.is_performance is False
        assert result.score < 0.3

    def test_classify_regression_fix(self):
        commit = {
            "title": "sched: fix regression in load balance",
            "body": "Fixes: e4f5g6h (\"sched: optimize load balance\")",
            "diff": "+       if (unlikely(!env->cpus_allowed))\n+               return;",
            "files": ["kernel/sched/fair.c"],
            "reviewers": ["Peter Zijlstra"],
        }
        indexer = PerformanceIndexer()
        result = indexer.classify(commit)

        assert "bugfix" in result.type_tags
        assert "performance" in result.type_tags
        assert "regression" in result.type_tags

    def test_extract_performance_data_latency(self):
        body = """Performance testing:
W/o patch: real 0m1.018s
W/ patch: real 0m0.254s
75% improvement on Arm64 32-core server.
"""
        indexer = PerformanceIndexer()
        data = indexer.extract_performance_data(body)

        assert data is not None
        assert data.latency_before == "1.018s"
        assert data.latency_after == "0.254s"
        assert data.improvement_percent == 75

    def test_extract_performance_data_throughput(self):
        body = """Increases throughput from 1000 ops/s to 1500 ops/s.
Tested with fio 4k random read.
"""
        indexer = PerformanceIndexer()
        data = indexer.extract_performance_data(body)

        assert data is not None
        assert data.throughput_before == "1000 ops/s"
        assert data.throughput_after == "1500 ops/s"

    def test_extract_performance_data_cycles(self):
        body = """Before: 500 cycles per operation
After: 300 cycles per operation
"""
        indexer = PerformanceIndexer()
        data = indexer.extract_performance_data(body)

        assert data is not None
        assert data.cpu_cycles_before == 500
        assert data.cpu_cycles_after == 300

    def test_no_performance_data(self):
        body = "Fixes null pointer dereference."
        indexer = PerformanceIndexer()
        data = indexer.extract_performance_data(body)

        assert data is None

    def test_feature_association_semantic(self):
        commits = [
            {"title": "sched: introduce per-CPU vruntime", "hash": "a1"},
            {"title": "sched: optimize per-CPU vruntime for NUMA", "hash": "b2"},
            {"title": "sched: fix per-CPU vruntime regression", "hash": "c3"},
            {"title": "net: add batched skb allocation", "hash": "d4"},
        ]
        indexer = PerformanceIndexer()
        features = indexer.associate_features(commits, method="semantic")

        assert len(features) == 2
        vruntime_feature = [f for f in features if "vruntime" in f.name]
        assert len(vruntime_feature) == 1
        assert len(vruntime_feature[0].commits) == 3

    def test_feature_association_code_fingerprint(self):
        commits = [
            {
                "title": "sched: update vruntime",
                "hash": "a1",
                "modified_functions": ["update_curr", "pick_next_task"],
            },
            {
                "title": "sched: optimize vruntime",
                "hash": "b2",
                "modified_functions": ["update_curr", "enqueue_task"],
            },
            {
                "title": "net: tcp optimization",
                "hash": "c3",
                "modified_functions": ["tcp_sendmsg"],
            },
        ]
        indexer = PerformanceIndexer()
        features = indexer.associate_features(commits, method="code_fingerprint")

        assert len(features) == 2
        vruntime_feature = [f for f in features if "update_curr" in str(f.core_functions)]
        assert len(vruntime_feature) == 1
        assert len(vruntime_feature[0].commits) == 2

    def test_feature_association_series(self):
        commits = [
            {"title": "[PATCH 1/3] mm: batched rmap check", "hash": "a1", "series_link": "thread-123"},
            {"title": "[PATCH 2/3] mm: batched rmap unmap", "hash": "b2", "series_link": "thread-123"},
            {"title": "[PATCH 3/3] mm: batched rmap optimize", "hash": "c3", "series_link": "thread-123"},
            {"title": "sched: unrelated patch", "hash": "d4", "series_link": None},
        ]
        indexer = PerformanceIndexer()
        features = indexer.associate_features(commits, method="series")

        assert len(features) == 2
        rmap_feature = [f for f in features if len(f.commits) == 3]
        assert len(rmap_feature) == 1

    def test_feature_evolution_tracking(self):
        feature = {
            "name": "per-CPU vruntime",
            "commits": [
                {"hash": "a1", "type": "feature", "date": "2024-01-15"},
                {"hash": "b2", "type": "performance", "date": "2024-03-20"},
                {"hash": "c3", "type": "bugfix", "date": "2024-04-10"},
            ],
        }
        indexer = PerformanceIndexer()
        evolution = indexer.track_evolution(feature)

        assert evolution.status == "stable"
        assert evolution.total_commits == 3
        assert evolution.performance_commits == 1
        assert evolution.bugfix_commits == 1

    def test_performance_top_k_query(self):
        commits = [
            {"title": "opt1", "performance_data": {"improvement_percent": 75}},
            {"title": "opt2", "performance_data": {"improvement_percent": 50}},
            {"title": "opt3", "performance_data": {"improvement_percent": 90}},
            {"title": "opt4", "performance_data": {"improvement_percent": 30}},
        ]
        indexer = PerformanceIndexer()
        top_k = indexer.get_top_k(commits, k=3, metric="improvement_percent")

        assert len(top_k) == 3
        assert top_k[0].performance_data.improvement_percent == 90
        assert top_k[1].performance_data.improvement_percent == 75
        assert top_k[2].performance_data.improvement_percent == 50

    def test_index_performance_patch_with_real_kernel(self):
        from tests.conftest import KERNEL_REPO_PATH, BASE_VERSION, TARGET_VERSION

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        indexer = PerformanceIndexer()
        commits = indexer.index_performance_commits(
            KERNEL_REPO_PATH, BASE_VERSION, TARGET_VERSION, subsystems=["mm"]
        )

        assert len(commits) > 0
        assert all(c.performance_data is not None for c in commits)
        assert all(c.classification_score >= 0.5 for c in commits)

    def test_index_feature_with_real_kernel(self):
        from tests.conftest import KERNEL_REPO_PATH, BASE_VERSION, TARGET_VERSION

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        indexer = PerformanceIndexer()
        features = indexer.index_features(
            KERNEL_REPO_PATH, BASE_VERSION, TARGET_VERSION, subsystems=["mm"]
        )

        assert len(features) >= 0
        for f in features:
            assert f.name is not None
            assert len(f.commits) > 0
            assert f.subsys in ["sched", "mm", "net"]
