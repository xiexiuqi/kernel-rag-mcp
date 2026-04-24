import pytest
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from kernel_rag_mcp.server.tools.type_tools import TypeTools
from kernel_rag_mcp.server.tools.causal_tools import CausalTools
from kernel_rag_mcp.storage.graph_store import GraphStore
from kernel_rag_mcp.storage.metadata_store import MetadataStore


class TestMCPTypeTools:
    def test_git_search_by_type_integration(self, tmp_path):
        store = MetadataStore(tmp_path)
        store.save_git_commits([
            {"hash": "a1", "title": "sched: optimize vruntime", "author": "P", "date": "2024-01-01", "message": "", "type_tags": "performance"},
            {"hash": "a2", "title": "tcp: fix RTO", "author": "E", "date": "2024-01-02", "message": "", "type_tags": "bugfix"},
            {"hash": "a3", "title": "mm: add feature", "author": "M", "date": "2024-01-03", "message": "", "type_tags": "feature"},
        ])

        tools = TypeTools(store)
        results = tools.git_search_by_type(["performance"])

        assert len(results) == 1
        assert results[0]["hash"] == "a1"

    def test_git_type_stats_integration(self, tmp_path):
        store = MetadataStore(tmp_path)
        store.save_git_commits([
            {"hash": "a1", "title": "fix", "author": "P", "date": "2024-01-01", "message": "", "type_tags": "bugfix"},
            {"hash": "a2", "title": "optimize", "author": "E", "date": "2024-01-02", "message": "", "type_tags": "performance"},
        ])

        tools = TypeTools(store)
        stats = tools.git_type_stats()

        assert stats["total"] == 2
        assert stats["bugfix"] == 1
        assert stats["performance"] == 1


class TestMCPCausalTools:
    def test_git_causal_chain_upstream(self, tmp_path):
        graph = GraphStore(backend="networkx", path=tmp_path)
        graph.add_node("bug", {"title": "introduced bug"})
        graph.add_node("fix1", {"title": "partial fix"})
        graph.add_node("fix2", {"title": "complete fix"})

        graph.add_edge("fix1", "FIXES", "bug")
        graph.add_edge("fix2", "FIXES", "fix1")

        tools = CausalTools(graph)
        result = tools.git_causal_chain("fix2", direction="upstream")

        assert "fix2" in result
        assert "fix1" in result
        assert "bug" in result

    def test_git_bug_origin(self, tmp_path):
        graph = GraphStore(backend="networkx", path=tmp_path)
        graph.add_node("origin", {"title": "origin commit"})
        graph.add_node("fix", {"title": "fix commit"})

        graph.add_edge("fix", "FIXES", "origin")

        tools = CausalTools(graph)
        origin = tools.git_bug_origin("fix")

        assert origin == "origin"

    def test_git_backport_status_found(self, tmp_path):
        graph = GraphStore(backend="networkx", path=tmp_path)
        graph.add_node("main_fix", {"title": "main fix"})
        graph.add_node("stable_515", {"title": "stable 5.15"})

        graph.add_edge("stable_515", "CHERRY_PICK_FROM", "main_fix")

        tools = CausalTools(graph)
        status = tools.git_backport_status("main_fix")

        assert "stable_515" in status

    def test_git_backport_status_not_found(self, tmp_path):
        graph = GraphStore(backend="networkx", path=tmp_path)
        graph.add_node("main_fix", {"title": "main fix"})

        tools = CausalTools(graph)
        status = tools.git_backport_status("main_fix")

        assert "No backport" in status


class TestMCPRouter:
    def test_router_classifies_blame(self):
        from kernel_rag_mcp.server.router import IntentRouter
        router = IntentRouter()
        assert router.classify("这行代码是谁引入的") == "blame"

    def test_router_classifies_causal(self):
        from kernel_rag_mcp.server.router import IntentRouter
        router = IntentRouter()
        assert router.classify("这个bug是哪个commit引入的") == "causal"

    def test_router_classifies_patch_type(self):
        from kernel_rag_mcp.server.router import IntentRouter
        router = IntentRouter()
        assert router.classify("v6.12到v6.13之间sched有哪些改动") == "patch_type"

    def test_router_defaults_to_semantic(self):
        from kernel_rag_mcp.server.router import IntentRouter
        router = IntentRouter()
        assert router.classify("CFS怎么更新vruntime") == "semantic"
