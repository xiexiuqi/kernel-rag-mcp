import os
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .router import IntentRouter
from .tools.code_tools import CodeTools
from .tools.git_tools import GitTools
from .tools.kconfig_tools import KconfigTools
from ..retriever.hybrid_search import HybridSearcher
from ..indexer.performance_indexer import PerformanceIndexer


mcp = FastMCP("kernel-rag")
router = IntentRouter()

# Get repo path from environment or default
REPO_PATH = Path(os.environ.get("KERNEL_REPO", str(Path.home() / "linux")))
INDEX_PATH = Path(os.environ.get("INDEX_PATH", str(Path.home() / ".kernel-rag" / "repos" / "linux" / "v7.0")))

# Initialize tools
code_tools = CodeTools(REPO_PATH, INDEX_PATH)
git_tools = GitTools(REPO_PATH, INDEX_PATH)
kconfig_tools = KconfigTools(REPO_PATH)
performance_indexer = PerformanceIndexer()


@mcp.tool()
def kernel_query(query: str, repo: str = "linux", top_k: int = 5) -> str:
    """Unified kernel query entry point. Automatically routes to appropriate tools based on intent."""
    intent = router.classify(query)
    
    index_path = Path.home() / ".kernel-rag" / "repos" / repo
    searcher = HybridSearcher(index_path, REPO_PATH)
    results = searcher.search(query, top_k=top_k)
    
    output = f"Intent: {intent}\n\nResults:\n"
    for i, r in enumerate(results, 1):
        output += f"{i}. {r.chunk.file_path}:{r.chunk.start_line} {r.chunk.name}\n"
        if r.code:
            output += f"   {r.code[:100]}...\n"
    
    return output


@mcp.tool()
def kernel_search(query: str, repo: str = "linux", subsys: str = None, top_k: int = 5) -> str:
    """Search kernel code by semantic query."""
    results = code_tools.kernel_search(query, subsys=subsys, top_k=top_k)
    
    output = ""
    for i, r in enumerate(results, 1):
        output += f"{i}. {r.file_path}:{r.start_line} {r.content[:50]}...\n"
    
    return output if output else "No results found"


@mcp.tool()
def kernel_define(symbol: str, repo: str = "linux") -> str:
    """Find exact definition of a symbol (function, struct, macro)."""
    result = code_tools.kernel_define(symbol)
    
    if result:
        return f"{result.name} defined at {result.file_path}:{result.line}"
    
    return f"Symbol '{symbol}' not found"


@mcp.tool()
def kernel_callers(symbol: str, depth: int = 1, repo: str = "linux") -> str:
    """Find callers of a function. Use this for impact analysis."""
    callers = code_tools.kernel_callers(symbol, depth=depth)
    
    if not callers:
        return f"No callers found for '{symbol}'"
    
    output = f"Callers of {symbol}:\n"
    for c in callers:
        output += f"  - {c.caller_name}\n"
    
    return output


@mcp.tool()
def kernel_diff(symbol: str, v1: str, v2: str, repo: str = "linux") -> str:
    """Show diff of a symbol between two versions."""
    result = code_tools.kernel_diff(symbol, v1, v2)
    
    if result.changes:
        return f"Changes for {symbol} between {v1} and {v2}:\n{result.changes[0].get('diff', '')[:500]}"
    
    return f"No changes found for {symbol}"


@mcp.tool()
def git_search_commits(query: str, since: str = None, until: str = None, repo: str = "linux") -> str:
    """Search git commit history by query string."""
    commits = git_tools.git_search_commits(query, since=since, until=until)
    
    if not commits:
        return f"No commits found matching '{query}'"
    
    output = f"Commits matching '{query}':\n"
    for c in commits[:10]:
        output += f"  {c.hash[:8]}: {c.title} ({c.author}, {c.date})\n"
    
    return output


@mcp.tool()
def git_blame_line(file: str, line: int, repo: str = "linux") -> str:
    """Find who introduced a specific line of code."""
    result = git_tools.git_blame_line(file, line)
    
    return f"Line {line} in {file} was introduced by {result.author} in commit {result.commit_hash[:8]} ({result.date})"


