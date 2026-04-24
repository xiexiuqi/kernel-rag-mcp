import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from kernel_rag_mcp.indexer.parsers.causal_parser import CausalParser
from kernel_rag_mcp.storage.graph_store import GraphStore


class TestCausalParser:
    def test_extract_fixes_tag(self):
        body = 'Fixes: a1b2c3d4e5f6 ("tcp: broken RTO calculation")'
        parser = CausalParser()
        labels = parser.extract_labels(body)
        assert labels["Fixes"] == "a1b2c3d4e5f6"

    def test_extract_introduced_by(self):
        body = 'Introduced-by: b2c3d4e5f6a1 ("sched: new load balancer")'
        parser = CausalParser()
        labels = parser.extract_labels(body)
        assert labels["Introduced-by"] == "b2c3d4e5f6a1"

    def test_extract_cc_stable(self):
        body = "Cc: stable@vger.kernel.org"
        parser = CausalParser()
        labels = parser.extract_labels(body)
        assert labels.get("Cc-stable") is True

    def test_extract_revert(self):
        title = 'Revert "tcp: change RTO"'
        parser = CausalParser()
        assert parser.is_revert(title)

    def test_extract_reported_by(self):
        body = "Reported-by: John Doe <john@example.com>"
        parser = CausalParser()
        labels = parser.extract_labels(body)
        assert "John Doe" in labels["Reported-by"][0]

    def test_multiple_labels(self):
        body = """Fixes: a1b2c3d ("bug")
Reported-by: Alice
Reviewed-by: Bob
Tested-by: Carol"""
        parser = CausalParser()
        labels = parser.extract_labels(body)
        assert "Fixes" in labels
        assert "Reported-by" in labels
        assert "Reviewed-by" in labels
        assert "Tested-by" in labels


class TestCausalGraphBuilding:
    def test_add_fixes_edge(self, tmp_path):
        graph = GraphStore(backend="networkx", path=tmp_path)
        graph.add_node("fix_commit", {"title": "fix bug", "type_tags": ["bugfix"]})
        graph.add_node("bug_commit", {"title": "introduce bug", "type_tags": ["feature"]})
        graph.add_edge("fix_commit", "FIXES", "bug_commit")

        assert graph.has_edge("fix_commit", "bug_commit")

    def test_causal_chain_traversal(self, tmp_path):
        graph = GraphStore(backend="networkx", path=tmp_path)
        graph.add_node("bug", {"title": "bug"})
        graph.add_node("fix1", {"title": "partial fix"})
        graph.add_node("fix2", {"title": "complete fix"})

        graph.add_edge("fix1", "FIXES", "bug")
        graph.add_edge("fix2", "FIXES", "fix1")

        chain = graph.find_path("fix2", "bug")
        assert len(chain) == 3
        assert chain[0] == "fix2"
        assert chain[1] == "fix1"
        assert chain[2] == "bug"

    def test_find_bug_origin(self, tmp_path):
        graph = GraphStore(backend="networkx", path=tmp_path)
        graph.add_node("origin", {"title": "origin commit"})
        graph.add_node("fix", {"title": "fix commit"})

        graph.add_edge("fix", "FIXES", "origin")

        neighbors = graph.get_neighbors("fix")
        assert "origin" in neighbors

    def test_backport_edge(self, tmp_path):
        graph = GraphStore(backend="networkx", path=tmp_path)
        graph.add_node("main_fix", {"title": "main fix"})
        graph.add_node("stable_backport", {"title": "stable backport"})

        graph.add_edge("stable_backport", "CHERRY_PICK_FROM", "main_fix")

        assert graph.has_edge("stable_backport", "main_fix")

    def test_revert_edge(self, tmp_path):
        graph = GraphStore(backend="networkx", path=tmp_path)
        graph.add_node("original", {"title": "original"})
        graph.add_node("revert", {"title": "revert"})

        graph.add_edge("revert", "REVERTS", "original")

        assert graph.has_edge("revert", "original")


class TestCausalGraphIndexer:
    def test_index_commits_to_graph(self, tmp_path):
        from kernel_rag_mcp.indexer.causal_indexer import CausalIndexer

        indexer = CausalIndexer()
        graph = GraphStore(backend="networkx", path=tmp_path)

        commits = [
            {"hash": "a1b2c3d", "title": "tcp: broken RTO", "body": ""},
            {"hash": "d4e5f6a", "title": "tcp: fix RTO", "body": 'Fixes: a1b2c3d ("tcp: broken RTO")'},
        ]

        indexer.index_commits(commits, graph)

        assert graph.has_node("a1b2c3d")
        assert graph.has_node("d4e5f6a")
        assert graph.has_edge("d4e5f6a", "a1b2c3d")

    def test_index_multiple_fixes_links(self, tmp_path):
        from kernel_rag_mcp.indexer.causal_indexer import CausalIndexer

        indexer = CausalIndexer()
        graph = GraphStore(backend="networkx", path=tmp_path)

        commits = [
            {"hash": "a1b2c3d", "title": "bug 1", "body": ""},
            {"hash": "b2c3d4e", "title": "bug 2", "body": ""},
            {"hash": "c3d4e5f", "title": "fix all", "body": 'Fixes: a1b2c3d ("bug 1")\nFixes: b2c3d4e ("bug 2")'},
        ]

        indexer.index_commits(commits, graph)

        assert graph.has_edge("c3d4e5f", "a1b2c3d")
        assert graph.has_edge("c3d4e5f", "b2c3d4e")

    def test_index_introduced_by(self, tmp_path):
        from kernel_rag_mcp.indexer.causal_indexer import CausalIndexer

        indexer = CausalIndexer()
        graph = GraphStore(backend="networkx", path=tmp_path)

        commits = [
            {"hash": "a1b2c3d", "title": "introduce feature", "body": ""},
            {"hash": "b2c3d4e", "title": "fix regression", "body": 'Introduced-by: a1b2c3d ("introduce feature")'},
        ]

        indexer.index_commits(commits, graph)

        assert graph.has_edge("b2c3d4e", "a1b2c3d")


class TestCausalMCPQuery:
    def test_git_causal_chain(self, tmp_path):
        from kernel_rag_mcp.server.tools.causal_tools import CausalTools

        graph = GraphStore(backend="networkx", path=tmp_path)
        graph.add_node("origin", {"title": "origin"})
        graph.add_node("fix", {"title": "fix"})
        graph.add_edge("fix", "FIXES", "origin")

        tools = CausalTools(graph)
        result = tools.git_causal_chain("fix", direction="upstream")

        assert "origin" in result
        assert "fix" in result

    def test_git_bug_origin(self, tmp_path):
        from kernel_rag_mcp.server.tools.causal_tools import CausalTools

        graph = GraphStore(backend="networkx", path=tmp_path)
        graph.add_node("origin", {"title": "origin"})
        graph.add_node("fix", {"title": "fix"})
        graph.add_edge("fix", "FIXES", "origin")

        tools = CausalTools(graph)
        origin = tools.git_bug_origin("fix")

        assert origin == "origin"

    def test_git_backport_status(self, tmp_path):
        from kernel_rag_mcp.server.tools.causal_tools import CausalTools

        graph = GraphStore(backend="networkx", path=tmp_path)
        graph.add_node("main", {"title": "main fix"})
        graph.add_node("stable_515", {"title": "stable 5.15"})
        graph.add_edge("stable_515", "CHERRY_PICK_FROM", "main")

        tools = CausalTools(graph)
        status = tools.git_backport_status("main")

        assert "stable_515" in status
