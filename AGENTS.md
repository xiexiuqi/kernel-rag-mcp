# AGENTS.md — kernel-rag-mcp

> 面向 Linux 内核的专用 RAG（Retrieval-Augmented Generation）+ MCP（Model Context Protocol）工具链。
> 当前状态：设计文档阶段，尚未实现代码骨架。

---

## 1. 项目定位（一句话）

让 AI 编程工具（Claude Code、Cursor、OpenCode 等）能够**精确理解、引用和推理 Linux 内核源码**，解决“上下文窗口装不下整个内核”的根本矛盾。

---

## 2. 当前仓库状态

- **唯一文件**：`Kernel-RAG-MCP 设计目标.md`（1371 行，中文）
- **尚无**：`src/`、`pyproject.toml`、`Makefile`、`tests/`、CI 配置等任何可执行代码或构建配置
- **结论**：本仓库目前仅为**设计文档仓库**，所有架构、接口、目录结构均存在于该 Markdown 文件中，尚未落地为代码

> 若未来开始编码，应优先对照该设计文档的“6.1 项目源码仓库结构”章节搭建骨架。

---

## 3. 核心设计原则（agent 必须遵守）

### 3.1 精确溯源优先（Line-Number-First）
- 所有检索结果必须包含 **文件路径 + 精确行号**
- AI 生成的任何引用都必须能回溯到具体代码位置
- 没有行号的输出对内核开发者不可信

### 3.2 指针式索引（Pointer-Based Indexing）
- 索引数据库**不存储代码原文**，只存储：
  - 向量（Embedding）
  - 元数据（文件、行号、符号名、类型、Kconfig 条件）
  - 调用关系图谱
- 代码片段在查询时**现场读取**用户本地源码
- 收益：索引体积可控（~2GB/版本），本地 patch 与索引轻微错位时仍可用

### 3.3 内核原生感知（Kernel-Native Awareness）
| 特性 | 处理方式 |
|------|----------|
| Kconfig 条件编译 | 提取 `#ifdef CONFIG_XXX` 分支，作为独立 chunk 并标注依赖条件 |
| 头文件级联依赖 | 构建 `.c ↔ .h ↔ include/linux/` 类型依赖图谱 |
| 宏展开 | 对 `container_of`、`list_for_each_entry` 等高频宏做预展开标注 |
| 调用链追踪 | 基于 `cscope`/`clang` 提取精确调用关系，支持深度级联 |
| 版本化 | 索引与 Git commit 严格绑定，支持多版本并存 |

### 3.4 Kconfig 依赖精确建模
- **不自行手写 Kconfig 解析器**，复用成熟工具链分层处理：
  - **解析层**：`kconfiglib`（Python 原生解析）
  - **形式化层**：`kclause` 系列（`kextract → kclause → Z3`）
  - **验证层**：`Kismet` + `KconfigDetector`
  - **关联层**：`kmax`（分析 Kbuild Makefile，建立 `obj-$(CONFIG_X)` 与源文件的精确编译映射）

### 3.5 Git 历史原生索引
- 本地 Git 仓库是**唯一真相源**（Single Source of Truth）
- 所有索引（代码、Git 历史、Kconfig）都从本地 Git 仓库**派生**，而非外部导入
- Patch 类型识别：从 commit message 中自动提取非正交多维分类标签（`bugfix`、`performance`、`refactor`、`feature`、`revert`、`regression`、`documentation`、`test`、`security`、`stable`）
- 变更因果图谱：提取 `Fixes:`、`Introduced-by:`、`Cc: stable` 等标签构建图谱

### 3.6 本地优先（Local-First）
- 索引在用户本地生成，源码不离开用户机器
- 支持纯 CPU 运行（GPU 加速可选）
- 增量更新无需联网

### 3.7 MCP 原生（MCP-Native）
- 项目首要接口是 **MCP Server**，而非 Web UI 或 CLI
- 人类接口（CLI/Web）是次要补充
- 设计目标是让 AI 编程工具能够**无感调用**内核代码库

---

## 4. 与现有工具的关系：互补而非替代

