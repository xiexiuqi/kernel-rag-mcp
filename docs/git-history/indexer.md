# Git 历史索引设计

> 本文档描述 Git 历史索引的设计，包括 commit 索引、diff 索引、blame 索引和范围构建策略。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 设计原则

内核代码的**变更历史**与**代码本身**同等重要。Maintainer 的 commit message 包含设计决策、bug 修复原因、性能优化动机等无法从静态代码中推断的信息。

本地 Git 仓库是**唯一真相源**（Single Source of Truth）。所有索引都从本地 Git 仓库**派生**，而非外部导入。

---

## 2. 索引内容

| 数据类型 | 来源 | 用途 |
|----------|------|------|
| **Commit 元数据** | `git log --format` | 作者、日期、标题、正文、变更文件列表 |
| **Diff 摘要** | `git show --stat` + diff parser | 修改的函数名、增删行数、变更模式 |
| **Diff 代码上下文** | `git show` + 上下文提取 | 变更前后的代码片段，用于语义 embedding |
| **性能数据** | commit message 正则提取 | 延迟、吞吐、CPU 周期等量化指标 |
| **特性关联** | 语义聚类 + 代码指纹 + 补丁系列 | 将相关补丁关联到同一特性主题 |
| **Blame 行级映射** | `git blame -L`（当前 HEAD） | 精确回答"这行代码是谁引入的" |

---

## 3. Chunking 策略

### 3.1 Commit 卡片

每个 commit 为一个 chunk，包含：
- 标题、正文
- 变更文件列表
- 变更函数列表
- Patch 类型标签（含性能补丁的多源融合信号）
- 变更因果标签（Fixes:, Introduced-by: 等）
- **性能数据**（如为性能补丁）：量化指标、benchmark 工具、测试环境
- **特性关联**（如属于某特性）：feature_id、特性名称、在特性演进中的角色

### 3.2 Diff 上下文块

每个 commit 中每个被修改的函数为一个 chunk，包含：
- diff 内容
- 前后 5 行代码上下文
- 文件路径和行号范围

### 3.3 Blame 行（可选）

当前 HEAD 的每行代码指向的引入 commit（按需索引，避免爆炸）。

---

## 4. 与代码 RAG 的协同

- 查询代码实现时，**并行召回**当前代码 + 修改过该代码的近期 commits
- 回答版本差异问题时，**串联召回**两个版本的代码快照 + 中间的 commit diff 序列
- 回答"为什么这样设计"时，**优先召回**该代码区域的原始引入 commit 的 message

---

## 5. 查询能力

| MCP Tool | 功能 | 触发场景 |
|----------|------|----------|
| `git_search_commits(query, since, until, author, file_pattern)` | 语义搜索 commit history | 问"谁改了什么" |
| `git_blame_line(file, line)` | 行级代码溯源 | "这行代码谁引入的" |
| `git_diff_summary(symbol, v1, v2)` | 两个版本间某符号的变更摘要 | "这个函数变了什么" |
| `git_changelog(subsys, since_tag, until_tag)` | 子系统变更日志生成 | "sched 子系统最近改了什么" |
| `git_commit_context(commit_hash)` | 获取某 commit 的完整上下文 | 审查具体 patch |
| `git_show_patch(commit_hash, file)` | 获取某 commit 在某文件的 diff | 看具体修改 |

---

## 6. 技术要点

- Diff 向量化时提取 **"变更后代码 + commit message"** 联合 embedding，避免 `+/-` 符号干扰
- 版本范围过滤使用 Git tag → commit hash 映射表，结合 Qdrant payload 过滤
- 全量 blame 索引规模过大，仅索引当前 HEAD；历史 blame 按需实时查询

---

## 7. Git 索引范围构建（避免全量爆炸）

内核 Git 历史长达 20 年、百万级 commit，全量索引不现实也不必要。支持**范围化构建**：

```bash
# 默认范围：最近 2-3 个 LTS 周期（约 2-3 年）
$ kernel-rag index-git
→ 默认索引 v6.6..HEAD（约 3 万个 commit）

# 显式范围构建
$ kernel-rag index-git --range v6.12..v6.18
$ kernel-rag index-git --range v6.6..v6.12
$ kernel-rag index-git --range 2024-01-01..2026-04-22

# 历史版本按需加载（不默认索引，用户主动触发）
$ kernel-rag index-git --range v5.15..v6.6
→ 提示：这将增加约 1.2GB 存储，确认？[Y/n]

# 子系统 + 范围联合
$ kernel-rag index-git --subsys sched,mm --range v6.12..v6.13
```

### 7.1 范围存储策略

| 范围类型 | 存储策略 | 说明 |
|----------|----------|------|
| **近期范围（默认）** | 完整索引：commit 卡片 + diff 上下文 + blame | 如 v6.6..HEAD |
| **中期范围（按需）** | 精简索引：commit 卡片 + diff 摘要（无代码上下文） | 如 v5.15..v6.6 |
| **远期范围（归档）** | 元数据索引：仅 commit 卡片（标题/作者/日期/标签） | 如 v4.19..v5.15 |
| **Blame 索引** | 仅当前 HEAD | 历史 blame 按需实时查询 |

### 7.2 存储估算

| 范围 | Commit 数 | 存储大小 | 内容 |
|------|-----------|----------|------|
| v6.12..v6.13（1 年） | ~15,000 | ~800MB | 完整卡片 + diff 上下文 |
| v6.6..v6.12（2 年） | ~45,000 | ~2.0GB | 完整卡片 + diff 上下文 |
| v5.15..v6.6（5 年） | ~120,000 | ~1.5GB | 精简卡片（无 diff 代码） |
| v4.19..v5.15（归档） | ~300,000 | ~600MB | 仅元数据卡片 |

---

## 8. 增量更新策略

利用 Git 自身差异能力，实现**秒级~分钟级**增量索引：

```bash
# nightly 增量任务（由 kernel-rag 自动执行）
git fetch origin
NEW_HEAD=$(git rev-parse origin/master)
OLD_HEAD=$(cat ~/.kernel-rag/repos/linux/v6.12/current/metadata.json | jq -r .base_commit)

# 1. 获取变更范围
git diff --name-only $OLD_HEAD $NEW_HEAD > changed_files.txt

# 2. 代码 RAG 增量：只重新索引变更文件
kernel-rag index --incremental --files changed_files.txt

# 3. Git RAG 增量：只索引新增 commits（在范围内）
git log --format='%H' $OLD_HEAD..$NEW_HEAD > new_commits.txt
kernel-rag index-git --commits new_commits.txt --append-to v6.12

# 4. 变更因果图谱增量：解析新增 commit 的标签
kernel-rag index-causal --commits new_commits.txt
# 提取 Fixes:, Introduced-by:, Cc: stable 等标签，更新图谱边

# 5. 性能补丁索引增量：识别新增的性能补丁并提取数据
kernel-rag index-performance --commits new_commits.txt
# 多源融合识别、性能数据提取、特性关联更新

# 6. 更新 Kconfig（如果 Kconfig 文件有变更）

# 5. 更新 Kconfig（如果 Kconfig 文件有变更）
if grep -q "Kconfig" changed_files.txt; then
    kextract && kclause  # 重新生成逻辑公式
fi

# 7. 生成 delta 目录（不修改 base，保持基线稳定）
mkdir -p ~/.kernel-rag/repos/linux/v6.12/delta-$(git describe --tags $NEW_HEAD)
# 将增量索引写入 delta 目录
```

**级联控制**：头文件变更（如 `sched.h`）触发 `depth=1` 级联（重算直接包含者），避免全量重建。
