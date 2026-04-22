# 索引层测试设计

> 本文档描述索引生成器各子模块的测试策略和用例设计。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 测试范围

索引层包含以下子模块，每个子模块需要独立的测试设计：
- 代码语义索引（Code Indexer）
- Git 历史索引（Git Indexer）
- Kconfig 索引（Kconfig Indexer）
- Patch 类型索引（Type Indexer）
- 变更因果图谱索引（Causal Indexer）
- 索引调度器（Index Scheduler）

---

## 2. 代码语义索引测试

### 2.1 单元测试

| 测试用例 | 输入 | 预期输出 | 优先级 |
|----------|------|----------|--------|
| 函数边界识别 | 包含多个函数的 C 文件 | 正确识别每个函数的起止行号 | P0 |
| 结构体识别 | 包含结构体定义的 C 文件 | 正确识别结构体名称和字段 | P0 |
| 宏定义识别 | 包含复杂宏的头文件 | 正确识别宏名和参数 | P0 |
| Kconfig 条件提取 | 包含 `#ifdef CONFIG_SMP` 的代码 | 提取条件表达式并标注 | P0 |
| 嵌套函数处理 | 包含静态嵌套函数的文件 | 正确处理嵌套作用域 | P1 |
| 宏展开标注 | 包含 `container_of` 的代码 | 正确添加预展开标注 | P1 |

### 2.2 集成测试

| 测试用例 | 场景 | 验证点 |
|----------|------|--------|
| 完整文件索引 | 一个真实的内核 C 文件 | chunk 数量、边界正确性、元数据完整性 |
| 子系统索引 | `kernel/sched/` 目录 | 所有文件被索引、无遗漏 |
| Embedding 一致性 | 相同代码片段两次索引 | 向量相似度 > 0.99 |
| 增量索引 | 修改一个函数后重新索引 | 仅变更函数被重新索引 |

### 2.3 性能测试

| 测试用例 | 目标 |
|----------|------|
| 单文件索引速度 | ≤ 1 秒/千行 |
| 完整内核索引时间 | ≤ 8 小时（CPU）/ ≤ 1 小时（GPU） |
| 内存占用 | ≤ 4GB |

---

## 3. Git 历史索引测试

### 3.1 单元测试

| 测试用例 | 输入 | 预期输出 |
|----------|------|----------|
| Commit 解析 | 标准 commit message | 正确提取标题、正文、作者、日期 |
| Fixes 标签提取 | 含 `Fixes: a1b2c3d` 的 message | 正确提取 Fixes 目标 commit |
| Cc: stable 提取 | 含 `Cc: stable@vger.kernel.org` | 正确提取 backport 目标版本 |
| Diff 解析 | 标准 git diff | 正确识别变更文件和函数 |
| Patch 类型分类 | 各类 commit message | 正确分类（单标签/多标签） |

### 3.2 集成测试

| 测试用例 | 场景 | 验证点 |
|----------|------|--------|
| 范围索引 | `v6.12..v6.13` | 所有 commit 被索引、无遗漏 |
| Blame 索引 | 当前 HEAD | 行级映射正确 |
| 增量 Git 索引 | 新增 100 个 commit | 仅新增 commit 被索引 |

---

## 4. Kconfig 索引测试

### 4.1 单元测试

| 测试用例 | 输入 | 预期输出 |
|----------|------|----------|
| 符号解析 | `config SMP` | 类型=bool、默认值=y |
| 依赖提取 | `depends on X86 && !UML` | 正确解析依赖表达式 |
| select 提取 | `select IRQ_DOMAIN` | 正确提取反向依赖 |
| 菜单树构建 | 完整 Kconfig 文件 | 层级结构正确 |

### 4.2 形式化验证测试

| 测试用例 | 输入 | 预期输出 |
|----------|------|----------|
| 可满足性验证 | `CONFIG_SMP=y ∧ CONFIG_NUMA=n` | SAT/UNSAT 正确 |
| 依赖闭包计算 | `CONFIG_SCHED_MC` | 所有直接和间接依赖 |
| 配置组合抽样 | 随机 100 个组合 | Z3 验证通过 |

---

## 5. 变更因果图谱测试

### 5.1 单元测试

| 测试用例 | 输入 | 预期输出 |
|----------|------|----------|
| 边构建 | 含 Fixes: 的 commit | FIXES 边正确指向 |
| 多标签提取 | 复杂 commit message | 所有标签被提取 |
| 环检测 | 循环依赖的 Fixes 链 | 正确检测并报告 |

### 5.2 集成测试

| 测试用例 | 场景 | 验证点 |
|----------|------|--------|
| 完整因果链查询 | 已知 bug 的修复链 | 从引入到修复的完整路径 |
| Backport 状态查询 | 含 Cc: stable 的 commit | 正确识别 backport 目标版本 |

---

## 6. 测试 Fixtures

```plain
tests/fixtures/
├── mini-kernel/                 # ~100 文件的微型内核树
│   ├── kernel/
│   │   └── sched/
│   ├── include/
│   │   └── linux/
│   ├── mm/
│   ├── net/
│   ├── Kconfig
│   └── Makefile
├── sample-commits/              # 各类 commit message 样本
│   ├── bugfix.sample
│   ├── performance.sample
│   ├── regression.sample
│   └── revert.sample
└── kconfig-expressions/         # Kconfig 表达式测试用例
    ├── simple.depends
    ├── complex.select
    └── nested.if
```

---

## 7. 持续集成

```yaml
# .github/workflows/ci.yml 索引层测试阶段
jobs:
  indexer-tests:
    steps:
      - name: Unit Tests
        run: pytest tests/unit/indexer/ -v
      
      - name: Integration Tests
        run: pytest tests/integration/indexer/ -v --fixture=tests/fixtures/mini-kernel
      
      - name: Performance Benchmarks
        run: pytest tests/performance/indexer/ -v --benchmark-only
      
      - name: Kconfig Validation
        run: python scripts/verify-kconfig.py tests/fixtures/mini-kernel/
```
