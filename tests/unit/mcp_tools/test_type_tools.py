import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from kernel_rag_mcp.storage.metadata_store import MetadataStore
from kernel_rag_mcp.server.tools.type_tools import TypeTools


class TestTypeTools:
    def test_search_by_single_type(self, tmp_path):
        store = MetadataStore(tmp_path)
        store.save_git_commits([
            {"hash": "a1", "title": "sched: optimize", "author": "P", "date": "2024-01-01", "message": "", "type_tags": "performance"},
            {"hash": "a2", "title": "tcp: fix bug", "author": "E", "date": "2024-01-02", "message": "", "type_tags": "bugfix"},
            {"hash": "a3", "title": "mm: add feature", "author": "M", "date": "2024-01-03", "message": "", "type_tags": "feature"},
        ])

        tools = TypeTools(store)
        results = tools.git_search_by_type(["performance"])

        assert len(results) == 1
        assert results[0]["hash"] == "a1"

    def test_search_by_multiple_types(self, tmp_path):
        store = MetadataStore(tmp_path)
        store.save_git_commits([
            {"hash": "a1", "title": "fix regression", "author": "P", "date": "2024-01-01", "message": "", "type_tags": "bugfix,regression,performance"},
            {"hash": "a2", "title": "pure optimize", "author": "E", "date": "2024-01-02", "message": "", "type_tags": "performance"},
            {"hash": "a3", "title": "pure bugfix", "author": "M", "date": "2024-01-03", "message": "", "type_tags": "bugfix"},
        ])

        tools = TypeTools(store)
        results = tools.git_search_by_type(["performance"])

        assert len(results) == 2
        hashes = {r["hash"] for r in results}
        assert "a1" in hashes
        assert "a2" in hashes

    def test_search_with_subsys_filter(self, tmp_path):
        store = MetadataStore(tmp_path)
        store.save_git_commits([
            {"hash": "a1", "title": "sched: optimize", "author": "P", "date": "2024-01-01", "message": "", "type_tags": "performance"},
            {"hash": "a2", "title": "mm: optimize", "author": "E", "date": "2024-01-02", "message": "", "type_tags": "performance"},
        ])

        tools = TypeTools(store)
        results = tools.git_search_by_type(["performance"], subsys="sched")

        assert len(results) == 1
        assert results[0]["hash"] == "a1"

    def test_type_stats(self, tmp_path):
        store = MetadataStore(tmp_path)
        store.save_git_commits([
            {"hash": "a1", "title": "fix", "author": "P", "date": "2024-01-01", "message": "", "type_tags": "bugfix"},
            {"hash": "a2", "title": "optimize", "author": "E", "date": "2024-01-02", "message": "", "type_tags": "performance"},
            {"hash": "a3", "title": "fix2", "author": "M", "date": "2024-01-03", "message": "", "type_tags": "bugfix"},
            {"hash": "a4", "title": "refactor", "author": "A", "date": "2024-01-04", "message": "", "type_tags": "refactor"},
        ])

        tools = TypeTools(store)
        stats = tools.git_type_stats()

        assert stats["bugfix"] == 2
        assert stats["performance"] == 1
        assert stats["refactor"] == 1
        assert stats["total"] == 4

    def test_type_stats_empty(self, tmp_path):
        store = MetadataStore(tmp_path)
        tools = TypeTools(store)
        stats = tools.git_type_stats()

        assert stats["total"] == 0

    def test_search_by_type_nonexistent(self, tmp_path):
        store = MetadataStore(tmp_path)
        store.save_git_commits([
            {"hash": "a1", "title": "fix", "author": "P", "date": "2024-01-01", "message": "", "type_tags": "bugfix"},
        ])

        tools = TypeTools(store)
        results = tools.git_search_by_type(["security"])

        assert len(results) == 0

    def test_search_by_type_with_date_range(self, tmp_path):
        store = MetadataStore(tmp_path)
        store.save_git_commits([
            {"hash": "a1", "title": "old optimize", "author": "P", "date": "2023-01-01", "message": "", "type_tags": "performance"},
            {"hash": "a2", "title": "new optimize", "author": "E", "date": "2024-06-01", "message": "", "type_tags": "performance"},
        ])

        tools = TypeTools(store)
        results = tools.git_search_by_type(["performance"], since="2024-01-01", until="2024-12-31")

        assert len(results) == 1
        assert results[0]["hash"] == "a2"
