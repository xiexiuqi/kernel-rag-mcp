# 存储层设计

> 本文档描述索引数据库的存储策略、存放路径和版本管理。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 核心原则

- 索引数据与源码树**物理隔离**，不侵入内核仓库
- 以**大版本（如 v6.12）为命名空间**，小版本（6.12.1, 6.12.2）作为**增量补丁**存放
- **绝不自动清理**，仅提示用户手动管理

---

## 2. 默认存放路径

```plain
~/.kernel-rag/                     # 全局索引根目录（$XDG_DATA_HOME/kernel-rag）
├── repos.json                       # 注册仓库清单（名称 → 路径映射）
├── repos/                           # 按仓库名隔离
│   └── linux/                       # 仓库名（取自目录名或用户指定）
│       ├── v6.12/                   # 大版本命名空间（基线 + 增量 + 合并）
│       │   ├── base/                # v6.12.0 全量基线索引
│       │   │   ├── qdrant/
│       │   │   ├── meili/
│       │   │   ├── graph.pickle
│       │   │   └── metadata.json    # 记录 commit hash、日期、子系统列表
│       │   ├── delta-v6.12.1/       # 6.12.0 → 6.12.1 的增量索引（仅变更文件）
│       │   ├── delta-v6.12.2/       # 6.12.1 → 6.12.2 的增量索引
│       │   ├── delta-v6.12.3/
│       │   └── merged-v6.12.5/      # 手动合并后的完整索引（可选，用户触发）
│       │       ├── qdrant/          # 合并后的完整向量库
│       │       ├── meili/
│       │       ├── graph.pickle     # 包含合并后因果图谱
│       │       └── metadata.json    # 记录 merged_from: [base, delta-v6.12.1, ...]
│       │
│       ├── v6.13/                   # 另一大版本命名空间
│       │   ├── base/                # v6.13.0 全量基线
│       │   └── delta-v6.13.1/
│       │
│       └── current -> v6.12/base    # 符号链接，指向当前活跃索引（默认基线）
│                                    # 用户可手动切换到 merged-v6.12.5/
```

---

## 3. 查询时的索引叠加策略

### 方案 A（默认）：基线查询 + 实时 Git 校验

- 使用 `v6.12/base` 索引召回候选结果
- 通过 `git diff v6.12.0..HEAD -- <file>` 实时校验该文件是否变更
- 若变更，提示用户"索引基于 6.12.0，当前为 6.12.3，建议应用增量或合并索引"

### 方案 B（增量叠加）：基线 + 所有 delta 联合查询

- 查询时同时搜索 `base` + `delta-v6.12.1` + `delta-v6.12.2` + `delta-v6.12.3`
- 对同一文件的重复 chunk，以最新 delta 为准
- 无需合并即可查询到最新状态，但查询延迟随 delta 数量增加

### 方案 C（手动合并）：使用 merged 完整索引

- 用户运行 `kernel-rag merge v6.12 --target v6.12.5`
- 将 `base` + `delta-6.12.1..5` 合并为一个完整索引 `merged-v6.12.5/`
- 切换 `current` 指向合并后的索引
- 查询性能最佳，无叠加开销

**推荐工作流**：
- 日常开发（源码在 6.12.x）：使用 **方案 B**（基线 + deltas），延迟可接受
- 长期稳定（源码锁定 6.12.5）：运行 `kernel-rag merge` 生成 **方案 C**，获得最佳性能
- 审查历史（回溯 6.12.0）：直接切换 `current` 到 `base/`

---

## 4. metadata.json 结构

```json
{
  "repo_name": "linux",
  "repo_path": "/home/user/linux",
  "version_namespace": "v6.12",
  "base_commit": "e33f3b9a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e",
  "base_tag": "v6.12.0",
  "index_type": "base",
  "index_date": "2026-04-22T09:17:00Z",
  "kernel_version": "6.12.0",
  "subsystems": ["sched", "mm", "net", "fs", "block", "drivers"],
  "chunks": {
    "code": 450000,
    "commits": 12000,
    "blame_lines": 850000
  },
  "storage": {
    "vectors_mb": 1536,
    "sparse_mb": 512,
    "graph_mb": 198,
    "total_mb": 2246
  },
  "tools_version": {
    "kernel_rag_mcp": "0.1.0",
    "kconfiglib": "14.1.0",
    "kclause": "2.1.0"
  }
}
```

---

## 5. 多仓库支持

用户通常有多个内核仓库（upstream、公司内部分支、个人实验分支）：

