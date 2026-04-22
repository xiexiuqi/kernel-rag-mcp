# Kernel-RAG-MCP 设计目标

> 为 Linux 内核开发者构建的专用代码智能基础设施  
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 项目定位

**Kernel-RAG-MCP** 是一个面向 **Linux 内核**代码库的专用 RAG（Retrieval-Augmented Generation）工具链。它不是通用代码搜索的替代品，而是内核开发工作流的**语义增强层**。

**核心命题**：让 AI 编程工具（Claude Code、Cursor、OpenCode 等）能够精确理解、引用和推理 Linux 内核源码，解决"上下文窗口装不下整个内核"的根本矛盾。

---

## 2. 目标用户

| 用户群体                   | 核心痛点                                                    | 使用场景                             |
| -------------------------- | ----------------------------------------------------------- | ------------------------------------ |
| **内核新人/学生**          | 宏展开、条件编译、跨文件引用构成的理解壁垒                  | 自然语言查询机制，定位到精确行号学习 |
| **跨子系统开发者**         | 写驱动时需要理解 `mm/` 或 `block/` 的接口契约               | 语义检索调用链与错误处理模式         |
| **代码审查者（Reviewer）** | 确认补丁跨模块影响范围，检查模式一致性                      | 调用图谱分析 + 历史变更追踪          |
| **安全研究员**             | 追踪敏感函数（`copy_from_user`、`kmalloc`）的调用与检查模式 | 跨函数语义模式匹配                   |
| **企业/发行版维护者**      | 审查大量下游补丁，比对 upstream 实现差异                    | 版本化索引 + 差异分析                |
| **回归分析工程师**         | 追踪 bug 引入源头、修复链路和 backport 状态                 | 变更因果图谱查询                     |
| **性能分析工程师**         | 追踪特定子系统的性能优化历史                                | Patch 类型筛选 + 性能变更溯源        |
| **AI 辅助编程工具**        | 缺乏内核领域的精确上下文注入能力                            | 通过 MCP 协议实时查询代码库          |

**非目标用户**：
- 子系统核心 Maintainer（他们依赖邮件列表和大脑索引，不需要 RAG）
- 纯应用层开发者（不接触内核代码）

---

## 3. 核心设计原则

### 3.1 精确溯源优先（Line-Number-First）
所有检索结果必须包含 **文件路径 + 精确行号**。没有行号的输出对内核开发者不可信。AI 生成的任何引用都必须能回溯到具体代码位置。

### 3.2 指针式索引（Pointer-Based Indexing）
索引数据库**不存储代码原文**，只存储：
- 向量（Embedding）
- 元数据（文件、行号、符号名、类型、Kconfig 条件）
- 调用关系图谱

代码片段在查询时**现场读取**用户本地源码。这保证：
- 索引体积可控（~2GB/版本，而非 5~7GB）
- 本地 patch 与索引轻微错位时仍可用
- 保持架构清晰，即使全 GPL 项目也避免数据层冗余

### 3.3 内核原生感知（Kernel-Native Awareness）
通用代码 RAG 忽略的内核特性，是本项目的核心差异化：

| 特性                 | 处理方式                                                     |
| -------------------- | ------------------------------------------------------------ |
| **Kconfig 条件编译** | 提取 `#ifdef CONFIG_XXX` 分支，作为独立 chunk 并标注依赖条件 |
| **头文件级联依赖**   | 构建 `.c ↔ .h ↔ include/linux/` 类型依赖图谱                 |
| **宏展开**           | 对 `container_of`、`list_for_each_entry` 等高频宏做预展开标注 |
| **调用链追踪**       | 基于 `cscope`/`clang` 提取精确调用关系，支持深度级联         |
| **版本化**           | 索引与 Git commit 严格绑定，支持多版本并存                   |

### 3.4 Kconfig 依赖精确建模（Kconfig-Aware）
Kconfig 不是简单的键值对，而是包含 `depends on`、`select`、`imply`、`choice`、`if` 等复杂语义的配置语言。本项目**不自行手写 Kconfig 解析器**，而是复用成熟工具链分层处理：

| 层级         | 工具                                        | 作用                                                         |
| ------------ | ------------------------------------------- | ------------------------------------------------------------ |
| **解析层**   | **kconfiglib**                              | Python 原生解析 Kconfig 语法，提取符号属性（类型、默认值、依赖、help text）、生成菜单树结构 |
| **形式化层** | **kclause 系列**（kextract → kclause → Z3） | 将 Kconfig 编译为命题逻辑公式（DIMACS/Z3），精确求解配置组合的可满足性 |
| **验证层**   | **Kismet** + **KconfigDetector**            | 检测 unmet dependency bugs、反向依赖风险、配置值错误         |
| **关联层**   | **kmax**                                    | 分析 Kbuild Makefile，建立 `obj-$(CONFIG_X)` 与源文件的精确编译映射 |

**收益**：RAG 索引中的每个代码 chunk 都附带精确的 Kconfig 条件向量；查询时可用 Z3 验证 "CONFIG_SMP=y ∧ CONFIG_NUMA=n" 是否合法，并召回对应条件分支。

### 3.5 Git 历史原生索引、Patch 类型识别与变更因果图谱（Git-Native & Causal Graph）
本地 Git 仓库是内核知识库的**唯一真相源**（Single Source of Truth）。所有索引（代码、Git 历史、Kconfig）都从本地 Git 仓库**派生**，而非外部导入。

Git 数据作为 RAG 的三层价值：

| 层级               | 内容                    | RAG 价值                                            |
| ------------------ | ----------------------- | --------------------------------------------------- |
| **Commit Message** | `git log` 的标题 + 正文 | 理解**设计意图**和**变更原因**（Maintainer 的原话） |
| **Diff Patch**     | `git show` 的代码增删   | 理解**具体改了哪几行**、**影响哪些函数**            |
| **Blame 元数据**   | `git blame` 的行级归属  | 精确回答"这行代码是谁、在哪个版本、因为什么引入的"  |

**Patch 类型识别**：从 commit message 中自动提取 patch 类型标签，支持**非正交多维分类**：

| 类型维度          | 识别来源                                        | 示例                                       |
| ----------------- | ----------------------------------------------- | ------------------------------------------ |
| **bugfix**        | `Fixes:` 标签、标题含 "fix"/"bug"/"repair"      | `tcp: fix inaccurate RTO`                  |
| **performance**   | 标题含 "optim"/"speedup"/"fast"/"latency"       | `sched: optimize vruntime update`          |
| **refactor**      | 标题含 "refactor"/"cleanup"/"simplify"/"remove" | `mm: refactor slab allocation path`        |
| **feature**       | 标题含 "add"/"support"/"implement"/"new"        | `net: add MPTCP v1 support`                |
| **revert**        | 标题含 "Revert"                                 | `Revert "tcp: change RTO"`                 |
| **regression**    | 标题含 "regression" 或 `Fixes:` 指向近期 commit | `fix regression in scheduler load balance` |
| **documentation** | 标题含 "doc"/"comment"/"Docs:"                  | `doc: update scheduler documentation`      |
| **test**          | 标题含 "selftest"/"test"/"kselftest"            | `selftest: add TCP fastopen test`          |
| **security**      | `CVE-` 引用、`Reported-by: security@`           | `fix use-after-free in mm (CVE-2023-XXXX)` |

**非正交设计**：一个 patch 可同时拥有多个类型标签。例如修复性能回归的 patch 同时标记为 `["bugfix", "performance", "regression"]`。这保证用户查询"6.12 到 6.13 之间的性能改动"时，既能召回纯优化 patch，也能召回修复性能回归的 bugfix。

**变更因果图谱**：内核社区有高度规范的 commit message 标签（`Fixes:`、`Link:`、`Reported-by:` 等）。提取这些标签可构建**变更因果链**，回答通用大模型完全无法触及的问题：
- "这个 bug 是哪个 commit 引入的？"
- "修复它的补丁后来又被 revert 过吗？"
- "这个修复有没有 backport 到 stable 分支？"

### 3.6 本地优先（Local-First）
- 索引在用户本地生成，源码不离开用户机器
- 支持纯 CPU 运行（GPU 加速可选）
- 增量更新无需联网

### 3.7 MCP 原生（MCP-Native）
项目首要接口是 **MCP Server**，而非 Web UI 或 CLI。人类接口（CLI/Web）是次要补充。设计目标是让 AI 编程工具能够**无感调用**内核代码库。

---

## 4. 与现有工具的关系：互补而非替代

### 4.1 能力矩阵对比

