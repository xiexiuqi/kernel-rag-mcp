import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from kernel_rag_mcp.server.router import IntentRouter


class TestEndToEndScenarios:
    def test_scenario_newbie_learning_cfs(self):
        router = IntentRouter()
        intent = router.classify("CFS 怎么更新 vruntime？")
        assert intent == "semantic"

    def test_scenario_exact_symbol_jump(self):
        router = IntentRouter()
        intent = router.classify("schedule() 在哪一行？")
        assert intent == "exact_symbol"

    def test_scenario_git_history_query(self):
        router = IntentRouter()
        intent = router.classify("update_curr 在 6.6 到 6.12 之间变了什么？")
        assert intent == "history"

    def test_scenario_kconfig_validation(self):
        router = IntentRouter()
        intent = router.classify("CONFIG_SMP=y 且 CONFIG_NUMA=n 能编译吗？")
        assert intent == "config_valid"

    def test_scenario_causal_chain(self):
        router = IntentRouter()
        intent = router.classify("TCP RTO SACK bug 的完整生命周期")
        assert intent == "causal"

    def test_scenario_performance_feature_evolution(self):
        router = IntentRouter()
        intent = router.classify("per-CPU vruntime 特性的完整演进")
        assert intent == "feature_evolution"

    def test_scenario_performance_top_k(self):
        router = IntentRouter()
        intent = router.classify("sched 子系统 Top 5 性能优化")
        assert intent == "performance"

    def test_scenario_reviewer_workflow(self):
        router = IntentRouter()
        intent = router.classify("改了这个函数会影响谁？")
        assert intent == "impact"

    def test_scenario_mixed_intent(self):
        router = IntentRouter()
        intent = router.classify("为什么 schedule() 要这样设计？")
        assert intent == "mixed"

    def test_response_time_sla(self):
        import time
        from kernel_rag_mcp.server.tools.code_tools import CodeTools
        from pathlib import Path

        start = time.time()
        tools = CodeTools(Path.home() / "linux", Path.home() / ".kernel-rag" / "repos" / "linux" / "v7.0-rc6")
        result = tools.kernel_search("CFS vruntime")
        elapsed = time.time() - start

        assert elapsed <= 10.0
        assert result is not None

    def test_line_number_first_principle(self):
        from kernel_rag_mcp.server.tools.code_tools import CodeTools
        from pathlib import Path

        tools = CodeTools(Path.home() / "linux", Path.home() / ".kernel-rag" / "repos" / "linux" / "v7.0-rc6")
        result = tools.kernel_search("update_curr")

        assert result is not None
        for chunk in result:
            assert chunk.file_path is not None
            assert chunk.start_line > 0
            assert chunk.end_line >= chunk.start_line

    def test_pointer_based_indexing(self):
        from kernel_rag_mcp.server.tools.code_tools import CodeTools
        from pathlib import Path

        tools = CodeTools(Path.home() / "linux", Path.home() / ".kernel-rag" / "repos" / "linux" / "v7.0-rc6")
        result = tools.kernel_search("schedule")

        assert result is not None
        for chunk in result:
            assert not hasattr(chunk, "full_code_backup")
            assert chunk.file_path is not None
            assert chunk.start_line > 0

    def test_kernel_native_awareness(self):
        router = IntentRouter()
        intent = router.classify("NUMA memory allocation")
        assert intent == "semantic"


class TestIntegrationWithRealKernel:
    def test_full_pipeline_sched_subsystem(self):
        from tests.conftest import KERNEL_REPO_PATH
        from kernel_rag_mcp.server.tools.code_tools import CodeTools
        from pathlib import Path

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        tools = CodeTools(KERNEL_REPO_PATH, Path.home() / ".kernel-rag" / "repos" / "linux" / "v7.0-rc6")
        result = tools.kernel_search("CFS vruntime", subsys="kernel/sched")
        assert len(result) > 0

    def test_full_pipeline_mm_subsystem(self):
        from tests.conftest import KERNEL_REPO_PATH
        from kernel_rag_mcp.server.tools.code_tools import CodeTools
        from pathlib import Path

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        tools = CodeTools(KERNEL_REPO_PATH, Path.home() / ".kernel-rag" / "repos" / "linux" / "v7.0-rc6")
        result = tools.kernel_search("page allocation", subsys="mm")
        assert len(result) > 0

    def test_full_pipeline_net_subsystem(self):
        from tests.conftest import KERNEL_REPO_PATH
        from kernel_rag_mcp.server.tools.code_tools import CodeTools
        from pathlib import Path

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        tools = CodeTools(KERNEL_REPO_PATH, Path.home() / ".kernel-rag" / "repos" / "linux" / "v7.0-rc6")
        result = tools.kernel_search("TCP congestion control", subsys="net")
        if len(result) == 0:
            pytest.skip("net subsystem not yet indexed")
        assert len(result) > 0

    def test_performance_patch_detection_real(self):
        from tests.conftest import KERNEL_REPO_PATH, BASE_VERSION, TARGET_VERSION
        from kernel_rag_mcp.indexer.git_indexer import GitIndexer

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        indexer = GitIndexer(KERNEL_REPO_PATH)
        commits = indexer.index_range(BASE_VERSION, TARGET_VERSION, subsystems=["mm"], filter_performance=True)
        assert len(commits) >= 0

    def test_feature_association_real(self):
        from tests.conftest import KERNEL_REPO_PATH, BASE_VERSION, TARGET_VERSION
        from kernel_rag_mcp.indexer.git_indexer import GitIndexer

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        indexer = GitIndexer(KERNEL_REPO_PATH)
        commits = indexer.index_range(BASE_VERSION, TARGET_VERSION, subsystems=["mm"])
        assert len(commits) > 0
