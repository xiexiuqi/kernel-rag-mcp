import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from kernel_rag_mcp.server.mcp_server import MCPServer
from kernel_rag_mcp.server.router import IntentRouter


class TestEndToEndScenarios:
    def test_scenario_newbie_learning_cfs(self):
        server = MCPServer()
        result = server.kernel_query(
            intent="semantic",
            query="CFS 怎么更新 vruntime？",
            context={}
        )

        assert result is not None
        assert len(result.code_chunks) > 0
        assert any("update_curr" in c.name for c in result.code_chunks)
        assert all(c.file_path for c in result.code_chunks)
        assert all(c.start_line > 0 for c in result.code_chunks)

        first_chunk = result.code_chunks[0]
        assert "kernel/sched/fair.c" in first_chunk.file_path

    def test_scenario_exact_symbol_jump(self):
        server = MCPServer()
        result = server.kernel_query(
            intent="exact_symbol",
            query="schedule()",
            context={}
        )

        assert result is not None
        assert result.file_path == "kernel/sched/core.c"
        assert result.line > 0
        assert result.symbol == "schedule"

    def test_scenario_git_history_query(self):
        server = MCPServer()
        result = server.kernel_query(
            intent="history",
            query="update_curr 在 6.6 到 6.12 之间变了什么？",
            context={"symbol": "update_curr", "v1": "v6.6", "v2": "v6.12"}
        )

        assert result is not None
        assert len(result.commits) >= 0
        assert all(c.hash for c in result.commits)
        assert all(c.title for c in result.commits)

    def test_scenario_kconfig_validation(self):
        server = MCPServer()
        result = server.kernel_query(
            intent="config_valid",
            query="CONFIG_SMP=y 且 CONFIG_NUMA=n 能编译吗？",
            context={"config_combo": {"CONFIG_SMP": "y", "CONFIG_NUMA": "n"}}
        )

        assert result is not None
        assert result.satisfiable is True
        assert result.explanation is not None

    def test_scenario_causal_chain(self):
        server = MCPServer()
        result = server.kernel_query(
            intent="causal",
            query="TCP RTO SACK bug 的完整生命周期",
            context={"commit_hash": "e33f3b9"}
        )

        assert result is not None
        assert len(result.chain) >= 2
        assert result.chain[0].type == "introduce"
        assert result.chain[-1].type == "fix"

    def test_scenario_performance_feature_evolution(self):
        server = MCPServer()
        result = server.kernel_query(
            intent="feature_evolution",
            query="per-CPU vruntime 特性的完整演进",
            context={"feature_name": "per-CPU vruntime"}
        )

        assert result is not None
        assert result.feature_name == "per-CPU vruntime"
        assert len(result.commits) >= 3
        assert result.total_performance_gain is not None

    def test_scenario_performance_top_k(self):
        server = MCPServer()
        result = server.kernel_query(
            intent="performance",
            query="sched 子系统 Top 5 性能优化",
            context={"subsys": "sched", "k": 5}
        )

        assert result is not None
        assert len(result.patches) == 5
        assert all(p.performance_data for p in result.patches)
        assert result.patches[0].performance_data.improvement_percent >= \
               result.patches[1].performance_data.improvement_percent

    def test_scenario_reviewer_workflow(self):
        server = MCPServer()

        diff_result = server.git_diff_summary("patch.diff")
        assert diff_result.modified_functions is not None

        callers_result = server.kernel_callers(diff_result.modified_functions[0], depth=2)
        assert len(callers_result) > 0

        kconfig_result = server.kconfig_impact(diff_result.changed_configs[0])
        assert len(kconfig_result.affected_files) > 0

        causal_result = server.git_causal_chain(diff_result.commit_hash)
        assert causal_result is not None

    def test_scenario_mixed_intent(self):
        server = MCPServer()
        result = server.kernel_query(
            intent="mixed",
            query="为什么 schedule() 要这样设计？",
            context={}
        )

        assert result is not None
        assert len(result.code_chunks) > 0
        assert len(result.git_commits) > 0
        assert any("schedule" in c.name for c in result.code_chunks)

    def test_response_time_sla(self):
        import time
        server = MCPServer()

        start = time.time()
        result = server.kernel_query(
            intent="semantic",
            query="CFS vruntime",
            context={}
        )
        elapsed = time.time() - start

        assert elapsed <= 2.0
        assert result is not None

    def test_line_number_first_principle(self):
        server = MCPServer()
        result = server.kernel_query(
            intent="semantic",
            query="update_curr",
            context={}
        )

        assert result is not None
        for chunk in result.code_chunks:
            assert chunk.file_path is not None
            assert chunk.start_line > 0
            assert chunk.end_line >= chunk.start_line
            assert chunk.line_validated is True

    def test_pointer_based_indexing(self):
        server = MCPServer()
        result = server.kernel_query(
            intent="semantic",
            query="schedule",
            context={}
        )

        assert result is not None
        for chunk in result.code_chunks:
            assert not hasattr(chunk, "full_code_backup")
            assert chunk.file_path is not None
            assert chunk.start_line > 0

    def test_kernel_native_awareness(self):
        server = MCPServer()
        result = server.kernel_query(
            intent="semantic",
            query="NUMA memory allocation",
            context={"kconfig": {"CONFIG_NUMA": "y"}}
        )

        assert result is not None
        for chunk in result.code_chunks:
            if chunk.kconfig_condition:
                assert "CONFIG_NUMA" in chunk.kconfig_condition or chunk.kconfig_condition is None


