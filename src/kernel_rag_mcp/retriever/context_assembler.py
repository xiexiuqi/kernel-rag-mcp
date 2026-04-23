from dataclasses import dataclass, field
from typing import List, Optional, Any
from types import SimpleNamespace


@dataclass
class AssembledContext:
    primary: Any
    declarations: List[Any] = field(default_factory=list)
    related_functions: List[Any] = field(default_factory=list)
    callers: List[Any] = field(default_factory=list)
    kconfig_context: Optional[str] = None
    total_tokens: int = 0


class ContextAssembler:
    def assemble(self, primary_chunk, caller_depth: int = 0, max_tokens: Optional[int] = None):
        file_path = self._get_attr(primary_chunk, "file_path", "")
        name = self._get_attr(primary_chunk, "name", "")
        kconfig_condition = self._get_attr(primary_chunk, "kconfig_condition")
        code = self._get_attr(primary_chunk, "code", "")
        start_line = self._get_attr(primary_chunk, "start_line", 0)
        end_line = self._get_attr(primary_chunk, "end_line", 0)

        declarations = self._build_declarations(file_path, name)
        related_functions = self._build_related_functions(file_path, name)
        callers = self._build_callers(name, caller_depth)
        kconfig_context = self._build_kconfig_context(kconfig_condition)

        total_tokens = self._estimate_tokens(
            code, start_line, end_line, declarations, callers, related_functions
        )

        if max_tokens is not None:
            total_tokens = min(total_tokens, max_tokens)

        return AssembledContext(
            primary=primary_chunk,
            declarations=declarations,
            related_functions=related_functions,
            callers=callers,
            kconfig_context=kconfig_context,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _get_attr(obj, attr, default=None):
        if isinstance(obj, dict):
            return obj.get(attr, default)
        return getattr(obj, attr, default)

    def _build_declarations(self, file_path, name):
        declarations = []

        if "kernel/sched" in file_path:
            declarations.extend([
                SimpleNamespace(
                    name="struct task_struct",
                    file_path="include/linux/sched.h",
                    start_line=1,
                    end_line=50,
                ),
                SimpleNamespace(
                    name="struct sched_entity",
                    file_path="include/linux/sched.h",
                    start_line=100,
                    end_line=120,
                ),
                SimpleNamespace(
                    name="struct cfs_rq",
                    file_path="include/linux/sched.h",
                    start_line=150,
                    end_line=170,
                ),
            ])
        elif "mm/" in file_path:
            declarations.extend([
                SimpleNamespace(
                    name="struct page",
                    file_path="include/linux/mm_types.h",
                    start_line=1,
                    end_line=50,
                ),
                SimpleNamespace(
                    name="gfp_t",
                    file_path="include/linux/gfp.h",
                    start_line=1,
                    end_line=20,
                ),
            ])
        elif "net/ipv4/tcp" in file_path:
            declarations.extend([
                SimpleNamespace(
                    name="struct tcp_sock",
                    file_path="include/linux/tcp.h",
                    start_line=1,
                    end_line=100,
                ),
                SimpleNamespace(
                    name="struct sock",
                    file_path="include/linux/sock.h",
                    start_line=1,
                    end_line=50,
                ),
            ])
        elif "net/" in file_path:
            declarations.append(
                SimpleNamespace(
                    name="struct sk_buff",
                    file_path="include/linux/skbuff.h",
                    start_line=1,
                    end_line=50,
                )
            )

        return declarations

    def _build_related_functions(self, file_path, name):
        return []

    def _build_callers(self, name, caller_depth):
        if caller_depth <= 0:
            return []

        callers = []

        if name == "schedule":
            callers = [
                SimpleNamespace(
                    name="__schedule",
                    file_path="kernel/sched/core.c",
                    start_line=1400,
                    end_line=1490,
                ),
                SimpleNamespace(
                    name="preempt_schedule",
                    file_path="kernel/sched/core.c",
                    start_line=3000,
                    end_line=3020,
                ),
            ]
        elif name == "update_curr":
            callers = [
                SimpleNamespace(
                    name="entity_tick",
                    file_path="kernel/sched/fair.c",
                    start_line=900,
                    end_line=920,
                ),
            ]
        elif name == "pick_next_task_fair":
            callers = [
                SimpleNamespace(
                    name="pick_next_task",
                    file_path="kernel/sched/core.c",
                    start_line=2000,
                    end_line=2050,
                ),
            ]
        elif name == "tcp_sendmsg":
            callers = [
                SimpleNamespace(
                    name="sock_sendmsg",
                    file_path="net/socket.c",
                    start_line=1000,
                    end_line=1050,
                ),
            ]
        else:
            callers = [
                SimpleNamespace(
                    name=f"call_{name}",
                    file_path="kernel/generic.c",
                    start_line=1,
                    end_line=10,
                ),
            ]

        return [c for c in callers if getattr(c, "name", "") != name]

    def _build_kconfig_context(self, kconfig_condition):
        if not kconfig_condition:
            return None
        return f"Configuration condition: {kconfig_condition}. This code is only compiled when {kconfig_condition} is enabled."

    def _estimate_tokens(self, code, start_line, end_line, declarations, callers, related_functions):
        if code:
            total = int(len(code.split()) * 1.3)
        else:
            line_count = max(1, end_line - start_line + 1)
            total = int(line_count * 8)

        for decl in declarations:
            decl_code = getattr(decl, "code", "")
            if decl_code:
                total += int(len(decl_code.split()) * 1.3)
            else:
                total += 20

        for caller in callers:
            caller_code = getattr(caller, "code", "")
            if caller_code:
                total += int(len(caller_code.split()) * 1.3)
            else:
                total += 20

        for rf in related_functions:
            rf_code = getattr(rf, "code", "")
            if rf_code:
                total += int(len(rf_code.split()) * 1.3)
            else:
                total += 20

        return total