| 维度               | `ctags`            | `cscope`             | `grep`           | Semantic Code Search (Sourcegraph/GitHub) | **Kernel-RAG-MCP**                              |
| ------------------ | ------------------ | -------------------- | ---------------- | ----------------------------------------- | ----------------------------------------------- |
| **输入**           | 源代码             | 源代码               | 源代码           | 源代码 + 仓库图谱                         | 源代码 + Kconfig + 调用链 + Git 历史 + 变更因果 |
| **查询方式**       | 精确符号名跳转     | 符号、文本、调用关系 | 正则表达式       | 符号引用、文件路径、类型查询              | **自然语言意图** + 语义相似度                   |
| **理解深度**       | 语法级（定义位置） | 文本级 + 调用关系    | 文本级           | AST/引用图谱级                            | **语义级 + 内核领域知识 + 变更历史 + 因果链**   |
| **条件编译**       | ❌ 无感知           | ❌ 无感知             | ❌ 无感知         | ❌ 无感知                                  | ✅ **Kconfig 分支感知**                          |
| **宏展开**         | ❌ 无               | ❌ 无                 | ❌ 无             | ⚠️ 有限                                    | ✅ **高频宏预标注**                              |
| **跨文件组装**     | ❌ 手动跳转         | ⚠️ 逐层跳转           | ❌ 手动           | ⚠️ 引用列表                                | ✅ **自动组装上下文**                            |
| **AI 自动调用**    | ❌ 无               | ❌ 无                 | ❌ 无             | ⚠️ API/插件需人工触发                      | ✅ **MCP 原生协议**                              |
| **Git 历史溯源**   | ❌ 无               | ❌ 无                 | ❌ 无             | ⚠️ 有限                                    | ✅ **Commit/Blame/Diff 级精确召回**              |
| **Patch 类型筛选** | ❌ 无               | ❌ 无                 | ❌ 无             | ❌ 无                                      | ✅ **性能/bugfix/重构/特性多维筛选**             |
| **Bug 因果链**     | ❌ 无               | ❌ 无                 | ❌ 无             | ❌ 无                                      | ✅ **Fixes/Introduced-by/Regression 图谱**       |
| **确定性**         | 100% 精确          | 100% 精确            | 100% 精确        | 高                                        | ⚠️ **概率性**（召回率/精确率权衡）               |
| **延迟**           | 毫秒级             | 毫秒级               | 秒级（全量搜索） | 百毫秒级                                  | 百毫秒~秒级                                     |

### 4.2 定位差异

**`ctags` / `cscope`：精确导航仪**
- **哲学**："你告诉我要去哪，我画最短路径"
- **优势**：零幻觉、毫秒级、符号级精确跳转、调用关系确定
- **边界**：你必须**知道函数名**才能查；无法理解"vruntime 更新机制"这种意图；无法区分 `CONFIG_SMP` 下的不同实现；跨文件理解需要人脑手动拼装

**`grep`：文本挖掘机**
- **哲学**："你告诉我关键词，我全文扫描"
- **优势**：简单、万能、无需索引
- **边界**：无法理解语义（搜 `schedule` 会漏掉 `__schedule` 或 `pick_next_task`）；条件编译分支混杂；结果噪音极大

**Semantic Code Search（Sourcegraph/GitHub）：代码浏览器增强**
- **哲学**："基于 AST 和引用关系的结构化导航"
- **优势**：跨仓库跳转、精确的"查找所有引用"、类型定义追踪
- **边界**：仍然是**符号驱动**的查询（你需要知道符号名）；对自然语言意图理解有限；对内核 Kconfig 条件编译无特殊处理；不主动为 AI 组装上下文

**Kernel-RAG-MCP：语义外接大脑**
- **哲学**："你描述问题，我推测该看什么代码"
- **优势**：
  - 自然语言查询（"CFS 怎么更新 vruntime" → 召回 `update_curr()`）
  - 自动跨文件上下文组装（函数实现 + 头文件声明 + 结构体定义 + Kconfig 条件）
  - Git 历史精确溯源（"这行代码谁引入的" → 精确到 commit hash 和作者）
  - **Patch 类型多维筛选**（"6.12 到 6.13 之间 sched 子系统的性能改动" → 精确召回）
  - **变更因果图谱**（"这个 bug 是哪个 commit 引入的" → 追踪 Fixes: 和 Introduced-by: 链）
  - AI 编程工具**自动触发**（Claude Code 自己判断何时查询内核代码库）
  - 内核原生感知（条件编译分支隔离、宏展开标注）
- **边界**：概率性检索，可能漏招或误招；无法替代精确符号跳转

### 4.3 集成策略：复用而非重复造轮子

本项目**不重新实现** `ctags` 或 `cscope` 的解析能力，而是**将其作为输入层和工具层**：

| 现有工具               | 在本项目中的角色                                             |
| ---------------------- | ------------------------------------------------------------ |
| **`ctags`**            | 提供初始符号表（函数名、结构体名、宏名），用于构建稀疏索引（BM25）和符号验证 |
| **`cscope`**           | 提供调用关系数据库（`cscope -b` 生成的 `cscope.out`），作为调用链图谱的**基础数据源** |
| **`clang`/`clangd`**   | 提供精确的 AST 和类型依赖（替代 cscope 的文本级分析，用于复杂宏和类型推导） |
| **`tree-sitter`**      | 提供函数级、结构体级的精确切分边界（替代正则切分，保证 chunk 语义完整） |
| **`grep` / `ripgrep`** | 作为 MCP 暴露的底层工具，供 AI 在需要文本模式匹配时调用      |

### 4.4 MCP 包装传统工具：让 AI 也能调用 ctags/cscope/grep

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

### 4.5 推荐的用户工作流

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

### 4.6 一句话总结

> **`ctags` 告诉你"东西在哪一行"，`cscope` 告诉你"谁调用了谁"，Sourcegraph 告诉你"这个符号在全仓库的引用"，Git log 告诉你"为什么改成这样"，而 Kernel-RAG-MCP 告诉 AI"用户问了一个关于调度器的问题，该把哪几段代码、哪几个 commit、哪条 bugfix 链、哪些性能补丁塞进上下文窗口"。**

------

## 5. 功能目标

### 5.1 索引层（Indexer）

- [ ] **多版本支持**：支持对任意 Git tag/commit 建立索引（`v5.15`、`v6.6.y`、`v6.12` 等）
- [ ] **子系统级索引**：允许单独索引 `kernel/sched/`、`mm/`、`net/` 等子系统，降低资源门槛
- [ ] **增量更新**：基于 Git diff 的增量索引，级联深度可控（Depth 0/1/2/Full）
- [ ] **混合切分策略**：
  - 函数/结构体/宏定义级（AST 精确切分）
  - 文件级摘要（模块说明）
  - Kconfig/Makefile 元数据（编译条件）
- [ ] **多架构 Embedding**：支持 `jina-embeddings-v2-base-code`、`BAAI/bge-m3` 等代码专用模型，支持本地 CPU/GPU 推理

#### 5.1.1 Kconfig 解析与建模（专用子模块）

**解析层（kconfiglib）**：

- [ ] 读取内核顶层 `Kconfig` 及所有子目录 `Kconfig` 文件
- [ ] 提取每个 `config` 符号的属性：类型（bool/tristate/string/hex/int）、默认值、`depends on`、`select`、`imply`、`help text`
- [ ] 生成菜单树结构，理解 `menu`、`choice`、`if` 的层级关系
- [ ] 读取 `.config` 文件，建立符号-值映射

**形式化层（kclause 系列）**：

- [ ] 调用 `kextract` 对内核 Kconfig 做去糖化（desugaring）
- [ ] 调用 `kclause` 生成 Z3 / DIMACS 逻辑公式
- [ ] 对每个代码 chunk 的 Kconfig 条件，计算其**可满足性**和**依赖闭包**

**验证层（KconfigDetector + Kismet）**：

- [ ] 导入 KconfigDetector 的 JSON 输出，标注高风险配置项（依赖未满足、反向依赖风险）
- [ ] 导入 Kismet 的 bug 模式库，在 RAG 中提示 "unmet dependency" 风险

**关联层（kmax）**：

- [ ] 分析 Kbuild Makefile 的 `obj-$(CONFIG_X)`、`ccflags-y` 等规则
- [ ] 建立 "配置项 ↔ 源文件集合" 的精确映射

#### 5.1.2 Git 历史索引（Git History Indexer）

内核代码的**变更历史**与**代码本身**同等重要。Maintainer 的 commit message 包含设计决策、bug 修复原因、性能优化动机等无法从静态代码中推断的信息。

**索引内容**：

| 数据类型            | 来源                            | 用途                                   |
| :------------------ | :------------------------------ | :------------------------------------- |
| **Commit 元数据**   | `git log --format`              | 作者、日期、标题、正文、变更文件列表   |
| **Diff 摘要**       | `git show --stat` + diff parser | 修改的函数名、增删行数、变更模式       |
| **Diff 代码上下文** | `git show` + 上下文提取         | 变更前后的代码片段，用于语义 embedding |
| **Blame 行级映射**  | `git blame -L`（当前 HEAD）     | 精确回答"这行代码是谁引入的"           |

**Chunking 策略**：

- **Commit 卡片**：每个 commit 为一个 chunk，包含标题、正文、变更文件、变更函数列表
- **Diff 上下文块**：每个 commit 中每个被修改的函数为一个 chunk，包含 diff + 前后 5 行代码
- **Blame 行**（可选）：当前 HEAD 的每行代码指向的引入 commit（按需索引，避免爆炸）

