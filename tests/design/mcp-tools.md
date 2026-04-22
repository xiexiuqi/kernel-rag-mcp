# MCP 工具层测试设计

> 本文档描述 MCP Server 和工具层的测试策略和用例设计。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 测试范围

MCP 工具层包含：
- 统一查询网关（`kernel_query`）
- 意图识别与路由引擎
- 各工具实现（code_tools, git_tools, type_tools, causal_tools, kconfig_tools, legacy_tools）
- MCP 协议兼容性

---

## 2. 路由引擎测试

| 测试用例 | 用户问题 | 预期路由 | 优先级 |
|----------|----------|----------|--------|
| 语义搜索路由 | "CFS 怎么更新 vruntime？" | `code_rag.search()` | P0 |
| 精确符号路由 | "schedule() 在哪一行？" | `ctags.jump()` | P0 |
| Git 历史路由 | "这个函数在 6.6 到 6.12 之间变了什么？" | `git_rag.diff_summary()` | P0 |
| Kconfig 路由 | "开启 CONFIG_SMP 且关闭 CONFIG_NUMA 能编译吗？" | `kconfig_solver.check()` | P0 |
| 因果图谱路由 | "这个 bug 是哪个 commit 引入的？" | `git_causal.bug_origin()` | P0 |
| Patch 类型路由 | "6.12 到 6.13 之间有哪些性能优化？" | `git_rag.search_by_type()` | P0 |
| 混合路由 | "为什么这里要这样设计？" | `hybrid_assemble()` | P1 |
| 模糊查询路由 | "那个调度器的东西" | `code_rag.search()` | P1 |

---

## 3. 工具功能测试

### 3.1 代码语义工具

| 工具 | 测试用例 | 验证点 |
|------|----------|--------|
| `kernel_search` | 搜索 "vruntime" | 返回 `update_curr()` 实现 |
| `kernel_define` | 查询 "struct task_struct" | 返回定义位置和完整定义 |
| `kernel_callers` | 查询 "schedule()" 的调用者 | 返回所有调用点（深度 1/2/3） |
| `kernel_diff` | 对比 `update_curr()` 在 6.6 和 6.12 | 返回变更摘要 |
| `kernel_cross_ref` | 查询 "pick_next_task" | 返回声明、定义、使用点 |

### 3.2 Git 历史工具

| 工具 | 测试用例 | 验证点 |
|------|----------|--------|
| `git_search_commits` | 搜索 "fix RTO" | 返回相关 commit 列表 |
| `git_blame_line` | 查询 `fair.c:1234` | 返回引入该行的 commit |
| `git_diff_summary` | 对比 `tcp_cong` 在 5.15 和 6.12 | 返回变更函数列表 |
| `git_changelog` | 查询 `sched` 子系统 6.12..6.13 | 返回变更日志 |

### 3.3 Kconfig 工具

| 工具 | 测试用例 | 验证点 |
|------|----------|--------|
| `kconfig_describe` | 查询 "CONFIG_SMP" | 返回类型、默认值、help |
| `kconfig_deps` | 查询 "CONFIG_NUMA" 依赖 | 返回完整依赖链 |
| `kconfig_check` | 验证 `SMP=y ∧ NUMA=n` | 返回 SAT |
| `kconfig_impact` | 查询关闭 "CONFIG_SMP" | 返回影响的源文件列表 |

### 3.4 变更因果工具

| 工具 | 测试用例 | 验证点 |
|------|----------|--------|
| `git_causal_chain` | 查询修复 commit | 返回从引入到修复的完整链 |
| `git_bug_origin` | 查询 regression commit | 返回问题引入源头 |
| `git_backport_status` | 查询含 Cc: stable 的 commit | 返回 backport 状态 |
| `git_fixes_complete` | 验证 Fixes 链 | 报告是否完整覆盖 |

### 3.5 精确工具

| 工具 | 测试用例 | 验证点 |
|------|----------|--------|
| `ctags_jump` | 跳转 "schedule" | 返回精确文件和行号 |
| `cscope_callers` | 查询 "kmem_cache_alloc" | 返回调用者列表 |
| `grep_code` | 搜索 "copy_from_user" | 返回匹配行和上下文 |

---

## 4. MCP 协议兼容性测试

| 测试用例 | 协议特性 | 验证点 |
|----------|----------|--------|
| stdio 传输 | MCP stdio | 工具列表、调用、返回正确 |
| SSE 传输 | MCP SSE | 长连接、流式响应 |
| HTTP 传输 | MCP HTTP | RESTful 接口正确 |
| 工具发现 | `tools/list` | 返回所有可用工具 |
| 错误处理 | 无效参数 | 返回标准 MCP 错误格式 |
| 并发调用 | 同时调用多个工具 | 无冲突、结果正确 |

---

## 5. 与 AI 客户端集成测试

| 客户端 | 测试内容 |
|--------|----------|
| Claude Code | MCP stdio 集成、工具调用 |
| Cursor | MCP json 配置、工具调用 |
| OpenCode | MCP/HTTP 集成、工具调用 |
| Windsurf | MCP 兼容性 |

---

## 6. 端到端测试场景

### 6.1 内核新人学习场景

```
用户："CFS 怎么更新 vruntime？"

验证点：
1. AI 调用 kernel_search("CFS vruntime update")
2. 返回 update_curr() 实现（含行号）
3. AI 解释 vruntime 机制
4. 用户可点击行号跳转到源码
```

### 6.2 Reviewer 审查场景

```
用户："审查这个 patch，确认影响范围"

验证点：
1. AI 调用 git_diff_summary(patch)
2. AI 调用 kernel_callers(changed_symbol, 2)
3. AI 调用 kconfig_impact(changed_config)
4. AI 调用 git_causal_chain(patch_commit)
5. 返回结构化审查摘要
```

### 6.3 回归分析场景

```
用户："这个 TCP RTO bug 的完整生命周期"

验证点：
1. AI 调用 git_causal_chain(fix_commit)
2. 追踪 Fixes: → Introduced-by: 链
3. 查询 backport 状态
4. 返回完整因果链报告
```
