# 性能补丁索引设计

> 本文档描述性能补丁的索引设计，包括多源融合识别、特性关联、性能数据提取和索引结构。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 设计目标

1. **高精度识别**：解决"只看标题漏招率极高"的问题，通过多源融合（标题+正文+diff+统计+专家）实现 ≥95% 的召回率
2. **特性关联**：识别哪些性能补丁属于同一特性/优化主题，构建"特性 → 系列补丁"的映射
3. **性能数据提取**：提取量化指标（延迟、吞吐、CPU 周期等），支持"按性能提升幅度排序"
4. **演进追踪**：追踪同一性能特性的完整演进（初始实现 → 优化 → 修复回归 → backport）

---

## 2. 多源融合识别架构

```plain
Commit (性能候选)
    │
    ├── 标题分析 ──→ 关键词匹配 ──→ 信号强度: 0.2
    │
    ├── 正文分析 ──→ 性能声明/量化数据提取 ──→ 信号强度: 0.15
    │
    ├── Diff 分析 ──→ 代码指纹匹配 ──→ 信号强度: 0.45 (最强)
    │
    ├── 文件路径分析 ──→ 热路径匹配 ──→ 信号强度: 0.1
    │
    ├── 统计特征 ──→ 删增比/影响范围 ──→ 信号强度: 0.05
    │
    └── 社区元数据 ──→ 专家关联 ──→ 信号强度: 0.05
    │
    ▼
综合打分模型 ──→ performance / probably_performance / other
    │
    ▼
性能补丁索引 ──→ 注入向量库 + 因果图谱 + 特性图谱
```

---

## 3. 性能数据提取

### 3.1 量化指标提取

从 commit message 中提取结构化性能数据：

```json
{
  "performance_metrics": {
    "latency": {
      "before": "100us",
      "after": "20us",
      "improvement": "80%",
      "benchmark": "hackbench"
    },
    "throughput": {
      "before": "1000 ops/s",
      "after": "1500 ops/s",
      "improvement": "50%",
      "benchmark": "fio"
    },
    "cpu_cycles": {
      "before": "500 cycles/op",
      "after": "300 cycles/op",
      "improvement": "40%",
      "benchmark": "perf stat"
    },
    "memory": {
      "before": "10MB",
      "after": "8MB",
      "improvement": "20%",
      "benchmark": "slabinfo"
    }
  }
}
```

### 3.2 提取规则

| 模式类型 | 正则表达式示例 | 提取字段 |
|----------|---------------|----------|
| 百分比提升 | `improve.*by\s+~?(\d+)%` | improvement_percent |
| 延迟对比 | `reduces?\s+latency\s+from\s+(\d+\w+)\s+to\s+(\d+\w+)` | latency_before, latency_after |
| 吞吐对比 | `increase.*throughput.*from\s+(\d+)\s+to\s+(\d+)` | throughput_before, throughput_after |
| 周期对比 | `(\d+)\s+cycles.*per.*op` | cycles_per_op |
| Benchmark 引用 | `Tested with (\w+)` | benchmark_tool |

---

## 4. 特性关联设计

### 4.1 问题背景

多个补丁可能属于同一特性或优化主题。例如：
- `sched: introduce per-CPU vruntime` (v6.12)
- `sched: optimize per-CPU vruntime for NUMA` (v6.12.5)
- `sched: fix regression in per-CPU vruntime` (v6.12.8)
- `sched: backport per-CPU vruntime to 5.15` (stable)

用户问："per-CPU vruntime 这个特性的完整演进是什么？"

### 4.2 特性识别策略

**策略一：语义聚类**
- 对性能补丁的标题和正文做 Embedding
- 使用聚类算法（HDBSCAN/DBSCAN）将相似补丁分组
- 每组代表一个"特性主题"

**策略二：代码指纹关联**
- 提取每个性能补丁修改的核心函数/数据结构
- 如果补丁 A 和补丁 B 修改了同一组函数，可能属于同一特性
- 示例：都修改 `update_curr()` 和 `sched_entity` 的补丁属于"vruntime 优化"特性

**策略三：补丁系列关联**
- 利用 commit message 中的系列标识：
  - `[PATCH v2]` / `[PATCH v3]` 前缀
  - `Link:` 标签指向同一邮件线程
  - `References:` 标签
- 同一系列的补丁通常属于同一特性

**策略四：时间窗口关联**
- 同一作者在短时间内（如 2 周内）提交的多个性能补丁
- 修改同一子系统的相关文件
- 可能属于同一特性的迭代

