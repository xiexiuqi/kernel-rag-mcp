import json
import subprocess
from pathlib import Path
import click

DEFAULT_INDEX_ROOT = Path.home() / ".kernel-rag"
REPOS_JSON = DEFAULT_INDEX_ROOT / "repos.json"

@click.group()
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def cli(ctx, verbose):
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

@cli.command()
@click.option("--repo-path", "-p", type=click.Path(exists=True), default=".")
@click.option("--name", "-n")
@click.pass_context
def init(ctx, repo_path, name):
    repo_path = Path(repo_path).resolve()
    if not name:
        name = repo_path.name
    
    if not (repo_path / ".git").exists():
        click.echo(f"Error: {repo_path} is not a git repository", err=True)
        return 1
    
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "describe", "--tags", "--always"],
            capture_output=True, text=True, check=True
        )
        version = result.stdout.strip()
    except subprocess.CalledProcessError:
        version = "unknown"
    
    DEFAULT_INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    
    repos = {}
    if REPOS_JSON.exists():
        with open(REPOS_JSON) as f:
            repos = json.load(f)
    
    repos[name] = {"path": str(repo_path), "version": version}
    with open(REPOS_JSON, "w") as f:
        json.dump(repos, f, indent=2)
    
    click.echo(f"Initialized '{name}' at {repo_path} ({version})")

@cli.command()
@click.option("--repo", "-r", required=True)
@click.option("--subsystems", "-s")
@click.option("--base", "-b")
@click.option("--target", "-t")
def index(repo, subsystems, base, target):
    if not REPOS_JSON.exists():
        click.echo("Error: Run `kernel-rag init` first", err=True)
        return 1
    
    with open(REPOS_JSON) as f:
        repos = json.load(f)
    
    if repo not in repos:
        click.echo(f"Error: Repository '{repo}' not found", err=True)
        return 1
    
    repo_path = Path(repos[repo]["path"])
    if not base:
        base = repos[repo].get("version", "HEAD~100")
    if not target:
        target = "HEAD"
    
    subsys_list = [s.strip() for s in subsystems.split(",")] if subsystems else ["kernel/sched", "mm", "net"]
    
    click.echo(f"Indexing {repo}: {base}..{target} subsystems={subsys_list}")
    
    from kernel_rag_mcp.indexer.main import Indexer
    indexer = Indexer(repo_path, DEFAULT_INDEX_ROOT / "repos" / repo)
    result = indexer.build_index(base, target, subsys_list)
    click.echo(f"Done. Index saved to: {result}")

@cli.command()
@click.option("--repo", "-r", required=True)
@click.option("--query", "-q", required=True)
@click.option("--top-k", "-k", default=5)
def query(repo, query, top_k):
    from kernel_rag_mcp.retriever.hybrid_search import HybridSearcher
    
    searcher = HybridSearcher(DEFAULT_INDEX_ROOT / "repos" / repo)
    results = searcher.search(query, top_k=top_k)
    
    click.echo(f"Query: {query}")
    for i, r in enumerate(results, 1):
        click.echo(f"  {i}. {r.chunk.file_path}:{r.chunk.start_line} {r.chunk.name}")

@cli.command()
def status():
    if not REPOS_JSON.exists():
        click.echo("No repositories initialized")
        return
    
    with open(REPOS_JSON) as f:
        repos = json.load(f)
    
    for name, config in repos.items():
        click.echo(f"{name}: {config['path']} ({config.get('version', 'unknown')})")

@cli.group()
def mcp():
    pass

@mcp.command("install")
@click.option("--client", "-c", required=True, type=click.Choice(["claude-code", "cursor", "opencode"]))
@click.option("--repo", "-r", default="linux")
def mcp_install(client, repo):
    """Install MCP configuration for AI client."""
    
    config = {
        "mcpServers": {
            "kernel-rag": {
                "command": "python",
                "args": ["-m", "kernel_rag_mcp.server.mcp_server"],
                "env": {
                    "KERNEL_REPO": str(Path.home() / "linux"),
                    "INDEX_PATH": str(DEFAULT_INDEX_ROOT / "repos" / repo / "v7.0-rc6"),
                }
            }
        }
    }
    
    if client == "claude-code":
        config_path = Path.home() / ".claude" / "config.json"
    elif client == "cursor":
        config_path = Path.home() / ".cursor" / "mcp.json"
    elif client == "opencode":
        config_path = Path.home() / ".opencode" / "mcp.json"
    
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    
    click.echo(f"MCP configuration installed for {client} at {config_path}")
    click.echo(f"Config: {json.dumps(config, indent=2)}")

if __name__ == "__main__":
    cli()
