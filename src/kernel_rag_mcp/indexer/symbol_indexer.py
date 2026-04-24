import subprocess
from pathlib import Path
from typing import List, Dict, Any


class SymbolIndexBuilder:
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.ctags_cmd = "ctags"
    
    def generate_symbols(self, file_paths: List[Path]) -> List[Dict[str, Any]]:
        symbols = []
        
        for file_path in file_paths:
            if not file_path.exists():
                continue
                
            rel_path = str(file_path.relative_to(self.repo_path))
            
            try:
                result = subprocess.run(
                    [
                        self.ctags_cmd,
                        "-x", "--kinds-c=fms",
                        "--fields=+n",
                        str(file_path)
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode != 0:
                    continue
                
                for line in result.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    
                    parts = line.split(None, 3)
                    if len(parts) < 3:
                        continue
                    
                    name = parts[0]
                    symbol_type = parts[1]
                    line_num = int(parts[2])
                    
                    symbols.append({
                        "name": name,
                        "file_path": rel_path,
                        "line": line_num,
                        "symbol_type": symbol_type,
                    })
                    
            except (subprocess.TimeoutExpired, ValueError):
                continue
        
        return symbols
    
    def index_subsystem(self, subsys_path: Path) -> List[Dict[str, Any]]:
        c_files = list(subsys_path.rglob("*.c")) + list(subsys_path.rglob("*.h"))
        return self.generate_symbols(c_files)
