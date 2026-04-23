from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ...indexer.parsers.kconfig_parser import KconfigParser


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
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.parser = None
        self._load_kconfig()
    
    def _load_kconfig(self):
        kconfig_path = self.repo_path / "Kconfig"
        if kconfig_path.exists():
            self.parser = KconfigParser(kconfig_path)
            self.parser.parse()
    
    def kconfig_describe(self, config_name: str) -> Optional[KconfigDesc]:
        if not self.parser:
            return None
        
        symbol = self.parser.get_symbol(config_name)
        if not symbol and config_name.startswith("CONFIG_"):
            symbol = self.parser.get_symbol(config_name[7:])
        if symbol:
            return KconfigDesc(
                name=config_name,
                type=symbol.type,
                help=symbol.help_text[:200] if symbol.help_text else "",
                default=symbol.default,
            )
        return None
    
    def kconfig_deps(self, config_name: str) -> KconfigDeps:
        if not self.parser:
            return KconfigDeps(direct_deps=[], all_deps=[])
        
        symbol = self.parser.get_symbol(config_name)
        if not symbol and config_name.startswith("CONFIG_"):
            symbol = self.parser.get_symbol(config_name[7:])
        if symbol:
            all_deps = self.parser.get_all_deps(config_name)
            return KconfigDeps(direct_deps=symbol.depends_on, all_deps=all_deps)
        
        return KconfigDeps(direct_deps=[], all_deps=[])
    
    def kconfig_check(self, config_dict: dict) -> KconfigCheckResult:
        if not self.parser:
            return KconfigCheckResult(satisfiable=True)
        
        result = self.parser.check_config(config_dict)
        return KconfigCheckResult(satisfiable=result.get("satisfiable", True))
    
    def kconfig_impact(self, config_name: str) -> KconfigImpact:
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
