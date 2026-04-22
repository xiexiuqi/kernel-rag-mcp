# 集成与部署设计

> 本文档描述与 OpenCode、Claude Code、Cursor 等 AI 工具的集成方式，以及运维部署策略。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 与 OpenCode 的深度集成

### 1.1 集成方式 A：MCP 标准接入（推荐）

```json
// .opencode/mcp.json 或全局配置
{
  "mcpServers": {
    "kernel-rag": {
      "command": "python",
      "args": ["-m", "kernel_rag_mcp.server"],
      "env": {
        "KERNEL_REPO": "/home/user/linux",
        "INDEX_PATH": "/home/user/.kernel-rag/repos/linux/v6.12/current"
      }
    }
  }
}
```

OpenCode 在对话中自动触发：
- 用户问内核问题 → OpenCode 调用 `kernel_query` → 返回带行号的上下文 → OpenCode 生成回答

### 1.2 集成方式 B：与 `/init-deep` 分层上下文协同

OpenCode 的 `/init-deep` 生成项目级 `AGENTS.md`，本项目可为其**注入内核领域上下文**：

```markdown
<!-- AGENTS.md（由 /init-deep 生成，kernel-rag-mcp 可追加注入） -->
# 项目上下文
- 项目：Linux 内核 v6.12
- 架构：x86_64

# MCP 工具可用性
- 内核语义搜索：通过 `kernel-rag` MCP Server
- 精确符号跳转：通过 `ctags_jump` 工具
- Git 历史查询：通过 `git_rag` 工具
- Patch 类型筛选：通过 `git_search_by_type` 工具
- 变更因果追踪：通过 `git_causal` 工具
- Kconfig 验证：通过 `kconfig_solver` 工具

# 查询规范
当用户询问内核实现细节时，优先调用 `kernel-rag` 获取代码上下文；
当用户询问"为什么这样设计"时，优先调用 `git_rag` 获取 commit message；
当用户问"最近有哪些性能优化"时，调用 `git_search_by_type` 筛选 performance 标签；
当用户问"这个 bug 是谁引入的"时，调用 `git_causal` 追踪 Fixes:/Introduced-by: 链；
当用户提到具体函数名时，调用 `ctags_jump` 验证精确行号。
```

**效果**：OpenCode 的 AI 在理解项目概貌（`/init`）的同时，能通过 MCP 实时查询内核代码库的深度语义、Patch 类型和变更因果。

### 1.3 集成方式 C：通用大模型（无 MCP 支持）

如果用户使用不支持 MCP 的通用大模型（如网页版 ChatGPT、DeepSeek 网页版），提供**CLI 管道模式**：

```bash
# 用户手动查询上下文，复制粘贴给大模型
$ kernel-rag query "TCP RTO SACK bug 引入源头和修复链"
→ [输出带行号的代码 + commit + Fixes: 链 + backport 状态]

# 用户将输出粘贴到 ChatGPT 作为上下文
```

---

## 2. 维护者专用工作流（Reviewer 场景）

针对内核 Maintainer 和 Reviewer 的高阶需求，设计**审查模式**：

```bash
# 审查一个 patch 时，AI 自动执行以下查询链
1. git_diff_summary(patch_file)          # 这个 patch 改了哪些函数
2. kernel_callers(changed_symbol, 2)     # 这些函数的二级调用者
3. kconfig_impact(changed_config)          # 是否影响编译条件
4. git_blame_line(changed_file, line)    # 原始代码是谁写的（找专家）
5. git_search_by_type(["performance"], since="1.year")  # 历史上同类性能改动
6. git_causal_chain(patch_commit, "upstream")  # 上游是否有相关修复/回归
7. git_fixes_complete(patch_commit)      # Fixes: 链是否完整
8. git_backport_status(patch_commit)     # 是否需要/已经 backport
```

**输出**：一份结构化审查摘要，包含影响范围、历史背景、同类改动参考、修复完整性、Backport 状态、潜在风险点。

---

## 3. Git Hooks 集成（可选）

提供可选的 Git hooks，在切换分支或合并时自动触发增量索引：

```bash
# 安装 hooks（用户主动选择）
$ kernel-rag hooks install ~/linux
→ 创建 ~/linux/.git/hooks/post-checkout
→ 创建 ~/linux/.git/hooks/post-merge

# post-checkout 示例
#!/bin/bash
PREV_COMMIT=$1
NEW_COMMIT=$2
if [ "$3" = "1" ]; then  # branch checkout
    kernel-rag update --repo ~/linux --background
fi
```

**注意**：Git hooks 默认**不启用**，避免拖慢日常 Git 操作。用户显式安装后，增量更新在后台运行（`--background` 模式，低优先级）。

---

## 4. 不侵入源码树

- **不在内核仓库内创建文件**：所有索引数据存放在 `~/.kernel-rag/`，内核源码目录保持干净
- **可选的轻量标记文件**：用户可选择在内核根目录生成 `.kernel-rag.toml`（仅含外部索引引用），方便团队协作时共享配置：

```toml
# /home/user/linux/.kernel-rag.toml（可选，可加入 .gitignore）
[index]
repo_name = "linux"
version_namespace = "v6.12"

[mcp]
enabled = true
auto_update = false
```

---

## 5. 兼容性

- **AI 客户端**：Claude Code（MCP stdio）、Cursor（MCP json）、OpenCode（MCP/HTTP）、Windsurf
- **内核版本**：Linux 5.x / 6.x（主分支 + LTS）
- **平台**：Linux x86_64 / aarch64（开发机），macOS（Apple Silicon，通过 Rosetta/原生）
