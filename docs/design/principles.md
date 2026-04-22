# 核心设计原则

> 本文档定义 Kernel-RAG-MCP 的顶层设计原则，所有子系统实现必须遵守。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 精确溯源优先（Line-Number-First）

所有检索结果必须包含 **文件路径 + 精确行号**。没有行号的输出对内核开发者不可信。AI 生成的任何引用都必须能回溯到具体代码位置。

**要求**：
- 每个索引 chunk 必须记录起始行号和结束行号
- 查询返回结果必须附带 `file:line` 格式
- 行号在返回前需现场验证（读取本地文件校验）

---

## 2. 指针式索引（Pointer-Based Indexing）

索引数据库**不存储代码原文**，只存储：
- 向量（Embedding）
- 元数据（文件、行号、符号名、类型、Kconfig 条件）
- 调用关系图谱

代码片段在查询时**现场读取**用户本地源码。

**收益**：
- 索引体积可控（~2GB/版本，而非 5~7GB）
- 本地 patch 与索引轻微错位时仍可用
- 保持架构清晰，即使全 GPL 项目也避免数据层冗余

---

## 3. 内核原生感知（Kernel-Native Awareness）

通用代码 RAG 忽略的内核特性，是本项目的核心差异化：

| 特性 | 处理方式 |
|------|----------|
| **Kconfig 条件编译** | 提取 `#ifdef CONFIG_XXX` 分支，作为独立 chunk 并标注依赖条件 |
| **头文件级联依赖** | 构建 `.c ↔ .h ↔ include/linux/` 类型依赖图谱 |
| **宏展开** | 对 `container_of`、`list_for_each_entry` 等高频宏做预展开标注 |
| **调用链追踪** | 基于 `cscope`/`clang` 提取精确调用关系，支持深度级联 |
| **版本化** | 索引与 Git commit 严格绑定，支持多版本并存 |

---

## 4. Kconfig 依赖精确建模（Kconfig-Aware）

Kconfig 不是简单的键值对，而是包含 `depends on`、`select`、`imply`、`choice`、`if` 等复杂语义的配置语言。本项目**不自行手写 Kconfig 解析器**，而是复用成熟工具链分层处理：

| 层级 | 工具 | 作用 |
|------|------|------|
| **解析层** | **kconfiglib** | Python 原生解析 Kconfig 语法，提取符号属性（类型、默认值、依赖、help text）、生成菜单树结构 |
| **形式化层** | **kclause 系列**（kextract → kclause → Z3） | 将 Kconfig 编译为命题逻辑公式（DIMACS/Z3），精确求解配置组合的可满足性 |
| **验证层** | **Kismet** + **KconfigDetector** | 检测 unmet dependency bugs、反向依赖风险、配置值错误 |
| **关联层** | **kmax** | 分析 Kbuild Makefile，建立 `obj-$(CONFIG_X)` 与源文件的精确编译映射 |

**收益**：RAG 索引中的每个代码 chunk 都附带精确的 Kconfig 条件向量；查询时可用 Z3 验证 "CONFIG_SMP=y ∧ CONFIG_NUMA=n" 是否合法，并召回对应条件分支。

---

## 5. Git 历史原生索引、Patch 类型识别与变更因果图谱（Git-Native & Causal Graph）

本地 Git 仓库是内核知识库的**唯一真相源**（Single Source of Truth）。所有索引（代码、Git 历史、Kconfig）都从本地 Git 仓库**派生**，而非外部导入。

### 5.1 Git 数据的三层价值

| 层级 | 内容 | RAG 价值 |
|------|------|----------|
| **Commit Message** | `git log` 的标题 + 正文 | 理解**设计意图**和**变更原因**（Maintainer 的原话） |
| **Diff Patch** | `git show` 的代码增删 | 理解**具体改了哪几行**、**影响哪些函数** |
| **Blame 元数据** | `git blame` 的行级归属 | 精确回答"这行代码是谁、在哪个版本、因为什么引入的" |

### 5.2 Patch 类型识别

从 commit message 中自动提取 patch 类型标签，支持**非正交多维分类**：

