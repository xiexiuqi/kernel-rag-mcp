import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Set


class CallGraphBuilder:
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.cscope_db = repo_path / "cscope.out"
        self._calls: Dict[str, Set[str]] = {}
        self._callers: Dict[str, Set[str]] = {}
    
    def build(self, source_dirs: List[str] = None) -> bool:
        if not source_dirs:
            source_dirs = ["kernel/sched", "mm", "net"]
        
        # Generate file list
        files = []
        for dir_name in source_dirs:
            dir_path = self.repo_path / dir_name
            if dir_path.exists():
                for ext in ["*.c", "*.h"]:
                    files.extend(dir_path.rglob(ext))
        
        if not files:
            return False
        
        # Write cscope.files
        files_list = self.repo_path / "cscope.files"
        with open(files_list, "w") as f:
            for file_path in files:
                f.write(str(file_path) + "\n")
        
        # Build cscope database
        try:
            subprocess.run(
                ["cscope", "-b", "-q", "-k", "-i", str(files_list)],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False
    
    def get_callers(self, symbol: str) -> List[str]:
        if not self.cscope_db.exists():
            return []

        try:
            result = subprocess.run(
                ["cscope", "-d", "-L3", symbol],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )

            callers = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    callers.append(parts[0])

            return list(set(callers))
        except Exception:
            return []
    
    def get_callees(self, symbol: str) -> List[str]:
        if not self.cscope_db.exists():
            return []

        try:
            result = subprocess.run(
                ["cscope", "-d", "-L2", symbol],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )

            callees = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    callees.append(parts[0])

            return list(set(callees))
        except Exception:
            return []
    
    def get_call_chain(self, symbol: str, depth: int = 2, direction: str = "up") -> List[List[str]]:
        chains = []
        
        def traverse(current: str, current_chain: List[str], remaining_depth: int):
            if remaining_depth == 0:
                chains.append(current_chain[:])
                return
            
            if direction == "up":
                next_symbols = self.get_callers(current)
            else:
                next_symbols = self.get_callees(current)
            
            if not next_symbols:
                chains.append(current_chain[:])
                return
            
            for next_sym in next_symbols:
                if next_sym not in current_chain:  # Avoid cycles
                    current_chain.append(next_sym)
                    traverse(next_sym, current_chain, remaining_depth - 1)
                    current_chain.pop()
        
        traverse(symbol, [symbol], depth)
        return chains
