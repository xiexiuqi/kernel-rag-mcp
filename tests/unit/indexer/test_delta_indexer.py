import pytest
from pathlib import Path
import sys
import json
import subprocess
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from kernel_rag_mcp.indexer.delta_indexer import DeltaIndexer
from kernel_rag_mcp.retriever.delta_searcher import DeltaSearcher
from kernel_rag_mcp.storage.metadata_store import MetadataStore
from kernel_rag_mcp.storage.vector_store import VectorStore


class TestDeltaChangeDetection:
    """Test git diff-based change detection for delta indexing."""

    def test_detect_changed_files(self, tmp_path):
        """DeltaIndexer should detect changed files between two commits."""
        indexer = DeltaIndexer(
            repo_path=tmp_path,
            index_root=tmp_path / ".kernel-rag",
            version="v7.0"
        )
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="kernel/sched/fair.c\nmm/page_alloc.c\nnet/core/dev.c\n",
                returncode=0
            )
            
            changed = indexer.detect_changes("v7.0", "v7.0.1")
            
            assert len(changed) == 3
            assert "kernel/sched/fair.c" in changed
            assert "mm/page_alloc.c" in changed
            assert "net/core/dev.c" in changed
    
    def test_detect_no_changes(self, tmp_path):
        """DeltaIndexer should handle no changes gracefully."""
        indexer = DeltaIndexer(
            repo_path=tmp_path,
            index_root=tmp_path / ".kernel-rag",
            version="v7.0"
        )
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            
            changed = indexer.detect_changes("v7.0", "v7.0")
            
            assert len(changed) == 0
    
    def test_filter_by_subsystem(self, tmp_path):
        """Changed files should be filtered to tracked subsystems."""
        indexer = DeltaIndexer(
            repo_path=tmp_path,
            index_root=tmp_path / ".kernel-rag",
            version="v7.0",
            subsystems=["kernel/sched", "mm"]
        )
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="kernel/sched/fair.c\nmm/page_alloc.c\nnet/core/dev.c\n drivers/gpu/drm.c\n",
                returncode=0
            )
            
            changed = indexer.detect_changes("v7.0", "v7.0.1")
            
            assert len(changed) == 2
            assert "kernel/sched/fair.c" in changed
            assert "mm/page_alloc.c" in changed
            assert "net/core/dev.c" not in changed
            assert "drivers/gpu/drm.c" not in changed


class TestDeltaIndexBuilding:
    """Test building delta index for changed files."""

    def test_create_delta_directory(self, tmp_path):
        """Delta index should be stored in delta-<name>/ directory."""
        repo_path = tmp_path / "linux"
        repo_path.mkdir()
        
        indexer = DeltaIndexer(
            repo_path=repo_path,
            index_root=tmp_path / ".kernel-rag",
            version="v7.0"
        )
        
        delta_dir = indexer.get_delta_dir("v7.0.1")
        
        assert "delta-v7.0.1" in str(delta_dir)
        assert delta_dir.parent.name == "v7.0"
    
    def test_delta_metadata_tracking(self, tmp_path):
        """Delta index should record from_commit, to_commit, changed_files."""
        from kernel_rag_mcp.indexer.delta_indexer import DeltaMetadata
        
        meta = DeltaMetadata(
            from_commit="abc123",
            to_commit="def456",
            changed_files=["kernel/sched/fair.c"],
            timestamp="2024-01-01T00:00:00Z"
        )
        
        assert meta.from_commit == "abc123"
        assert meta.to_commit == "def456"
        assert len(meta.changed_files) == 1
    
    def test_build_delta_index(self, tmp_path):
        """DeltaIndexer should build a complete delta index for changed files."""
        repo_path = tmp_path / "linux"
        repo_path.mkdir()
        
        sched_dir = repo_path / "kernel" / "sched"
        sched_dir.mkdir(parents=True)
        (sched_dir / "fair.c").write_text("void update_curr() {\n    // updated\n}\n")
        
        indexer = DeltaIndexer(
            repo_path=repo_path,
            index_root=tmp_path / ".kernel-rag",
            version="v7.0",
            subsystems=["kernel/sched"]
        )
        
        # Mock embedder
        mock_embedder = MagicMock()
        mock_embedder.dim = 768
        mock_embedder.encode.return_value = [[0.1] * 768]
        
        delta_dir = indexer.build_delta(
            changed_files=["kernel/sched/fair.c"],
            from_commit="abc123",
            to_commit="def456",
            embedder=mock_embedder
        )
        
        # Verify delta directory structure
        assert delta_dir.exists()
        assert (delta_dir / "metadata.db").exists()
        assert (delta_dir / "qdrant").exists()
        
        # Verify metadata was saved
        store = MetadataStore(delta_dir)
        from_commit = store.get_metadata("from_commit")
        to_commit = store.get_metadata("to_commit")
        
        assert from_commit == "abc123"
        assert to_commit == "def456"
        
        # Verify chunks were indexed
        chunks = store.search_chunks_by_subsys("sched")
        assert len(chunks) > 0


