import re
from pathlib import Path
from typing import List

from .parsers.tree_sitter_c import TreeSitterCParser, IndexResult


class CodeIndexer:
    HOT_PATH_PATTERNS = [
        r"kernel/sched/.*",
        r"mm/page_alloc\.c",
        r"mm/slab\.c",
        r"mm/slub\.c",
        r"net/core/dev\.c",
        r"net/core/skbuff\.c",
        r"lib/radix-tree\.c",
        r"lib/rhashtable\.c",
        r"arch/x86/mm/.*",
        r"kernel/locking/.*",
    ]

    def __init__(self):
        self.parser = TreeSitterCParser()

    def index_file(self, file_path: Path) -> IndexResult:
        code = file_path.read_text(encoding="utf-8", errors="replace")
        file_path_str = str(file_path)

        chunks = []
        chunks.extend(self.parser.parse_functions(code, file_path_str))
        chunks.extend(self.parser.parse_structs(code, file_path_str))
        chunks.extend(self.parser.parse_macros(code, file_path_str))

        lines = code.split("\n")
        return IndexResult(
            file_path=file_path_str,
            chunks=chunks,
            total_lines=len(lines),
        )

    def index_directory(self, dir_path: Path) -> List[IndexResult]:
        results = []
        for file_path in dir_path.rglob("*.c"):
            results.append(self.index_file(file_path))
        for file_path in dir_path.rglob("*.h"):
            results.append(self.index_file(file_path))
        return results

    def is_hot_path(self, file_path: str) -> bool:
        for pattern in self.HOT_PATH_PATTERNS:
            if re.match(pattern, file_path):
                return True
        return False

    def get_subsystem(self, file_path: str) -> str:
        parts = file_path.split("/")
        if "kernel/sched" in file_path:
            return "sched"
        elif "mm/" in file_path:
            return "mm"
        elif "net/" in file_path:
            return "net"
        elif "fs/" in file_path:
            return "fs"
        elif "drivers/" in file_path:
            return "drivers"
        elif "block/" in file_path:
            return "block"
        elif len(parts) >= 1:
            return parts[0]
        return "unknown"
