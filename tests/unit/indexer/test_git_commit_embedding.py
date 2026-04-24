import pytest
from pathlib import Path
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from kernel_rag_mcp.indexer.git_indexer import GitIndexer, CommitEntry
from kernel_rag_mcp.storage.metadata_store import MetadataStore
from kernel_rag_mcp.storage.vector_store import VectorStore


class TestGitCommitEmbedding:
    """Test that commits can be embedded and stored for semantic search."""

    def test_commit_text_format(self):
        """Commit text for embedding should include title + body + file list."""
        commit = CommitEntry(
            hash="abc123",
            title="sched: optimize vruntime update",
            author="Peter Zijlstra",
            date="2024-01-15",
            body="Improve vruntime calculation for large CPU counts.\n\nThis reduces latency by 15%.",
        )

        text = f"{commit.title}\n{commit.body}"

        assert "sched" in text
        assert "vruntime" in text
        assert "latency" in text

    def test_store_commit_with_vector_id(self, tmp_path):
        """git_commits table should support vector_id for linking to Qdrant."""
        store = MetadataStore(tmp_path)

        commits = [{
            "hash": "abc123",
            "title": "sched: optimize vruntime",
            "author": "Peter Z",
            "date": "2024-01-15",
            "message": "Improve vruntime",
            "vector_id": "commit:abc123",
            "type_tags": "performance,sched",
        }]

        store.save_git_commits(commits)

        loaded = store.search_git_commits(query="vruntime")
        assert len(loaded) == 1
        assert loaded[0]["hash"] == "abc123"

    def test_store_commit_with_type_tags(self, tmp_path):
        """git_commits table should store type_tags for filtering."""
        store = MetadataStore(tmp_path)

        commits = [
            {"hash": "a1", "title": "sched: optimize vruntime", "author": "P", "date": "2024-01-01", "message": "", "type_tags": "performance"},
            {"hash": "a2", "title": "tcp: fix RTO bug", "author": "E", "date": "2024-01-02", "message": "", "type_tags": "bugfix"},
            {"hash": "a3", "title": "mm: refactor slab", "author": "M", "date": "2024-01-03", "message": "", "type_tags": "refactor,performance"},
        ]

        store.save_git_commits(commits)

        perf_commits = store.search_git_commits_by_type("performance")
        assert len(perf_commits) == 2
        hashes = {c["hash"] for c in perf_commits}
        assert "a1" in hashes
        assert "a3" in hashes

    def test_store_commit_with_labels(self, tmp_path):
        """git_commits table should store labels like Fixes:, Reported-by:."""
        store = MetadataStore(tmp_path)

        commits = [{
            "hash": "fix123",
            "title": "tcp: fix RTO",
            "author": "E",
            "date": "2024-01-01",
            "message": "Fixes: bad456 (\"tcp: broken RTO\")\nReported-by: John",
            "labels": '{"Fixes": "bad456", "Reported-by": ["John"]}',
        }]

        store.save_git_commits(commits)
        loaded = store.search_git_commits(query="RTO")
        assert len(loaded) == 1


class TestGitCommitVectorStore:
    """Test storing commit vectors in Qdrant."""

    def test_commit_vector_collection(self, tmp_path):
        """Should create 'git_commits' collection separate from 'code_chunks'."""
        store = VectorStore(backend="qdrant", path=tmp_path)
        store.create_collection("git_commits", 768)

        store.insert([{
            "id": "commit:abc123",
            "vector": [0.1] * 768,
            "metadata": {"title": "sched: optimize", "hash": "abc123"}
        }])

        results = store.search([0.1] * 768, top_k=1)
        assert len(results) == 1
        assert results[0].id == "commit:abc123"

    def test_commit_vector_search_by_semantics(self, tmp_path):
        """Semantic search should find commits by meaning, not just keywords."""
        store = VectorStore(backend="qdrant", path=tmp_path)
        store.create_collection("git_commits", 768)

        store.insert([
            {"id": "c1", "vector": [0.9] * 768, "metadata": {"title": "sched: optimize vruntime", "hash": "c1"}},
            {"id": "c2", "vector": [-0.9] * 768, "metadata": {"title": "doc: update README", "hash": "c2"}},
        ])

        results = store.search([0.9] * 768, top_k=2)
        assert results[0].id == "c1"


