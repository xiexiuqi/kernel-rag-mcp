# Git 历史与因果图谱测试设计

> 本文档描述 Git 历史索引和变更因果图谱的测试策略和用例设计。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 测试范围

- Git 历史索引（Commit 卡片、Diff 上下文、Blame 行级映射）
- Patch 类型识别（非正交多维分类）
- 变更因果图谱（节点、边、路径查询）

---

## 2. Commit 解析测试

| 测试用例 | 输入 | 预期输出 | 优先级 |
|----------|------|----------|--------|
| 标准 commit | 含标题、正文、Sign-off | 正确提取所有字段 | P0 |
| 空正文 commit | 仅标题 | 正文为空字符串 | P0 |
| 多行正文 | 含换行的正文 | 保留换行格式 | P1 |
| 非 UTF-8 编码 | 含中文的 commit | 正确解码 | P1 |
| 合并 commit | Merge commit | 正确处理多个父节点 | P1 |

---

## 3. 标签提取测试

### 3.1 Fixes: 标签

| 测试用例 | 输入 | 预期输出 |
|----------|------|----------|
| 标准 Fixes | `Fixes: a1b2c3d ("title")` | hash=a1b2c3d, title=title |
| 多 Fixes | 多个 Fixes: 行 | 提取所有 Fixes 目标 |
| 无效 Fixes | `Fixes: invalid` | 标记为解析失败 |

### 3.2 Cc: stable 标签

| 测试用例 | 输入 | 预期输出 |
|----------|------|----------|
| 标准 Cc | `Cc: stable@vger.kernel.org` | stable=true |
| 版本范围 | `Cc: stable@vger.kernel.org # 5.15+` | versions=[5.15+] |
| 多版本 | `Cc: stable@vger.kernel.org # 5.15+, 6.1+` | versions=[5.15+, 6.1+] |

### 3.3 Reviewed-by/Acked-by 标签

| 测试用例 | 输入 | 预期输出 |
|----------|------|----------|
| 单审查者 | `Reviewed-by: Alice` | reviewers=[Alice] |
| 多审查者 | 多个 Reviewed-by 行 | 提取所有审查者 |
| 混合标签 | Reviewed-by + Acked-by + Tested-by | 分类提取 |

---

## 4. Patch 类型分类测试

### 4.1 单标签分类

| 输入标题 | 预期标签 |
|----------|----------|
| `tcp: fix inaccurate RTO` | [bugfix] |
| `sched: optimize vruntime update` | [performance] |
| `mm: refactor slab allocation` | [refactor] |
| `net: add MPTCP support` | [feature] |
| `Revert "tcp: change RTO"` | [revert] |

### 4.2 多标签分类

| 输入 | 预期标签 |
|------|----------|
| `fix regression in scheduler` + Fixes: | [bugfix, regression] |
| `sched: optimize and cleanup vruntime` | [performance, refactor] |
| `tcp: fix use-after-free (CVE-2023-XXXX)` | [bugfix, security] |
| `stable: fix race in tcp` + Fixes: | [bugfix, stable] |

### 4.3 置信度测试

| 测试用例 | 验证点 |
|----------|--------|
| 明确关键词 | confidence > 0.9 |
| 模糊关键词 | confidence 0.5-0.8 |
| 无关键词 | confidence < 0.3 |

---

## 5. 变更因果图谱测试

### 5.1 节点测试

| 测试用例 | 操作 | 验证点 |
|----------|------|--------|
| 节点创建 | 创建 commit 节点 | 属性完整 |
| 节点更新 | 更新已有节点 | 属性合并正确 |
| 节点查询 | 按 hash 查询 | 返回正确节点 |
| 节点删除 | 删除节点 | 级联删除相关边 |

### 5.2 边测试

| 测试用例 | 操作 | 验证点 |
|----------|------|--------|
| FIXES 边 | 创建修复关系 | 方向正确（修复 → 问题） |
| INTRODUCED_BY 边 | 创建引入关系 | 方向正确（问题 → 引入） |
| REVIEWED_BY 边 | 创建审查关系 | 无向或双向 |
| 重复边 | 创建已存在的边 | 去重或更新属性 |

### 5.3 路径查询测试

| 测试用例 | 查询 | 预期结果 |
|----------|------|----------|
| 简单路径 | A → B → C | 返回 [A, B, C] |
| 多路径 | A → B → C 和 A → D → C | 返回最短路径 |
| 无路径 | A 和 Z 无连接 | 返回空 |
| 环路径 | A → B → C → A | 检测并报告环 |

### 5.4 典型场景测试

| 场景 | 验证点 |
|------|--------|
| Bug 完整生命周期 | 从引入 → 发现 → 修复 → backport |
| 回归链 | 追踪 Introduced-by → Fixes → Revert |
| 审查网络 | 某 Reviewer 审查过的所有 patch |
| Backport 状态 | Cc: stable → cherry-pick 验证 |

---

## 6. 数据一致性测试

| 测试用例 | 场景 | 验证点 |
|----------|------|--------|
| Fixes 链完整性 | Fixes: 指向不存在的 commit | 报告断链 |
| 重复 commit | 同一 commit 多次索引 | 去重正确 |
| 增量更新 | 新增 commit 后更新图谱 | 新增节点和边正确 |
| 全量重建 | 删除后重新索引 | 数据与之前一致 |

---

## 7. 性能测试

| 测试用例 | 目标 |
|----------|------|
| Commit 解析速度 | ≥ 1000 commit/秒 |
| 图谱构建速度 | ≥ 10000 边/秒 |
| 路径查询延迟 | ≤ 200ms（深度 5） |
| 邻居查询延迟 | ≤ 50ms |
| 存储占用 | 100万 commit ≤ 500MB |
