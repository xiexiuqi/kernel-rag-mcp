# 端到端测试设计

> 本文档描述 Kernel-RAG-MCP 的端到端测试场景和验收标准。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 测试目标

验证整个系统从用户提问到返回结果的完整链路，确保各子系统协同工作。

---

## 2. 测试场景

### 2.1 场景一：内核新人学习

**用户**："CFS 怎么更新 vruntime？"

**预期行为**：
1. AI 识别为语义搜索意图
2. 调用 `kernel_search("CFS vruntime update")`
3. 检索引擎召回 `update_curr()` 实现
4. 上下文组装拉取相关声明和结构体
5. 返回带行号的结果
6. AI 生成解释

**验收标准**：
- 返回结果包含 `kernel/sched/fair.c` 中 `update_curr()` 的实现
- 包含精确行号
- 包含 `struct sched_entity` 的定义
- 响应时间 ≤ 2 秒

---

### 2.2 场景二：精确符号跳转

**用户**："schedule() 在哪一行？"

**预期行为**：
1. AI 识别为精确符号查询
2. 调用 `ctags_jump("schedule")`
3. 返回精确文件和行号

**验收标准**：
- 返回 `kernel/sched/core.c` 中 `schedule()` 的定义行号
- 行号误差为 0
- 响应时间 ≤ 100ms

---

### 2.3 场景三：Git 历史查询

**用户**："这个函数在 6.6 到 6.12 之间变了什么？"

**预期行为**：
1. AI 识别为 Git 历史查询
2. 调用 `git_diff_summary(symbol, "v6.6", "v6.12")`
3. 返回变更摘要

**验收标准**：
- 返回该函数在两个版本间的所有变更
- 包含变更的 commit hash、作者、日期
- 包含 diff 摘要
- 响应时间 ≤ 3 秒

---

### 2.4 场景四：Kconfig 验证

**用户**："开启 CONFIG_SMP 且关闭 CONFIG_NUMA 能编译吗？"

**预期行为**：
1. AI 识别为 Kconfig 验证
2. 调用 `kconfig_check({"CONFIG_SMP": "y", "CONFIG_NUMA": "n"})`
3. Z3 验证可满足性
4. 返回结果

**验收标准**：
- 如果 NUMA 依赖 SMP，返回 SAT（可满足）
- 如果 NUMA 不依赖 SMP，也返回 SAT
- 包含配置组合的合法性说明
- 响应时间 ≤ 500ms

---

### 2.5 场景五：变更因果追踪

**用户**："这个 TCP RTO bug 的完整生命周期"

**预期行为**：
1. AI 识别为因果图谱查询
2. 语义搜索召回相关 commit
3. 调用 `git_causal_chain(commit_hash)`
4. 遍历 Fixes: 和 Introduced-by: 链
5. 查询 backport 状态
6. 组装完整报告

**验收标准**：
- 返回从 bug 引入到修复的完整时间线
- 包含所有相关 commit hash
- 包含 backport 状态
- 响应时间 ≤ 3 秒

---

### 2.6 场景六：Patch 审查

**用户**："审查这个 patch，确认影响范围"

**预期行为**：
1. AI 调用 `git_diff_summary(patch_file)`
2. AI 调用 `kernel_callers(changed_symbol, 2)`
3. AI 调用 `kconfig_impact(changed_config)`
4. AI 调用 `git_causal_chain(patch_commit)`
5. 组装审查摘要

**验收标准**：
- 返回变更的函数列表
- 返回二级调用者分析
- 返回 Kconfig 影响分析
- 返回相关历史变更参考
- 响应时间 ≤ 10 秒

---

### 2.7 场景七：性能优化查询

**用户**："6.12 到 6.13 之间调度器有哪些性能改动？"

**预期行为**：
1. AI 识别为 Patch 类型筛选
2. 调用 `git_search_by_type(["performance"], subsys="sched", since="v6.12", until="v6.13")`
3. 返回性能相关 commit 列表

**验收标准**：
- 返回所有 performance 标签的 commit
- 包含纯优化和修复性能回归的 patch
- 按日期排序
- 响应时间 ≤ 3 秒

---

## 3. 性能验收标准

| 场景 | P95 延迟 | 成功率 |
|------|----------|--------|
| 语义搜索 | ≤ 2s | ≥ 99% |
| 精确符号 | ≤ 100ms | ≥ 99.9% |
| Git 历史 | ≤ 3s | ≥ 99% |
| Kconfig 验证 | ≤ 500ms | ≥ 99.9% |
| 因果追踪 | ≤ 3s | ≥ 99% |
| Patch 审查 | ≤ 10s | ≥ 99% |
| 性能查询 | ≤ 3s | ≥ 99% |

---

## 4. 测试环境

### 4.1 最小测试环境

- CPU：4 核
- 内存：8GB
- 磁盘：20GB SSD
- 内核源码：mini-kernel fixture（~100 文件）

### 4.2 标准测试环境

- CPU：16 核
- 内存：32GB
- 磁盘：100GB SSD
- GPU：RTX 4090（可选）
- 内核源码：完整 Linux 内核（~25000 文件）

---

## 5. 自动化测试框架

```python
# tests/e2e/test_scenarios.py

class TestKernelRAGMCP:
    def test_cfs_vruntime_query(self):
        """场景一：内核新人学习"""
        result = kernel_query("CFS 怎么更新 vruntime？")
        assert "update_curr" in result
        assert "kernel/sched/fair.c" in result
        assert result.response_time <= 2.0
    
    def test_schedule_symbol_jump(self):
        """场景二：精确符号跳转"""
        result = ctags_jump("schedule")
        assert "kernel/sched/core.c" in result
        assert result.response_time <= 0.1
    
    def test_git_diff_summary(self):
        """场景三：Git 历史查询"""
        result = git_diff_summary("update_curr", "v6.6", "v6.12")
        assert len(result.commits) > 0
        assert result.response_time <= 3.0
    
    def test_kconfig_check(self):
        """场景四：Kconfig 验证"""
        result = kconfig_check({"CONFIG_SMP": "y", "CONFIG_NUMA": "n"})
        assert result.satisfiable == True
        assert result.response_time <= 0.5
    
    def test_causal_chain(self):
        """场景五：变更因果追踪"""
        result = git_causal_chain("e33f3b9...")
        assert len(result.chain) >= 2
        assert result.response_time <= 3.0
    
    def test_patch_review(self):
        """场景六：Patch 审查"""
        result = review_patch("patch.diff")
        assert "impact" in result
        assert "callers" in result
        assert result.response_time <= 10.0
    
    def test_performance_patches(self):
        """场景七：性能优化查询"""
        result = git_search_by_type(
            ["performance"],
            subsys="sched",
            since="v6.12",
            until="v6.13"
        )
        assert len(result.commits) > 0
        assert result.response_time <= 3.0
```
