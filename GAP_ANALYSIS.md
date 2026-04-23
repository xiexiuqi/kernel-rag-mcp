# Kernel-RAG-MCP 实现差距分析

**分析日期**: 2026-04-22
**当前状态**: 68/68 单元测试通过，但大量功能使用 Mock 数据

---

## 1. 严重问题：MCP Tools 仍在使用 Mock 数据

### 1.1 CodeTools - 完全 Mock

**当前实现** (`src/kernel_rag_mcp/server/tools/code_tools.py`):
```python
class CodeTools:
    _MOCK_CHUNKS: List[CodeChunk] = [
        CodeChunk(file_path="kernel/sched/fair.c", start_line=100, ...),
        CodeChunk(file_path="kernel/sched/core.c", start_line=200, ...),
    ]
    
    def kernel_search(self, query: str) -> List[CodeChunk]:
        return list(self._MOCK_CHUNKS)  # 返回硬编码数据！
```

**问题**:
- `kernel_search()` 返回固定的3个mock chunk
- `kernel_define()` 返回固定的符号表
- `kernel_callers()` 返回固定的调用者列表
- `kernel_diff()` 返回空变化

**设计目标**: 应该查询真实的 Qdrant 索引和本地源码

### 1.2 GitTools - 完全 Mock

**当前实现** (`src/kernel_rag_mcp/server/tools/git_tools.py`):
```python
class GitTools:
    _MOCK_COMMITS: List[CommitInfo] = [
        CommitInfo(hash="abc123", title="sched: fix RTO calculation"),
        CommitInfo(hash="def456", title="tcp: fix SACK handling"),
    ]
    
    def git_search_commits(self, query, since, until):
        return list(self._MOCK_COMMITS)  # 返回硬编码数据！
```

**问题**:
- `git_search_commits()` 返回固定的2个commit
- `git_blame_line()` 返回固定的 blame 结果
- `git_changelog()` 返回固定的变更日志
- `git_commit_context()` 返回空上下文

**设计目标**: 应该查询真实的 Git 仓库

### 1.3 KconfigTools - 完全 Mock

**当前实现** (`src/kernel_rag_mcp/server/tools/kconfig_tools.py`):
```python
class KconfigTools:
    _MOCK_CONFIGS: dict[str, KconfigDesc] = {
        "CONFIG_SMP": KconfigDesc(name="CONFIG_SMP", type="bool", ...),
    }
    
    def kconfig_describe(self, config_name: str) -> KconfigDesc:
        return self._MOCK_CONFIGS.get(config_name, KconfigDesc(...))
```

**问题**:
- `kconfig_describe()` 只认识 CONFIG_SMP
- `kconfig_deps()` 返回固定依赖
- `kconfig_check()` 总是返回可满足
- `kconfig_impact()` 返回固定文件列表

**设计目标**: 应该解析真实的 Kconfig 文件

---

## 2. MCP Server 接口不完整

### 2.1 当前实现的工具 (3个)

1. `kernel_query()` - 统一查询入口
2. `kernel_search()` - 代码搜索
3. `kernel_define()` - 符号定义

### 2.2 设计目标要求的工具 (30+个)

**代码语义层** (5个):
- `kernel_search` ✅
- `kernel_define` ✅
- `kernel_callers` ❌ (未暴露)
- `kernel_diff` ❌ (未暴露)
- `kernel_cross_ref` ❌ (未实现)

**Git历史层** (6个):
- `git_search_commits` ❌ (Mock)
- `git_blame_line` ❌ (Mock)
- `git_diff_summary` ❌ (未实现)
- `git_changelog` ❌ (Mock)
- `git_commit_context` ❌ (Mock)
- `git_show_patch` ❌ (未实现)

**Patch类型筛选** (3个):
- `git_search_by_type` ❌ (未实现)
- `git_type_stats` ❌ (未实现)
- `git_find_performance_regression_fix` ❌ (未实现)

**性能补丁工具** (5个):
- `performance_feature_query` ❌ (未暴露)
- `performance_compare` ❌ (未实现)
- `performance_top_k` ❌ (未暴露)
- `performance_impact` ❌ (未实现)
- `performance_regression_query` ❌ (未实现)