class TestIntegrationWithRealKernel:
    def test_full_pipeline_sched_subsystem(self):
        from tests.conftest import KERNEL_REPO_PATH

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        server = MCPServer()

        index_result = server.index_subsystem("sched")
        assert index_result.success is True
        assert index_result.chunks_indexed > 0

        search_result = server.kernel_query(
            intent="semantic",
            query="CFS vruntime",
            context={"subsys": "sched"}
        )
        assert len(search_result.code_chunks) > 0

    def test_full_pipeline_mm_subsystem(self):
        from tests.conftest import KERNEL_REPO_PATH

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        server = MCPServer()

        index_result = server.index_subsystem("mm")
        assert index_result.success is True

        search_result = server.kernel_query(
            intent="semantic",
            query="page allocation",
            context={"subsys": "mm"}
        )
        assert len(search_result.code_chunks) > 0

    def test_full_pipeline_net_subsystem(self):
        from tests.conftest import KERNEL_REPO_PATH

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        server = MCPServer()

        index_result = server.index_subsystem("net")
        assert index_result.success is True

        search_result = server.kernel_query(
            intent="semantic",
            query="TCP congestion control",
            context={"subsys": "net"}
        )
        assert len(search_result.code_chunks) > 0

    def test_performance_patch_detection_real(self):
        from tests.conftest import KERNEL_REPO_PATH, BASE_VERSION, TARGET_VERSION

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        server = MCPServer()
        result = server.index_performance_patches(
            KERNEL_REPO_PATH, BASE_VERSION, TARGET_VERSION, subsystems=["mm"]
        )

        assert result.success is True
        assert len(result.performance_patches) > 0

        for patch in result.performance_patches:
            assert patch.classification_score >= 0.5
            assert patch.performance_data is not None

    def test_feature_association_real(self):
        from tests.conftest import KERNEL_REPO_PATH, BASE_VERSION, TARGET_VERSION

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        server = MCPServer()
        result = server.index_features(
            KERNEL_REPO_PATH, BASE_VERSION, TARGET_VERSION, subsystems=["mm"]
        )

        assert result.success is True
        assert len(result.features) >= 0

        for feature in result.features:
            assert feature.name is not None
            assert len(feature.commits) > 0
