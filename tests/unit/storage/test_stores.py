import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from kernel_rag_mcp.storage.vector_store import VectorStore
from kernel_rag_mcp.storage.sparse_store import SparseStore
from kernel_rag_mcp.storage.graph_store import GraphStore
from kernel_rag_mcp.storage.metadata_store import MetadataStore


class TestVectorStore:
    def test_insert_and_search(self, tmp_path):
        store = VectorStore(backend="qdrant", path=tmp_path)
        chunks = [
            {"id": "chunk1", "vector": [0.1] * 768, "metadata": {"file": "a.c", "line": 10}},
            {"id": "chunk2", "vector": [0.2] * 768, "metadata": {"file": "b.c", "line": 20}},
        ]

        store.insert(chunks)
        results = store.search([0.1] * 768, top_k=2)

        assert len(results) == 2
        assert results[0].id == "chunk1"

    def test_delete(self, tmp_path):
        store = VectorStore(backend="qdrant", path=tmp_path)
        store.insert([{"id": "chunk1", "vector": [0.1] * 768}])
        store.delete("chunk1")

        results = store.search([0.1] * 768, top_k=1)
        assert len(results) == 0

    def test_update_metadata(self, tmp_path):
        store = VectorStore(backend="qdrant", path=tmp_path)
        store.insert([{"id": "chunk1", "vector": [0.1] * 768, "metadata": {"old": "value"}}])
        store.update_metadata("chunk1", {"new": "value"})

        results = store.search([0.1] * 768, top_k=1)
        assert results[0].metadata["new"] == "value"

    def test_filter_by_metadata(self, tmp_path):
        store = VectorStore(backend="qdrant", path=tmp_path)
        store.insert([
            {"id": "c1", "vector": [0.1] * 768, "metadata": {"subsys": "sched"}},
            {"id": "c2", "vector": [0.2] * 768, "metadata": {"subsys": "mm"}},
        ])

        results = store.search([0.1] * 768, top_k=2, filter={"subsys": "sched"})
        assert len(results) == 1
        assert results[0].metadata["subsys"] == "sched"


class TestSparseStore:
    def test_index_and_search(self, tmp_path):
        store = SparseStore(backend="meilisearch", path=tmp_path)
        docs = [
            {"id": "d1", "symbol": "update_curr", "file": "kernel/sched/fair.c"},
            {"id": "d2", "symbol": "pick_next_task", "file": "kernel/sched/core.c"},
        ]

        store.index(docs)
        results = store.search("update_curr")

        assert len(results) > 0
        assert results[0].symbol == "update_curr"

    def test_prefix_search(self, tmp_path):
        store = SparseStore(backend="meilisearch", path=tmp_path)
        store.index([
            {"id": "d1", "symbol": "sched_init"},
            {"id": "d2", "symbol": "schedule"},
            {"id": "d3", "symbol": "scheduler_tick"},
        ])

        results = store.search("sched")
        assert len(results) == 3

    def test_filter_search(self, tmp_path):
        store = SparseStore(backend="meilisearch", path=tmp_path)
        store.index([
            {"id": "d1", "symbol": "update_curr", "subsys": "sched"},
            {"id": "d2", "symbol": "page_alloc", "subsys": "mm"},
        ])

        results = store.search("alloc", filter={"subsys": "mm"})
        assert len(results) == 1
        assert results[0].symbol == "page_alloc"


class TestGraphStore:
    def test_add_node_and_edge(self, tmp_path):
        store = GraphStore(backend="networkx", path=tmp_path)
        store.add_node("commit_a", {"title": "fix bug"})
        store.add_node("commit_b", {"title": "introduce feature"})
        store.add_edge("commit_a", "FIXES", "commit_b")

        assert store.has_node("commit_a")
        assert store.has_edge("commit_a", "commit_b")

    def test_path_query(self, tmp_path):
        store = GraphStore(backend="networkx", path=tmp_path)
        store.add_edge("a", "FIXES", "b")
        store.add_edge("b", "INTRODUCES", "c")

        path = store.find_path("a", "c")
        assert len(path) == 3
        assert path[0] == "a"
        assert path[2] == "c"

    def test_neighbor_query(self, tmp_path):
        store = GraphStore(backend="networkx", path=tmp_path)
        store.add_edge("a", "FIXES", "b")
        store.add_edge("a", "REVIEWED_BY", "reviewer_x")

        neighbors = store.get_neighbors("a")
        assert len(neighbors) == 2

    def test_cycle_detection(self, tmp_path):
        store = GraphStore(backend="networkx", path=tmp_path)
        store.add_edge("a", "FIXES", "b")
        store.add_edge("b", "FIXES", "c")
        store.add_edge("c", "FIXES", "a")

        cycles = store.find_cycles()
        assert len(cycles) > 0

    def test_feature_evolution_query(self, tmp_path):
        store = GraphStore(backend="networkx", path=tmp_path)
        store.add_node("feat_vruntime", {"type": "feature"})
        store.add_edge("commit_intro", "INTRODUCES", "feat_vruntime")
        store.add_edge("commit_opt", "OPTIMIZES", "feat_vruntime")
        store.add_edge("commit_fix", "FIXES_REGRESSION_IN", "commit_opt")

        evolution = store.get_feature_evolution("feat_vruntime")
        assert len(evolution.commits) == 3
        assert evolution.commits[0].type == "introduce"
        assert evolution.commits[1].type == "optimize"
        assert evolution.commits[2].type == "fix_regression"


class TestMetadataStore:
    def test_save_and_load(self, tmp_path):
        store = MetadataStore(path=tmp_path)
        metadata = {
            "repo_name": "linux",
            "version_namespace": "v6.12",
            "base_commit": "abc123",
            "subsystems": ["sched", "mm", "net"],
        }

        store.save(metadata)
        loaded = store.load()

        assert loaded.repo_name == "linux"
        assert loaded.version_namespace == "v6.12"
        assert "sched" in loaded.subsystems

    def test_version_tracking(self, tmp_path):
        store = MetadataStore(path=tmp_path)
        store.save({"base_commit": "abc123", "merged_to": None})

        assert store.is_fresh("abc123") is True
        assert store.is_fresh("def456") is False

    def test_delta_tracking(self, tmp_path):
        store = MetadataStore(path=tmp_path)
        store.save({
            "base_commit": "abc123",
            "deltas": ["delta-v6.12.1", "delta-v6.12.2"],
        })

        assert store.has_delta("delta-v6.12.1") is True
        assert store.has_delta("delta-v6.12.3") is False

    def test_consistency_check(self, tmp_path):
        store = MetadataStore(path=tmp_path)
        store.save({
            "base_commit": "abc123",
            "chunks": {"code": 1000, "commits": 100},
        })

        assert store.check_consistency() is True

        store.save({"base_commit": None})
        assert store.check_consistency() is False
