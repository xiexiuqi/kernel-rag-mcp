import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict


@dataclass
class KconfigDesc:
    name: str
    type: str
    help: str
    default: str = ""


@dataclass
class KconfigCheckResult:
    satisfiable: bool
    conflicts: List[str]


class KconfigParser:
    SUBSYSTEM_MAP = {
        "sched": "kernel/sched/Kconfig",
        "mm": "mm/Kconfig",
        "net": "net/Kconfig",
    }

    def __init__(self, repo_path: Path):
        self.repo_path = Path(repo_path)
        self._kconf = None
        self.symbols: Dict[str, dict] = {}

    def _expr_to_str(self, expr) -> str:
        if expr is None:
            return ""
        if hasattr(expr, 'str_value'):
            return expr.str_value
        if hasattr(expr, 'name'):
            return expr.name
        if isinstance(expr, tuple):
            if len(expr) == 3:
                op, left, right = expr
                op_str = self._expr_to_str(op)
                left_str = self._expr_to_str(left)
                right_str = self._expr_to_str(right)
                if op_str and left_str and right_str:
                    return f"({left_str} {op_str} {right_str})"
                return left_str or right_str or ""
            elif len(expr) == 2:
                op, operand = expr
                op_str = self._expr_to_str(op)
                operand_str = self._expr_to_str(operand)
                if op_str and operand_str:
                    return f"({op_str} {operand_str})"
                return operand_str or ""
        return str(expr)

    def parse_subsystem(self, subsys: str) -> bool:
        kconfig_file = self.SUBSYSTEM_MAP.get(subsys, f"{subsys}/Kconfig")
        path = self.repo_path / kconfig_file

        if not path.exists():
            return False

        try:
            import kconfiglib
            old_cwd = os.getcwd()
            os.chdir(self.repo_path)
            self._kconf = kconfiglib.Kconfig(str(path))
            os.chdir(old_cwd)

            self.symbols = {}
            for name, sym in self._kconf.syms.items():
                try:
                    if sym.nodes:
                        node = sym.nodes[0]
                        help_text = node.help if node.help else ""
                        defaults = []
                        for default, _ in sym.defaults:
                            if hasattr(default, 'str_value'):
                                defaults.append(default.str_value)

                        deps = []
                        if sym.direct_dep is not None:
                            dep_str = self._expr_to_str(sym.direct_dep)
                            if dep_str and dep_str != "y":
                                deps.append(dep_str)

                        self.symbols[name] = {
                            "name": name,
                            "type": kconfiglib.TYPE_TO_STR[sym.type],
                            "help": help_text,
                            "defaults": defaults,
                            "depends_on": deps,
                        }
                except Exception:
                    continue

            return True
        except Exception:
            import traceback
            traceback.print_exc()
            return False

    def describe(self, config_name: str) -> Optional[KconfigDesc]:
        if config_name.startswith("CONFIG_"):
            config_name = config_name[7:]

        sym = self.symbols.get(config_name)
        if not sym:
            return None

        return KconfigDesc(
            name=f"CONFIG_{config_name}",
            type=sym.get("type", "unknown"),
            help=sym.get("help", "")[:500],
            default=sym.get("defaults", [""])[0] if sym.get("defaults") else "",
        )

    def get_dependencies(self, config_name: str) -> List[str]:
        if config_name.startswith("CONFIG_"):
            config_name = config_name[7:]

        sym = self.symbols.get(config_name)
        if not sym:
            return []

        return sym.get("depends_on", [])

    def get_all_dependencies(self, config_name: str) -> List[str]:
        direct = self.get_dependencies(config_name)
        all_deps = set(direct)

        for dep in direct:
            if dep.startswith("CONFIG_"):
                dep = dep[7:]
            dep_sym = self.symbols.get(dep)
            if dep_sym:
                for d in dep_sym.get("depends_on", []):
                    all_deps.add(d)

        return list(all_deps)

    def check_config(self, config_dict: Dict[str, str]) -> KconfigCheckResult:
        conflicts = []
        seen = {}

        for name, value in config_dict.items():
            clean_name = name[7:] if name.startswith("CONFIG_") else name
            clean_value = value.upper()

            if clean_name in seen:
                prev = seen[clean_name]
                if (prev in ["Y", "YES", "1"] and clean_value in ["N", "NO", "0"]) or \
                   (prev in ["N", "NO", "0"] and clean_value in ["Y", "YES", "1"]):
                    conflicts.append(f"{name} cannot be both {prev} and {clean_value}")
            seen[clean_name] = clean_value

        if not self._kconf:
            return KconfigCheckResult(satisfiable=len(conflicts) == 0, conflicts=conflicts)

        return KconfigCheckResult(satisfiable=len(conflicts) == 0, conflicts=conflicts)

    def get_impact(self, config_name: str) -> List[str]:
        if config_name.startswith("CONFIG_"):
            config_name = config_name[7:]

        impacted = []
        for name, sym in self.symbols.items():
            deps = sym.get("depends_on", [])
            for dep in deps:
                if config_name in dep or dep == config_name or dep == f"CONFIG_{config_name}":
                    impacted.append(name)
                    break

        return impacted