### 4.3 特性图谱构建

```python
# 特性节点
feature_node = {
    "feature_id": "feat_sched_percpu_vruntime_2024",
    "feature_name": "per-CPU vruntime optimization",
    "subsys": "sched",
    "keywords": ["per-cpu", "vruntime", "sched_entity"],
    "core_functions": ["update_curr", "pick_next_task"],
    "core_structs": ["sched_entity", "cfs_rq"],
    "commits": [
        {
            "hash": "a1b2c3d",
            "title": "sched: introduce per-CPU vruntime",
            "type": "feature",
            "date": "2024-01-15",
            "performance_metrics": {...}
        },
        {
            "hash": "e4f5g6h",
            "title": "sched: optimize per-CPU vruntime for NUMA",
            "type": "performance",
            "date": "2024-03-20",
            "performance_metrics": {...}
        },
        {
            "hash": "i7j8k9l",
            "title": "sched: fix regression in per-CPU vruntime",
            "type": "bugfix",
            "date": "2024-04-10",
            "fixes": "e4f5g6h"
        }
    ],
    "evolution_chain": [
        ("a1b2c3d", "INTRODUCES", "feat_sched_percpu_vruntime_2024"),
        ("e4f5g6h", "OPTIMIZES", "feat_sched_percpu_vruntime_2024"),
        ("i7j8k9l", "FIXES_REGRESSION_IN", "e4f5g6h")
    ],
    "total_performance_gain": "65% latency reduction",
    "status": "stable"  # active / stable / deprecated / reverted
}
```

---

## 5. 索引结构

### 5.1 性能补丁专用索引

```json
{
  "type": "performance_patch",
  "hash": "e33f3b9...",
  "title": "sched: optimize per-CPU vruntime for NUMA",
  "feature_id": "feat_sched_percpu_vruntime_2024",
  "feature_name": "per-CPU vruntime optimization",
  
  "classification": {
    "type_tags": ["performance", "optimization"],
    "confidence": 0.95,
    "signals": {
      "title_keyword": 0.2,
      "body_claim": 0.15,
      "diff_fingerprint": 0.45,
      "hot_path_file": 0.1,
      "statistical": 0.05,
      "expert_review": 0.05
    }
  },
  
  "performance_data": {
    "metrics": {
      "latency": {"before": "100us", "after": "20us", "improvement": "80%"},
      "throughput": {"before": "1000", "after": "1500", "improvement": "50%"}
    },
    "benchmark_tools": ["hackbench", "schbench"],
    "test_environment": "2-socket Intel Xeon, 64 cores",
    "workload": "high-frequency scheduling"
  },
  
  "code_fingerprints": [
    "per_cpu_add",
    "this_cpu_inc",
    "spin_lock_removal",
    "rcu_conversion"
  ],
  
  "impact_analysis": {
    "modified_files": ["kernel/sched/fair.c", "kernel/sched/core.c"],
    "modified_functions": ["update_curr", "pick_next_task"],
    "callers_affected": 15,
    "kconfig_impact": ["CONFIG_SMP", "CONFIG_NUMA"]
  },
  
  "evolution_context": {
    "feature_introduced_by": "a1b2c3d",
    "previous_optimization": null,
    "regression_fixes": ["i7j8k9l"],
    "backport_commits": ["m0n1o2p"]
  }
}
```

### 5.2 特性级索引

```json
{
  "type": "performance_feature",
  "feature_id": "feat_sched_percpu_vruntime_2024",
  "feature_name": "per-CPU vruntime optimization",
  "subsys": "sched",
  
  "summary": {
    "total_commits": 5,
    "performance_commits": 3,
    "bugfix_commits": 1,
    "feature_commits": 1,
    "total_performance_gain": "65% latency reduction",
    "timeline": "2024-01-15 to 2024-06-30"
  },
  
  "commits": [
    {"hash": "a1b2c3d", "type": "feature", "date": "2024-01-15"},
    {"hash": "e4f5g6h", "type": "performance", "date": "2024-03-20"},
    {"hash": "i7j8k9l", "type": "bugfix", "date": "2024-04-10"}
  ],
  
  "evolution": {
    "status": "stable",
    "current_version": "v6.12.5",
    "backported_to": ["v5.15.112", "v6.1.25"],
    "known_regressions": ["i7j8k9l"]
  }
}
```

---

## 6. 查询能力扩展

### 6.1 性能补丁查询

