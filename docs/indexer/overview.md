# 索引层设计

> 本文档描述索引生成器的设计，包括代码索引、Git 历史索引、Kconfig 索引、Patch 类型索引和变更因果图谱索引。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 索引层目标

- **多版本支持**：支持对任意 Git tag/commit 建立索引（`v5.15`、`v6.6.y`、`v6.12` 等）
- **子系统级索引**：允许单独索引 `kernel/sched/`、`mm/`、`net/` 等子系统，降低资源门槛
- **增量更新**：基于 Git diff 的增量索引，级联深度可控（Depth 0/1/2/Full）
- **混合切分策略**：
  - 函数/结构体/宏定义级（AST 精确切分）
  - 文件级摘要（模块说明）
  - Kconfig/Makefile 元数据（编译条件）
- **多架构 Embedding**：支持 `jina-embeddings-v2-base-code`、`BAAI/bge-m3` 等代码专用模型，支持本地 CPU/GPU 推理

---

## 2. 代码语义索引（Code Indexer）

### 2.1 解析流程

```plain
C/H 源文件
    │
    ├── Tree-sitter 解析 ──→ AST
    │
    ├── 函数边界识别 ──→ 函数级 chunk
    ├── 结构体/宏识别 ──→ 类型级 chunk
    ├── Kconfig 条件提取 ──→ 条件分支 chunk
    └── 文件级摘要 ──→ 模块说明 chunk
    │
    └── Embedding 模型 ──→ 向量
            │
            ├── jina-embeddings-v2-base-code
            ├── BAAI/bge-m3
            └── 其他代码专用模型
```

### 2.2 Chunk 类型

| Chunk 类型 | 边界识别 | 元数据 |
|-----------|----------|--------|
| 函数定义 | AST 函数节点 | 函数名、参数列表、返回类型、文件、行号 |
| 结构体/联合体 | AST 结构体节点 | 类型名、字段列表、文件、行号 |
| 宏定义 | `#define` 预处理 | 宏名、参数、展开提示、文件、行号 |
| Kconfig 条件分支 | `#ifdef CONFIG_XXX` | 条件表达式、依赖配置项、文件、行号 |
| 文件级摘要 | 文件头注释 | 模块名、作者、许可证、文件路径 |

### 2.3 宏展开标注

对高频宏做预展开标注：
- `container_of(ptr, type, member)` → 标注为"从成员指针获取父结构体"
- `list_for_each_entry(pos, head, member)` → 标注为"链表遍历"
- `rcu_read_lock()` / `rcu_read_unlock()` → 标注为"RCU 读临界区"

---

## 3. Git 历史索引（Git History Indexer）

详见 [docs/git-history/indexer.md](indexer.md)

---

## 4. Kconfig 索引（Kconfig Indexer）

详见 [docs/kconfig/indexer.md](indexer.md)

---

## 5. Patch 类型索引（Type Indexer）

详见 [docs/git-history/patch-types.md](../git-history/patch-types.md)

---

## 6. 变更因果图谱索引（Causal Indexer）

详见 [docs/causal-graph/indexer.md](indexer.md)

---

## 7. 索引调度入口

```python
# src/kernel_rag_mcp/indexer/main.py

class IndexScheduler:
    """统一索引调度器，协调各子索引器的工作。"""
    
    def index_base(self, repo_path: str, version: str):
        """建立全量基线索引。"""
        pass
    
    def index_incremental(self, repo_path: str, version: str, changed_files: list):
        """基于变更文件列表做增量索引。"""
        pass
    
    def index_subsystem(self, repo_path: str, version: str, subsystems: list):
        """仅索引指定子系统。"""
        pass
    
    def merge_deltas(self, version: str, target: str):
        """合并基线 + 所有 delta 为完整索引。"""
        pass
```

---

## 8. 索引生命周期

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

---

## 9. 性能目标

| 指标 | 目标 | 备注 |
|------|------|------|
| 全量索引时间（消费级 GPU） | ≤ 1 小时 | RTX 4090，完整内核 |
| 全量索引时间（纯 CPU 16核） | ≤ 8 小时 | 可接受的后台任务 |
| 增量更新时间（普通 commit） | ≤ 3 分钟 | 纯 CPU |
| 索引磁盘占用（基线） | ≤ 2.5GB | 指针式索引，不含原文 |
| 索引磁盘占用（单 delta） | ≤ 50MB | 仅变更文件 |