```bash
# 注册多个仓库
$ kernel-rag init ~/linux-upstream --name linux-upstream
$ kernel-rag init ~/linux-company --name linux-company
$ kernel-rag init ~/linux-personal --name linux-personal

# ~/.kernel-rag/repos.json
{
  "linux-upstream": {"path": "/home/user/linux-upstream", "default_version": "v6.12"},
  "linux-company": {"path": "/home/user/linux-company", "default_version": "v6.12"},
  "linux-personal": {"path": "/home/user/linux-personal", "default_version": "v6.13"}
}
```

MCP Server 根据当前工作目录自动匹配仓库，或显式指定：

```python
kernel_search(query="vruntime", repo="linux-upstream", version="v6.12")
```

---

## 6. 存储管理策略：绝不自动清理，仅提示

**原则**：索引是用户资产，工具**不擅自删除**，仅提供信息提示和手动管理命令。

| 场景 | 行为 |
|------|------|
| **磁盘空间不足** | CLI 打印警告：`[Warning] ~/.kernel-rag 占用 45GB，建议运行 kernel-rag status 查看` |
| **增量过多** | 提示：`v6.12 有 15 个 delta，查询延迟增加 200ms，建议合并` |
| **旧版本长期未用** | 提示：`v6.10 基线索引 180 天未访问，可手动清理` |
| **清理命令** | `kernel-rag status` 列出所有版本和大小，`kernel-rag remove v6.10` 手动删除 |
| **合并命令** | `kernel-rag merge v6.12 --target v6.12.15` 手动合并 deltas |
| **保留标记** | `kernel-rag pin v6.12` 标记大版本长期保留，status 中显示 PIN 标记 |

```bash
$ kernel-rag status
Repository: linux @ /home/user/linux
Version      Type     Size    LastUsed  Pin  Deltas  Merged
------------------------------------------------------------
v6.13        base     2.3GB   2h ago    -    3       -
v6.12        base     2.1GB   1d ago    ✓    15      merged-v6.12.15
v6.11        base     2.0GB   30d ago   -    0       -
v6.10        base     1.9GB   180d ago  -    0       -

Total: 8.3GB  (提示: v6.10 已 180 天未用，可手动移除)
```

---

## 7. 注册与初始化流程

```bash
# 1. 注册仓库（一次性的）
$ cd ~/linux
$ kernel-rag init
→ 扫描 Git 仓库 → 识别当前 tag (v6.12.5) → 创建 ~/.kernel-rag/repos/linux/v6.12/
→ 提示：运行 `kernel-rag index` 建立基线索引

# 2. 建立基线索引（大版本首版）
$ kernel-rag index --base
→ 生成 ~/.kernel-rag/repos/linux/v6.12/base/

# 3. 日常增量（小版本更新后）
$ git fetch origin && git checkout v6.12.6
$ kernel-rag update
→ 生成 ~/.kernel-rag/repos/linux/v6.12/delta-v6.12.6/

# 4. 手动合并（可选，优化查询性能）
$ kernel-rag merge v6.12 --target v6.12.6
→ 生成 ~/.kernel-rag/repos/linux/v6.12/merged-v6.12.6/

# 5. 注册到 MCP（自动或手动）
$ kernel-rag mcp install --client claude-code
→ 写入 ~/.claude/config.json

# 6. 使用
$ claude
→ AI 自动调用 kernel-rag 查询代码
```

---

## 8. 版本锁定与一致性校验

查询时执行以下校验链：

```python
def verify_index_freshness(repo_path, index_meta):
    # 1. 检查源码 commit 是否匹配索引基线或合并目标
    current_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path)
    indexed_commit = index_meta.get("merged_to") or index_meta["base_commit"]
    
    if current_head.stdout.strip() != indexed_commit:
        return {
            "status": "stale",
            "suggestion": "Run `kernel-rag update` to create delta, or `kernel-rag merge` to sync",
            "drift_commits": count_commits_between(indexed_commit, current_head)
        }
    
    # 2. 抽查行号一致性（随机选 10 个 chunk 验证）
    for chunk in random.sample(chunks, 10):
        actual_line = read_file_line(repo_path + chunk.file, chunk.line)
        if actual_line.strip() != chunk.expected_line.strip():
            return {"status": "corrupted", "suggestion": "Re-index recommended"}
    
    return {"status": "fresh"}
```

**用户感知**：如果索引过期，MCP Server 在返回结果前附加警告：

> ⚠️ 索引基于 `v6.12.0`，当前源码为 `v6.12.3`，相差 47 个 commit。已应用 3 个 delta 叠加查询，建议运行 `kernel-rag merge v6.12` 获得最佳性能。
