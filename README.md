# Kernel-RAG-MCP

> 面向 Linux 内核的专用 RAG（Retrieval-Augmented Generation）+ MCP（Model Context Protocol）工具链。

---

## 项目定位

让 AI 编程工具（Claude Code、Cursor、OpenCode 等）能够**精确理解、引用和推理 Linux 内核源码**，解决"上下文窗口装不下整个内核"的根本矛盾。

---

## 当前状态

**设计文档阶段**。项目架构和接口设计已完成，代码骨架待实现。

- ✅ 完整设计文档（1371 行）
- ✅ 拆分后的模块化文档（docs/）
- ✅ 测试设计文档（tests/design/）
- ⬜ 源代码实现
- ⬜ 构建配置（pyproject.toml, Makefile）
- ⬜ CI/CD 配置

---

## 快速开始

```bash
# 1. 克隆仓库
git clone <repo-url>
cd kernel-rag-mcp

# 2. 安装依赖（待实现）
pip install -e ".[dev]"

# 3. 注册内核仓库
cd ~/linux
kernel-rag init

# 4. 建立基线索引
kernel-rag index --base

# 5. 启动 MCP Server
kernel-rag serve

# 6. 在 Claude Code / Cursor / OpenCode 中配置 MCP
kernel-rag mcp install --client claude-code
```

---

## 文档目录

| 目录 | 内容 |
|------|------|
| `docs/design/` | 核心设计原则、里程碑规划 |
| `docs/architecture/` | 技术架构概览、分层设计 |
| `docs/mcp-tools/` | MCP 工具清单、路由策略、集成方式 |
| `docs/indexer/` | 索引层设计（代码、Git、Kconfig、Patch 类型、因果图谱） |
| `docs/retriever/` | 检索引擎设计（混合召回、上下文组装） |
| `docs/storage/` | 存储层设计（索引存放策略、版本管理） |
| `docs/git-history/` | Git 历史索引设计（commit、diff、blame、Patch 类型） |
| `docs/kconfig/` | Kconfig 解析与形式化建模设计 |
| `docs/causal-graph/` | 变更因果图谱设计 |
| `docs/integration/` | 与 OpenCode/Claude Code/Cursor 的集成 |
| `docs/ops/` | 运维监控、数据一致性、性能目标 |

---

## 测试设计目录

| 目录 | 内容 |
|------|------|
| `tests/design/indexer.md` | 索引层测试设计 |
| `tests/design/retriever.md` | 检索层测试设计 |
| `tests/design/storage.md` | 存储层测试设计 |
| `tests/design/mcp-tools.md` | MCP 工具层测试设计 |
| `tests/design/git-history.md` | Git 历史与因果图谱测试设计 |
| `tests/design/kconfig.md` | Kconfig 索引测试设计 |
| `tests/design/e2e.md` | 端到端测试设计 |
| `tests/design/integration.md` | 集成测试设计 |
| `tests/design/fixtures.md` | 测试 Fixtures 设计 |

---

## 核心设计原则

1. **精确溯源优先**：所有结果必须包含文件路径 + 精确行号
2. **指针式索引**：索引不存代码原文，只存向量+元数据+图谱
3. **内核原生感知**：Kconfig 条件编译、头文件依赖、宏展开、调用链追踪
4. **Kconfig 精确建模**：复用 kconfiglib + kclause + Z3 工具链
5. **Git 历史原生索引**：本地 Git 是唯一真相源
6. **本地优先**：索引本地生成，源码不离开用户机器
7. **MCP 原生**：首要接口是 MCP Server

---

## 架构概览

```plain
AI 客户端 (Claude Code / Cursor / OpenCode)
    │ MCP 协议
    ▼
kernel-rag-mcp Server (FastMCP / stdio / HTTP)
    ├── kernel_query (统一路由网关)
    └── 智能路由引擎
    │
    ▼
检索引擎 (Hybrid Search + Context Assembler)
    │
    ▼
存储层 (Qdrant + Meilisearch + Graph DB)
    │
    ▼
索引生成器 (Tree-sitter + kconfiglib + Git Parser)
    │
    ▼
本地内核源码 (~/linux) + 索引数据库 (~/.kernel-rag/)
```

---

## 里程碑

- **Phase 1**（4 周）：单系统 MVP（sched 子系统）
- **Phase 2**（4 周）：完整内核 + Kconfig + 大版本粒度
- **Phase 3**（4 周）：Patch 类型 + 变更因果图谱 + Rust-for-Linux
- **Phase 4**（持续）：CI 与生态集成

详见 [docs/design/roadmap.md](docs/design/roadmap.md)

---

## 许可证

- 项目代码：MIT/Apache-2.0
- 索引数据：仅含指针信息，不含代码原文
- 内核引用：用户需自行遵守 GPL-2.0

---

## 参考

- [设计文档全集](docs/)
- [AGENTS.md](AGENTS.md) - OpenCode 会话指南
- [原始设计文档](Kernel-RAG-MCP%20设计目标.md)
