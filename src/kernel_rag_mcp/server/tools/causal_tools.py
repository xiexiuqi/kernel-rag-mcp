from typing import List

from ...storage.graph_store import GraphStore


class CausalTools:
    def __init__(self, graph: GraphStore):
        self.graph = graph

    def git_causal_chain(self, commit_hash: str, direction: str = "upstream") -> str:
        if not self.graph.has_node(commit_hash):
            return f"Commit {commit_hash} not found in causal graph"

        if direction == "upstream":
            path = self._find_upstream_chain(commit_hash)
        else:
            path = self._find_downstream_chain(commit_hash)

        if not path:
            return f"No causal chain found for {commit_hash}"

        lines = []
        for node_id in path:
            attrs = self.graph._nodes.get(node_id, {})
            title = attrs.get("title", node_id[:8])
            lines.append(f"- {node_id[:8]}: {title}")

        return "\n".join(lines)

    def _find_upstream_chain(self, start: str) -> List[str]:
        chain = [start]
        current = start
        visited = {current}

        while True:
            found = False
            for label, to_id in self.graph._outgoing.get(current, []):
                if label in ("FIXES", "INTRODUCED_BY", "REVERTS") and to_id not in visited:
                    chain.append(to_id)
                    visited.add(to_id)
                    current = to_id
                    found = True
                    break
            if not found:
                break

        return chain

    def _find_downstream_chain(self, start: str) -> List[str]:
        chain = [start]
        current = start
        visited = {current}

        while True:
            found = False
            for from_id, label in self.graph._incoming.get(current, []):
                if label in ("FIXES", "INTRODUCED_BY", "REVERTS") and from_id not in visited:
                    chain.append(from_id)
                    visited.add(from_id)
                    current = from_id
                    found = True
                    break
            if not found:
                break

        return chain

    def git_bug_origin(self, commit_hash: str) -> str:
        if not self.graph.has_node(commit_hash):
            return ""

        current = commit_hash
        for _ in range(100):
            upstream = self._find_upstream_chain(current)
            if len(upstream) <= 1:
                break
            current = upstream[-1]

        return current

    def git_backport_status(self, commit_hash: str) -> str:
        if not self.graph.has_node(commit_hash):
            return f"Commit {commit_hash} not found"

        backports = []
        for from_id, label in self.graph._incoming.get(commit_hash, []):
            if label == "CHERRY_PICK_FROM":
                backports.append(from_id)

        for label, to_id in self.graph._outgoing.get(commit_hash, []):
            if label == "CHERRY_PICK_FROM":
                backports.append(to_id)

        if not backports:
            return f"No backport information for {commit_hash}"

        return f"Backports: {', '.join(backports)}"
