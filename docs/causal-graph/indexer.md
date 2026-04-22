# 变更因果图谱设计

> 本文档描述从 commit message 标签中提取变更因果关系并构建图谱的设计。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 设计原则

内核 commit message 遵循严格的社区规范，包含大量**机器可解析的元数据标签**。提取这些标签可构建**变更因果图谱**（Change Causal Graph），这是通用大模型完全无法触及的深度知识。

---

## 2. 提取的标签类型

| 标签 | 示例 | 语义 | 图谱边类型 |
|------|------|------|-----------|
| **Fixes:** | `Fixes: a1b2c3d ("tcp: fix RTO")` | 本 commit 修复了 a1b2c3d 引入的问题 | `FIXES →` (修复指向问题源) |
| **Link:** | `Link: https://bugzilla...` | 关联到外部 bug report | `REPORTS →` |
| **Reported-by:** | `Reported-by: John Doe` | 问题报告者 | `REPORTED_BY →` |
| **Bisected-by:** | `Bisected-by: Jane Smith` | 定位出问题提交的人 | `BISECTED_BY →` |
| **Introduced-by:** | `Introduced-by: e4f5g6h` | 明确指出问题由哪个提交引入 | `INTRODUCED_BY →` |
| **Cc: stable@...** | `Cc: stable@vger.kernel.org` | 需要 backport 到 stable 树 | `BACKPORT_TO →` |
| **Reviewed-by:** | `Reviewed-by: Alice` | 代码审查者 | `REVIEWED_BY →` |
| **Tested-by:** | `Tested-by: Bob` | 测试者 | `TESTED_BY →` |
| **Acked-by:** | `Acked-by: Maintainer` | 子系统维护者认可 | `ACKED_BY →` |
| **Suggested-by:** | `Suggested-by: Expert` | 方案建议者 | `SUGGESTED_BY →` |
| **Co-developed-by:** | `Co-developed-by: Partner` | 共同开发者 | `CO_DEV_WITH →` |
| **Regression:** | 标题含 "regression" | 标记回归问题 | `IS_REGRESSION` |
| **Revert** | `Revert "xxx"` | 回滚某个提交 | `REVERTS →` |
| **cherry-picked from** | `(cherry picked from commit ...)` | stable 树 backport | `CHERRY_PICK_FROM →` |

---

## 3. 图谱构建策略

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

---

## 4. 查询能力

| MCP Tool | 功能 | 触发场景 |
|----------|------|----------|
| `git_causal_chain(commit_hash, direction)` | 查询变更因果链 | "这个 bug 的完整修复链是什么" |
| `git_bug_origin(commit_hash)` | 追踪问题引入源头 | "这个 regression 是哪个 commit 引入的" |
| `git_backport_status(commit_hash)` | 查询 backport 状态 | "这个修复有没有进 stable 分支" |
| `git_reviewer_expertise(reviewer)` | 查询审查者的专业领域 | "David Miller 审查过哪些网络子系统的补丁" |
| `git_regression_chain(subsys, since)` | 查询某子系统的回归链 | "最近一年 mm 子系统有哪些 regression" |
| `git_patch_series(commit_hash)` | 查询补丁系列关系 | "这个 commit 属于哪个系列，前后 patch 是什么" |
| `git_fixes_complete(commit_hash)` | 验证 Fixes 链完整性 | "这个修复是否完整覆盖了所有引入点" |

---

## 5. 典型查询示例

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

---

## 6. 与代码 RAG 的协同

- 审查 patch 时，自动查询该 patch 的 `Fixes:` 链，确认是否完整修复了问题根因
- 分析回归时，追踪 `Introduced-by:` → `Fixes:` → `Revert` 的完整生命周期
- 评估 backport 需求时，查询 `Cc: stable` 和 cherry-pick 关系

---

## 7. 数据一致性保证

| 检查点 | 机制 | 目的 |
|--------|------|------|
| **因果链闭环检查** | 定期验证 Fixes: 指向的 commit 是否存在于索引中 | 防止断链 |