| MCP Tool | 功能 | 触发场景 |
|----------|------|----------|
| `git_search_by_type(["performance"], ...)` | 按类型筛选 | "最近有哪些性能优化" |
| `git_find_performance_regression_fix(...)` | 查找性能回归修复 | "最近修复了哪些性能回归" |
| `performance_feature_query(feature_name)` | 查询特性完整演进 | "per-CPU vruntime 的完整演进" |
| `performance_compare(v1, v2, subsys)` | 对比两个版本性能 | "6.12 到 6.13 sched 性能变化" |
| `performance_top_k(subsys, since, metric)` | 按性能提升排序 | "sched 子系统 Top 10 性能优化" |
| `performance_impact(commit_hash)` | 查询性能影响范围 | "这个补丁影响了哪些性能指标" |

### 6.2 查询示例

> **用户问**："per-CPU vruntime 这个特性的完整演进是什么？性能提升了多少？"

**RAG 行为**：
1. 语义搜索召回 feature_name 含 "per-CPU vruntime" 的特性节点
2. 读取特性图谱中的 commits 列表
3. 按时间线组装演进：
   - v6.12: 初始引入 (feature)
   - v6.12.5: NUMA 优化 (performance, +50%)
   - v6.12.8: 回归修复 (bugfix)
   - stable: backport 到 5.15
4. 汇总总性能提升：65% latency reduction
5. 返回结构化报告

---

## 7. 与现有索引的协同

```plain
性能补丁索引
    │
    ├── 注入代码 RAG ──→ 向量库（Qdrant）
    │   └── 性能补丁的代码上下文可被语义搜索召回
    │
    ├── 注入因果图谱 ──→ 图存储（NetworkX/Neo4j）
    │   └── Fixes: / Introduced-by: / 特性演进链
    │
    ├── 注入稀疏索引 ──→ Meilisearch
    │   └── 按特性名、函数名、优化类型筛选
    │
    └── 注入特性图谱 ──→ 专用图结构
        └── 特性 → 补丁系列 → 演进关系
```

---

## 8. 实现要点

### 8.1 性能数据提取器

```python
class PerformanceDataExtractor:
    """从 commit message 中提取结构化性能数据。"""
    
    PATTERNS = {
        "latency": r"reduces?\s+latency\s+from\s+(\d+\w*)\s+to\s+(\d+\w*)",
        "throughput": r"increase.*throughput.*from\s+(\d+)\s+to\s+(\d+)",
        "percentage": r"improve.*by\s+~?(\d+)%",
        "benchmark": r"Tested with (\w+)",
        "cycles": r"(\d+)\s+cycles.*per.*op"
    }
    
    def extract(self, commit_message: str) -> dict:
        """提取性能指标。"""
        pass
```

### 8.2 特性关联器

```python
class FeatureAssociator:
    """将性能补丁关联到特性主题。"""
    
    def cluster_by_semantic(self, commits: list) -> dict:
        """基于语义相似度聚类。"""
        pass
    
    def cluster_by_code_fingerprint(self, commits: list) -> dict:
        """基于代码指纹关联。"""
        pass
    
    def cluster_by_series(self, commits: list) -> dict:
        """基于补丁系列关联。"""
        pass
    
    def build_feature_graph(self, clusters: dict) -> FeatureGraph:
        """构建特性图谱。"""
        pass
```

### 8.3 特性图谱存储

```python
class FeatureGraphStore:
    """特性图谱的存储和查询。"""
    
    def add_feature(self, feature: FeatureNode):
        pass
    
    def add_commit_to_feature(self, feature_id: str, commit: CommitNode):
        pass
    
    def query_feature_evolution(self, feature_id: str) -> EvolutionChain:
        pass
    
    def query_performance_top_k(self, subsys: str, k: int) -> list:
        pass
```

---

## 9. 数据一致性

| 检查点 | 机制 | 目的 |
|--------|------|------|
| 性能数据校验 | 提取的指标是否合理（如提升 > 1000% 告警） | 防止提取错误 |
| 特性关联验证 | 人工抽查 10% 的特性关联结果 | 确保聚类质量 |
| 演进链闭环 | 验证特性中的所有 commit 是否存在于索引中 | 防止断链 |
| 重复检测 | 同一 commit 不重复计入多个特性 | 防止重复计数 |

---

## 10. 总结

> 性能补丁索引的核心价值不仅在于"识别出这是性能补丁"，更在于：
> 1. **提取量化数据**：让用户问"提升了多少"时有精确答案
> 2. **关联特性演进**：让用户问"这个特性的完整历史"时有完整时间线
> 3. **构建性能知识库**：让 AI 在回答内核性能问题时，引用真实的优化案例和数据
