from typing import List, Dict, Any

from ..storage.graph_store import GraphStore
from .parsers.causal_parser import CausalParser


class CausalIndexer:
    def __init__(self):
        self.parser = CausalParser()

    def index_commits(self, commits: List[Dict[str, Any]], graph: GraphStore):
        for commit in commits:
            commit_hash = commit["hash"]
            title = commit.get("title", "")
            body = commit.get("body", "")

            graph.add_node(commit_hash, {
                "title": title,
                "type_tags": commit.get("type_tags", []),
            })

            labels = self.parser.extract_labels(body)

            if "Fixes" in labels:
                targets = labels["Fixes"]
                if isinstance(targets, str):
                    targets = [targets]
                for target in targets:
                    graph.add_node(target, {"title": f"bug introduced by {target[:8]}"})
                    graph.add_edge(commit_hash, "FIXES", target)

            if "Introduced-by" in labels:
                targets = labels["Introduced-by"]
                if isinstance(targets, str):
                    targets = [targets]
                for target in targets:
                    graph.add_node(target, {"title": f"introduced by {target[:8]}"})
                    graph.add_edge(commit_hash, "INTRODUCED_BY", target)

            if "Cherry-picked-from" in labels:
                target = labels["Cherry-picked-from"]
                graph.add_node(target, {"title": f"original {target[:8]}"})
                graph.add_edge(commit_hash, "CHERRY_PICK_FROM", target)

            if self.parser.is_revert(title):
                reverted = self._extract_reverted_hash(title, body)
                if reverted:
                    graph.add_node(reverted, {"title": f"reverted {reverted[:8]}"})
                    graph.add_edge(commit_hash, "REVERTS", reverted)

            if "Cc-stable" in labels:
                graph.add_node(commit_hash, {"title": title, "backport": True})

    def _extract_reverted_hash(self, title: str, body: str) -> str:
        import re
        match = re.search(r'Revert\s+["\']?([a-f0-9]+)', title + "\n" + body, re.IGNORECASE)
        if match:
            return match.group(1)
        match = re.search(r'this\s+reverts?\s+commit\s+([a-f0-9]+)', body, re.IGNORECASE)
        if match:
            return match.group(1)
        return ""
