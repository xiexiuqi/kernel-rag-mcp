from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ...indexer.parsers.kconfig_parser import KconfigParser as RealKconfigParser


@dataclass
class KconfigDesc:
    name: str
    type: str
    help: str
    default: str = ""


@dataclass
class KconfigDeps:
    direct_deps: List[str]
    all_deps: List[str]


@dataclass
class KconfigCheckResult:
    satisfiable: bool


@dataclass
class KconfigImpact:
    affected_files: List[str]


class KconfigTools:
    SUBSYSTEMS = ["sched", "mm", "net"]

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self._parsers = {}
        self._load_all_subsystems()

    def _load_all_subsystems(self):
        for subsys in self.SUBSYSTEMS:
            parser = RealKconfigParser(self.repo_path)
            if parser.parse_subsystem(subsys):
                self._parsers[subsys] = parser

    def _find_symbol(self, config_name: str):
        for parser in self._parsers.values():
            desc = parser.describe(config_name)
            if desc:
                return parser, desc
        return None, None

    def kconfig_describe(self, config_name: str) -> Optional[KconfigDesc]:
        parser, desc = self._find_symbol(config_name)
        if desc:
            return KconfigDesc(
                name=desc.name,
                type=desc.type,
                help=desc.help[:200],
                default=desc.default,
            )
        return None

    def kconfig_deps(self, config_name: str) -> KconfigDeps:
        parser, desc = self._find_symbol(config_name)
        if parser and desc:
            direct = parser.get_dependencies(config_name)
            all_deps = parser.get_all_dependencies(config_name)
            return KconfigDeps(direct_deps=direct, all_deps=all_deps)
        return KconfigDeps(direct_deps=[], all_deps=[])

    def kconfig_check(self, config_dict: dict) -> KconfigCheckResult:
        for parser in self._parsers.values():
            result = parser.check_config(config_dict)
            if not result.satisfiable:
                return KconfigCheckResult(satisfiable=False)
        return KconfigCheckResult(satisfiable=True)

    def kconfig_impact(self, config_name: str) -> KconfigImpact:
        parser, desc = self._find_symbol(config_name)
        if parser and desc:
            impacted = parser.get_impact(config_name)
            return KconfigImpact(affected_files=impacted[:20])

        import subprocess
        try:
            result = subprocess.run(
                ["grep", "-r", "-l", "--include=*.c", "--include=*.h", config_name, str(self.repo_path)],
                capture_output=True, text=True, timeout=10
            )
            files = [f.replace(str(self.repo_path) + "/", "") for f in result.stdout.strip().split("\n") if f]
            return KconfigImpact(affected_files=files[:20])
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return KconfigImpact(affected_files=[])