| 类型维度 | 识别来源 | 示例 |
|----------|----------|------|
| **bugfix** | `Fixes:` 标签、标题含 "fix"/"bug"/"repair" | `tcp: fix inaccurate RTO` |
| **performance** | 标题含 "optim"/"speedup"/"fast"/"latency" | `sched: optimize vruntime update` |
| **refactor** | 标题含 "refactor"/"cleanup"/"simplify"/"remove" | `mm: refactor slab allocation path` |
| **feature** | 标题含 "add"/"support"/"implement"/"new" | `net: add MPTCP v1 support` |
| **revert** | 标题含 "Revert" | `Revert "tcp: change RTO"` |
| **regression** | 标题含 "regression" 或 `Fixes:` 指向近期 commit | `fix regression in scheduler load balance` |
| **documentation** | 标题含 "doc"/"comment"/"Docs:" | `doc: update scheduler documentation` |
| **test** | 标题含 "selftest"/"test"/"kselftest" | `selftest: add TCP fastopen test` |
| **security** | `CVE-` 引用、`Reported-by: security@` | `fix use-after-free in mm (CVE-2023-XXXX)` |

**非正交设计**：一个 patch 可同时拥有多个类型标签。例如修复性能回归的 patch 同时标记为 `["bugfix", "performance", "regression"]`。

### 5.3 变更因果图谱

内核社区有高度规范的 commit message 标签（`Fixes:`、`Link:`、`Reported-by:` 等）。提取这些标签可构建**变更因果链**，回答通用大模型完全无法触及的问题：
- "这个 bug 是哪个 commit 引入的？"
- "修复它的补丁后来又被 revert 过吗？"
- "这个修复有没有 backport 到 stable 分支？"

---

## 6. 本地优先（Local-First）

- 索引在用户本地生成，源码不离开用户机器
- 支持纯 CPU 运行（GPU 加速可选）
- 增量更新无需联网

---

## 7. MCP 原生（MCP-Native）

- 项目首要接口是 **MCP Server**，而非 Web UI 或 CLI
- 人类接口（CLI/Web）是次要补充
- 设计目标是让 AI 编程工具能够**无感调用**内核代码库

---

## 8. 与现有工具的关系：互补而非替代

| 工具 | 本项目中的角色 |
|------|---------------|
| `ctags` | 提供初始符号表，用于构建稀疏索引（BM25）和符号验证 |
| `cscope` | 提供调用关系数据库（`cscope.out`），作为调用链图谱的基础数据源 |
| `clang`/`clangd` | 提供精确的 AST 和类型依赖（替代 cscope 的文本级分析） |
| `tree-sitter` | 提供函数级、结构体级的精确切分边界（替代正则切分） |
| `grep` / `ripgrep` | 作为 MCP 暴露的底层工具，供 AI 在需要文本模式匹配时调用 |

> **哲学**：`ctags` 告诉你"东西在哪一行"，`cscope` 告诉你"谁调用了谁"，Sourcegraph 告诉你"这个符号在全仓库的引用"，Git log 告诉你"为什么改成这样"，而 Kernel-RAG-MCP 告诉 AI"用户问了一个关于调度器的问题，该把哪几段代码、哪几个 commit、哪条 bugfix 链、哪些性能补丁塞进上下文窗口"。

---

## 9. 推荐的用户工作流

```plain
日常开发/Review
├── 精确跳转（我知道函数名）        → ctags / cscope / LSP
├── 全文搜索（我有关键词）          → grep / ripgrep
├── 跨仓库引用（我看代码历史）      → Sourcegraph / GitHub Code Search
├── 语义理解/自然语言提问           → Kernel-RAG-MCP（本工具）
│   └── AI 自动查询 → 召回代码片段 → 人工用 ctags 精读确认
├── 问"为什么这样设计"              → Kernel-RAG-MCP Git 历史层
│   └── 召回 commit message + diff → 人工用 git show 验证
├── 问"这个 bug 是谁引入的"          → Kernel-RAG-MCP 变更因果图谱
│   └── 追踪 Fixes: / Introduced-by: 链 → 人工用 git log --oneline 验证
├── 问"最近有哪些性能优化"            → Kernel-RAG-MCP Patch 类型筛选
│   └── 召回 performance 标签 commits → 人工用 git show 验证
└── 写代码时 AI 辅助                → Claude Code / Cursor（通过 MCP 自动调用本工具）
```

---

## 10. 设计哲学

> 内核是计算机系统最精密的工程 artifact 之一。我们不做"又一个通用代码搜索"，而是为这门手艺打造专用的语义工具。与 `ctags`、`cscope` 和 `git log` 并肩工作，而非取代它们。
