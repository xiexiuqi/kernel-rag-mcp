from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .router import IntentRouter
from .tools.code_tools import CodeTools
from .tools.git_tools import GitTools
from .tools.kconfig_tools import KconfigTools
from .tools.type_tools import TypeTools
from .tools.causal_tools import CausalTools
from ..retriever.hybrid_search import HybridSearcher
from ..indexer.performance_indexer import PerformanceIndexer
from ..storage.graph_store import GraphStore
from ..storage.metadata_store import MetadataStore
from ..config import get_config
from .stdio_compat import stdio_server_compat


mcp = FastMCP("kernel-rag")
router = IntentRouter()

# Load configuration from ~/.kernel-rag/config.json
_cfg = get_config()
REPO_PATH = _cfg.kernel_repo
INDEX_PATH = _cfg.index_dir("v7.0")

# Initialize tools
code_tools = CodeTools(REPO_PATH, INDEX_PATH)
git_tools = GitTools(REPO_PATH, INDEX_PATH)
kconfig_tools = KconfigTools(REPO_PATH)
performance_indexer = PerformanceIndexer()

_metadata_store = None
_base_path = INDEX_PATH / "base"
if _base_path.exists():
    _metadata_store = MetadataStore(_base_path)
    type_tools = TypeTools(_metadata_store)
else:
    type_tools = None

_graph_store = GraphStore(backend="networkx", path=INDEX_PATH)
causal_tools = CausalTools(_graph_store)


@mcp.tool(name="kernel_query")
def kernel_query(query: str, repo: str = "linux", top_k: int = 5) -> str:
    """万能内核查询入口。当用户问任何与 Linux 内核相关的问题时，优先调用此工具。
    
    适用场景：
    - "ext4 有什么新特性？"
    - "schedule() 函数怎么实现？"
    - "CFS 调度器的工作原理"
    - "TCP 拥塞控制最新改动"
    - "内存管理的页分配机制"
    
    此工具会自动识别意图并路由到最佳工具。"""
    intent = router.classify(query)
    
    # 使用配置好的索引路径，避免路径解析错误
    searcher = HybridSearcher(INDEX_PATH, REPO_PATH)
    results = searcher.search(query, top_k=top_k)
    
    output = f"Intent: {intent}\n\nResults:\n"
    for i, r in enumerate(results, 1):
        output += f"{i}. {r.chunk.file_path}:{r.chunk.start_line} {r.chunk.name}\n"
        if r.code:
            output += f"   {r.code[:100]}...\n"
    
    return output


@mcp.tool(name="kernel_search")
def kernel_search(query: str, repo: str = "linux", subsys: str = None, top_k: int = 5) -> str:
    """语义搜索内核代码。当用户用自然语言询问内核实现、机制、原理时调用。
    
    适用场景：
    - "CFS 怎么更新 vruntime？"
    - "TCP 三次握手在哪里实现？"
    - "内存回收的 LRU 算法"
    - "ext4 文件系统的日志机制"
    
    比 grep 更适合自然语言查询，会返回最相关的代码片段及行号。"""
    results = code_tools.kernel_search(query, subsys=subsys, top_k=top_k)
    
    output = ""
    for i, r in enumerate(results, 1):
        output += f"{i}. {r.file_path}:{r.start_line} {r.content[:50]}...\n"
    
    return output if output else "No results found"


@mcp.tool(name="kernel_define")
def kernel_define(symbol: str, repo: str = "linux") -> str:
    """Find exact definition of a symbol (function, struct, macro)."""
    result = code_tools.kernel_define(symbol)
    
    if result:
        return f"{result.name} defined at {result.file_path}:{result.line}"
    
    return f"Symbol '{symbol}' not found"


@mcp.tool(name="kernel_callers")
def kernel_callers(symbol: str, depth: int = 1, repo: str = "linux") -> str:
    """查找函数的调用者。当用户问"谁调用了这个函数"或"改了会影响谁"时调用。
    
    适用场景：
    - "谁调用了 schedule()？"
    - "改了 update_curr 会影响哪些地方？"
    - "这个函数的调用链是什么？"
    
    参数 depth 控制递归深度，1=直接调用者，2=二级调用者。"""
    callers = code_tools.kernel_callers(symbol, depth=depth)
    
    if not callers:
        return f"No callers found for '{symbol}'"
    
    output = f"Callers of {symbol}:\n"
    for c in callers:
        output += f"  - {c.caller_name}\n"
    
    return output