| 工具 | 本项目中的角色 |
|------|---------------|
| `ctags` | 提供初始符号表，用于构建稀疏索引（BM25）和符号验证 |
| `cscope` | 提供调用关系数据库（`cscope.out`），作为调用链图谱的基础数据源 |
| `clang`/`clangd` | 提供精确的 AST 和类型依赖（替代 cscope 的文本级分析） |
| `tree-sitter` | 提供函数级、结构体级的精确切分边界（替代正则切分） |
| `grep` / `ripgrg` | 作为 MCP 暴露的底层工具，供 AI 在需要文本模式匹配时调用 |

> **哲学**：`ctags` 告诉你“东西在哪一行”，`cscope` 告诉你“谁调用了谁”，Sourcegraph 告诉你“这个符号在全仓库的引用”，Git log 告诉你“为什么改成这样”，而 Kernel-RAG-MCP 告诉 AI“用户问了一个关于调度器的问题，该把哪几段代码、哪几个 commit、哪条 bugfix 链、哪些性能补丁塞进上下文窗口”。

---

## 5. 推荐的用户工作流

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

## 6. 技术架构概览

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
│                                          │
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

---

## 7. 项目仓库结构（设计目标）

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

---

## 8. 索引数据库的存放策略

### 8.1 核心原则
- 索引数据与源码树**物理隔离**，不侵入内核仓库
- 以**大版本（如 v6.12）为命名空间**，小版本（6.12.1, 6.12.2）作为**增量补丁**存放
- **绝不自动清理**，仅提示用户手动管理

### 8.2 默认存放路径
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

### 8.3 查询时的索引叠加策略

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

---

## 9. 注册与初始化流程

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

---

## 10. MCP 工具清单

### 10.1 统一查询网关
| Tool | 功能 | 触发场景 |
|------|------|----------|
| `kernel_query(intent, query, context)` | 统一内核查询入口，内部自动路由 | AI 模型只需调用此工具 |

### 10.2 代码语义层工具
| Tool | 功能 | 触发场景 |
|------|------|----------|
| `kernel_search(query, subsys, kconfig, top_k)` | 语义搜索内核代码 | 用户询问实现细节、机制原理 |
| `kernel_define(symbol, file_hint)` | 精确符号定义查询 | 用户提到具体函数/宏/结构体 |
| `kernel_callers(symbol, depth)` | 调用链追踪 | 影响分析、审查范围确认 |
| `kernel_diff(symbol, v1, v2)` | 版本差异对比 | 问"这个函数在 5.15 和 6.12 之间变了什么" |
| `kernel_cross_ref(symbol)` | 跨文件关联 | 找声明、定义、使用点 |

### 10.3 Git 历史层工具
| Tool | 功能 | 触发场景 |
|------|------|----------|
| `git_search_commits(query, since, until, author, file_pattern)` | 语义搜索 commit history | 问"谁改了什么" |
| `git_blame_line(file, line)` | 行级代码溯源 | "这行代码谁引入的" |
| `git_diff_summary(symbol, v1, v2)` | 两个版本间某符号的变更摘要 | "这个函数变了什么" |
| `git_changelog(subsys, since_tag, until_tag)` | 子系统变更日志生成 | "sched 子系统最近改了什么" |
| `git_commit_context(commit_hash)` | 获取某 commit 的完整上下文 | 审查具体 patch |
| `git_show_patch(commit_hash, file)` | 获取某 commit 在某文件的 diff | 看具体修改 |

### 10.4 Patch 类型筛选工具
| Tool | 功能 | 触发场景 |
|------|------|----------|
| `git_search_by_type(type_tags[], subsys, since, until)` | 按类型标签筛选 commits | "某版本范围内某子系统的性能改动" |
| `git_type_stats(subsys, since, until)` | 统计各类型 patch 分布 | "过去半年 mm 子系统有多少 bugfix" |
| `git_find_performance_regression_fix(subsys, since)` | 查找性能回归修复 | "最近修复了哪些性能回归" |