**与代码 RAG 的协同**：

- 查询代码实现时，**并行召回**当前代码 + 修改过该代码的近期 commits
- 回答版本差异问题时，**串联召回**两个版本的代码快照 + 中间的 commit diff 序列
- 回答"为什么这样设计"时，**优先召回**该代码区域的原始引入 commit 的 message

**查询能力**：

- `git_search_commits(query, since, until, author, file_pattern)`：语义搜索 commit history
- `git_blame_line(file, line)`：行级代码溯源
- `git_diff_summary(symbol, v1, v2)`：两个版本间某符号的变更摘要
- `git_changelog(subsys, since_tag, until_tag)`：生成子系统的变更日志

**技术要点**：

- Diff 向量化时提取 **"变更后代码 + commit message"** 联合 embedding，避免 `+/-` 符号干扰
- 版本范围过滤使用 Git tag → commit hash 映射表，结合 Qdrant payload 过滤
- 全量 blame 索引规模过大，仅索引当前 HEAD；历史 blame 按需实时查询

#### 5.1.3 Patch 类型识别与多维筛选（Patch Type Classification）

从 commit message 中**自动提取 Patch 类型标签**，支持**非正交多维分类**（一个 patch 可同时属于多个类型）：

**识别规则**：

| 类型标签        | 触发规则（标题/正文/标签）                                   | 示例                                       |
| :-------------- | :----------------------------------------------------------- | :----------------------------------------- |
| `bugfix`        | 含 `Fixes:` 标签、标题含 "fix"/"bug"/"repair"/"correct"      | `tcp: fix inaccurate RTO`                  |
| `performance`   | 标题含 "optim"/"speedup"/"fast"/"latency"/"throughput"/"scale" | `sched: optimize vruntime update`          |
| `refactor`      | 标题含 "refactor"/"cleanup"/"simplify"/"remove"/"rework"     | `mm: refactor slab allocation path`        |
| `feature`       | 标题含 "add"/"support"/"implement"/"introduce"/"new"         | `net: add MPTCP v1 support`                |
| `revert`        | 标题以 "Revert" 开头                                         | `Revert "tcp: change RTO"`                 |
| `regression`    | 标题含 "regression"、或 `Fixes:` 指向 ≤30 天内的 commit      | `fix regression in scheduler load balance` |
| `documentation` | 标题含 "doc"/"comment"/"Docs:"                               | `doc: update scheduler documentation`      |
| `test`          | 标题含 "selftest"/"test"/"kselftest"                         | `selftest: add TCP fastopen test`          |
| `security`      | 含 `CVE-` 引用、`Reported-by: security@`、`Fixes:` 指向安全修复 | `fix use-after-free in mm (CVE-2023-XXXX)` |
| `stable`        | 含 `Cc: stable@`、`stable:`、`[PATCH stable]`                | `stable: fix race in tcp`                  |

**非正交设计原则**：

- 一个 patch 可以同时拥有多个标签。例如修复性能回归的 patch：`["bugfix", "performance", "regression"]`
- 重构同时修复 bug：`["refactor", "bugfix"]`
- 新特性包含性能优化：`["feature", "performance"]`

**索引注入**：

```json
{
  "type": "commit",
  "hash": "e33f3b9...",
  "title": "sched: optimize vruntime update for large CPU counts",
  "type_tags": ["performance", "scalability"],
  "confidence": {"performance": 0.95, "scalability": 0.88}
}
```

**查询能力**：

| MCP Tool                                                | 功能                        | 触发场景                                   |
| :------------------------------------------------------ | :-------------------------- | :----------------------------------------- |
| `git_search_by_type(type_tags[], subsys, since, until)` | 按类型标签筛选 commits      | "6.12 到 6.13 之间 sched 子系统的性能改动" |
| `git_type_stats(subsys, since, until)`                  | 统计某时期各类型 patch 分布 | "过去半年 mm 子系统有多少 bugfix 和重构"   |
| `git_find_performance_regression_fix(subsys, since)`    | 查找性能回归修复            | "最近修复了哪些性能回归问题"               |

**典型查询示例**：

> **用户问**："v6.12 到 v6.13 之间，调度器子系统有哪些性能相关的改动？包括优化和性能回归修复。"

**RAG 行为**：

1. 范围过滤：`since=v6.12`, `until=v6.13`
2. 子系统过滤：`files_changed` 匹配 `kernel/sched/`
3. 类型过滤：`type_tags` 包含 `performance`（同时召回纯优化和 `["bugfix", "performance", "regression"]`）
4. 按日期排序返回，附带 diff 摘要和变更函数

#### 5.1.4 变更因果图谱（Change Causal Graph）

内核 commit message 遵循严格的社区规范，包含大量**机器可解析的元数据标签**。提取这些标签可构建**变更因果图谱**（Change Causal Graph），这是通用大模型完全无法触及的深度知识。

**提取的标签类型**：

| 标签                   | 示例                              | 语义                                | 图谱边类型                 |
| :--------------------- | :-------------------------------- | :---------------------------------- | :------------------------- |
| **Fixes:**             | `Fixes: a1b2c3d ("tcp: fix RTO")` | 本 commit 修复了 a1b2c3d 引入的问题 | `FIXES →` (修复指向问题源) |
| **Link:**              | `Link: https://bugzilla...`       | 关联到外部 bug report               | `REPORTS →`                |
| **Reported-by:**       | `Reported-by: John Doe`           | 问题报告者                          | `REPORTED_BY →`            |
| **Bisected-by:**       | `Bisected-by: Jane Smith`         | 定位出问题提交的人                  | `BISECTED_BY →`            |
| **Introduced-by:**     | `Introduced-by: e4f5g6h`          | 明确指出问题由哪个提交引入          | `INTRODUCED_BY →`          |
| **Cc: stable@...**     | `Cc: stable@vger.kernel.org`      | 需要 backport 到 stable 树          | `BACKPORT_TO →`            |
| **Reviewed-by:**       | `Reviewed-by: Alice`              | 代码审查者                          | `REVIEWED_BY →`            |
| **Tested-by:**         | `Tested-by: Bob`                  | 测试者                              | `TESTED_BY →`              |
| **Acked-by:**          | `Acked-by: Maintainer`            | 子系统维护者认可                    | `ACKED_BY →`               |
| **Suggested-by:**      | `Suggested-by: Expert`            | 方案建议者                          | `SUGGESTED_BY →`           |
| **Co-developed-by:**   | `Co-developed-by: Partner`        | 共同开发者                          | `CO_DEV_WITH →`            |
| **Regression:**        | 标题含 "regression"               | 标记回归问题                        | `IS_REGRESSION`            |
| **Revert**             | `Revert "xxx"`                    | 回滚某个提交                        | `REVERTS →`                |
| **cherry-picked from** | `(cherry picked from commit ...)` | stable 树 backport                  | `CHERRY_PICK_FROM →`       |

**图谱构建策略**：

```python
# 每个 commit 作为图谱节点
commit_node = {
    "hash": "e33f3b9...",
    "title": "tcp: fix inaccurate RTO for SACK retransmissions",
    "author": "Eric Dumazet",
    "date": "2023-04-12",
    "tags": ["bugfix", "tcp", "rto"],
    "type_tags": ["bugfix"],
    "labels": {
        "Fixes": "a1b2c3d...",           # 指向问题引入源
        "Link": "https://bugzilla...",
        "Reported-by": ["John Doe"],
        "Bisected-by": ["Jane Smith"],
        "Cc-stable": ["5.15+", "6.1+"],
        "Reviewed-by": ["David Miller"],
        "Tested-by": ["KernelCI"]
    }
}

# 边构建
edges = [
    ("e33f3b9...", "FIXES", "a1b2c3d..."),      # 修复关系
    ("e33f3b9...", "REPORTED_BY", "John Doe"),    # 报告关系
    ("e33f3b9...", "REVIEWED_BY", "David Miller"), # 审查关系
    ("stable-5.15", "CHERRY_PICK_FROM", "e33f3b9..."), # backport 关系
]
```

**查询能力**：

| MCP Tool                                   | 功能                 | 触发场景                                      |
| :----------------------------------------- | :------------------- | :-------------------------------------------- |
| `git_causal_chain(commit_hash, direction)` | 查询变更因果链       | "这个 bug 的完整修复链是什么"                 |
| `git_bug_origin(commit_hash)`              | 追踪问题引入源头     | "这个 regression 是哪个 commit 引入的"        |
| `git_backport_status(commit_hash)`         | 查询 backport 状态   | "这个修复有没有进 stable 分支"                |
| `git_reviewer_expertise(reviewer)`         | 查询审查者的专业领域 | "David Miller 审查过哪些网络子系统的补丁"     |
| `git_regression_chain(subsys, since)`      | 查询某子系统的回归链 | "最近一年 mm 子系统有哪些 regression"         |
| `git_patch_series(commit_hash)`            | 查询补丁系列关系     | "这个 commit 属于哪个系列，前后 patch 是什么" |