@mcp.tool(name="kernel_diff")
def kernel_diff(symbol: str, v1: str, v2: str, repo: str = "linux") -> str:
    """Show diff of a symbol between two versions."""
    result = code_tools.kernel_diff(symbol, v1, v2)
    
    if result.changes:
        return f"Changes for {symbol} between {v1} and {v2}:\n{result.changes[0].get('diff', '')[:500]}"
    
    return f"No changes found for {symbol}"


@mcp.tool(name="git_search_commits")
def git_search_commits(query: str, since: str = None, until: str = None, repo: str = "linux") -> str:
    """搜索 Git 提交历史。当用户询问内核变更、补丁、提交记录时调用。
    
    适用场景：
    - "ext4 最近有什么改动？"
    - "v6.12 到 v7.0 之间 schedule 变了什么？"
    - "谁修复了 TCP 的 RTO bug？"
    - "查找和内存回收相关的提交"
    
    since/until 可以是标签如 'v6.12' 或日期如 '2025-01-01'。"""
    commits = git_tools.git_search_commits(query, since=since, until=until)
    
    if not commits:
        return f"No commits found matching '{query}'"
    
    output = f"Commits matching '{query}':\n"
    for c in commits[:10]:
        output += f"  {c.hash[:8]}: {c.title} ({c.author}, {c.date})\n"
    
    return output


@mcp.tool(name="git_blame_line")
def git_blame_line(file: str, line: int, repo: str = "linux") -> str:
    """追溯某行代码的作者。当用户问"这行代码是谁写的"或"谁引入了这个"时调用。
    
    适用场景：
    - "kernel/sched/core.c 第 100 行是谁写的？"
    - "这个 bug 是哪个人引入的？"
    - "这段代码的历史作者是谁？"
    
    返回：作者名、提交哈希、日期。"""
    result = git_tools.git_blame_line(file, line)
    
    return f"Line {line} in {file} was introduced by {result.author} in commit {result.commit_hash[:8]} ({result.date})"


@mcp.tool(name="git_changelog")
def git_changelog(subsys: str, since_tag: str = None, until_tag: str = None, repo: str = "linux") -> str:
    """生成子系统的变更日志。当用户问"某个子系统最近改了什么"时调用。
    
    适用场景：
    - "sched 子系统 v7.0 有什么新特性？"
    - "mm 子系统从 v6.12 到 v7.0 的变更"
    - "ext4 文件系统最近的改动列表"
    
    subsys 可以是 'sched', 'mm', 'net', 'ext4', 'fs' 等。"""
    result = git_tools.git_changelog(subsys, since_tag=since_tag, until_tag=until_tag)
    
    if not result.entries:
        return f"No changes found for {subsys}"
    
    output = f"Changelog for {subsys}:\n"
    for e in result.entries[:10]:
        output += f"  {e['hash'][:8]}: {e['title']}\n"
    
    return output


@mcp.tool(name="git_commit_context")
def git_commit_context(commit_hash: str, repo: str = "linux") -> dict:
    """Get full context of a commit including diff."""
    result = git_tools.git_commit_context(commit_hash)
    
    return {
        "commit": result.hash[:8],
        "title": result.title,
        "author": result.author,
        "date": result.date,
        "diff": result.diff[:1000]
    }


@mcp.tool(name="kconfig_describe")
def kconfig_describe(config_name: str, repo: str = "linux") -> str:
    """查询内核配置选项的详细信息。当用户问"CONFIG_XXX 是什么"时调用。
    
    适用场景：
    - "CONFIG_SMP 是什么意思？"
    - "CONFIG_NUMA 的默认值是什么？"
    - "这个配置选项有什么作用？"
    
    返回：类型、帮助文本、默认值。"""
    result = kconfig_tools.kconfig_describe(config_name)
    
    if result:
        return f"{result.name} ({result.type}):\nHelp: {result.help}\nDefault: {result.default}"
    
    return f"Config '{config_name}' not found"