### 10.5 变更因果图谱工具
| Tool | 功能 | 触发场景 |
|------|------|----------|
| `git_causal_chain(commit_hash, direction="both")` | 查询变更因果链（上游/下游） | "这个 bug 的完整修复链是什么" |
| `git_bug_origin(commit_hash)` | 追踪问题引入源头 | "这个 regression 是哪个 commit 引入的" |
| `git_backport_status(commit_hash)` | 查询 backport 状态 | "这个修复有没有进 stable 分支" |
| `git_reviewer_expertise(reviewer, subsys)` | 查询审查者的专业领域 | "David Miller 审查过哪些网络补丁" |
| `git_regression_chain(subsys, since)` | 查询某子系统的回归链 | "最近一年 mm 子系统有哪些 regression" |
| `git_patch_series(commit_hash)` | 查询补丁系列关系 | "这个 commit 属于哪个系列" |
| `git_fixes_complete(commit_hash)` | 验证 Fixes 链完整性 | "这个修复是否完整覆盖了所有引入点" |

### 10.6 Kconfig 配置层工具
| Tool | 功能 | 触发场景 |
|------|------|----------|
| `kconfig_describe(config_name)` | 查询配置项的 help、类型、默认值 | "CONFIG_SMP 是什么" |
| `kconfig_deps(config_name)` | 查询直接和间接依赖 | "开启这个需要什么前置条件" |
| `kconfig_check(combo_dict)` | 验证配置组合的可满足性 | "A=y 且 B=n 是否合法" |
| `kconfig_impact(config_name)` | 查询修改某配置影响的源文件 | "关闭这个会少编译哪些文件" |

### 10.7 精确工具层（包装传统命令）
| Tool | 底层命令 | 用途 |
|------|----------|------|
| `ctags_jump(symbol)` | `ctags -x` | 毫秒级精确跳转 |
| `cscope_callers(symbol, depth)` | `cscope -d -L3` | 调用关系查询 |
| `grep_code(pattern, path)` | `ripgrep -n -C 3` | 文本模式匹配 |

---

## 11. AI 自动选择策略

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

---

## 12. 里程碑规划

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

---

## 13. 关键外部依赖与工具链

| 依赖 | 用途 | 许可证 |
|------|------|--------|
| `kconfiglib` | Python 原生解析 Kconfig 语法 | MIT |
| `kclause` / `kextract` / `kmax` / `klocalizer` / `krepair` | Kconfig 形式化分析与配置覆盖工具链 | BSD-3-Clause |
| `Kismet` | Kconfig 依赖缺陷检测 | BSD-3-Clause |
| `KconfigDetector` | openEuler Kconfig 配置错误检测 | Mulan PSL v2 |
| `tree-sitter` | C/H 文件 AST 解析 | MIT |
| `Qdrant` | 向量数据库 | Apache-2.0 |
| `Meilisearch` | 稀疏符号索引 | MIT |
| `jina-embeddings-v2-base-code` / `BAAI/bge-m3` | 代码专用 Embedding 模型 | 各模型自有许可证 |
| `cscope` | 调用关系数据库 | BSD |
| `ctags` | 符号定位表 | GPL-2.0+ |
| `clang`/`clangd` | 精确 AST 和类型依赖 | Apache-2.0 |
| `Z3` | Kconfig 可满足性求解 | MIT |

---

## 14. 许可证与合规

- **项目代码**：MIT/Apache-2.0，与内核 GPL-2.0 隔离
- **隐私**：默认本地运行，无遥测、无云端上传
- **数据安全**：索引不含代码原文，仅含指针信息；即使泄露也无法还原完整源码
- **GPL 声明**：明确标注索引包含对 GPL-2.0 代码的元数据引用，用户需自行遵守内核许可证

---

## 15. 与 OpenCode 的深度集成

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

