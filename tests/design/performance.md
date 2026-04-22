# 性能补丁测试设计

> 本文档描述性能补丁识别、特性关联和性能数据提取的测试策略。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 测试范围

- 性能补丁多源融合识别
- 性能数据提取（量化指标）
- 特性关联（语义聚类、代码指纹、补丁系列）
- 特性图谱构建和查询
- 性能补丁索引注入和召回

---

## 2. 性能补丁识别测试

### 2.1 单源识别测试

| 测试用例 | 输入 | 预期输出 | 优先级 |
|----------|------|----------|--------|
| 标题关键词匹配 | `"sched: optimize vruntime"` | performance 标签 | P0 |
| 标题无关键词 | `"tcp: switch to rhashtable"` | 需其他信号补充 | P0 |
| 正文性能声明 | `"improves by 15%"` | performance 标签 | P0 |
| 正文无声明 | 纯技术描述 | 依赖 diff 信号 | P0 |
| Diff 代码指纹 | `+ this_cpu_add()` | performance 标签 | P0 |
| Diff 反模式 | `+ pr_err()` | 非 performance | P0 |
| 热路径文件 | `mm/page_alloc.c` | 加分项 | P1 |
| 专家关联 | `Reviewed-by: Mel Gorman` | 加分项 | P1 |

### 2.2 多源融合测试

| 测试用例 | 标题 | 正文 | Diff | 预期得分 | 预期标签 |
|----------|------|------|------|----------|----------|
| 强信号全中 | optimize | improves 15% | +per_cpu | 0.95 | performance |
| 标题弱+正文强 | use per-cpu | reduces contention | +spin_lock | 0.85 | performance |
| 标题无+正文无+Diff强 | switch to rhashtable | 技术描述 | +READ_ONCE | 0.65 | probably_performance |
| 全弱信号 | cleanup | 无 | +pr_err | 0.1 | other |
| 回归修复 | fix regression | Fixes: abc | -bug | 0.55 | bugfix+performance+regression |

### 2.3 边界测试

| 测试用例 | 输入 | 验证点 |
|----------|------|--------|
| 模糊标题 | `"mm: improve page allocation"` | improve 是弱信号，需其他源确认 |
| 混合类型 | `"sched: refactor and optimize"` | 同时标记 refactor + performance |
| 反模式干扰 | `"fix bug in per-cpu path"` | per-cpu 是性能词但 fix 是 bugfix |
| 大量 debug 代码 | `+ #ifdef CONFIG_DEBUG_FS` | 排除 performance |

---

## 3. 性能数据提取测试

### 3.1 正则提取测试

| 测试用例 | 输入文本 | 预期提取 |
|----------|----------|----------|
| 百分比提升 | `"improves performance by ~15%"` | improvement: 15% |
| 延迟对比 | `"reduces latency from 100us to 20us"` | before: 100us, after: 20us |
| 吞吐对比 | `"increases throughput from 1000 to 1500 ops/s"` | before: 1000, after: 1500 |
| 周期对比 | `"500 cycles per operation"` | cycles: 500 |
| Benchmark 引用 | `"Tested with hackbench"` | benchmark: hackbench |
| 多指标混合 | `"latency: 100us→20us, throughput: 1000→1500"` | 提取两个指标 |
| 无性能数据 | `"Fixes null pointer dereference"` | 空结果 |

### 3.2 数据校验测试

| 测试用例 | 输入 | 验证点 |
|----------|------|--------|
| 合理范围 | improvement: 50% | 通过 |
| 极端值 | improvement: 10000% | 告警（可能提取错误） |
| 单位不一致 | latency: 100ms → 20us | 正确处理单位转换 |
| 负数提升 | improvement: -10% | 标记为性能退化 |

---

## 4. 特性关联测试

### 4.1 语义聚类测试

| 测试用例 | 输入 commits | 预期聚类 |
|----------|-------------|----------|
| 同一特性 | "per-CPU vruntime", "optimize per-CPU vruntime", "fix per-CPU vruntime" | 同一类 |
| 不同特性 | "per-CPU vruntime", "RCU lockless lookup", "batch skb alloc" | 不同类 |
| 模糊边界 | "optimize scheduler", "optimize vruntime" | 可能同类或子类 |

### 4.2 代码指纹关联测试

| 测试用例 | Commit A 修改 | Commit B 修改 | 预期关联 |
|----------|--------------|--------------|----------|
| 同一函数 | `update_curr()` | `update_curr()` | 强关联 |
| 同一结构体 | `struct sched_entity` | `struct sched_entity` | 强关联 |
| 调用关系 | `schedule()` | `pick_next_task()` | 中关联 |
| 无关函数 | `update_curr()` | `tcp_sendmsg()` | 无关联 |

### 4.3 补丁系列关联测试

| 测试用例 | Commit A | Commit B | 预期关联 |
|----------|----------|----------|----------|
| 同一系列 | `[PATCH 1/3]` | `[PATCH 2/3]` | 强关联 |
| 版本迭代 | `[PATCH v1]` | `[PATCH v2]` | 强关联 |
| 同一线程 | Link: thread-123 | Link: thread-123 | 强关联 |
| 不同线程 | Link: thread-123 | Link: thread-456 | 无关联 |

