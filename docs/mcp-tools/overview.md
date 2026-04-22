# MCP Server 设计

> 本文档描述 MCP Server 层的接口设计、工具清单和路由策略。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 统一查询网关

AI 客户端不直接面对多个后端，而是连接**单一的 `kernel-rag-mcp` Server**。Server 内部根据查询意图**自动路由**：

```python
@mcp.tool()
def kernel_query(intent: str, query: str, context: dict) -> str:
    """
    统一内核查询入口。AI 模型只需调用此工具，内部自动路由。
    """
    if intent == "semantic":           # 自然语言问机制
        return code_rag.search(query)
    elif intent == "exact_symbol":     # 精确符号跳转
        return ctags.jump(query)
    elif intent == "history":          # 问变更历史
        return git_rag.search_commits(query)
    elif intent == "blame":            # 问这行代码谁写的
        return git_rag.blame(context['file'], context['line'])
    elif intent == "config_valid":     # 问配置组合是否合法
        return kconfig_solver.check(context['config_combo'])
    elif intent == "impact":           # 问影响范围
        return cscope.callers(query) + code_rag.cross_ref(query)
    elif intent == "causal":           # 问 bug 因果链
        return git_causal.graph_query(query)
    elif intent == "patch_type":       # 按类型筛选 patch
        return git_rag.search_by_type(context['type_tags'], context['range'])
    elif intent == "performance":       # 性能补丁查询
        return performance_rag.query(context['query'], context.get('subsys'))
    elif intent == "feature_evolution": # 特性演进追踪
        return performance_rag.feature_evolution(context['feature_name'])
    else:
        # 混合路由：同时召回代码 + Git + Kconfig + 因果链 + 类型 + 性能，由 LLM 组装
        return hybrid_assemble(query)
```

---

## 2. AI 自动选择策略

通过 MCP tool description 提示 AI 自动选择路由：

| 用户问题模式 | AI 自动选择的路由 | 调用的底层工具 |
|:------------|:----------------|:-------------|
| "CFS 怎么更新 vruntime？" | 语义搜索 | `code_rag.search()` |
| "schedule() 在哪一行？" | 精确符号 | `ctags.jump()` |
| "这个函数在 6.6 到 6.12 之间变了什么？" | Git 历史 | `git_rag.diff_summary()` |
| "这行代码是谁引入的？" | 行级溯源 | `git_rag.blame()` |
| "开启 CONFIG_X 且关闭 CONFIG_Y 能编译吗？" | Kconfig 验证 | `kconfig_solver.check()` |
| "改了这个函数会影响谁？" | 影响分析 | `cscope.callers()` + `code_rag.search()` |
| "为什么这里要这样设计？" | 混合召回 | `code_rag.search()` + `git_rag.commit_message()` |
| "这个 bug 是哪个 commit 引入的？" | 变更因果 | `git_causal.bug_origin()` |
| "这个修复有没有 backport？" | 变更因果 | `git_causal.backport_status()` |
| "6.12 到 6.13 之间有哪些性能优化？" | Patch 类型 | `git_rag.search_by_type(["performance"])` |
| "最近修复了哪些性能回归？" | Patch 类型 | `git_rag.search_by_type(["bugfix", "performance", "regression"])` |
| "per-CPU vruntime 特性的完整演进？" | 特性追踪 | `performance_rag.feature_evolution("per-CPU vruntime")` |
| "sched 子系统 Top 5 性能优化？" | 性能排序 | `performance_rag.top_k("sched", metric="improvement")` |
| "这个补丁提升了多少性能？" | 性能数据 | `performance_rag.impact("commit_hash")` |

---

## 3. 代码语义层工具

| Tool | 功能 | 触发场景 |
|------|------|----------|
| `kernel_search(query, subsys, kconfig, top_k)` | 语义搜索内核代码 | 用户询问实现细节、机制原理 |
| `kernel_define(symbol, file_hint)` | 精确符号定义查询 | 用户提到具体函数/宏/结构体 |
| `kernel_callers(symbol, depth)` | 调用链追踪 | 影响分析、审查范围确认 |
| `kernel_diff(symbol, v1, v2)` | 版本差异对比 | 问"这个函数在 5.15 和 6.12 之间变了什么" |
| `kernel_cross_ref(symbol)` | 跨文件关联 | 找声明、定义、使用点 |

---

## 4. Git 历史层工具

| Tool | 功能 | 触发场景 |
|------|------|----------|
| `git_search_commits(query, since, until, author, file_pattern)` | 语义搜索 commit history | 问"谁改了什么" |
| `git_blame_line(file, line)` | 行级代码溯源 | "这行代码谁引入的" |
| `git_diff_summary(symbol, v1, v2)` | 两个版本间某符号的变更摘要 | "这个函数变了什么" |
| `git_changelog(subsys, since_tag, until_tag)` | 子系统变更日志生成 | "sched 子系统最近改了什么" |
| `git_commit_context(commit_hash)` | 获取某 commit 的完整上下文 | 审查具体 patch |
| `git_show_patch(commit_hash, file)` | 获取某 commit 在某文件的 diff | 看具体修改 |

---

## 5. Patch 类型筛选工具