**典型查询示例**：

> **用户问**："TCP RTO 的那个 SACK bug，最初是哪个 commit 引入的？后来怎么修复的？有没有 backport？"

**RAG 行为**：

1. 语义搜索召回标题含 "SACK RTO" 的 commit → 找到修复 commit `e33f3b9`
2. 读取 `e33f3b9` 的 `Fixes:` 标签 → 指向问题源 `a1b2c3d`
3. 读取 `a1b2c3d` 的元数据 → 确认它是问题引入者
4. 读取 `e33f3b9` 的 `Cc: stable@...` → 确认 backport 到 5.15+、6.1+
5. 读取 `e33f3b9` 的 `Reported-by:` / `Bisected-by:` → 还原问题发现过程
6. 组装完整因果链返回

**输出**：

```markdown
问题引入：commit `a1b2c3d` ("tcp: optimize SACK processing") by Eric Dumazet, 2023-01-15
  ↓ 引入问题：SACK 重传时 RTO 计算不准确
  ↓ 被发现：Reported-by John Doe, Bisected-by Jane Smith (Link: bugzilla#12345)
修复提交：commit `e33f3b9` ("tcp: fix inaccurate RTO...") by Eric Dumazet, 2023-04-12
  ↓ Reviewed-by: David Miller, Tested-by: KernelCI
  ↓ Backport: Cc: stable@vger.kernel.org [5.15+, 6.1+]
  ↓ Cherry-picked to: v6.1.25, v5.15.112
```

**与代码 RAG 的协同**：

- 审查 patch 时，自动查询该 patch 的 `Fixes:` 链，确认是否完整修复了问题根因
- 分析回归时，追踪 `Introduced-by:` → `Fixes:` → `Revert` 的完整生命周期
- 评估 backport 需求时，查询 `Cc: stable` 和 cherry-pick 关系

### 5.2 检索层（Retriever）

- [ ] **混合召回**：Dense（向量）+ Sparse（BM25 符号名）+ Reciprocal Rank Fusion
- [ ] **Kconfig 过滤**：查询时可指定 `CONFIG_SMP=y/n` 过滤条件编译分支
- [ ] **Kconfig 可满足性验证**：用 Z3 验证用户查询的配置组合是否合法（如 `CONFIG_SMP=y ∧ CONFIG_NUMA=n` 是否可满足）
- [ ] **调用链召回**：支持 `get_callers(symbol, depth)` 和 `get_callees(symbol, depth)`
- [ ] **跨文件上下文组装**：自动拉取被召回函数的声明（`.h`）、实现（`.c`）和依赖类型定义
- [ ] **版本差异检索**：对比两个 Git 版本间某函数/符号的变化
- [ ] **Git 历史召回**：语义搜索 commit message 和 diff 上下文，回答变更原因
- [ ] **Patch 类型筛选**：按 `bugfix`/`performance`/`refactor`/`feature` 等标签多维过滤 commits
- [ ] **变更因果召回**：基于 Fixes:/Introduced-by: 等标签的图谱遍历

### 5.3 MCP 接口层

#### 5.3.1 统一查询网关（智能路由）

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
    else:
        # 混合路由：同时召回代码 + Git + Kconfig + 因果链 + 类型，由 LLM 组装
        return hybrid_assemble(query)
```

**AI 自动选择策略**（通过 MCP tool description 提示）：

| 用户问题模式                               | AI 自动选择的路由 | 调用的底层工具                                               |
| :----------------------------------------- | :---------------- | :----------------------------------------------------------- |
| "CFS 怎么更新 vruntime？"                  | 语义搜索          | `code_rag.search()`                                          |
| "schedule() 在哪一行？"                    | 精确符号          | `ctags.jump()`                                               |
| "这个函数在 6.6 到 6.12 之间变了什么？"    | Git 历史          | `git_rag.diff_summary()`                                     |
| "这行代码是谁引入的？"                     | 行级溯源          | `git_rag.blame()`                                            |
| "开启 CONFIG_X 且关闭 CONFIG_Y 能编译吗？" | Kconfig 验证      | `kconfig_solver.check()`                                     |
| "改了这个函数会影响谁？"                   | 影响分析          | `cscope.callers()` + `code_rag.search()`                     |
| "为什么这里要这样设计？"                   | 混合召回          | `code_rag.search()` + `git_rag.commit_message()`             |
| "这个 bug 是哪个 commit 引入的？"          | 变更因果          | `git_causal.bug_origin()`                                    |
| "这个修复有没有 backport？"                | 变更因果          | `git_causal.backport_status()`                               |
| "6.12 到 6.13 之间有哪些性能优化？"        | Patch 类型        | `git_rag.search_by_type(["performance"])`                    |
| "最近修复了哪些性能回归？"                 | Patch 类型        | `git_rag.search_by_type(["bugfix", "performance", "regression"])` |

#### 5.3.2 代码语义层工具

| Tool                                           | 功能             | 触发场景                                 |
| :--------------------------------------------- | :--------------- | :--------------------------------------- |
| `kernel_search(query, subsys, kconfig, top_k)` | 语义搜索内核代码 | 用户询问实现细节、机制原理               |
| `kernel_define(symbol, file_hint)`             | 精确符号定义查询 | 用户提到具体函数/宏/结构体               |
| `kernel_callers(symbol, depth)`                | 调用链追踪       | 影响分析、审查范围确认                   |
| `kernel_diff(symbol, v1, v2)`                  | 版本差异对比     | 问"这个函数在 5.15 和 6.12 之间变了什么" |
| `kernel_cross_ref(symbol)`                     | 跨文件关联       | 找声明、定义、使用点                     |

#### 5.3.3 Git 历史层工具

| Tool                                                         | 功能                          | 触发场景                   |
| :----------------------------------------------------------- | :---------------------------- | :------------------------- |
| `git_search_commits(query, since, until, author, file_pattern)` | 语义搜索 commit history       | 问"谁改了什么"             |
| `git_blame_line(file, line)`                                 | 行级代码溯源                  | "这行代码谁引入的"         |
| `git_diff_summary(symbol, v1, v2)`                           | 两个版本间某符号的变更摘要    | "这个函数变了什么"         |
| `git_changelog(subsys, since_tag, until_tag)`                | 子系统变更日志生成            | "sched 子系统最近改了什么" |
| `git_commit_context(commit_hash)`                            | 获取某 commit 的完整上下文    | 审查具体 patch             |
| `git_show_patch(commit_hash, file)`                          | 获取某 commit 在某文件的 diff | 看具体修改                 |

#### 5.3.4 Patch 类型筛选工具

| Tool                                                    | 功能                   | 触发场景                          |
| :------------------------------------------------------ | :--------------------- | :-------------------------------- |
| `git_search_by_type(type_tags[], subsys, since, until)` | 按类型标签筛选 commits | "某版本范围内某子系统的性能改动"  |
| `git_type_stats(subsys, since, until)`                  | 统计各类型 patch 分布  | "过去半年 mm 子系统有多少 bugfix" |
| `git_find_performance_regression_fix(subsys, since)`    | 查找性能回归修复       | "最近修复了哪些性能回归"          |

#### 5.3.5 变更因果图谱工具

| Tool                                              | 功能                        | 触发场景                               |
| :------------------------------------------------ | :-------------------------- | :------------------------------------- |
| `git_causal_chain(commit_hash, direction="both")` | 查询变更因果链（上游/下游） | "这个 bug 的完整修复链是什么"          |
| `git_bug_origin(commit_hash)`                     | 追踪问题引入源头            | "这个 regression 是哪个 commit 引入的" |
| `git_backport_status(commit_hash)`                | 查询 backport 状态          | "这个修复有没有进 stable 分支"         |
| `git_reviewer_expertise(reviewer, subsys)`        | 查询审查者的专业领域        | "David Miller 审查过哪些网络补丁"      |
| `git_regression_chain(subsys, since)`             | 查询某子系统的回归链        | "最近一年 mm 子系统有哪些 regression"  |
| `git_patch_series(commit_hash)`                   | 查询补丁系列关系            | "这个 commit 属于哪个系列"             |
| `git_fixes_complete(commit_hash)`                 | 验证 Fixes 链完整性         | "这个修复是否完整覆盖了所有引入点"     |

#### 5.3.6 Kconfig 配置层工具

| Tool                            | 功能                            | 触发场景                   |
| :------------------------------ | :------------------------------ | :------------------------- |
| `kconfig_describe(config_name)` | 查询配置项的 help、类型、默认值 | "CONFIG_SMP 是什么"        |
| `kconfig_deps(config_name)`     | 查询直接和间接依赖              | "开启这个需要什么前置条件" |
| `kconfig_check(combo_dict)`     | 验证配置组合的可满足性          | "A=y 且 B=n 是否合法"      |
| `kconfig_impact(config_name)`   | 查询修改某配置影响的源文件      | "关闭这个会少编译哪些文件" |

#### 5.3.7 精确工具层（包装传统命令）



| Tool                            | 底层命令          | 用途           |
| :------------------------------ | :---------------- | :------------- |
| `ctags_jump(symbol)`            | `ctags -x`        | 毫秒级精确跳转 |
| `cscope_callers(symbol, depth)` | `cscope -d -L3`   | 调用关系查询   |
| `grep_code(pattern, path)`      | `ripgrep -n -C 3` | 文本模式匹配   |

### 5.4 人类接口层（次要）

- [ ] **CLI 工具**：`kernel-rag index`、`kernel-rag search`、`kernel-rag serve`
- [ ] **Web 预览**：极简本地页面，用于学习场景下的代码浏览（非必需）

------

## 6. 项目仓库组织与源码配合

### 6.1 项目源码仓库结构（本工具自身的仓库）



```plain
kernel-rag-mcp/                    # 本项目开源仓库
├── pyproject.toml                 # Python 包配置（uv/pip 安装）
├── README.md
├── LICENSE                        # MIT/Apache-2.0
├── Makefile                       # 快捷命令：make install / make test / make index
├── docs/                          # 文档
│   ├── DESIGN.md                  # 本设计文档
│   ├── INSTALL.md                 # 安装指南
│   ├── USAGE.md                   # CLI 与 MCP 使用教程
│   ├── MCP_SETUP.md               # Claude Code / Cursor / OpenCode 配置
│   └── SUBSYSTEM_RULES.md         # 子系统规则编写指南（社区贡献手册）
├── src/
│   └── kernel_rag_mcp/            # 主 Python 包
│       ├── __init__.py
│       ├── cli.py                 # 命令行入口：kernel-rag
│       ├── config.py              # 全局配置管理（索引路径、模型选择、日志级别）
│       ├── server/                # MCP Server 层
│       │   ├── __init__.py
│       │   ├── mcp_server.py      # FastMCP 主服务（stdio / sse）
│       │   ├── router.py          # 意图识别与工具路由引擎
│       │   └── tools/             # MCP 工具实现
│       │       ├── __init__.py
│       │       ├── code_tools.py      # kernel_search / kernel_define / kernel_callers
│       │       ├── git_tools.py       # git_search / git_blame / git_diff / git_changelog
│       │       ├── type_tools.py      # git_search_by_type / git_type_stats
│       │       ├── causal_tools.py    # git_causal_chain / git_bug_origin / git_backport_status
│       │       ├── kconfig_tools.py   # kconfig_describe / kconfig_check / kconfig_impact
│       │       └── legacy_tools.py    # ctags_jump / cscope_callers / grep_code
│       ├── indexer/               # 索引生成器（CLI: kernel-rag index）
│       │   ├── __init__.py
│       │   ├── main.py            # 统一索引调度入口
│       │   ├── code_indexer.py    # 代码语义索引（Tree-sitter + Embedding）
│       │   ├── git_indexer.py     # Git 历史索引（commit / diff / blame）
│       │   ├── type_indexer.py    # Patch 类型识别与标签注入
│       │   ├── causal_indexer.py  # 变更因果图谱索引（Fixes: / Introduced-by: 标签）
│       │   ├── kconfig_indexer.py # Kconfig 索引（kconfiglib + kclause）
│       │   ├── parsers/
│       │   │   ├── __init__.py
│       │   │   ├── tree_sitter_c.py   # C/H 文件 AST 解析
│       │   │   ├── kconfig_parser.py  # 包装 kconfiglib
│       │   │   ├── git_parser.py       # Commit message 标签提取器
│       │   │   ├── type_parser.py      # Patch 类型分类器
│       │   │   └── diff_parser.py      # Diff 函数级切分器
│       │   ├── embedders/
│       │   │   └── code_embedder.py    # jina / bge 封装
│       │   └── graph_builder/
│       │       ├── callgraph.py        # cscope / clang 调用关系
│       │       └── causal_graph.py     # 变更因果图构建器
│       ├── retriever/             # 检索引擎
│       │   ├── __init__.py
│       │   ├── hybrid_search.py       # Dense + Sparse + RRF
│       │   ├── context_assembler.py   # 跨文件上下文组装
│       │   └── causal_traverser.py    # 因果图谱遍历
│       ├── storage/               # 存储抽象层（多后端适配）
│       │   ├── __init__.py
│       │   ├── vector_store.py      # Qdrant / Chroma / Milvus 封装
│       │   ├── sparse_store.py      # Meilisearch / 符号索引封装
│       │   ├── graph_store.py       # 因果图存储（NetworkX / Neo4j / 内存邻接表）
│       │   └── metadata_store.py    # 索引版本元数据（JSON）
│       └── rules/                 # 子系统领域规则（社区共建，热加载）
│           ├── __init__.py
│           ├── sched/
│           │   └── indexing_rules.yaml   # 调度器特殊切分规则
│           ├── mm/
│           │   └── indexing_rules.yaml   # 内存管理特殊规则
│           └── net/
│               └── indexing_rules.yaml   # 网络子系统特殊规则
├── scripts/                       # 运维脚本
│   ├── install-mcp.sh             # 一键安装 MCP 配置到 Claude Code / Cursor
│   ├── nightly-index.sh           # 夜间增量索引 Cron 脚本模板
│   └── verify-index.sh            # 索引一致性校验脚本
├── tests/                         # 测试
│   ├── unit/                      # 单元测试
│   ├── integration/               # 集成测试（含小型内核 fixture）
│   └── fixtures/                  # 测试用微型内核树（~100 文件）
└── .github/
    └── workflows/
        └── ci.yml                 # CI：测试 + 发布预生成索引