@mcp.tool(name="kconfig_deps")
def kconfig_deps(config_name: str, repo: str = "linux") -> str:
    """Show dependencies of a Kconfig option."""
    result = kconfig_tools.kconfig_deps(config_name)
    
    output = f"Dependencies for {config_name}:\n"
    output += f"Direct: {', '.join(result.direct_deps) if result.direct_deps else 'None'}\n"
    output += f"All: {', '.join(result.all_deps) if result.all_deps else 'None'}"
    
    return output


@mcp.tool(name="kconfig_check")
def kconfig_check(config_dict: str, repo: str = "linux") -> str:
    """Check if a Kconfig combination is satisfiable. Pass config as JSON string."""
    import json
    try:
        configs = json.loads(config_dict)
        result = kconfig_tools.kconfig_check(configs)
        return f"Configuration is {'valid' if result.satisfiable else 'invalid'}"
    except json.JSONDecodeError:
        return "Invalid config format. Use JSON like '{\"CONFIG_SMP\": \"y\", \"CONFIG_NUMA\": \"n\"}'"


@mcp.tool(name="kconfig_impact")
def kconfig_impact(config_name: str, repo: str = "linux") -> str:
    """Show files affected by a Kconfig option."""
    result = kconfig_tools.kconfig_impact(config_name)
    
    if result.affected_files:
        output = f"Files affected by {config_name}:\n"
        for f in result.affected_files[:20]:
            output += f"  {f}\n"
        return output
    
    return f"No files found referencing {config_name}"


@mcp.tool(name="git_search_by_type")
def git_search_by_type(type_tags: str, subsys: str = None, since: str = None, until: str = None, repo: str = "linux") -> str:
    """Search commits by patch type tags. Pass type_tags as comma-separated string like 'performance,bugfix'."""
    if type_tools is None:
        return "Type tools not available (no index found)"
    
    tags = [t.strip() for t in type_tags.split(",")]
    results = type_tools.git_search_by_type(tags, subsys=subsys, since=since, until=until)
    
    if not results:
        return f"No commits found with tags '{type_tags}'"
    
    output = f"Commits with tags '{type_tags}':\n"
    for r in results[:10]:
        output += f"  {r['hash'][:8]}: {r['title']} ({r.get('type_tags', '')})\n"
    
    return output


@mcp.tool(name="git_type_stats")
def git_type_stats(subsys: str = None, since: str = None, until: str = None, repo: str = "linux") -> str:
    """Show patch type distribution statistics."""
    if type_tools is None:
        return "Type tools not available (no index found)"
    
    stats = type_tools.git_type_stats(subsys=subsys, since=since, until=until)
    
    output = f"Patch type statistics:\n"
    output += f"Total commits: {stats.get('total', 0)}\n"
    for tag, count in sorted(stats.items()):
        if tag != "total":
            output += f"  {tag}: {count}\n"
    
    return output


@mcp.tool(name="git_causal_chain")
def git_causal_chain(commit_hash: str, direction: str = "upstream", repo: str = "linux") -> str:
    """Query the causal chain of a commit (upstream=bug origin, downstream=fixes)."""
    return causal_tools.git_causal_chain(commit_hash, direction=direction)


@mcp.tool(name="git_bug_origin")
def git_bug_origin(commit_hash: str, repo: str = "linux") -> str:
    """Find the root commit that introduced a bug."""
    return causal_tools.git_bug_origin(commit_hash)


@mcp.tool(name="git_backport_status")
def git_backport_status(commit_hash: str, repo: str = "linux") -> str:
    """Check backport status of a commit."""
    return causal_tools.git_backport_status(commit_hash)


@mcp.tool(name="performance_top_k")
def performance_top_k(subsys: str = "sched", k: int = 5, repo: str = "linux") -> str:
    """Find top K performance optimizations in a subsystem."""
    return f"Top {k} performance optimizations in {subsys}:\n(Performance indexing not yet fully implemented)"


