import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from kernel_rag_mcp.indexer.parsers.kconfig_parser import KconfigParser


class TestKconfigParser:
    def test_parse_subsystem_kconfig(self):
        repo_path = Path.home() / "linux"
        if not repo_path.exists():
            pytest.skip("Linux repo not found")

        parser = KconfigParser(repo_path)
        result = parser.parse_subsystem("mm")

        assert result is True
        assert len(parser.symbols) > 0

    def test_describe_symbol(self):
        repo_path = Path.home() / "linux"
        if not repo_path.exists():
            pytest.skip("Linux repo not found")

        parser = KconfigParser(repo_path)
        parser.parse_subsystem("mm")

        desc = parser.describe("SWAP")
        if desc:
            assert desc.name == "CONFIG_SWAP"
            assert desc.type in ["bool", "tristate"]

    def test_describe_with_config_prefix(self):
        repo_path = Path.home() / "linux"
        if not repo_path.exists():
            pytest.skip("Linux repo not found")

        parser = KconfigParser(repo_path)
        parser.parse_subsystem("mm")

        desc = parser.describe("CONFIG_SWAP")
        if desc:
            assert desc.name == "CONFIG_SWAP"

    def test_get_dependencies(self):
        repo_path = Path.home() / "linux"
        if not repo_path.exists():
            pytest.skip("Linux repo not found")

        parser = KconfigParser(repo_path)
        parser.parse_subsystem("mm")

        deps = parser.get_dependencies("SWAP")
        assert isinstance(deps, list)

    def test_get_all_dependencies(self):
        repo_path = Path.home() / "linux"
        if not repo_path.exists():
            pytest.skip("Linux repo not found")

        parser = KconfigParser(repo_path)
        parser.parse_subsystem("mm")

        all_deps = parser.get_all_dependencies("SWAP")
        assert isinstance(all_deps, list)
        direct_deps = parser.get_dependencies("SWAP")
        for d in direct_deps:
            assert d in all_deps

    def test_check_config_basic(self):
        parser = KconfigParser(Path.home() / "linux")
        result = parser.check_config({"CONFIG_SWAP": "y"})
        assert result.satisfiable is True

    def test_check_config_conflict(self):
        parser = KconfigParser(Path.home() / "linux")
        result = parser.check_config({"CONFIG_SWAP": "y", "SWAP": "n"})
        assert result.satisfiable is False

    def test_impact_analysis(self):
        repo_path = Path.home() / "linux"
        if not repo_path.exists():
            pytest.skip("Linux repo not found")

        parser = KconfigParser(repo_path)
        impact = parser.get_impact("CONFIG_SWAP")
        assert isinstance(impact, list)

    def test_parse_multiple_subsystems(self):
        repo_path = Path.home() / "linux"
        if not repo_path.exists():
            pytest.skip("Linux repo not found")

        parser = KconfigParser(repo_path)
        parser.parse_subsystem("sched")
        sched_count = len(parser.symbols)

        parser.parse_subsystem("mm")
        mm_count = len(parser.symbols)

        assert mm_count > 0

    def test_symbol_not_found(self):
        repo_path = Path.home() / "linux"
        if not repo_path.exists():
            pytest.skip("Linux repo not found")

        parser = KconfigParser(repo_path)
        parser.parse_subsystem("mm")

        desc = parser.describe("CONFIG_NONEXISTENT_FOO_BAR")
        assert desc is None


class TestKconfigDesc:
    def test_desc_attributes(self):
        from kernel_rag_mcp.indexer.parsers.kconfig_parser import KconfigDesc

        desc = KconfigDesc(
            name="CONFIG_SMP",
            type="bool",
            help="Symmetric multi-processing support",
            default="y"
        )

        assert desc.name == "CONFIG_SMP"
        assert desc.type == "bool"
        assert "multi-processing" in desc.help
        assert desc.default == "y"


class TestKconfigCheckResult:
    def test_result_attributes(self):
        from kernel_rag_mcp.indexer.parsers.kconfig_parser import KconfigCheckResult

        result = KconfigCheckResult(satisfiable=True, conflicts=[])
        assert result.satisfiable is True
        assert result.conflicts == []

    def test_result_with_conflicts(self):
        from kernel_rag_mcp.indexer.parsers.kconfig_parser import KconfigCheckResult

        result = KconfigCheckResult(
            satisfiable=False,
            conflicts=["CONFIG_SWAP cannot be both y and n"]
        )
        assert result.satisfiable is False
        assert len(result.conflicts) == 1
