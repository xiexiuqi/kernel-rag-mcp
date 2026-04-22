# 检索层设计

> 本文档描述检索引擎的设计，包括混合召回、上下文组装和路由策略。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 检索层目标

- **混合召回**：Dense（向量）+ Sparse（BM25 符号名）+ Reciprocal Rank Fusion
- **Kconfig 过滤**：查询时可指定 `CONFIG_SMP=y/n` 过滤条件编译分支
- **Kconfig 可满足性验证**：用 Z3 验证用户查询的配置组合是否合法（如 `CONFIG_SMP=y ∧ CONFIG_NUMA=n` 是否可满足）
- **调用链召回**：支持 `get_callers(symbol, depth)` 和 `get_callees(symbol, depth)`
- **跨文件上下文组装**：自动拉取被召回函数的声明（`.h`）、实现（`.c`）和依赖类型定义
- **版本差异检索**：对比两个 Git 版本间某函数/符号的变化
- **Git 历史召回**：语义搜索 commit message 和 diff 上下文，回答变更原因
- **Patch 类型筛选**：按 `bugfix`/`performance`/`refactor`/`feature` 等标签多维过滤 commits
- **变更因果召回**：基于 Fixes:/Introduced-by: 等标签的图谱遍历

---

## 2. 混合召回（Hybrid Search）

### 2.1 Dense 召回（语义相似度）

- 使用 Qdrant 向量数据库
- 查询文本经 Embedding 模型编码为向量
- 召回 top-k 最相似的代码 chunk

### 2.2 Sparse 召回（BM25 符号匹配）

- 使用 Meilisearch 稀疏索引
- 基于函数名、结构体名、宏名等符号的文本匹配
- 对精确符号查询（如 "schedule()"）召回率更高

### 2.3 RRF 融合（Reciprocal Rank Fusion）

```python
# RRF 公式
score = Σ(1 / (k + rank_i))

# 其中 rank_i 是第 i 个召回列表中的排名
# k 为常数（通常取 60）
```

融合 Dense 和 Sparse 的结果，生成最终排序。

---

## 3. 上下文组装（Context Assembler）

### 3.1 跨文件组装策略

当召回一个函数实现时，自动拉取：
- 头文件中的声明（函数签名、结构体定义）
- 同一文件中相关的辅助函数
- 被调用函数的声明（一级深度）
- 相关的 Kconfig 条件说明

### 3.2 组装示例

```python
# 用户查询："CFS 怎么更新 vruntime？"
# 召回 update_curr() 的实现

assembled_context = {
    "primary": "kernel/sched/fair.c:update_curr() 实现",
    "declarations": "include/linux/sched.h:struct sched_entity 定义",
    "helpers": "kernel/sched/fair.c:__update_curr() 辅助函数",
    "callers": "kernel/sched/core.c:scheduler_tick() 调用点",
    "kconfig": "CONFIG_FAIR_GROUP_SCHED 条件说明"
}
```

---

## 4. Kconfig 过滤

查询时可指定 Kconfig 条件：

```python
kernel_search(
    query="NUMA 内存分配",
    kconfig={"CONFIG_NUMA": "y", "CONFIG_SMP": "y"}
)
```

系统会：
1. 用 Z3 验证该配置组合是否可满足
2. 过滤掉不满足条件的代码分支
3. 优先召回与 `CONFIG_NUMA=y` 相关的 chunk

---

## 5. 性能目标

| 指标 | 目标 | 备注 |
|------|------|------|
| 查询延迟（P95，基线） | ≤ 500ms | 本地 Qdrant |
| 查询延迟（基线 + 5 个 delta） | ≤ 800ms | 叠加查询开销可控 |
| 查询延迟（合并后） | ≤ 500ms | 与基线一致 |
| 变更因果图谱查询 | ≤ 200ms | 图数据库或内存索引 |
