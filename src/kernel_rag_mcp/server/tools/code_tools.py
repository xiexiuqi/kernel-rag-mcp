from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ...retriever.hybrid_search import HybridSearcher
from ...indexer.graph_builder.callgraph import CallGraphBuilder


@dataclass
class CodeChunk:
    file_path: str
    start_line: int
    end_line: int = 0
    content: str = ""


@dataclass
class SymbolDef:
    name: str
    file_path: str
    line: int = 0


@dataclass
class CallerInfo:
    caller_name: str
    file_path: str = ""
    line: int = 0


@dataclass
class DiffResult:
    changes: List[dict]


class CodeTools:
    def __init__(self, repo_path: Path, index_path: Path):
        self.repo_path = repo_path
        self.index_path = index_path
        self.searcher = HybridSearcher(index_path, repo_path)
        self.callgraph = CallGraphBuilder(repo_path)
    
    SUBSYS_ALIASES = {
        "network": "net",
        "networking": "net",
        "scheduling": "kernel/sched",
        "scheduler": "kernel/sched",
        "memory": "mm",
        "file system": "fs",
        "filesystem": "fs",
        "fs": "fs",
        "usb": "drivers/usb",
        "x86": "arch/x86",
        "locking": "kernel/locking",
    }

    def _resolve_subsys(self, subsys: str) -> str:
        if not subsys:
            return subsys
        subsys = subsys.lower().strip()
        return self.SUBSYS_ALIASES.get(subsys, subsys)

    def kernel_search(self, query: str, subsys: str = None, top_k: int = 10) -> List[CodeChunk]:
        subsys = self._resolve_subsys(subsys)
        results = self.searcher.search(query, subsys=subsys, top_k=top_k)
        
        # Fallback: if subsys filter returns empty, search globally
        if not results and subsys:
            results = self.searcher.search(query, subsys=None, top_k=top_k)
        
        chunks = []
        for r in results:
            chunks.append(CodeChunk(
                file_path=r.chunk.file_path,
                start_line=r.chunk.start_line,
                end_line=r.chunk.end_line,
                content=r.code[:500] if r.code else "",
            ))
        return chunks
    
    def kernel_define(self, symbol: str) -> Optional[SymbolDef]:
        results = self.searcher.search(symbol, top_k=1)
        if results:
            r = results[0]
            return SymbolDef(
                name=r.chunk.name,
                file_path=r.chunk.file_path,
                line=r.chunk.start_line,
            )
        return None
    
    def kernel_callers(self, symbol: str, depth: int = 1) -> List[CallerInfo]:
        # Build cscope db if needed
        if not (self.repo_path / "cscope.out").exists():
            self.callgraph.build()
        
        callers = self.callgraph.get_callers(symbol)
        return [CallerInfo(caller_name=c) for c in callers[:20]]
    
    def kernel_diff(self, symbol: str, v1: str, v2: str) -> DiffResult:
        import subprocess
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo_path), "diff", f"{v1}..{v2}", "--", "*.c"],
                capture_output=True, text=True, check=True
            )
            return DiffResult(changes=[{"diff": result.stdout[:1000]}])
        except subprocess.CalledProcessError:
            return DiffResult(changes=[])