@mcp.tool(name="ctags_jump")
def ctags_jump(symbol: str, repo: str = "linux") -> str:
    """Fast symbol lookup using ctags."""
    result = code_tools.kernel_define(symbol)
    
    if result:
        return f"{result.name} at {result.file_path}:{result.line}"
    
    return f"Symbol '{symbol}' not found"


@mcp.tool(name="cscope_callers")
def cscope_callers(symbol: str, depth: int = 1, repo: str = "linux") -> str:
    """Find callers using cscope."""
    return kernel_callers(symbol, depth=depth, repo=repo)


@mcp.tool(name="grep_code")
def grep_code(pattern: str, path: str = "*.c", repo: str = "linux") -> str:
    """精确文本搜索内核代码。当用户提到具体函数名、变量名、宏时调用。
    
    适用场景：
    - "ext4 文件系统在哪里定义？" → grep_code("ext4", "fs/ext4")
    - "查找所有使用 spin_lock 的地方" → grep_code("spin_lock")
    - "TCP 的 head 结构体在哪？" → grep_code("struct tcphdr", "net/ipv4")
    
    pattern 应该是代码关键字，不要用完整句子。
    path 可以是目录如 "fs/ext4" 或文件模式如 "*.c"。"""
    import shutil, subprocess
    from pathlib import Path

    try:
        search_path = str(REPO_PATH)
        include_pattern = path

        # If path contains directory, determine if it's a directory path or file pattern
        if "/" in path:
            full_path = REPO_PATH / path
            if full_path.is_dir():
                # path is a directory (e.g., "fs/ext4")
                search_path = str(full_path)
                include_pattern = "*"
            else:
                # path is a dir/file pattern (e.g., "fs/*.c")
                dir_part = path.rsplit("/", 1)[0]
                file_part = path.rsplit("/", 1)[1]
                search_path = str(REPO_PATH / dir_part)
                include_pattern = file_part

        # Prefer ripgrep (faster)
        if shutil.which("rg"):
            if include_pattern and include_pattern != "*":
                result = subprocess.run(
                    ["rg", "-n", "-S", "--max-count", "20", "-g", include_pattern, pattern, search_path],
                    capture_output=True, text=True, timeout=10
                )
            else:
                result = subprocess.run(
                    ["rg", "-n", "-S", "--max-count", "20", pattern, search_path],
                    capture_output=True, text=True, timeout=10
                )
        else:
            result = subprocess.run(
                ["grep", "-r", "-n", "--include", include_pattern, "-m", "20", pattern, search_path],
                capture_output=True, text=True, timeout=10
            )

        if result.returncode != 0:
            # Try extracting keywords from long natural language queries
            if len(pattern.split()) > 2:
                keywords = [w for w in pattern.split() if len(w) > 3 and w.lower() not in ("what", "how", "does", "this", "that", "with", "from", "into", "about", "than")]
                if keywords:
                    fallback_pattern = keywords[0]
                    try:
                        if shutil.which("rg"):
                            if include_pattern and include_pattern != "*":
                                result2 = subprocess.run(
                                    ["rg", "-n", "-S", "--max-count", "20", "-g", include_pattern, fallback_pattern, search_path],
                                    capture_output=True, text=True, timeout=10
                                )
                            else:
                                result2 = subprocess.run(
                                    ["rg", "-n", "-S", "--max-count", "20", fallback_pattern, search_path],
                                    capture_output=True, text=True, timeout=10
                                )
                        else:
                            result2 = subprocess.run(
                                ["grep", "-r", "-n", "--include", include_pattern, "-m", "20", fallback_pattern, search_path],
                                capture_output=True, text=True, timeout=10
                            )
                        if result2.returncode == 0:
                            lines = result2.stdout.strip().split("\n")[:20]
                            return f"No exact match for '{pattern}'. Showing results for keyword '{fallback_pattern}':\n" + "\n".join(lines)
                    except Exception:
                        pass
            return f"No matches found for '{pattern}'"
        lines = result.stdout.strip().split("\n")[:20]
        return "\n".join(lines)
    except subprocess.TimeoutExpired:
        return f"Search timed out for '{pattern}'. Try a more specific keyword."
    except Exception:
        return f"Search error for '{pattern}'"


if __name__ == "__main__":
    mcp.run()