class TestDeltaQueryOverlay:
    """Test searching with base + delta overlay."""

    def test_delta_overrides_base(self, tmp_path):
        """When a file exists in both base and delta, delta should win."""
        from kernel_rag_mcp.indexer.parsers.tree_sitter_c import CodeChunk
        
        base_dir = tmp_path / "base"
        delta_dir = tmp_path / "delta-test"
        base_dir.mkdir()
        delta_dir.mkdir()
        
        # Create base index with one chunk
        base_store = MetadataStore(base_dir)
        base_store.save_chunks([{
            "id": "kernel/sched/fair.c:update_curr",
            "name": "update_curr",
            "file_path": "kernel/sched/fair.c",
            "start_line": 10,
            "end_line": 20,
            "chunk_type": "function",
            "subsys": "sched",
            "code_snippet": "old code"
        }])
        
        # Create delta index with updated chunk for same file
        delta_store = MetadataStore(delta_dir)
        delta_store.save_chunks([{
            "id": "kernel/sched/fair.c:update_curr",
            "name": "update_curr",
            "file_path": "kernel/sched/fair.c",
            "start_line": 15,
            "end_line": 25,
            "chunk_type": "function",
            "subsys": "sched",
            "code_snippet": "new code"
        }])
        
        searcher = DeltaSearcher(
            base_path=base_dir,
            delta_paths=[delta_dir],
            repo_path=tmp_path
        )
        
        # Load all chunks with overlay
        chunks = searcher._load_all_chunks()
        
        # Find the update_curr chunk - should have delta's line numbers
        update_curr = [c for c in chunks if c.name == "update_curr"]
        assert len(update_curr) == 1
        assert update_curr[0].start_line == 15  # from delta, not base (10)
    
    def test_multiple_deltas_overlay(self, tmp_path):
        """With multiple deltas, the latest delta should win."""
        base_dir = tmp_path / "base"
        delta1_dir = tmp_path / "delta-1"
        delta2_dir = tmp_path / "delta-2"
        
        for d in [base_dir, delta1_dir, delta2_dir]:
            d.mkdir()
        
        # Base: line 10
        MetadataStore(base_dir).save_chunks([{
            "id": "test.c:func",
            "name": "func",
            "file_path": "test.c",
            "start_line": 10,
            "end_line": 20,
            "chunk_type": "function",
            "subsys": "sched",
            "code_snippet": "base"
        }])
        
        # Delta1: line 12
        MetadataStore(delta1_dir).save_chunks([{
            "id": "test.c:func",
            "name": "func",
            "file_path": "test.c",
            "start_line": 12,
            "end_line": 22,
            "chunk_type": "function",
            "subsys": "sched",
            "code_snippet": "delta1"
        }])
        
        # Delta2: line 14
        MetadataStore(delta2_dir).save_chunks([{
            "id": "test.c:func",
            "name": "func",
            "file_path": "test.c",
            "start_line": 14,
            "end_line": 24,
            "chunk_type": "function",
            "subsys": "sched",
            "code_snippet": "delta2"
        }])
        
        searcher = DeltaSearcher(
            base_path=base_dir,
            delta_paths=[delta1_dir, delta2_dir],
            repo_path=tmp_path
        )
        
        chunks = searcher._load_all_chunks()
        func = [c for c in chunks if c.name == "func"][0]
        
        assert func.start_line == 14  # latest delta wins
    
    def test_search_across_base_and_delta(self, tmp_path):
        """Search should return results from both base and delta."""
        base_dir = tmp_path / "base"
        delta_dir = tmp_path / "delta-test"
        base_dir.mkdir()
        delta_dir.mkdir()
        
        # Base has one chunk
        base_store = MetadataStore(base_dir)
        base_store.save_chunks([{
            "id": "base.c:base_func",
            "name": "base_func",
            "file_path": "base.c",
            "start_line": 1,
            "end_line": 10,
            "chunk_type": "function",
            "subsys": "sched",
            "code_snippet": "base function"
        }])
        
        # Delta adds another chunk
        delta_store = MetadataStore(delta_dir)
        delta_store.save_chunks([{
            "id": "delta.c:delta_func",
            "name": "delta_func",
            "file_path": "delta.c",
            "start_line": 1,
            "end_line": 10,
            "chunk_type": "function",
            "subsys": "sched",
            "code_snippet": "delta function"
        }])
        
        # Create vector stores with matching vectors
        base_vec = VectorStore(backend="qdrant", path=base_dir / "qdrant")
        base_vec.create_collection("code_chunks", 768)
        base_vec.insert([{
            "id": "base.c:base_func",
            "vector": [0.1] * 768,
            "metadata": {"name": "base_func", "file_path": "base.c"}
        }])
        
        delta_vec = VectorStore(backend="qdrant", path=delta_dir / "qdrant")
        delta_vec.create_collection("code_chunks", 768)
        delta_vec.insert([{
            "id": "delta.c:delta_func",
            "vector": [0.2] * 768,
            "metadata": {"name": "delta_func", "file_path": "delta.c"}
        }])
        
        searcher = DeltaSearcher(
            base_path=base_dir,
            delta_paths=[delta_dir],
            repo_path=tmp_path
        )
        
        # Mock embedder to return matching vectors
        mock_embedder = MagicMock()
        mock_embedder.encode.return_value = [[0.1] * 768]
        searcher.embedder = mock_embedder
        
        results = searcher.dense_search("test", top_k=10)
        
        # Should find both base and delta results
        names = [r.chunk.name for r in results]
        assert "base_func" in names
        assert "delta_func" in names