```

### 6.2 索引数据库的存放策略：大版本为粒度

**核心原则**：索引数据与源码树**物理隔离**，不侵入内核仓库；以**大版本（如 v6.12）为命名空间**，小版本（6.12.1, 6.12.2）作为**增量补丁**存放；**绝不自动清理**，仅提示用户手动管理。

#### 默认存放路径

```plain
~/.kernel-rag/                     # 全局索引根目录（$XDG_DATA_HOME/kernel-rag）
├── repos.json                       # 注册仓库清单（名称 → 路径映射）
├── repos/                           # 按仓库名隔离
│   └── linux/                       # 仓库名（取自目录名或用户指定）
│       ├── v6.12/                   # 大版本命名空间（基线 + 增量 + 合并）
│       │   ├── base/                # v6.12.0 全量基线索引
│       │   │   ├── qdrant/
│       │   │   ├── meili/
│       │   │   ├── graph.pickle
│       │   │   └── metadata.json    # 记录 commit hash、日期、子系统列表
│       │   ├── delta-v6.12.1/       # 6.12.0 → 6.12.1 的增量索引（仅变更文件）
│       │   ├── delta-v6.12.2/       # 6.12.1 → 6.12.2 的增量索引
│       │   ├── delta-v6.12.3/
│       │   └── merged-v6.12.5/      # 手动合并后的完整索引（可选，用户触发）
│       │       ├── qdrant/          # 合并后的完整向量库
│       │       ├── meili/
│       │       ├── graph.pickle     # 包含合并后因果图谱
│       │       └── metadata.json    # 记录 merged_from: [base, delta-v6.12.1, ...]
│       │
│       ├── v6.13/                   # 另一大版本命名空间
│       │   ├── base/                # v6.13.0 全量基线
│       │   └── delta-v6.13.1/
│       │
│       └── current -> v6.12/base    # 符号链接，指向当前活跃索引（默认基线）
│                                    # 用户可手动切换到 merged-v6.12.5/
```

#### 查询时的索引叠加策略

默认查询走 `current` 指向的索引。如果 `current` 指向 `v6.12/base`，而用户源码已更新到 `v6.12.3`：

**方案 A（默认）：基线查询 + 实时 Git 校验**

- 使用 `v6.12/base` 索引召回候选结果
- 通过 `git diff v6.12.0..HEAD -- <file>` 实时校验该文件是否变更
- 若变更，提示用户"索引基于 6.12.0，当前为 6.12.3，建议应用增量或合并索引"

**方案 B（增量叠加）：基线 + 所有 delta 联合查询**

- 查询时同时搜索 `base` + `delta-v6.12.1` + `delta-v6.12.2` + `delta-v6.12.3`
- 对同一文件的重复 chunk，以最新 delta 为准
- 无需合并即可查询到最新状态，但查询延迟随 delta 数量增加

**方案 C（手动合并）：使用 merged 完整索引**

- 用户运行 `kernel-rag merge v6.12 --target v6.12.5`
- 将 `base` + `delta-6.12.1..5` 合并为一个完整索引 `merged-v6.12.5/`
- 切换 `current` 指向合并后的索引
- 查询性能最佳，无叠加开销

**推荐工作流**：

- 日常开发（源码在 6.12.x）：使用 **方案 B**（基线 + deltas），延迟可接受
- 长期稳定（源码锁定 6.12.5）：运行 `kernel-rag merge` 生成 **方案 C**，获得最佳性能
- 审查历史（回溯 6.12.0）：直接切换 `current` 到 `base/`

#### metadata.json 结构

```json
{
  "repo_name": "linux",
  "repo_path": "/home/user/linux",
  "version_namespace": "v6.12",
  "base_commit": "e33f3b9a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e",
  "base_tag": "v6.12.0",
  "index_type": "base",
  "index_date": "2026-04-22T09:17:00Z",
  "kernel_version": "6.12.0",
  "subsystems": ["sched", "mm", "net", "fs", "block", "drivers"],
  "chunks": {
    "code": 450000,
    "commits": 12000,
    "blame_lines": 850000
  },
  "storage": {
    "vectors_mb": 1536,
    "sparse_mb": 512,
    "graph_mb": 198,
    "total_mb": 2246
  },
  "tools_version": {
    "kernel_rag_mcp": "0.1.0",
    "kconfiglib": "14.1.0",
    "kclause": "2.1.0"
  }
}
```

#### 多仓库支持

用户通常有多个内核仓库（upstream、公司内部分支、个人实验分支）：

```bash
# 注册多个仓库
$ kernel-rag init ~/linux-upstream --name linux-upstream
$ kernel-rag init ~/linux-company --name linux-company
$ kernel-rag init ~/linux-personal --name linux-personal

