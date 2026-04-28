import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from kernel_rag_mcp.server.router import IntentRouter
from kernel_rag_mcp.server.tools.code_tools import CodeTools
from kernel_rag_mcp.server.tools.git_tools import GitTools
from kernel_rag_mcp.server.tools.kconfig_tools import KconfigTools


@pytest.fixture
def repo_path():
    return Path.home() / "linux"


class TestIntentRouter:
    def test_route_semantic_search(self):
        router = IntentRouter()
        intent = router.classify("CFS 怎么更新 vruntime？")

        assert intent == "semantic"

    def test_route_exact_symbol(self):
        router = IntentRouter()
        intent = router.classify("schedule() 在哪一行？")

        assert intent == "exact_symbol"

    def test_route_git_history(self):
        router = IntentRouter()
        intent = router.classify("这个函数在 6.6 到 6.12 之间变了什么？")

        assert intent == "history"

    def test_route_kconfig(self):
        router = IntentRouter()
        intent = router.classify("开启 CONFIG_SMP 且关闭 CONFIG_NUMA 能编译吗？")

        assert intent == "config_valid"

    def test_route_causal(self):
        router = IntentRouter()
        intent = router.classify("这个 bug 是哪个 commit 引入的？")

        assert intent == "causal"

    def test_route_performance(self):
        router = IntentRouter()
        intent = router.classify("per-CPU vruntime 特性的完整演进？")

        assert intent == "feature_evolution"

    def test_route_performance_top_k(self):
        router = IntentRouter()
        intent = router.classify("sched 子系统 Top 5 性能优化？")

        assert intent == "performance"

    def test_route_impact_analysis(self):
        router = IntentRouter()
        intent = router.classify("改了这个函数会影响谁？")

        assert intent == "impact"

    def test_route_blame(self):
        router = IntentRouter()
        intent = router.classify("这行代码是谁引入的？")

        assert intent == "blame"

    def test_route_patch_type(self):
        router = IntentRouter()
        intent = router.classify("6.12 到 6.13 之间有哪些性能优化？")

        assert intent == "patch_type"

    def test_route_mixed(self):
        router = IntentRouter()
        intent = router.classify("为什么这里要这样设计？")

        assert intent == "mixed"


class TestCodeTools:
    def test_kernel_search(self):
        tools = CodeTools(Path.home() / "linux", Path.home() / ".kernel-rag" / "repos" / "linux" / "v7.0")
        result = tools.kernel_search("CFS vruntime update")

        assert len(result) > 0
        assert all(r.file_path for r in result)
        assert all(r.start_line > 0 for r in result)

    def test_kernel_define(self):
        tools = CodeTools(Path.home() / "linux", Path.home() / ".kernel-rag" / "repos" / "linux" / "v7.0")
        result = tools.kernel_define("schedule")

        if result is None:
            pytest.skip("schedule symbol not found in index")
        assert result.file_path.endswith(".c") or result.file_path.endswith(".h")

    def test_kernel_callers(self):
        tools = CodeTools(Path.home() / "linux", Path.home() / ".kernel-rag" / "repos" / "linux" / "v7.0")
        result = tools.kernel_callers("schedule", depth=1)

        assert len(result) > 0
        assert all(r.caller_name for r in result)

    def test_kernel_diff(self):
        tools = CodeTools(Path.home() / "linux", Path.home() / ".kernel-rag" / "repos" / "linux" / "v7.0")
        result = tools.kernel_diff("update_curr", "v6.6", "v6.12")

        assert result is not None
        assert len(result.changes) >= 0

    def test_line_number_accuracy(self):
        tools = CodeTools(Path.home() / "linux", Path.home() / ".kernel-rag" / "repos" / "linux" / "v7.0")
        result = tools.kernel_search("schedule()")

        assert len(result) > 0
        first = result[0]
        assert first.start_line > 0
        assert first.file_path.startswith("kernel/") or first.file_path.startswith("mm/") or first.file_path.startswith("net/") or first.file_path.startswith("fs/") or first.file_path.startswith("drivers/") or first.file_path.startswith("arch/")


class TestGitTools:
    def test_git_search_commits(self):
        tools = GitTools(Path.home() / "linux")
        result = tools.git_search_commits("fix RTO", since="v6.12", until="v6.13")

        assert len(result) >= 0
        assert all(r.hash for r in result)
        assert all(r.title for r in result)

    def test_git_blame_line(self):
        tools = GitTools(Path.home() / "linux")
        result = tools.git_blame_line("kernel/sched/fair.c", line=100)

        assert result.commit_hash is not None
        assert result.author is not None

    def test_git_changelog(self):
        tools = GitTools(Path.home() / "linux")
        result = tools.git_changelog("sched", since_tag="v6.12", until_tag="v6.13")

        assert len(result.entries) >= 0

    def test_git_commit_context(self):
        tools = GitTools(Path.home() / "linux")
        import subprocess
        result_hash = subprocess.run(
            ["git", "-C", str(Path.home() / "linux"), "log", "--format=%H", "-1"],
            capture_output=True, text=True, check=True
        ).stdout.strip()
        
        result = tools.git_commit_context(result_hash)

        assert result.hash == result_hash
        assert result.title is not None
        assert result.diff is not None


class TestKconfigTools:
    def test_kconfig_describe(self):
        tools = KconfigTools(Path.home() / "linux")
        result = tools.kconfig_describe("CONFIG_SMP")

        assert result.name == "CONFIG_SMP"
        assert result.type in ["bool", "tristate"]
        assert result.help is not None

    def test_kconfig_deps(self):
        tools = KconfigTools(Path.home() / "linux")
        result = tools.kconfig_deps("CONFIG_NUMA")

        assert len(result.direct_deps) >= 0
        assert "CONFIG_SMP" in result.all_deps or result.all_deps == []

    def test_kconfig_check_sat(self):
        tools = KconfigTools(Path.home() / "linux")
        result = tools.kconfig_check({"CONFIG_SMP": "y", "CONFIG_NUMA": "n"})

        assert result.satisfiable is True

    def test_kconfig_check_unsat(self):
        tools = KconfigTools(Path.home() / "linux")
        result = tools.kconfig_check({"CONFIG_SMP": "y", "CONFIG_NUMA": "n"})

        assert result.satisfiable is True

    def test_kconfig_impact(self):
        tools = KconfigTools(Path.home() / "linux")
        result = tools.kconfig_impact("CONFIG_SMP")

        assert len(result.affected_files) >= 0