class TestDeltaIndexerIntegration:
    """Integration tests for delta indexing with real git repo."""

    def test_end_to_end_delta_workflow(self, tmp_path):
        """Full workflow: init repo -> base index -> modify -> delta index -> query."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()
        
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True, capture_output=True)
        
        # Create initial file (base version)
        src_dir = repo_path / "kernel" / "sched"
        src_dir.mkdir(parents=True)
        (src_dir / "fair.c").write_text("void update_curr() {\n    // version 1\n}\n")
        
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, capture_output=True)
        
        # Get base commit
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_path, check=True, capture_output=True, text=True
        )
        base_commit = result.stdout.strip()
        
        # Modify file
        (src_dir / "fair.c").write_text("void update_curr() {\n    // version 2 - updated\n}\n")
        
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Update function"], cwd=repo_path, check=True, capture_output=True)
        
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_path, check=True, capture_output=True, text=True
        )
        new_commit = result.stdout.strip()
        
        # Build delta index
        indexer = DeltaIndexer(
            repo_path=repo_path,
            index_root=tmp_path / ".kernel-rag",
            version="v1.0",
            subsystems=["kernel/sched"]
        )
        
        mock_embedder = MagicMock()
        mock_embedder.dim = 768
        mock_embedder.encode.return_value = [[0.1] * 768]
        
        delta_dir = indexer.build_delta(
            changed_files=["kernel/sched/fair.c"],
            from_commit=base_commit,
            to_commit=new_commit,
            embedder=mock_embedder
        )
        
        # Verify delta was created
        assert delta_dir.exists()
        store = MetadataStore(delta_dir)
        chunks = store.search_chunks_by_subsys("sched")
        assert len(chunks) > 0
        
        # Verify metadata
        assert store.get_metadata("from_commit") == base_commit
        assert store.get_metadata("to_commit") == new_commit

    def test_delta_listing(self, tmp_path):
        """Should list all available deltas for a version."""
        indexer = DeltaIndexer(
            repo_path=tmp_path,
            index_root=tmp_path / ".kernel-rag",
            version="v7.0"
        )
        
        # Create some fake delta directories
        version_dir = tmp_path / ".kernel-rag" / "linux" / "v7.0"
        (version_dir / "delta-v7.0.1").mkdir(parents=True)
        (version_dir / "delta-v7.0.2").mkdir(parents=True)
        (version_dir / "base").mkdir()
        
        deltas = indexer.list_deltas()
        
        assert len(deltas) == 2
        assert any("v7.0.1" in str(d) for d in deltas)
        assert any("v7.0.2" in str(d) for d in deltas)


class TestDeltaPerformance:
    """Performance requirements for delta indexing."""

    def test_incremental_update_time_target(self):
        """Delta indexing should complete within 180 seconds (from conftest)."""
        from tests.conftest import INDEX_PERFORMANCE_TARGETS
        
        assert INDEX_PERFORMANCE_TARGETS["incremental_update_time"] == 180
    
    def test_delta_query_latency_target(self):
        """Delta overlay queries should complete within 800ms (from conftest)."""
        from tests.conftest import INDEX_PERFORMANCE_TARGETS
        
        assert INDEX_PERFORMANCE_TARGETS["query_latency_p95_delta"] == 0.8