# ~/.kernel-rag/repos.json
{
  "linux-upstream": {"path": "/home/user/linux-upstream", "default_version": "v6.12"},
  "linux-company": {"path": "/home/user/linux-company", "default_version": "v6.12"},
  "linux-personal": {"path": "/home/user/linux-personal", "default_version": "v6.13"}
}
```

MCP Server 根据当前工作目录自动匹配仓库，或显式指定：

```python
kernel_search(query="vruntime", repo="linux-upstream", version="v6.12")
```

#### 存储管理策略：绝不自动清理，仅提示

**原则**：索引是用户资产，工具**不擅自删除**，仅提供信息提示和手动管理命令。

| 场景               | 行为                                                         |
| :----------------- | :----------------------------------------------------------- |
| **磁盘空间不足**   | CLI 打印警告：`[Warning] ~/.kernel-rag 占用 45GB，建议运行 kernel-rag status 查看` |
| **增量过多**       | 提示：`v6.12 有 15 个 delta，查询延迟增加 200ms，建议合并`   |
| **旧版本长期未用** | 提示：`v6.10 基线索引 180 天未访问，可手动清理`              |
| **清理命令**       | `kernel-rag status` 列出所有版本和大小，`kernel-rag remove v6.10` 手动删除 |
| **合并命令**       | `kernel-rag merge v6.12 --target v6.12.15` 手动合并 deltas   |
| **保留标记**       | `kernel-rag pin v6.12` 标记大版本长期保留，status 中显示 PIN 标记 |

```bash
$ kernel-rag status
Repository: linux @ /home/user/linux
Version      Type     Size    LastUsed  Pin  Deltas  Merged
------------------------------------------------------------
v6.13        base     2.3GB   2h ago    -    3       -
v6.12        base     2.1GB   1d ago    ✓    15      merged-v6.12.15
v6.11        base     2.0GB   30d ago   -    0       -
v6.10        base     1.9GB   180d ago  -    0       -

Total: 8.3GB  (提示: v6.10 已 180 天未用，可手动移除)
```

### 6.3 与内核源码仓库的配合机制

#### 不侵入源码树

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

#### 注册与初始化流程

```bash
# 1. 注册仓库（一次性的）
$ cd ~/linux
$ kernel-rag init
→ 扫描 Git 仓库 → 识别当前 tag (v6.12.5) → 创建 ~/.kernel-rag/repos/linux/v6.12/
→ 提示：运行 `kernel-rag index` 建立基线索引

# 2. 建立基线索引（大版本首版）
$ kernel-rag index --base
→ 生成 ~/.kernel-rag/repos/linux/v6.12/base/

# 3. 日常增量（小版本更新后）
$ git fetch origin && git checkout v6.12.6
$ kernel-rag update
→ 生成 ~/.kernel-rag/repos/linux/v6.12/delta-v6.12.6/

# 4. 手动合并（可选，优化查询性能）
$ kernel-rag merge v6.12 --target v6.12.6
→ 生成 ~/.kernel-rag/repos/linux/v6.12/merged-v6.12.6/

# 5. 注册到 MCP（自动或手动）
$ kernel-rag mcp install --client claude-code
→ 写入 ~/.claude/config.json

# 6. 使用
$ claude
→ AI 自动调用 kernel-rag 查询代码
```

#### Git Hooks 集成（可选）

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

#### 版本锁定与一致性校验

查询时执行以下校验链：

```python
def verify_index_freshness(repo_path, index_meta):
    # 1. 检查源码 commit 是否匹配索引基线或合并目标
    current_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path)
    indexed_commit = index_meta.get("merged_to") or index_meta["base_commit"]
    
    if current_head.stdout.strip() != indexed_commit:
        return {
            "status": "stale",
            "suggestion": "Run `kernel-rag update` to create delta, or `kernel-rag merge` to sync",
            "drift_commits": count_commits_between(indexed_commit, current_head)
        }
    
    # 2. 抽查行号一致性（随机选 10 个 chunk 验证）
    for chunk in random.sample(chunks, 10):
        actual_line = read_file_line(repo_path + chunk.file, chunk.line)
        if actual_line.strip() != chunk.expected_line.strip():
            return {"status": "corrupted", "suggestion": "Re-index recommended"}
    
    return {"status": "fresh"}
```

**用户感知**：如果索引过期，MCP Server 在返回结果前附加警告：

> ⚠️ 索引基于 `v6.12.0`，当前源码为 `v6.12.3`，相差 47 个 commit。已应用 3 个 delta 叠加查询，建议运行 `kernel-rag merge v6.12` 获得最佳性能。

### 6.4 Git 索引范围构建（避免全量爆炸）

内核 Git 历史长达 20 年、百万级 commit，全量索引不现实也不必要。支持**范围化构建**：

```bash
# 默认范围：最近 2-3 个 LTS 周期（约 2-3 年）
$ kernel-rag index-git
→ 默认索引 v6.6..HEAD（约 3 万个 commit）

# 显式范围构建
$ kernel-rag index-git --range v6.12..v6.18
$ kernel-rag index-git --range v6.6..v6.12
$ kernel-rag index-git --range 2024-01-01..2026-04-22

# 历史版本按需加载（不默认索引，用户主动触发）
$ kernel-rag index-git --range v5.15..v6.6
→ 提示：这将增加约 1.2GB 存储，确认？[Y/n]

