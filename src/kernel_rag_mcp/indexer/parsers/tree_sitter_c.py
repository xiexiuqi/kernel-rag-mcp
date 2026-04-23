import re
from dataclasses import dataclass, field
from typing import List, Optional

from tree_sitter import Language, Parser
import tree_sitter_c as tsc


@dataclass
class CodeChunk:
    name: str
    file_path: str
    start_line: int
    end_line: int
    code: str = ""
    chunk_type: str = "function"
    annotations: List[str] = field(default_factory=list)
    kconfig_condition: Optional[str] = None
    subsys: Optional[str] = None

    def __post_init__(self):
        if not self.subsys and self.file_path:
            self.subsys = self._extract_subsystem()

    def _extract_subsystem(self) -> Optional[str]:
        parts = self.file_path.split("/")
        if "kernel/sched" in self.file_path:
            return "sched"
        elif "mm/" in self.file_path:
            return "mm"
        elif "net/" in self.file_path:
            return "net"
        elif len(parts) >= 2:
            return parts[0] if parts[0] != "include" else parts[1] if len(parts) > 1 else None
        return None

    def set_subsystem(self, subsys: str):
        self.subsys = subsys


@dataclass
class IndexResult:
    file_path: str
    chunks: List[CodeChunk]
    total_lines: int = 0


@dataclass
class KconfigCondition:
    condition: str
    start_line: int
    end_line: int
    code: str


class TreeSitterCParser:
    def __init__(self):
        self.parser = Parser()
        self.parser.language = Language(tsc.language())

    def _find_function_name(self, node) -> Optional[str]:
        for child in node.children:
            if child.type == "function_declarator":
                for sub in child.children:
                    if sub.type == "identifier":
                        return sub.text.decode()
            elif child.type == "pointer_declarator":
                for sub in child.children:
                    if sub.type == "function_declarator":
                        for ssub in sub.children:
                            if ssub.type == "identifier":
                                return ssub.text.decode()
        return None

    def parse_functions(self, code: str, file_path: str = "") -> List[CodeChunk]:
        tree = self.parser.parse(code.encode())
        root = tree.root_node
        chunks = []

        for node in root.children:
            if node.type == "function_definition":
                func_name = self._find_function_name(node)
                if not func_name:
                    continue

                start_line = node.start_point.row + 1
                end_line = node.end_point.row + 1
                func_code = "\n".join(code.split("\n")[start_line - 1:end_line])

                annotations = []
                if func_name in ["container_of"]:
                    annotations.append("从成员指针获取父结构体")
                elif func_name in ["list_for_each_entry"]:
                    annotations.append("链表遍历")
                elif func_name in ["rcu_read_lock", "rcu_read_unlock"]:
                    annotations.append("RCU 读临界区")

                chunks.append(
                    CodeChunk(
                        name=func_name,
                        file_path=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        code=func_code,
                        chunk_type="function",
                        annotations=annotations,
                    )
                )

        return chunks

    def parse_structs(self, code: str, file_path: str = "") -> List[CodeChunk]:
        tree = self.parser.parse(code.encode())
        root = tree.root_node
        chunks = []

        for node in root.children:
            if node.type == "struct_specifier":
                name_node = None
                body_node = None
                for child in node.children:
                    if child.type == "type_identifier":
                        name_node = child
                    elif child.type == "field_declaration_list":
                        body_node = child
                if name_node and body_node:
                    struct_name = name_node.text.decode()
                    start_line = node.start_point.row + 1
                    end_line = node.end_point.row + 1
                    struct_code = "\n".join(code.split("\n")[start_line - 1:end_line])
                    chunks.append(CodeChunk(
                        name=struct_name,
                        file_path=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        code=struct_code,
                        chunk_type="struct",
                    ))

        return chunks

    def parse_macros(self, code: str, file_path: str = "") -> List[CodeChunk]:
        tree = self.parser.parse(code.encode())
        root = tree.root_node
        chunks = []

        for node in root.children:
            if node.type == "preproc_function_def":
                macro_name = None
                for child in node.children:
                    if child.type == "identifier":
                        macro_name = child.text.decode()
                        break
                if macro_name:
                    start_line = node.start_point.row + 1
                    end_line = node.end_point.row + 1
                    macro_code = "\n".join(code.split("\n")[start_line - 1:end_line])

                    annotations = []
                    if macro_name == "container_of":
                        annotations.append("从成员指针获取父结构体")
                    elif macro_name == "list_for_each_entry":
                        annotations.append("链表遍历")
                    elif macro_name in ["rcu_read_lock", "rcu_read_unlock"]:
                        annotations.append("RCU 读临界区")

                    chunks.append(CodeChunk(
                        name=macro_name,
                        file_path=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        code=macro_code,
                        chunk_type="macro",
                        annotations=annotations,
                    ))

        return chunks

    def extract_kconfig_conditions(self, code: str) -> List[KconfigCondition]:
        conditions = []
        lines = code.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i]
            match = re.match(r"^#ifdef\s+(\w+)", line.strip())
            if match:
                condition = match.group(1)
                start_line = i + 1

                j = i + 1
                depth = 1
                while j < len(lines) and depth > 0:
                    stripped = lines[j].strip()
                    if stripped.startswith("#ifdef") or stripped.startswith("#if"):
                        depth += 1
                    elif stripped.startswith("#endif"):
                        depth -= 1
                    j += 1

                end_line = j
                cond_code = "\n".join(lines[i:j])

                conditions.append(KconfigCondition(
                    condition=condition,
                    start_line=start_line,
                    end_line=end_line,
                    code=cond_code,
                ))
                i = j
            else:
                i += 1

        return conditions