OpenCode 在对话中自动触发：
- 用户问内核问题 → OpenCode 调用 `kernel_query` → 返回带行号的上下文 → OpenCode 生成回答

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
当用户问"这个 bug 是谁引入的"时，调用 `git_causal` 追踪 Fixes:/Introduced-by: 链；
当用户提到具体函数名时，调用 `ctags_jump` 验证精确行号。
```

**效果**：OpenCode 的 AI 在理解项目概貌（`/init`）的同时，能通过 MCP 实时查询内核代码库的深度语义、Patch 类型和变更因果。

### 集成方式 C：通用大模型（无 MCP 支持）

如果用户使用不支持 MCP 的通用大模型（如网页版 ChatGPT、DeepSeek 网页版），提供**CLI 管道模式**：

```bash
# 用户手动查询上下文，复制粘贴给大模型
$ kernel-rag query "TCP RTO SACK bug 引入源头和修复链"
→ [输出带行号的代码 + commit + Fixes: 链 + backport 状态]

# 用户将输出粘贴到 ChatGPT 作为上下文
```

---

## 16. 维护者专用工作流（Reviewer 场景）

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

## 17. 增量更新策略（基于 Git 的增量）

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

---

## 18. 数据一致性保证

| 检查点 | 机制 | 目的 |
|:------|:-----|:-----|
| **索引-源码一致性** | 索引中存储 `base_commit` 和 `merged_to`，查询时校验本地 `HEAD` | 防止索引过期导致行号漂移 |
| **行号现场验证** | 检索后读取本地文件时，校验该行内容是否与索引摘要匹配 | 防止 patch 错位 |
| **Kconfig 公式校验** | 每次索引后随机抽样 100 个配置组合，用 Z3 验证可满足性 | 确保形式化层无逻辑错误 |
| **Git 完整性** | 索引前运行 `git fsck`，确保仓库无损坏 | 防止历史数据污染 |
| **因果链闭环检查** | 定期验证 Fixes: 指向的 commit 是否存在于索引中 | 防止断链 |

---

## 19. 成功标准

项目成功的衡量标准不是 Star 数，而是：

1. **一个内核新人能用自然语言在 30 秒内找到 `update_curr()` 的实现并理解 `vruntime` 机制**
2. **一个 Reviewer 能在审查跨子系统补丁时，5 分钟内确认影响范围**
3. **一个 AI 编程工具在写内核模块时，能自动引用真实内核代码而非幻觉**
4. **一个开发者能在不离开终端的情况下，让 AI 同时调用语义搜索和 `cscope` 精确验证**
5. **一个配置工程师能问"开启 CONFIG_BPF_JIT 且不开启 CONFIG_NUMA 是否合法"并得到精确答案**
6. **一个维护者能问"这行代码是谁引入的，为什么"并得到精确的 commit hash、作者、日期和设计理由**
7. **一个回归分析工程师能问"这个 TCP RTO bug 的完整生命周期"并得到从引入→发现→修复→backport 的完整因果链**
8. **一个性能分析工程师能问"6.12 到 6.13 之间调度器有哪些性能改动"并得到按类型分类的详细 commit 列表和 diff 摘要**
9. **一个团队能在 10 分钟内完成从 `git clone linux` 到 AI 可查询的完整索引部署**

---

## 20. 参考与致谢

- Linux Kernel: https://kernel.org/ (GPL-2.0)
- ctags: https://ctags.io/
- cscope: http://cscope.sourceforge.net/
- **kconfiglib**: https://github.com/ulfalizer/Kconfiglib (MIT)
- **kclause / kextract / kmax / klocalizer / krepair**: https://github.com/paulgazz/kmax (BSD-3-Clause)
- **Kismet**: https://github.com/paulgazz/kismet (BSD-3-Clause)
- **KconfigDetector**: https://gitee.com/openeuler/KconfigDetector (Mulan PSL v2)
- MCP Protocol: https://modelcontextprotocol.io/
- Tree-sitter: https://tree-sitter.github.io/
- Qdrant: https://qdrant.tech/
- Jina Embeddings: https://jina.ai/

---

> **设计哲学**：内核是计算机系统最精密的工程 artifact 之一。我们不做"又一个通用代码搜索"，而是为这门手艺打造专用的语义工具。与 `ctags`、`cscope` 和 `git log` 并肩工作，而非取代它们。
