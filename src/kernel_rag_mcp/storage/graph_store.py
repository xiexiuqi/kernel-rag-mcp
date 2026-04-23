"""In-memory causal graph store."""

from collections import deque
from pathlib import Path


class EvolutionCommit:
    """Commit entry inside a :class:`FeatureEvolution`."""

    def __init__(self, commit_id: str, commit_type: str):
        self.id = commit_id
        self.type = commit_type


class FeatureEvolution:
    """Evolution history of a single feature."""

    def __init__(self, commits: list[EvolutionCommit]):
        self.commits = commits


class GraphStore:
    """Directed graph backed by adjacency lists.

    Parameters
    ----------
    backend: str
        Reserved for future real backend selection (e.g. "networkx").
    path: Path | str | None
        Directory where persistent data could live.
    """

    def __init__(self, backend: str = "networkx", path=None):
        self.backend = backend
        self.path = Path(path) if path else None

        self._nodes: dict[str, dict] = {}
        self._outgoing: dict[str, list[tuple[str, str]]] = {}
        self._incoming: dict[str, list[tuple[str, str]]] = {}

    def add_node(self, id: str, attrs: dict) -> None:
        """Add a node (idempotent)."""
        self._nodes[id] = attrs
        self._outgoing.setdefault(id, [])
        self._incoming.setdefault(id, [])

    def add_edge(self, from_id: str, label: str, to_id: str) -> None:
        """Add a directed edge *from_id* --[*label*]--> *to_id*."""
        self._nodes.setdefault(from_id, {})
        self._nodes.setdefault(to_id, {})
        self._outgoing.setdefault(from_id, [])
        self._incoming.setdefault(to_id, [])
        self._outgoing[from_id].append((label, to_id))
        self._incoming[to_id].append((from_id, label))

    def has_node(self, id: str) -> bool:
        return id in self._nodes

    def has_edge(self, from_id: str, to_id: str) -> bool:
        """Return ``True`` if *any* edge from *from_id* to *to_id* exists."""
        for _label, target in self._outgoing.get(from_id, []):
            if target == to_id:
                return True
        return False

    def find_path(self, from_id: str, to_id: str) -> list[str]:
        """BFS shortest path from *from_id* to *to_id*."""
        if from_id not in self._nodes or to_id not in self._nodes:
            return []

        queue = deque([(from_id, [from_id])])
        visited = {from_id}

        while queue:
            current, path = queue.popleft()
            if current == to_id:
                return path

            for _label, neighbor in self._outgoing.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        return []

    def get_neighbors(self, id: str) -> list[str]:
        """Return all target nodes of outgoing edges from *id*."""
        return [to_id for _label, to_id in self._outgoing.get(id, [])]

    def find_cycles(self) -> list[list[str]]:
        """Return every directed cycle found via DFS."""
        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(node: str, path: list[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for _label, neighbor in self._outgoing.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    idx = path.index(neighbor)
                    cycles.append(path[idx:] + [neighbor])

            path.pop()
            rec_stack.remove(node)

        for node in list(self._nodes.keys()):
            if node not in visited:
                dfs(node, [])

        return cycles

    def get_feature_evolution(self, feature_id: str) -> FeatureEvolution:
        """Walk backwards from *feature_id* and build an evolution timeline.

        The walk starts with every commit that has a direct edge **to**
        *feature_id*, then continues recursively along incoming edges to
        discover fix/regression commits.
        """
        commits: list[EvolutionCommit] = []
        visited: set[str] = set()
        queue = deque()

        for from_id, label in self._incoming.get(feature_id, []):
            queue.append((from_id, label))
            visited.add(from_id)

        while queue:
            commit_id, edge_label = queue.popleft()
            commits.append(EvolutionCommit(commit_id, self._label_to_type(edge_label)))

            for from_id, label in self._incoming.get(commit_id, []):
                if from_id not in visited:
                    visited.add(from_id)
                    queue.append((from_id, label))

        return FeatureEvolution(commits)

    @staticmethod
    def _label_to_type(label: str) -> str:
        """Map an edge label to a commit-type slug."""
        mapping = {
            "INTRODUCES": "introduce",
            "OPTIMIZES": "optimize",
            "FIXES_REGRESSION_IN": "fix_regression",
        }
        if label in mapping:
            return mapping[label]
        t = label.lower()
        if t.endswith("s"):
            t = t[:-1]
        return t
