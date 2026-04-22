# 集成测试设计

> 本文档描述各子系统间集成测试的策略和用例设计。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 测试范围

验证以下子系统间的协同工作：
- 索引层 ↔ 存储层
- 检索层 ↔ 存储层
- MCP 工具层 ↔ 检索层
- Git 历史索引 ↔ 变更因果图谱
- Kconfig 索引 ↔ 代码索引
- 增量更新 ↔ 查询一致性

---

## 2. 索引-存储集成测试

| 测试用例 | 操作 | 验证点 |
|----------|------|--------|
| 代码索引写入向量库 | 索引 `kernel/sched/` → 写入 Qdrant | 向量可检索、元数据完整 |
| Git 索引写入稀疏库 | 索引 commit → 写入 Meilisearch | 符号搜索可召回 |
| 因果图谱写入图库 | 构建图谱 → 写入 NetworkX | 路径查询正确 |
| 元数据持久化 | 索引完成后写入 metadata.json | 重启后可读取 |
| 多后端一致性 | 同一数据写入 Qdrant 和 Chroma | 查询结果一致 |

---

## 3. 检索-存储集成测试

| 测试用例 | 操作 | 验证点 |
|----------|------|--------|
| 混合召回 | Dense + Sparse 同时查询 | RRF 融合结果正确 |
| Kconfig 过滤查询 | 带 CONFIG 条件的查询 | 过滤后结果正确 |
| 跨文件上下文组装 | 召回函数 → 拉取声明 | 组装内容完整 |
| 版本差异检索 | 对比两个版本的代码 | 差异识别正确 |
| 因果图谱遍历 | 查询因果链 | 遍历结果完整 |

---

## 4. MCP-检索集成测试

| 测试用例 | 操作 | 验证点 |
|----------|------|--------|
| 语义搜索端到端 | `kernel_search()` → 混合召回 → 返回 | 结果含行号、文件路径 |
| 精确符号端到端 | `kernel_define()` → ctags → 返回 | 行号精确 |
| Git 查询端到端 | `git_search_commits()` → 稀疏索引 → 返回 | 含 commit hash |
| Kconfig 验证端到端 | `kconfig_check()` → Z3 → 返回 | SAT/UNSAT 正确 |
| 因果查询端到端 | `git_causal_chain()` → 图遍历 → 返回 | 链完整 |

---

## 5. Git-因果图谱集成测试

| 测试用例 | 操作 | 验证点 |
|----------|------|--------|
| Commit 索引触发图谱更新 | 新增 commit → 提取标签 → 更新图 | 新节点和边正确 |
| Fixes 链完整性 | 索引含 Fixes: 的 commit → 查询图谱 | 边指向正确 |
| Backport 关系 | 索引 cherry-pick → 查询 backport 状态 | 关系正确 |
| 增量更新一致性 | 新增 delta → 图谱增量更新 → 查询 | 新旧数据一致 |

---

## 6. Kconfig-代码索引集成测试

| 测试用例 | 操作 | 验证点 |
|----------|------|--------|
| Kconfig 条件标注 | 索引 `#ifdef CONFIG_SMP` 代码 → 标注条件 | chunk 含 Kconfig 条件 |
| 配置过滤查询 | 查询带 `CONFIG_SMP=y` → 过滤结果 | 仅返回 SMP 相关代码 |
| 可满足性验证 | 查询前验证配置组合 | 非法组合被拒绝 |
| 源文件映射 | Kconfig 变更 → 重新索引相关文件 | 仅受影响文件被重索引 |

---

## 7. 增量更新-查询一致性测试

| 测试用例 | 操作 | 验证点 |
|----------|------|--------|
| 基线查询 | 索引 base → 查询 | 结果正确 |
| Delta 叠加查询 | 添加 delta → 查询 | 基线 + delta 结果正确 |
| 合并后查询 | 合并为 merged → 查询 | 结果与叠加查询一致 |
| 过期检测 | 源码更新 → 查询 | 检测到过期并提示 |
| 回滚查询 | 切换 current 到旧版本 → 查询 | 返回旧版本结果 |

---

## 8. 多仓库集成测试

| 测试用例 | 操作 | 验证点 |
|----------|------|--------|
| 多仓库注册 | 注册 upstream 和 company 仓库 | 两个仓库索引隔离 |
| 跨仓库查询 | 指定 repo 参数查询 | 返回指定仓库结果 |
| 默认仓库 | 不指定 repo → 查询 | 使用当前工作目录匹配的仓库 |
| 仓库切换 | 切换 current 指向 | 查询结果切换 |

---

## 9. CI 集成测试

```yaml
# .github/workflows/ci.yml
jobs:
  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - name: Setup Environment
        run: |
          pip install -e ".[test]"
          docker run -d -p 6333:6333 qdrant/qdrant
          docker run -d -p 7700:7700 getmeili/meilisearch
      
      - name: Index Layer Tests
        run: pytest tests/integration/indexer/ -v
      
      - name: Retriever Tests
        run: pytest tests/integration/retriever/ -v
      
      - name: MCP Tools Tests
        run: pytest tests/integration/mcp-tools/ -v
      
      - name: End-to-End Tests
        run: pytest tests/e2e/ -v --fixture=tests/fixtures/mini-kernel
      
      - name: Consistency Checks
        run: |
          python scripts/verify-index.py tests/fixtures/mini-kernel/
          python scripts/verify-causal-graph.py
          python scripts/verify-kconfig.py tests/fixtures/mini-kernel/
```