@mcp.tool()
def git_changelog(subsys: str, since_tag: str = None, until_tag: str = None, repo: str = "linux") -> str:
    """Generate changelog for a subsystem between tags."""
    result = git_tools.git_changelog(subsys, since_tag=since_tag, until_tag=until_tag)
    
    if not result.entries:
        return f"No changes found for {subsys}"
    
    output = f"Changelog for {subsys}:\n"
    for e in result.entries[:10]:
        output += f"  {e['hash'][:8]}: {e['title']}\n"
    
    return output


@mcp.tool()
def git_commit_context(commit_hash: str, repo: str = "linux") -> str:
    """Get full context of a commit including diff."""
    result = git_tools.git_commit_context(commit_hash)
    
    output = f"Commit {result.hash[:8]}: {result.title}\n"
    output += f"Author: {result.author}, Date: {result.date}\n\n"
    output += f"Diff:\n{result.diff[:1000]}"
    
    return output


@mcp.tool()
def kconfig_describe(config_name: str, repo: str = "linux") -> str:
    """Describe a Kconfig option (type, help, default)."""
    result = kconfig_tools.kconfig_describe(config_name)
    
    if result:
        return f"{result.name} ({result.type}):\nHelp: {result.help}\nDefault: {result.default}"
    
    return f"Config '{config_name}' not found"


@mcp.tool()
def kconfig_deps(config_name: str, repo: str = "linux") -> str:
    """Show dependencies of a Kconfig option."""
    result = kconfig_tools.kconfig_deps(config_name)
    
    output = f"Dependencies for {config_name}:\n"
    output += f"Direct: {', '.join(result.direct_deps) if result.direct_deps else 'None'}\n"
    output += f"All: {', '.join(result.all_deps) if result.all_deps else 'None'}"
    
    return output


@mcp.tool()
def kconfig_check(config_dict: str, repo: str = "linux") -> str:
    """Check if a Kconfig combination is satisfiable. Pass config as JSON string."""
    import json
    try:
        configs = json.loads(config_dict)
        result = kconfig_tools.kconfig_check(configs)
        return f"Configuration is {'valid' if result.satisfiable else 'invalid'}"
    except json.JSONDecodeError:
        return "Invalid config format. Use JSON like '{\"CONFIG_SMP\": \"y\", \"CONFIG_NUMA\": \"n\"}'"


@mcp.tool()
def kconfig_impact(config_name: str, repo: str = "linux") -> str:
    """Show files affected by a Kconfig option."""
    result = kconfig_tools.kconfig_impact(config_name)
    
    if result.affected_files:
        output = f"Files affected by {config_name}:\n"
        for f in result.affected_files[:20]:
            output += f"  {f}\n"
        return output
    
    return f"No files found referencing {config_name}"


@mcp.tool()
def performance_top_k(subsys: str = "sched", k: int = 5, repo: str = "linux") -> str:
    """Find top K performance optimizations in a subsystem."""
    return f"Top {k} performance optimizations in {subsys}:\n(Performance indexing not yet fully implemented)"


@mcp.tool()
def ctags_jump(symbol: str, repo: str = "linux") -> str:
    """Fast symbol lookup using ctags."""
    result = code_tools.kernel_define(symbol)
    
    if result:
        return f"{result.name} at {result.file_path}:{result.line}"
    
    return f"Symbol '{symbol}' not found"


@mcp.tool()
def cscope_callers(symbol: str, depth: int = 1, repo: str = "linux") -> str:
    """Find callers using cscope."""
    return kernel_callers(symbol, depth=depth, repo=repo)


@mcp.tool()
def grep_code(pattern: str, path: str = "*.c", repo: str = "linux") -> str:
    """Search code using grep/ripgrep."""
    import subprocess
    try:
        result = subprocess.run(
            ["grep", "-r", "-n", "--include", path, pattern, str(REPO_PATH)],
            capture_output=True, text=True, check=True
        )
        lines = result.stdout.strip().split("\n")[:20]
        return "\n".join(lines)
    except subprocess.CalledProcessError:
        return f"No matches found for '{pattern}'"


if __name__ == "__main__":
    mcp.run()