| Tool | 功能 | 触发场景 |
|------|------|----------|
| `git_search_by_type(type_tags[], subsys, since, until)` | 按类型标签筛选 commits | "某版本范围内某子系统的性能改动" |
| `git_type_stats(subsys, since, until)` | 统计各类型 patch 分布 | "过去半年 mm 子系统有多少 bugfix" |
| `git_find_performance_regression_fix(subsys, since)` | 查找性能回归修复 | "最近修复了哪些性能回归" |

---

## 6. 性能补丁工具

| Tool | 功能 | 触发场景 |
|------|------|----------|
| `performance_feature_query(feature_name)` | 查询特性完整演进 | "per-CPU vruntime 的完整演进" |
| `performance_compare(v1, v2, subsys)` | 对比两个版本性能 | "6.12 到 6.13 sched 性能变化" |
| `performance_top_k(subsys, since, metric)` | 按性能提升排序 | "sched 子系统 Top 10 性能优化" |
| `performance_impact(commit_hash)` | 查询性能影响范围 | "这个补丁影响了哪些性能指标" |
| `performance_regression_query(subsys, since)` | 查询性能回归 | "最近有哪些性能退化" |

---

## 7. 变更因果图谱工具

| Tool | 功能 | 触发场景 |
|------|------|----------|
| `git_causal_chain(commit_hash, direction="both")` | 查询变更因果链（上游/下游） | "这个 bug 的完整修复链是什么" |
| `git_bug_origin(commit_hash)` | 追踪问题引入源头 | "这个 regression 是哪个 commit 引入的" |
| `git_backport_status(commit_hash)` | 查询 backport 状态 | "这个修复有没有进 stable 分支" |
| `git_reviewer_expertise(reviewer, subsys)` | 查询审查者的专业领域 | "David Miller 审查过哪些网络补丁" |
| `git_regression_chain(subsys, since)` | 查询某子系统的回归链 | "最近一年 mm 子系统有哪些 regression" |
| `git_patch_series(commit_hash)` | 查询补丁系列关系 | "这个 commit 属于哪个系列" |
| `git_fixes_complete(commit_hash)` | 验证 Fixes 链完整性 | "这个修复是否完整覆盖了所有引入点" |

---

## 8. Kconfig 配置层工具

| Tool | 功能 | 触发场景 |
|------|------|----------|
| `kconfig_describe(config_name)` | 查询配置项的 help、类型、默认值 | "CONFIG_SMP 是什么" |
| `kconfig_deps(config_name)` | 查询直接和间接依赖 | "开启这个需要什么前置条件" |
| `kconfig_check(combo_dict)` | 验证配置组合的可满足性 | "A=y 且 B=n 是否合法" |
| `kconfig_impact(config_name)` | 查询修改某配置影响的源文件 | "关闭这个会少编译哪些文件" |

---

## 9. 精确工具层（包装传统命令）

| Tool | 底层命令 | 用途 |
|------|----------|------|
| `ctags_jump(symbol)` | `ctags -x` | 毫秒级精确跳转 |
| `cscope_callers(symbol, depth)` | `cscope -d -L3` | 调用关系查询 |
| `grep_code(pattern, path)` | `ripgrep -n -C 3` | 文本模式匹配 |

---

## 10. MCP 包装传统工具示例

自然语言本身不能直接调用 `ctags`/`cscope`，但 MCP 协议可以。本项目通过 MCP Server 把这些命令行工具包装成 AI 可调用的函数：

```python
# 示例：MCP Server 内部暴露的底层工具
@mcp.tool()
def ctags_jump(symbol: str) -> str:
    """精确跳转到符号定义。当用户提到具体函数名/宏名，需要验证行号时调用。"""

@mcp.tool()
def cscope_callers(symbol: str, depth: int = 1) -> str:
    """查询某函数的调用者列表。当需要分析影响范围、追踪调用链时调用。"""

@mcp.tool()
def grep_code(pattern: str, path: str = "*.c") -> str:
    """文本搜索代码库。当需要查找特定字符串、注释或错误处理模式时调用。"""
```

AI 模型在对话中会根据问题类型**自动选择**调用：
- "用户问 `schedule()` 在哪" → 调用 `ctags_jump("schedule")`
- "用户问谁调用了 `kmem_cache_alloc`" → 调用 `cscope_callers("kmem_cache_alloc")`
- "用户问哪里用了 `copy_from_user` 但没检查返回值" → 调用 `grep_code("copy_from_user", "*.c")`

---

## 11. 与 OpenCode 的集成

### 集成方式 A：MCP 标准接入（推荐）

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

### 集成方式 B：与 `/init-deep` 分层上下文协同

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
当用户问"某个特性的完整演进"时，调用 `performance_feature_query` 追踪特性历史；
当用户问"Top K 性能优化"时，调用 `performance_top_k` 按提升幅度排序；
当用户问"这个 bug 是谁引入的"时，调用 `git_causal` 追踪 Fixes:/Introduced-by: 链；
当用户提到具体函数名时，调用 `ctags_jump` 验证精确行号。
```

### 集成方式 C：通用大模型（无 MCP 支持）

如果用户使用不支持 MCP 的通用大模型（如网页版 ChatGPT、DeepSeek 网页版），提供**CLI 管道模式**：

```bash
# 用户手动查询上下文，复制粘贴给大模型
$ kernel-rag query "TCP RTO SACK bug 引入源头和修复链"
→ [输出带行号的代码 + commit + Fixes: 链 + backport 状态]

# 用户将输出粘贴到 ChatGPT 作为上下文
```