### 4.4 时间窗口关联测试

| 测试用例 | Commit A | Commit B | 预期关联 |
|----------|----------|----------|----------|
| 短时间内 | 2024-01-01 | 2024-01-05 | 可能关联 |
| 长时间间隔 | 2024-01-01 | 2024-06-01 | 不太可能 |
| 同一作者 | Author: Alice | Author: Alice | 加分项 |
| 不同子系统 | `kernel/sched/` | `mm/page_alloc` | 减分项 |

---

## 5. 特性图谱测试

### 5.1 图谱构建测试

| 测试用例 | 输入 | 验证点 |
|----------|------|--------|
| 简单特性 | 3 个关联 commit | 1 个特性节点，3 个 commit 边 |
| 复杂特性 | 10 个 commit，含 regression 和 fix | 完整演进链 |
| 多特性共存 | 2 个不相关特性 | 2 个独立特性节点 |
| 特性合并 | 2 个相关特性被识别为独立 | 后期合并为 1 个 |

### 5.2 图谱查询测试

| 测试用例 | 查询 | 预期结果 |
|----------|------|----------|
| 特性演进 | `feature_id="feat_xxx"` | 按时间线返回所有 commit |
| 性能 Top K | `subsys="sched", k=5` | 返回 Top 5 性能优化 |
| 版本对比 | `v6.12 vs v6.13, subsys="mm"` | 返回性能变化摘要 |
| 影响分析 | `commit_hash="abc"` | 返回影响的性能指标 |

---

## 6. 索引注入和召回测试

### 6.1 注入测试

| 测试用例 | 操作 | 验证点 |
|----------|------|--------|
| 向量注入 | 性能补丁 → Qdrant | 向量可语义搜索召回 |
| 稀疏索引 | 性能补丁 → Meilisearch | 可按特性名筛选 |
| 图谱注入 | 特性节点 → Graph DB | 可查询演进链 |
| 元数据注入 | 性能数据 → Metadata Store | 可按指标排序 |

### 6.2 召回测试

| 测试用例 | 查询 | 验证点 |
|----------|------|--------|
| 语义召回 | "per-CPU vruntime 优化" | 召回相关性能补丁 |
| 精确筛选 | `type_tags=["performance"]` | 仅返回 performance |
| 范围筛选 | `since="v6.12", until="v6.13"` | 仅返回范围内 |
| 子系统筛选 | `subsys="sched"` | 仅返回 sched |
| 排序 | `sort_by="performance_gain"` | 按提升幅度排序 |

---

## 7. 端到端场景测试

### 场景一：识别隐藏性能补丁

```
输入："tcp: switch to rhashtable for ehash"

验证点：
1. 标题无性能关键词 → 标题信号弱
2. 正文可能无性能声明 → 正文信号弱
3. Diff 含 rhashtable 替换 → 代码指纹强（rhashtable 是性能优化）
4. 文件路径 `net/ipv4/` → 热路径文件
5. 综合得分 ≥ 0.5 → 标记为 performance
```

### 场景二：特性演进追踪

```
输入："per-CPU vruntime 特性的完整演进"

验证点：
1. 语义搜索召回 feature_name 匹配的特性节点
2. 返回特性下的所有 commit（按时间排序）
3. 包含：feature commit + optimization commit + bugfix commit
4. 汇总总性能提升数据
5. 包含 backport 信息
```

### 场景三：性能 Top K 查询

```
输入："sched 子系统 Top 5 性能优化"

验证点：
1. 筛选 subsys="sched" + type_tags=["performance"]
2. 按 performance_metrics.improvement 排序
3. 返回 Top 5
4. 每个结果含：commit、标题、提升幅度、影响的函数
```

---

## 8. Fixtures

```plain
tests/fixtures/performance/
├── sample-commits/
│   ├── explicit-performance/       # 标题明确含性能词
│   ├── hidden-performance/         # 标题无性能词但代码是
│   ├── regression-fixes/           # 性能回归修复
│   └── non-performance/            # 非性能补丁（负样本）
├── sample-features/
│   ├── sched-percpu-vruntime/      # 完整特性演进（5 个 commit）
│   ├── mm-slab-optimization/       # 另一个特性
│   └── net-rhashtable-migration/   # 隐藏性能特性
├── performance-data/
│   ├── latency-comparisons.txt     # 延迟对比样本
│   ├── throughput-comparisons.txt  # 吞吐对比样本
│   └── benchmark-references.txt    # Benchmark 引用样本
└── expected-classifications.json   # 预期分类结果
```

---

## 9. 性能测试

| 测试用例 | 目标 |
|----------|------|
| 单 commit 识别速度 | ≤ 100ms |
| 1000 commit 批量识别 | ≤ 30 秒 |
| 特性聚类（1000 commits） | ≤ 60 秒 |
| 特性查询延迟 | ≤ 200ms |
| Top K 排序查询 | ≤ 500ms |
