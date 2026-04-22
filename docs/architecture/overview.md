# 技术架构概览

> 本文档描述 Kernel-RAG-MCP 的整体技术架构和分层设计。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 架构分层

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

## 2. 各层职责

### 2.1 MCP Server 层

- **统一入口**：`kernel_query()` 作为唯一对外接口
- **智能路由**：根据查询意图自动分发到不同子系统
- **工具暴露**：将底层能力包装为 MCP 工具供 AI 调用
- **传输协议**：支持 stdio（本地）、SSE（远程）、HTTP（服务化）

### 2.2 检索引擎层

- **混合召回**：Dense（向量语义）+ Sparse（BM25 符号名）+ RRF 融合
- **上下文组装**：自动拉取被召回函数的声明（`.h`）、实现（`.c`）和依赖类型定义
- **Kconfig 过滤**：查询时可指定 `CONFIG_SMP=y/n` 过滤条件编译分支
- **因果遍历**：基于变更因果图谱回答"这个 bug 的完整修复链是什么"

### 2.3 存储层

- **向量存储**：Qdrant（默认）/ Chroma / Milvus，存储代码语义向量
- **稀疏索引**：Meilisearch，存储符号名、函数名等文本索引
- **图存储**：NetworkX / Neo4j / 内存邻接表，存储调用关系和变更因果
- **元数据**：JSON 文件存储索引版本、commit hash、子系统列表等

### 2.4 索引生成器层

- **代码索引**：Tree-sitter 解析 C/H 文件 → AST 切分 → Embedding
- **Git 索引**：解析 commit message、diff、blame 元数据
- **Kconfig 索引**：kconfiglib 解析 + kclause 形式化 + Z3 验证
- **因果索引**：提取 Fixes:/Introduced-by: 等标签构建图谱
- **类型索引**：Patch 类型分类器标注每个 commit

---

## 3. 数据流

### 3.1 索引流程

```plain
本地内核源码 ~/linux
    │
    ├── 源码树 ──→ Tree-sitter 解析 ──→ AST 切分 ──→ Embedding ──→ Qdrant
    │               (c/h 文件)           (chunk)        (向量)
    │
    ├── .git/ ───→ git log/show ───→ Commit 卡片 ──→ Embedding ──→ Qdrant
    │               (历史)              (元数据+diff)    (向量)
    │
    ├── Kconfig ──→ kconfiglib ──→ 符号属性 ──→ kclause ──→ Z3 公式
    │               (配置)            (解析)       (形式化)     (验证)
    │
    └── Makefile ──→ kmax ──→ 配置-源文件映射 ──→ 元数据索引
                    (构建)       (关联层)
```

### 3.2 查询流程

```plain
用户提问
    │
    ▼
kernel_query(intent, query, context)
    │
    ├── 意图识别 ──→ 路由决策
    │
    ├── 语义搜索 ──→ Qdrant 向量召回 ──→ 现场读取源码 ──→ 返回带行号结果
    │
    ├── 精确符号 ──→ ctags / cscope ──→ 返回精确位置
    │
    ├── Git 历史 ──→ Meilisearch / Qdrant ──→ 返回 commit + diff
    │
    ├── Kconfig ──→ Z3 求解 ──→ 返回可满足性结果
    │
    └── 因果图谱 ──→ 图遍历 ──→ 返回完整因果链
```

---

## 4. 项目源码仓库结构

```plain
kernel-rag-mcp/                    # 本项目开源仓库
├── pyproject.toml                 # Python 包配置（uv/pip 安装）
├── README.md
├── LICENSE                        # MIT/Apache-2.0
├── Makefile                       # 快捷命令：make install / make test / make index
├── docs/                          # 文档
│   ├── design/                    # 设计原则
│   ├── architecture/              # 架构概览
│   ├── mcp-tools/                 # MCP 工具设计
│   ├── indexer/                   # 索引层设计
│   ├── retriever/                 # 检索层设计
│   ├── storage/                   # 存储层设计
│   ├── git-history/               # Git 历史索引设计
│   ├── kconfig/                   # Kconfig 索引设计
│   ├── causal-graph/              # 变更因果图谱设计
│   ├── integration/               # 集成与部署
│   └── ops/                       # 运维与监控
├── src/
│   └── kernel_rag_mcp/            # 主 Python 包
│       ├── __init__.py
│       ├── cli.py                 # 命令行入口：kernel-rag
│       ├── config.py              # 全局配置管理
│       ├── server/                # MCP Server 层
│       │   ├── __init__.py
│       │   ├── mcp_server.py      # FastMCP 主服务
│       │   ├── router.py          # 意图识别与工具路由引擎
│       │   └── tools/             # MCP 工具实现
│       │       ├── code_tools.py
│       │       ├── git_tools.py
│       │       ├── type_tools.py
│       │       ├── causal_tools.py
│       │       ├── kconfig_tools.py
│       │       └── legacy_tools.py
│       ├── indexer/               # 索引生成器
│       │   ├── __init__.py
│       │   ├── main.py            # 统一索引调度入口
│       │   ├── code_indexer.py
│       │   ├── git_indexer.py
│       │   ├── type_indexer.py
│       │   ├── causal_indexer.py
│       │   ├── kconfig_indexer.py
│       │   ├── parsers/
│       │   │   ├── tree_sitter_c.py
│       │   │   ├── kconfig_parser.py
│       │   │   ├── git_parser.py
│       │   │   ├── type_parser.py
│       │   │   └── diff_parser.py
│       │   ├── embedders/
│       │   │   └── code_embedder.py
│       │   └── graph_builder/
│       │       ├── callgraph.py
│       │       └── causal_graph.py
│       ├── retriever/             # 检索引擎
│       │   ├── __init__.py
│       │   ├── hybrid_search.py
│       │   ├── context_assembler.py
│       │   └── causal_traverser.py
│       ├── storage/               # 存储抽象层
│       │   ├── __init__.py
│       │   ├── vector_store.py
│       │   ├── sparse_store.py
│       │   ├── graph_store.py
│       │   └── metadata_store.py
│       └── rules/                 # 子系统领域规则
│           ├── __init__.py
│           ├── sched/
│           │   └── indexing_rules.yaml
│           ├── mm/
│           │   └── indexing_rules.yaml
│           └── net/
│               └── indexing_rules.yaml
├── scripts/                       # 运维脚本
│   ├── install-mcp.sh
│   ├── nightly-index.sh
│   └── verify-index.sh
├── tests/                         # 测试
│   ├── unit/                      # 单元测试
│   ├── integration/               # 集成测试
│   ├── fixtures/                  # 测试用微型内核树
│   └── design/                    # 测试设计文档
└── .github/
    └── workflows/
        └── ci.yml
```

---

## 5. 关键外部依赖

| 依赖 | 用途 | 许可证 |
|------|------|--------|
| `kconfiglib` | Python 原生解析 Kconfig 语法 | MIT |
| `kclause` / `kextract` / `kmax` | Kconfig 形式化分析与配置覆盖工具链 | BSD-3-Clause |
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

## 6. 许可证与合规

- **项目代码**：MIT/Apache-2.0，与内核 GPL-2.0 隔离
- **隐私**：默认本地运行，无遥测、无云端上传
- **数据安全**：索引不含代码原文，仅含指针信息；即使泄露也无法还原完整源码
- **GPL 声明**：明确标注索引包含对 GPL-2.0 代码的元数据引用，用户需自行遵守内核许可证
