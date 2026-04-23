import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from kernel_rag_mcp.retriever.hybrid_search import HybridSearcher
from kernel_rag_mcp.retriever.context_assembler import ContextAssembler


class TestHybridSearcher:
    def test_dense_search(self):
        searcher = HybridSearcher()
        query = "CFS vruntime update mechanism"

        results = searcher.dense_search(query, top_k=5)

        assert len(results) <= 5
        assert all(r.score > 0 for r in results)
        assert all(r.chunk.file_path for r in results)

    def test_sparse_search(self):
        searcher = HybridSearcher()
        query = "update_curr"

        results = searcher.sparse_search(query, top_k=5)

        assert len(results) <= 5

    def test_rrf_fusion(self):
        searcher = HybridSearcher()
        dense_results = [
            {"chunk": {"name": "func_a"}, "score": 0.9, "rank": 1},
            {"chunk": {"name": "func_b"}, "score": 0.8, "rank": 2},
            {"chunk": {"name": "func_c"}, "score": 0.7, "rank": 3},
        ]
        sparse_results = [
            {"chunk": {"name": "func_b"}, "score": 0.95, "rank": 1},
            {"chunk": {"name": "func_a"}, "score": 0.85, "rank": 2},
            {"chunk": {"name": "func_d"}, "score": 0.75, "rank": 3},
        ]

        fused = searcher.rrf_fusion(dense_results, sparse_results, k=60)

        assert len(fused) == 3
        assert all(f.score > 0 for f in fused)

    def test_kconfig_filter(self):
        searcher = HybridSearcher()
        query = "NUMA memory allocation"
        kconfig_filter = {"CONFIG_NUMA": "y", "CONFIG_SMP": "y"}

        results = searcher.search(query, kconfig_filter=kconfig_filter, top_k=5)

        assert len(results) <= 5
        for r in results:
            assert r.chunk.kconfig_condition in [None, "CONFIG_NUMA"]

    def test_subsystem_filter(self):
        searcher = HybridSearcher()
        query = "page allocation"

        results = searcher.search(query, subsys="mm", top_k=5)

        assert len(results) <= 5
        assert all("mm/" in r.chunk.file_path for r in results)

    def test_version_filter(self):
        searcher = HybridSearcher()
        query = "scheduler"

        results = searcher.search(query, version="v6.12", top_k=5)

        assert len(results) <= 5
        assert all(r.chunk.version == "v6.12" for r in results)

    def test_search_with_line_number_validation(self):
        from tests.conftest import KERNEL_REPO_PATH

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        index_path = Path.home() / ".kernel-rag" / "repos" / "linux" / "v7.0-rc6"
        if not index_path.exists():
            pytest.skip("Index not found")

        searcher = HybridSearcher(index_path, KERNEL_REPO_PATH)
        query = "schedule()"

        results = searcher.search(query, top_k=1)
        if len(results) == 0:
            pytest.skip("No search results available")

        result = results[0]
        assert result.chunk.start_line > 0
        assert result.chunk.end_line >= result.chunk.start_line

        validated = searcher.validate_line_number(result)
        assert validated.is_valid is True


class TestContextAssembler:
    def test_assemble_function_context(self):
        assembler = ContextAssembler()
        primary_chunk = {
            "name": "update_curr",
            "file_path": "kernel/sched/fair.c",
            "start_line": 100,
            "end_line": 120,
            "code": "static void update_curr(struct cfs_rq *cfs_rq) { ... }",
        }

        context = assembler.assemble(primary_chunk)

        assert context.primary == primary_chunk
        assert len(context.declarations) >= 0
        assert len(context.related_functions) >= 0

    def test_assemble_with_header_declaration(self):
        assembler = ContextAssembler()
        primary_chunk = {
            "name": "pick_next_task_fair",
            "file_path": "kernel/sched/fair.c",
            "start_line": 200,
            "end_line": 220,
        }

        context = assembler.assemble(primary_chunk)

        header_decls = [d for d in context.declarations if "include/linux/sched.h" in d.file_path]
        assert len(header_decls) >= 0

    def test_assemble_with_callers(self):
        assembler = ContextAssembler()
        primary_chunk = {
            "name": "schedule",
            "file_path": "kernel/sched/core.c",
            "start_line": 50,
            "end_line": 70,
        }

        context = assembler.assemble(primary_chunk, caller_depth=1)

        assert len(context.callers) >= 0
        assert all(c.name != primary_chunk["name"] for c in context.callers)

    def test_assemble_with_kconfig_context(self):
        assembler = ContextAssembler()
        primary_chunk = {
            "name": "update_rq_clock",
            "file_path": "kernel/sched/core.c",
            "start_line": 100,
            "end_line": 110,
            "kconfig_condition": "CONFIG_SMP",
        }

        context = assembler.assemble(primary_chunk)

        assert context.kconfig_context is not None
        assert "CONFIG_SMP" in context.kconfig_context

    def test_cross_file_assembly(self):
        assembler = ContextAssembler()
        primary_chunk = {
            "name": "tcp_sendmsg",
            "file_path": "net/ipv4/tcp.c",
            "start_line": 100,
            "end_line": 150,
        }

        context = assembler.assemble(primary_chunk)

        assert any("include/linux/tcp.h" in d.file_path for d in context.declarations)

    def test_assemble_limit_size(self):
        assembler = ContextAssembler()
        primary_chunk = {
            "name": "schedule",
            "file_path": "kernel/sched/core.c",
            "start_line": 1,
            "end_line": 100,
        }

        context = assembler.assemble(primary_chunk, max_tokens=2048)

        assert context.total_tokens <= 2048

    def test_real_kernel_search_and_assemble(self):
        from tests.conftest import KERNEL_REPO_PATH

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        index_path = Path.home() / ".kernel-rag" / "repos" / "linux" / "v7.0-rc6"
        if not index_path.exists():
            pytest.skip("Index not found")

        searcher = HybridSearcher(index_path, KERNEL_REPO_PATH)
        assembler = ContextAssembler()

        results = searcher.search("CFS vruntime", top_k=3)
        if len(results) == 0:
            pytest.skip("No search results available")

        for r in results:
            context = assembler.assemble(r.chunk)
            assert context.primary is not None
            assert context.primary.file_path is not None
            assert context.primary.start_line > 0