# 子系统 + 范围联合
$ kernel-rag index-git --subsys sched,mm --range v6.12..v6.13
```

**范围存储策略**：

| 范围类型             | 存储策略                                          | 说明                    |
| :------------------- | :------------------------------------------------ | :---------------------- |
| **近期范围（默认）** | 完整索引：commit 卡片 + diff 上下文 + blame       | 如 v6.6..HEAD           |
| **中期范围（按需）** | 精简索引：commit 卡片 + diff 摘要（无代码上下文） | 如 v5.15..v6.6          |
| **远期范围（归档）** | 元数据索引：仅 commit 卡片（标题/作者/日期/标签） | 如 v4.19..v5.15         |
| **Blame 索引**       | 仅当前 HEAD                                       | 历史 blame 按需实时查询 |

**存储估算**：

| 范围                 | Commit 数 | 存储大小 | 内容                     |
| :------------------- | :-------- | :------- | :----------------------- |
| v6.12..v6.13（1 年） | ~15,000   | ~800MB   | 完整卡片 + diff 上下文   |
| v6.6..v6.12（2 年）  | ~45,000   | ~2.0GB   | 完整卡片 + diff 上下文   |
| v5.15..v6.6（5 年）  | ~120,000  | ~1.5GB   | 精简卡片（无 diff 代码） |
| v4.19..v5.15（归档） | ~300,000  | ~600MB   | 仅元数据卡片             |

### 6.5 索引生命周期与运维

```plain
索引生命周期
├── 创建：kernel-rag init → index --base（大版本全量，1~8小时）
├── 日常：kernel-rag update（小版本增量，秒~分钟级）
│   └── 生成 delta-v6.12.x/
├── 合并：kernel-rag merge v6.12 --target v6.12.15（手动，优化性能）
│   └── 生成 merged-v6.12.15/
├── 切换：kernel-rag use v6.13/base（切换 current 符号链接）
├── 回滚：kernel-rag use v6.12/base（退回基线）
├── 清理：kernel-rag remove v6.11（手动删除，需确认）
├── 导出：kernel-rag export v6.12/merged-v6.12.15 /path/to/backup.tar.gz
└── 状态：kernel-rag status（查看所有版本、大小、pin 状态）
```

------

## 7. 本地 Git 原生架构

### 7.1 核心设计哲学

**本地 Git 仓库不仅是源码存储，更是内核知识库的"唯一真相源"（Single Source of Truth）。**

所有索引（代码、Git 历史、Kconfig、变更因果）都从本地 Git 仓库**派生**，而非外部导入。这保证：

- **版本严格一致**：索引的 commit hash 与本地 `HEAD` 完全对应，无版本漂移
- **实时可验证**：AI 返回的任何引用（行号、commit、作者）用户可用 `git show`、`git blame` 秒级验证
- **隐私绝对安全**：源码、提交历史、内部 patch 永不离开本地磁盘
- **增量天然支持**：Git 本身就是差异引擎，增量索引直接基于 `git diff`

### 7.2 四层索引架构（从 Git 仓库派生）

```plain
本地 Git 仓库 ~/linux
├── 源码树 (working tree / HEAD)
│   ├── kernel/sched/*.c          → 代码语义索引 (Code RAG)
│   ├── include/linux/*.h         → 头文件依赖图谱
│   ├── Kconfig / Makefile        → Kconfig 逻辑索引 (Kconfig RAG)
│   └── .config                   → 当前激活配置快照
│
├── Git 历史 (.git)
│   ├── git log --all             → Commit 元数据索引 (Git RAG)
│   ├── git blame HEAD            → 行级溯源索引 (Blame RAG)
│   ├── git tag -l                → 版本标签映射表
│   └── git log --format=...      → 变更因果图谱 (Causal Graph)
│       ├── Fixes: 标签            → 修复链边
│       ├── Introduced-by: 标签    → 问题引入边
│       ├── Cc: stable 标签        → Backport 边
│       ├── Reviewed-by: 标签      → 审查关系边
│       └── cherry-pick 标记       → Stable 树同步边
│
└── 工具输出 (由本项目自动生成)
    ├── cscope.out                → 调用关系图谱
    ├── tags (ctags)              → 符号定位表
    └── kclause.z3                → Kconfig 可满足性公式
```

### 7.3 与 OpenCode 的深度集成

OpenCode 原生支持 **MCP 协议**，同时其 `/init` 和 `/init-deep` 机制可与本项目形成**分层协作**：

#### 集成方式 A：MCP 标准接入（推荐）

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

#### 集成方式 B：与 `/init-deep` 分层上下文协同

OpenCode 的 `/init-deep` 生成项目级 `AGENTS.md`，本项目可为其**注入内核领域上下文**：

Markdown

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

#### 集成方式 C：通用大模型（无 MCP 支持）

如果用户使用不支持 MCP 的通用大模型（如网页版 ChatGPT、DeepSeek 网页版），提供**CLI 管道模式**：



```bash
# 用户手动查询上下文，复制粘贴给大模型
$ kernel-rag query "TCP RTO SACK bug 引入源头和修复链"
→ [输出带行号的代码 + commit + Fixes: 链 + backport 状态]

# 用户将输出粘贴到 ChatGPT 作为上下文
```

### 7.4 维护者专用工作流（Reviewer 场景）

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

### 7.5 增量更新策略（基于 Git 的增量）

利用 Git 自身差异能力，实现**秒级~分钟级**增量索引：



```bash
#  nightly 增量任务（由 kernel-rag 自动执行）
git fetch origin
NEW_HEAD=$(git rev-parse origin/master)
OLD_HEAD=$(cat ~/.kernel-rag/repos/linux/v6.12/current/metadata.json | jq -r .base_commit)

# 1. 获取变更范围
git diff --name-only $OLD_HEAD $NEW_HEAD > changed_files.txt

# 2. 代码 RAG 增量：只重新索引变更文件
kernel-rag index --incremental --files changed_files.txt

# 3. Git RAG 增量：只索引新增 commits（在范围内）
git log --format='%H' $OLD_HEAD..$NEW_HEAD > new_commits.txt
kernel-rag index-git --commits new_commits.txt --append-to v6.12

# 4. 变更因果图谱增量：解析新增 commit 的标签
kernel-rag index-causal --commits new_commits.txt
# 提取 Fixes:, Introduced-by:, Cc: stable 等标签，更新图谱边

# 5. 更新 Kconfig（如果 Kconfig 文件有变更）
if grep -q "Kconfig" changed_files.txt; then
    kextract && kclause  # 重新生成逻辑公式
fi

# 6. 生成 delta 目录（不修改 base，保持基线稳定）
mkdir -p ~/.kernel-rag/repos/linux/v6.12/delta-$(git describe --tags $NEW_HEAD)
# 将增量索引写入 delta 目录
```

**级联控制**：头文件变更（如 `sched.h`）触发 `depth=1` 级联（重算直接包含者），避免全量重建。

### 7.6 数据一致性保证

| 检查点               | 机制                                                         | 目的                     |
| :------------------- | :----------------------------------------------------------- | :----------------------- |
| **索引-源码一致性**  | 索引中存储 `base_commit` 和 `merged_to`，查询时校验本地 `HEAD` | 防止索引过期导致行号漂移 |
| **行号现场验证**     | 检索后读取本地文件时，校验该行内容是否与索引摘要匹配         | 防止 patch 错位          |
| **Kconfig 公式校验** | 每次索引后随机抽样 100 个配置组合，用 Z3 验证可满足性        | 确保形式化层无逻辑错误   |
| **Git 完整性**       | 索引前运行 `git fsck`，确保仓库无损坏                        | 防止历史数据污染         |
| **因果链闭环检查**   | 定期验证 Fixes: 指向的 commit 是否存在于索引中               | 防止断链                 |

### 7.7 一句话总结

> **本地 Git 仓库是内核 RAG 的"根"：代码从工作树来，历史从 `.git` 来，配置从 `Kconfig` 来，因果从 `Fixes:`/`Introduced-by:` 标签来，类型从 commit message 的标题语义来，验证从 `git blame` 来。通过统一的 MCP 网关，AI 编程工具（OpenCode、Claude Code、Cursor）可以像调用本地函数一样，自动路由到语义搜索、精确跳转、Git 溯源、Kconfig 验证、Patch 类型筛选或变更因果追踪——为开发者和维护者提供从"是什么"到"为什么"到"谁改的"到"引入了什么问题"到"有哪些同类优化"的完整信息闭环。**

------

## 8. 非功能目标

### 8.1 性能

| 指标                          | 目标     | 备注                 |
| :---------------------------- | :------- | :------------------- |
| 全量索引时间（消费级 GPU）    | ≤ 1 小时 | RTX 4090，完整内核   |
| 全量索引时间（纯 CPU 16核）   | ≤ 8 小时 | 可接受的后台任务     |
| 增量更新时间（普通 commit）   | ≤ 3 分钟 | 纯 CPU               |
| 查询延迟（P95，基线）         | ≤ 500ms  | 本地 Qdrant          |
| 查询延迟（基线 + 5 个 delta） | ≤ 800ms  | 叠加查询开销可控     |
| 查询延迟（合并后）            | ≤ 500ms  | 与基线一致           |
| 索引磁盘占用（基线）          | ≤ 2.5GB  | 指针式索引，不含原文 |
| 索引磁盘占用（单 delta）      | ≤ 50MB   | 仅变更文件           |
| 变更因果图谱查询              | ≤ 200ms  | 图数据库或内存索引   |

> Notes: 磁盘占用不是强约束，只是参考。

### 8.2 可扩展性

- 支持从单个子系统（`kernel/sched/`，~500 文件）到完整内核（~25000 文件）的弹性索引
- 向量库可切换：Qdrant（默认）/ Chroma / Milvus / pgvector
- 变更因果图谱支持 NetworkX / 内存邻接表多种后端（内核场景图规模可控，无需重型图数据库）

### 8.3 安全与合规

- **许可证**：项目代码采用 MIT/Apache-2.0，与内核 GPL-2.0 隔离
- **隐私**：默认本地运行，无遥测、无云端上传
- **数据安全**：索引不含代码原文，仅含指针信息；即使泄露也无法还原完整源码
- **GPL 声明**：明确标注索引包含对 GPL-2.0 代码的元数据引用，用户需自行遵守内核许可证

### 8.4 兼容性

- **AI 客户端**：Claude Code（MCP stdio）、Cursor（MCP json）、OpenCode（MCP/HTTP）、Windsurf
- **内核版本**：Linux 5.x / 6.x（主分支 + LTS）
- **平台**：Linux x86_64 / aarch64（开发机），macOS（Apple Silicon，通过 Rosetta/原生）

------

## 9. 技术架构目标

```plain
┌─────────────────────────────────────────┐
│  AI 客户端（Claude Code / Cursor / OpenCode）│
│  通过 MCP 协议调用工具                   │
├─────────────────────────────────────────┤
│  kernel-rag-mcp Server                  │
│  FastMCP / stdio / HTTP                 │
│  ├── kernel_query (统一路由网关)          │
│  │   ├── kernel_search / kernel_define   │
│  │   ├── kernel_callers / kernel_diff     │
│  │   ├── kernel_config / kernel_config_check│
│  │   ├── git_search_commits / git_blame   │
│  │   ├── git_diff_summary / git_changelog │
│  │   ├── git_search_by_type / git_type_stats│
│  │   ├── git_causal_chain / git_bug_origin│
│  │   ├── git_backport_status / git_fixes_complete│
│  │   ├── kconfig_describe / kconfig_check │
│  │   ├── ctags_jump / cscope_callers      │
│  │   └── grep_code                       │
│  └── 智能路由引擎（意图识别 + 工具选择）    │
├─────────────────────────────────────────┤
│  检索引擎                                │
│  Hybrid Search (Dense + Sparse + RRF)  │
│  Context Assembler（跨文件上下文组装）    │
│  Git Blame Resolver（行级溯源）           │
│  Causal Graph Traverser（变更因果遍历）    │
│  Z3 Solver（Kconfig 可满足性验证）        │
├─────────────────────────────────────────┤
│  存储层                                  │
│  Qdrant（向量 + 元数据）                 │
│  Meilisearch（稀疏符号索引）              │
│  cscope.out（调用关系数据源）             │
│  Causal Graph DB（变更因果图谱）           │
├─────────────────────────────────────────┤
│  索引生成器（CLI）                        │
│  Tree-sitter C Parser                    │
│  Kconfig Parser (kconfiglib)             │
│  Kconfig Formalizer (kextract/kclause)   │
│  Kconfig Validator (KconfigDetector)     │
│  Kbuild Analyzer (kmax)                  │
│  Git History Parser (git log/show/blame) │
│  Git Causal Extractor (Fixes/Introduced-by)│
│  Patch Type Classifier (性能/bugfix/重构/特性)│
│  Callgraph Builder (cscope/clang)        │
│  Embedding Pipeline                      │
├─────────────────────────────────────────┤
│  本地内核源码（用户已有）                  │
│  ~/linux                                 │
│  ├── .git/ (完整 Git 历史)                │
│  ├── .kernel-rag.toml（可选，外部索引引用）│
│  ├── ctags tags（可选，由工具自动生成）     │
│  └── cscope.out（可选，由工具自动生成）    │
│
│  索引数据库（外部隔离，大版本粒度）          │
│  ~/.kernel-rag/repos/linux/              │
│  ├── v6.12/                              │
│  │   ├── base/                           │
│  │   ├── delta-v6.12.1/                   │
│  │   ├── delta-v6.12.2/                   │
│  │   ├── merged-v6.12.5/                 │
│  │   └── current -> base/ 或 merged/...   │
│  └── v6.13/                              │
│      └── base/                           │
└─────────────────────────────────────────┘
```

------

## 10. 开源与社区目标

### 10.1 开源范围

| 组件                                 | 开源策略                       |
| :----------------------------------- | :----------------------------- |
| 索引生成脚本                         | ✅ 完全开源，MIT                |
| MCP Server                           | ✅ 完全开源，MIT                |
| 子系统规则模板（`sched/`、`mm/` 等） | ✅ CC0，鼓励厂商无负担贡献      |
| 预生成索引（向量+元数据）            | ⚠️ 可选分发，仅含指针，不含原文 |
| 文档与教程                           | ✅ CC-BY-SA                     |

### 10.2 社区协作模式

- **子系统自治**：调度器专家维护 `rules/sched/`，内存专家维护 `rules/mm/`，通过 YAML/JSON 规则文件贡献领域知识
- **版本化索引共享**：社区可上传特定 LTS 版本的预生成基线索引到 Release 页面，供不想自己跑索引的用户下载
- **CI 集成**：提供 GitHub Actions 模板，让下游项目自动索引自己的内核 fork

### 10.3 与上游生态的关系

- **不替代 cscope/grep**：定位是"语义增强"，精确跳转仍用传统工具
- **不生成补丁**：只提供上下文参考，最终代码决策必须由人类开发者做出并承担质量责任
- **尊重内核社区规范**：支持 `Assisted-by:` 等 AI 辅助标注的提醒

------

## 11. 里程碑规划

### Phase 1：单系统 MVP（4 周）

- [ ] 项目仓库结构搭建（`src/`、`tests/`、`docs/`）
- [ ] 支持 `kernel/sched/` 单个子系统的完整索引与检索
- [ ] CLI：`kernel-rag init`、`kernel-rag index --base ~/linux`
- [ ] 索引存放：`~/.kernel-rag/repos/linux/v6.12/base/` 基础结构
- [ ] MCP Server：暴露 `kernel_search` 和 `kernel_define`
- [ ] 接入 Claude Code，验证端到端体验

### Phase 2：完整内核 + Kconfig 感知 + 大版本粒度（4 周）

- [ ] 支持完整内核索引（`kernel-rag index --base ~/linux`）
- [ ] 大版本命名空间：`v6.12/base/`、`v6.13/base/`
- [ ] 增量 delta 结构：`delta-v6.12.1/`、`delta-v6.12.2`
- [ ] 手动合并命令：`kernel-rag merge v6.12 --target v6.12.5`
- [ ] 集成 **kconfiglib** 解析 Kconfig 符号属性
- [ ] 集成 **kclause** 生成 Z3 公式，支持 Kconfig 可满足性查询
- [ ] 集成 **Git 历史索引**（commit 卡片 + diff 上下文）
- [ ] Git 范围构建：`--range v6.12..v6.18`
- [ ] 增量更新（`kernel-rag update`）
- [ ] 接入 Cursor / OpenCode MCP

### Phase 3：Patch 类型 + 变更因果图谱 + Rust-for-Linux（4 周）

- [ ] 集成 **Patch 类型分类器**（性能/bugfix/重构/特性/回归）
- [ ] 暴露 `git_search_by_type`、`git_type_stats` 工具
- [ ] 集成 **Git 标签解析器**（Fixes:/Introduced-by:/Cc: stable 等）
- [ ] 构建 **变更因果图谱**（Change Causal Graph）
- [ ] 暴露 `git_causal_chain`、`git_bug_origin`、`git_backport_status` 工具
- [ ] 集成 **KconfigDetector** 风险标注
- [ ] 集成 **kmax** 建立配置-源文件映射
- [ ] 集成 **Git blame 行级溯源**
- [ ] Rust-for-Linux 模块解析与索引（`rust/` 目录）
- [ ] 子系统规则模板社区贡献机制
- [ ] 预生成基线索引分发（LTS 版本）

### Phase 4：CI 与生态集成（持续）

- [ ] 版本差异对比（`kernel_diff`）
- [ ] Kconfig 依赖推理（"开启 X 需要哪些前置配置"）
- [ ] CI/CD 集成（自动索引 PR 变更）
- [ ] 性能优化（更快的增量更新、更低的查询延迟）
- [ ] 变更因果图谱可视化（Web 预览）
- [ ] 团队索引导出/导入（`kernel-rag export/import`）

------

## 12. 成功标准

项目成功的衡量标准不是 Star 数，而是：

1. **一个内核新人能用自然语言在 30 秒内找到 `update_curr()` 的实现并理解 `vruntime` 机制**
2. **一个 Reviewer 能在审查跨子系统补丁时，5 分钟内确认影响范围**
3. **一个 AI 编程工具在写内核模块时，能自动引用真实内核代码而非幻觉**
4. **一个开发者能在不离开终端的情况下，让 AI 同时调用语义搜索和 `cscope` 精确验证**
5. **一个配置工程师能问"开启 CONFIG_BPF_JIT 且不开启 CONFIG_NUMA 是否合法"并得到精确答案**
6. **一个维护者能问"这行代码是谁引入的，为什么"并得到精确的 commit hash、作者、日期和设计理由**
7. **一个回归分析工程师能问"这个 TCP RTO bug 的完整生命周期"并得到从引入→发现→修复→backport 的完整因果链**
8. **一个性能分析工程师能问"6.12 到 6.13 之间调度器有哪些性能改动"并得到按类型分类的详细 commit 列表和 diff 摘要**
9. **一个团队能在 10 分钟内完成从 `git clone linux` 到 AI 可查询的完整索引部署**（时间不是强约束，只是示例）

------

## 13. 参考与致谢

- Linux Kernel: https://kernel.org/ (GPL-2.0)
- ctags: https://ctags.io/
- cscope: http://cscope.sourceforge.net/
- **kconfiglib**: https://github.com/ulfalizer/Kconfiglib (MIT) — Python Kconfig 解析与配置管理
- **kclause / kextract / kmax / klocalizer / krepair**: https://github.com/paulgazz/kmax (BSD-3-Clause) — Kconfig 形式化分析与配置覆盖工具链
- **Kismet**: https://github.com/paulgazz/kismet (BSD-3-Clause) — Kconfig 依赖缺陷检测（已集成 Intel 0-day CI）
- **KconfigDetector**: https://gitee.com/openeuler/KconfigDetector (Mulan PSL v2) — openEuler Kconfig 配置错误检测
- MCP Protocol: https://modelcontextprotocol.io/
- Tree-sitter: https://tree-sitter.github.io/
- Qdrant: https://qdrant.tech/
- Jina Embeddings: https://jina.ai/

------

> **设计哲学**：内核是计算机系统最精密的工程 artifact 之一。我们不做"又一个通用代码搜索"，而是为这门手艺打造专用的语义工具。与 `ctags`、`cscope` 和 `git log` 并肩工作，而非取代它们。