**变更因果图谱** (7个):
- `git_causal_chain` ❌ (未实现)
- `git_bug_origin` ❌ (未实现)
- `git_backport_status` ❌ (未实现)
- `git_reviewer_expertise` ❌ (未实现)
- `git_regression_chain` ❌ (未实现)
- `git_patch_series` ❌ (未实现)
- `git_fixes_complete` ❌ (未实现)

**Kconfig配置层** (4个):
- `kconfig_describe` ❌ (Mock)
- `kconfig_deps` ❌ (Mock)
- `kconfig_check` ❌ (Mock)
- `kconfig_impact` ❌ (Mock)

**精确工具层** (3个):
- `ctags_jump` ❌ (未实现)
- `cscope_callers` ❌ (未暴露)
- `grep_code` ❌ (未实现)

---

## 3. 配置和部署问题

### 3.1 MCP 配置未生成

**设计目标**:
```json
// ~/.opencode/mcp.json
{
  "mcpServers": {
    "kernel-rag": {
      "command": "python",
      "args": ["-m", "kernel_rag_mcp.server"],
      "env": {
        "KERNEL_REPO": "/home/user/linux",
        "INDEX_PATH": "/home/user/.kernel-rag/repos/linux/v6.12/current"
      }
    }
  }
}
```

**当前状态**: 没有自动生成 MCP 配置文件

### 3.2 环境变量处理

**当前问题**:
- MCP Server 硬编码使用 `~/.kernel-rag/repos/linux`
- 不支持通过环境变量指定仓库路径
- 不支持多仓库切换

### 3.3 安装脚本缺失

**设计目标**:
```bash
$ kernel-rag mcp install --client claude-code
→ 写入 ~/.claude/config.json
```

**当前状态**: 没有 `mcp install` 命令

---

## 4. 核心功能差距

### 4.1 Embedding 质量

**当前**: 使用 SHA256 hash 生成 384 维向量
**设计目标**: 使用 jina-embeddings-v2-base-code 或 BAAI/bge-m3
**影响**: 语义搜索效果差，无法捕捉代码语义

### 4.2 索引覆盖范围

**当前**: 只索引了 kernel/sched/ (1491 chunks)
**设计目标**: 完整索引 sched/mm/net/fs/block/drivers
**影响**: 只能查询调度器相关代码

### 4.3 Git 历史索引

**当前**: 未建立 Git commit 索引
**设计目标**: 索引所有 commit message + diff
**影响**: 无法回答"为什么这样设计"、"谁引入的bug"

### 4.4 Kconfig 形式化

**当前**: 简单正则提取 #ifdef CONFIG_XXX
**设计目标**: kconfiglib + kclause + Z3
**影响**: 无法验证复杂配置组合

### 4.5 因果图谱

**当前**: 内存中的简单图结构
**设计目标**: 基于 Fixes:/Introduced-by: 的完整因果链
**影响**: 无法追踪 bug 的完整生命周期

---

## 5. 测试覆盖问题

### 5.1 测试通过但无实际价值

当前 68 个测试通过，但:
- 测试的是 Mock 数据，不是真实内核
- 没有端到端集成测试
- 没有性能测试

### 5.2 缺少的测试

- [ ] 真实内核代码解析测试
- [ ] Qdrant 向量搜索准确性测试
- [ ] cscope 调用链测试
- [ ] Git 历史查询测试
- [ ] Kconfig Z3 可满足性测试
- [ ] MCP Server 端到端测试

---

## 6. 建议修复优先级

### P0 (立即修复)

1. **移除所有 Mock 数据**，连接真实存储层
2. **实现 MCP Server 完整工具集** (30+ tools)
3. **生成 MCP 配置文件** (.opencode/mcp.json)

### P1 (本周完成)

4. **集成真实 Embedding 模型** (sentence-transformers)
5. **扩展索引范围** 到 mm/net 子系统
6. **实现 Git 历史索引** (commit message + diff)

### P2 (下周完成)

7. **实现 Kconfig 形式化验证** (kconfiglib + Z3)
8. **实现变更因果图谱** (Fixes:/Introduced-by:)
9. **实现增量更新** (delta indexing)

### P3 (后续优化)

10. **性能优化** (并行索引、缓存)
11. **Web UI** (可选)
12. **团队协作功能** (共享索引)
