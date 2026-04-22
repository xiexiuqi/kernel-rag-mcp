# 测试 Fixtures 设计

> 本文档描述测试用 fixtures 的设计和结构。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 微型内核树（mini-kernel）

### 1.1 目录结构

```plain
tests/fixtures/mini-kernel/
├── kernel/
│   └── sched/
│       ├── core.c              # 调度器核心（~200 行）
│       ├── fair.c              # CFS 调度器（~300 行）
│       ├── rt.c                # RT 调度器（~100 行）
│       └── sched.h             # 调度器头文件（~150 行）
├── mm/
│   ├── page_alloc.c            # 页面分配（~150 行）
│   ├── slab.c                  # SLAB 分配器（~100 行）
│   └── mm.h                    # 内存管理头文件（~100 行）
├── net/
│   ├── tcp.c                   # TCP 协议栈（~200 行）
│   ├── udp.c                   # UDP 协议栈（~100 行）
│   └── sock.h                  # 网络头文件（~100 行）
├── include/
│   └── linux/
│       ├── sched.h             # 全局调度器头文件
│       ├── mm.h                # 全局内存管理头文件
│       └── net.h               # 全局网络头文件
├── init/
│   └── main.c                  # 内核入口
├── Kconfig                     # 顶层 Kconfig
├── Makefile                    # 顶层 Makefile
└── .git/                       # Git 仓库（预置历史）
```

### 1.2 代码特征

- 包含真实内核的简化版本
- 包含典型的内核模式：
  - 条件编译（`#ifdef CONFIG_SMP`）
  - 宏定义（`container_of`, `list_for_each_entry`）
  - 函数指针
  - 结构体嵌套
- 包含注释和文档字符串

### 1.3 Git 历史

预置 50 个 commit，覆盖：
- bugfix（10 个）
- performance（10 个）
- refactor（10 个）
- feature（10 个）
- documentation（5 个）
- test（5 个）

包含完整的 Fixes:、Cc: stable、Reviewed-by 等标签。

---

## 2. Commit Message 样本

```plain
tests/fixtures/sample-commits/
├── bugfix/
│   ├── simple-fix.txt
│   ├── fixes-tag.txt
│   └── regression-fix.txt
├── performance/
│   ├── optimization.txt
│   ├── speedup.txt
│   └── latency.txt
├── refactor/
│   ├── cleanup.txt
│   ├── simplify.txt
│   └── remove.txt
├── feature/
│   ├── add-support.txt
│   ├── implement.txt
│   └── new-feature.txt
├── revert/
│   └── revert-commit.txt
├── security/
│   ├── cve-fix.txt
│   └── reported-by-security.txt
└── stable/
    └── cc-stable.txt
```

---

## 3. Kconfig 表达式样本

```plain
tests/fixtures/kconfig-expressions/
├── simple/
│   ├── bool.config
│   ├── tristate.config
│   ├── string.config
│   ├── hex.config
│   └── int.config
├── dependencies/
│   ├── simple-depends.config
│   ├── negation.config
│   ├── conjunction.config
│   ├── disjunction.config
│   └── nested.config
├── select-imply/
│   ├── select.config
│   ├── conditional-select.config
│   └── imply.config
├── menu-choice/
│   ├── menu.config
│   ├── choice.config
│   └── if.config
└── invalid/
    ├── circular-dependency.config
    ├── unmet-dependency.config
    └── invalid-type.config
```

---

## 4. 因果图谱样本

```plain
tests/fixtures/causal-graphs/
├── simple-chain/
│   └── bug-introduced-fixed.json
├── regression-chain/
│   └── introduced-regression-fixed.json
├── backport-chain/
│   └── fix-backported.json
├── review-network/
│   └── reviewer-patches.json
└── complex/
    └── multi-path-causal.json
```

---

## 5. 向量数据样本

```plain
tests/fixtures/vector-samples/
├── code-embeddings/
│   ├── function-chunks.json
│   └── struct-chunks.json
├── commit-embeddings/
│   ├── commit-cards.json
│   └── diff-contexts.json
└── query-embeddings/
    ├── semantic-queries.json
    └── expected-results.json
```

---

## 6. 使用方式

```python
# 在测试中使用 fixtures

@pytest.fixture
def mini_kernel():
    return MiniKernelFixture("tests/fixtures/mini-kernel/")

def test_code_indexer(mini_kernel):
    indexer = CodeIndexer()
    chunks = indexer.index_file(mini_kernel.file("kernel/sched/fair.c"))
    assert len(chunks) > 0
    assert all(chunk.start_line > 0 for chunk in chunks)

def test_git_indexer(mini_kernel):
    indexer = GitIndexer(mini_kernel.repo_path)
    commits = indexer.index_range("HEAD~50", "HEAD")
    assert len(commits) == 50
    assert any("bugfix" in c.type_tags for c in commits)

def test_kconfig_parser(mini_kernel):
    parser = KconfigParser()
    result = parser.parse(mini_kernel.file("Kconfig"))
    assert len(result.symbols) > 0
    assert "CONFIG_SMP" in result.symbols
```
