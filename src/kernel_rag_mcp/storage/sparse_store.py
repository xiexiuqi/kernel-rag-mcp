"""In-memory sparse / symbolic index."""

from pathlib import Path


class SparseResult:
    """Single sparse search result."""

    def __init__(self, symbol: str, doc: dict):
        self.symbol = symbol
        self._doc = doc


class SparseStore:
    """Sparse store backed by an in-memory list.

    Parameters
    ----------
    backend: str
        Reserved for future real backend selection (e.g. "meilisearch").
    path: Path | str | None
        Directory where persistent data could live.
    """

    def __init__(self, backend: str = "meilisearch", path=None):
        self.backend = backend
        self.path = Path(path) if path else None
        self._docs: list[dict] = []

    def index(self, docs: list[dict]) -> None:
        """Add documents to the sparse index.

        Each document should contain at least:
        - ``id`` (str)
        - ``symbol`` (str)
        - optional fields such as ``file``, ``subsys``, …
        """
        self._docs.extend(docs)

    def search(self, query: str, filter: dict | None = None) -> list[SparseResult]:
        """Return documents whose ``symbol`` contains *query* as a substring.

        An optional *filter* dict performs exact-match filtering on document
        fields, e.g. ``{"subsys": "mm"}``.
        """
        query_lower = query.lower()
        results: list[SparseResult] = []

        for doc in self._docs:
            symbol = doc.get("symbol", "")
            if query_lower not in symbol.lower():
                continue

            if filter is not None:
                if not all(doc.get(k) == v for k, v in filter.items()):
                    continue

            results.append(SparseResult(symbol, doc))

        return results