class TestGitIndexerWithEmbedding:
    """Test GitIndexer embedding pipeline."""

    def test_index_commits_with_embedding(self, tmp_path):
        """GitIndexer should embed commits and store in both SQLite and Qdrant."""
        from kernel_rag_mcp.indexer.git_indexer import GitIndexer

        mock_embedder = MagicMock()
        mock_embedder.dim = 768
        mock_embedder.encode.return_value = [[0.1] * 768]

        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        indexer = GitIndexer(tmp_path)

        commits = [
            CommitEntry(hash="abc123", title="sched: optimize", author="P", date="2024-01-01", body="body"),
        ]

        metadata_store = MetadataStore(tmp_path / "metadata")
        vector_store = VectorStore(backend="qdrant", path=tmp_path / "qdrant")
        vector_store.create_collection("git_commits", 768)

        indexer.index_commits_with_embedding(commits, metadata_store, vector_store, mock_embedder)

        stored = metadata_store.search_git_commits(query="optimize")
        assert len(stored) == 1
        assert stored[0]["hash"] == "abc123"
        assert stored[0].get("vector_id") == "commit:abc123"

        vectors = vector_store.search([0.1] * 768, top_k=1)
        assert len(vectors) == 1

    def test_commit_type_tags_extraction(self):
        """GitIndexer should classify commits and assign type_tags."""
        from kernel_rag_mcp.indexer.git_indexer import GitIndexer

        indexer = GitIndexer(Path("."))

        perf_commit = CommitEntry(hash="a1", title="sched: optimize vruntime", author="P", date="2024-01-01", body="")
        bug_commit = CommitEntry(hash="a2", title="tcp: fix RTO bug", author="E", date="2024-01-01", body="")
        doc_commit = CommitEntry(hash="a3", title="doc: update scheduler docs", author="A", date="2024-01-01", body="")

        assert "performance" in indexer._classify_commit(perf_commit)
        assert "bugfix" in indexer._classify_commit(bug_commit)
        assert "documentation" in indexer._classify_commit(doc_commit)

    def test_commit_labels_extraction(self):
        """GitIndexer should extract Fixes: and Reported-by: labels from body."""
        from kernel_rag_mcp.indexer.git_indexer import GitIndexer

        indexer = GitIndexer(Path("."))

        body = """Fixes: bad456 ("tcp: broken RTO")
Reported-by: John Doe <john@example.com>
Reviewed-by: David Miller"""

        labels = indexer._extract_labels(body)

        assert labels.get("Fixes") == "bad456"
        assert any("John Doe" in entry for entry in labels.get("Reported-by", []))
        assert any("David Miller" in entry for entry in labels.get("Reviewed-by", []))


class TestGitSemanticSearch:
    """Test end-to-end semantic search for commits."""

    def test_semantic_search_finds_relevant_commits(self, tmp_path):
        """Searching 'performance optimization' should find performance commits."""
        metadata_store = MetadataStore(tmp_path / "metadata")
        vector_store = VectorStore(backend="qdrant", path=tmp_path / "qdrant")
        vector_store.create_collection("git_commits", 768)

        commits = [
            {"hash": "c1", "title": "sched: optimize vruntime for scalability", "author": "P", "date": "2024-01-01", "message": "", "vector_id": "commit:c1", "type_tags": "performance"},
            {"hash": "c2", "title": "doc: fix typo in sched doc", "author": "A", "date": "2024-01-02", "message": "", "vector_id": "commit:c2", "type_tags": "documentation"},
        ]
        metadata_store.save_git_commits(commits)

        vector_store.insert([
            {"id": "commit:c1", "vector": [0.9] * 768, "metadata": {"hash": "c1", "title": "sched: optimize vruntime"}},
            {"id": "commit:c2", "vector": [-0.9] * 768, "metadata": {"hash": "c2", "title": "doc: fix typo"}},
        ])

        query_vector = [0.9] * 768
        results = vector_store.search(query_vector, top_k=2)

        assert len(results) == 2
        assert results[0].id == "commit:c1"

        meta_results = metadata_store.get_git_commits_by_hashes(["c1"])
        assert len(meta_results) == 1
        assert meta_results[0]["type_tags"] == "performance"

    def test_type_filter_combined_with_semantic(self, tmp_path):
        """Should filter by type_tags after semantic search."""
        metadata_store = MetadataStore(tmp_path / "metadata")

        commits = [
            {"hash": "c1", "title": "sched: optimize vruntime", "author": "P", "date": "2024-01-01", "message": "", "type_tags": "performance"},
            {"hash": "c2", "title": "tcp: optimize RTO", "author": "E", "date": "2024-01-02", "message": "", "type_tags": "performance"},
            {"hash": "c3", "title": "mm: fix page allocation", "author": "M", "date": "2024-01-03", "message": "", "type_tags": "bugfix"},
        ]
        metadata_store.save_git_commits(commits)

        perf_commits = metadata_store.search_git_commits_by_type("performance")
        assert len(perf_commits) == 2

        bug_commits = metadata_store.search_git_commits_by_type("bugfix")
        assert len(bug_commits) == 1
        assert bug_commits[0]["hash"] == "c3"


class TestGitSearchPerformance:
    """Performance requirements for git semantic search."""

    def test_query_latency_target(self):
        from tests.conftest import INDEX_PERFORMANCE_TARGETS
        assert INDEX_PERFORMANCE_TARGETS["query_latency_p95_baseline"] <= 0.5
