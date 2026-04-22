# 检索层测试设计

> 本文档描述检索引擎的测试策略和用例设计。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 测试范围

检索层包含以下子模块：
- 混合召回（Hybrid Search）
- 上下文组装（Context Assembler）
- 因果图谱遍历（Causal Traverser）
- Kconfig 过滤与验证

---

## 2. 混合召回测试

### 2.1 Dense 召回测试

| 测试用例 | 查询 | 预期结果 | 优先级 |
|----------|------|----------|--------|
| 语义搜索 | "CFS vruntime 更新" | 召回 `update_curr()` | P0 |
| 同义词搜索 | "进程调度器" | 召回 scheduler 相关代码 | P0 |
| 英文查询 | "how CFS updates vruntime" | 召回 `update_curr()` | P1 |
| 中文查询 | "CFS 怎么更新 vruntime" | 召回 `update_curr()` | P1 |

### 2.2 Sparse 召回测试

| 测试用例 | 查询 | 预期结果 |
|----------|------|----------|
| 精确符号 | "schedule()" | 召回 schedule 函数定义 |
| 前缀匹配 | "sched_" | 召回所有 sched_ 前缀函数 |
| 结构体查询 | "struct task_struct" | 召回 task_struct 定义 |

### 2.3 RRF 融合测试

| 测试用例 | 场景 | 验证点 |
|----------|------|--------|
| 融合排序 | Dense 和 Sparse 结果有重叠 | 重叠项排名提升 |
| 互补召回 | Dense 召回 A，Sparse 召回 B | 最终结果包含 A 和 B |

---

## 3. 上下文组装测试

| 测试用例 | 召回目标 | 验证组装内容 |
|----------|----------|-------------|
| 函数实现召回 | `update_curr()` | 包含头文件声明、调用者、相关结构体 |
| 结构体召回 | `struct task_struct` | 包含所有使用该结构体的函数 |
| 跨文件召回 | `kernel/sched/core.c` | 包含相关的 `kernel/sched/fair.c` 代码 |

---

## 4. Kconfig 过滤测试

| 测试用例 | 配置条件 | 验证点 |
|----------|----------|--------|
| 简单过滤 | `CONFIG_SMP=y` | 仅召回 SMP 相关代码 |
| 组合过滤 | `CONFIG_SMP=y ∧ CONFIG_NUMA=n` | 召回 SMP 且非 NUMA 代码 |
| 不可满足配置 | `CONFIG_SMP=y ∧ CONFIG_SMP=n` | 返回 UNSAT 错误 |
| 依赖闭包 | `CONFIG_SCHED_MC` | 自动包含所有依赖配置 |

---

## 5. 性能测试

| 测试用例 | 目标 |
|----------|------|
| 基线查询延迟 | P95 ≤ 500ms |
| Delta 叠加查询 | P95 ≤ 800ms（5 个 delta） |
| 因果图谱查询 | ≤ 200ms |
| 并发查询 | 10 并发请求，P95 ≤ 1s |

---

## 6. 端到端测试

| 测试用例 | 用户问题 | 验证点 |
|----------|----------|--------|
| 语义查询 | "CFS 怎么更新 vruntime？" | 返回 `update_curr()` 实现 + 行号 |
| 精确查询 | "schedule() 在哪一行？" | 返回精确文件和行号 |
| 历史查询 | "这个函数在 6.6 到 6.12 之间变了什么？" | 返回 diff 摘要 |
| Kconfig 查询 | "开启 CONFIG_SMP 且关闭 CONFIG_NUMA 能编译吗？" | 返回 SAT/UNSAT |
| 因果查询 | "这个 bug 是哪个 commit 引入的？" | 返回完整因果链 |
