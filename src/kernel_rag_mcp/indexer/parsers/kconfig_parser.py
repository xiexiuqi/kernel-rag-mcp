import re
from pathlib import Path
from typing import List, Optional, Dict


class KconfigSymbol:
    def __init__(self, name: str, type_: str = "unknown", help_text: str = "", 
                 default: str = "", depends_on: List[str] = None, 
                 select: List[str] = None, imply: List[str] = None):
        self.name = name
        self.type = type_
        self.help_text = help_text
        self.default = default
        self.depends_on = depends_on or []
        self.select = select or []
        self.imply = imply or []


class KconfigParser:
    def __init__(self, kconfig_path: Path):
        self.kconfig_path = kconfig_path
        self.symbols: Dict[str, KconfigSymbol] = {}
    
    def parse(self):
        if not self.kconfig_path.exists():
            return
        
        self._parse_file(self.kconfig_path)
    
    def _parse_file(self, path: Path):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        for match in re.finditer(r'source\s+"([^"]+)"', content):
            raw = match.group(1)
            if "$(SRCARCH)" in raw:
                for arch in ["x86", "arm64", "arm", "riscv"]:
                    sub_path = path.parent / raw.replace("$(SRCARCH)", arch)
                    if sub_path.exists():
                        self._parse_file(sub_path)
                    else:
                        alt = self.kconfig_path.parent / raw.replace("$(SRCARCH)", arch)
                        if alt.exists():
                            self._parse_file(alt)
            else:
                sub_path = path.parent / raw
                if sub_path.exists():
                    self._parse_file(sub_path)
                else:
                    alt = self.kconfig_path.parent / raw
                    if alt.exists():
                        self._parse_file(alt)

        config_pattern = r'config\s+(\w+)\s*\n((?:\s+(?:bool|tristate|string|hex|int|prompt|default|depends on|select|imply|help|comment|if|endif|menu|endmenu)[^\n]*\n)+)'

        for match in re.finditer(config_pattern, content):
            name = match.group(1)
            body = match.group(2)

            symbol = KconfigSymbol(name=name)

            type_match = re.search(r'\s+(bool|tristate|string|hex|int)\s+(?:"([^"]+)"|(\w+))', body)
            if type_match:
                symbol.type = type_match.group(1)

            default_match = re.search(r'\s+default\s+(\S+)', body)
            if default_match:
                symbol.default = default_match.group(1)

            for dep_match in re.finditer(r'\s+depends on\s+(.+)', body):
                symbol.depends_on.append(dep_match.group(1).strip())

            for sel_match in re.finditer(r'\s+select\s+(\w+)', body):
                symbol.select.append(sel_match.group(1))

            for imp_match in re.finditer(r'\s+imply\s+(\w+)', body):
                symbol.imply.append(imp_match.group(1))

            help_match = re.search(r'\s+help\s*\n((?:\s+[^\n]*\n)+)', body)
            if help_match:
                symbol.help_text = help_match.group(1).strip()

            self.symbols[name] = symbol
    
    def get_symbol(self, name: str) -> Optional[KconfigSymbol]:
        return self.symbols.get(name)
    
    def get_all_deps(self, name: str) -> List[str]:
        symbol = self.symbols.get(name)
        if not symbol:
            return []
        
        all_deps = set(symbol.depends_on)
        for dep in symbol.depends_on:
            dep_symbol = self.symbols.get(dep)
            if dep_symbol:
                all_deps.update(dep_symbol.depends_on)
        
        return list(all_deps)
    
    def check_config(self, config_dict: Dict[str, str]) -> Dict:
        values = {}
        for name, value in config_dict.items():
            values[name] = value.upper()

        seen = {}
        for name, value in values.items():
            if name in seen:
                prev = seen[name]
                if (prev in ["Y", "YES", "1"] and value in ["N", "NO", "0"]) or \
                   (prev in ["N", "NO", "0"] and value in ["Y", "YES", "1"]):
                    return {
                        "satisfiable": False,
                        "error": "Direct contradiction",
                    }
            seen[name] = value

        try:
            from z3 import Solver, Bool, Implies, sat

            solver = Solver()
            bool_vars = {}

            for name in config_dict:
                bool_vars[name] = Bool(name)

            for name, symbol in self.symbols.items():
                if name in bool_vars:
                    for dep in symbol.depends_on:
                        if dep in bool_vars:
                            solver.add(Implies(bool_vars[name], bool_vars[dep]))

            for name, value in config_dict.items():
                if name in bool_vars:
                    if value.upper() in ["Y", "YES", "1"]:
                        solver.add(bool_vars[name] == True)
                    elif value.upper() in ["N", "NO", "0"]:
                        solver.add(bool_vars[name] == False)

            result = solver.check()

            return {
                "satisfiable": result == sat,
                "constraints": len(solver.assertions()),
            }
        except ImportError:
            return {
                "satisfiable": True,
                "error": "Z3 not available",
            }
