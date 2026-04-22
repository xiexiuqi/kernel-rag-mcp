# 性能相关的 RAG 索引内容补充，请根据下文描述补充到各子系统的设计文档中，如有不合理的地方指出来，并修正。

**只看标题（subject）漏招率极高**。内核社区很多性能补丁的标题非常隐晦，比如 `"mm: use per-cpu list for page allocation"` 或 `"sched: reduce rq lock contention"`，如果不认识这些术语，根本抓不到"性能"信号。

性能 Patch 的识别必须是**多源融合**的：标题 + 正文 + diff 代码模式 + 统计特征 + 专家关联。

------

## 1. 标题（Subject）——第一信号，但最浅



| 关键词模式                                            | 示例                                 | 可信度                |
| :---------------------------------------------------- | :----------------------------------- | :-------------------- |
| `optim*`, `speedup`, `fast*`, `latency`, `throughput` | `sched: optimize vruntime update`    | 高                    |
| `reduce *contention*`, `reduce *overhead*`            | `mm: reduce lock contention in slab` | 高                    |
| `batch`, `bulk`, `coalesce`                           | `net: batch skb allocations`         | 高                    |
| `cache*`, `prefetch`, `locality`                      | `mm: improve NUMA locality`          | 高                    |
| `scale*`, `scalable`                                  | `fs: scalable inode allocation`      | 高                    |
| `use percpu*`, `per-cpu`                              | `net: use per-cpu counters`          | 中高                  |
| `lockless`, `lock-free`, `RCU`                        | `kernel: convert to RCU lookup`      | 中高                  |
| `inline`, `__always_inline`                           | `mm: inline hot path`                | 中                    |
| `remove *unnecessary*`, `avoid *redundant*`           | `sched: avoid redundant updates`     | 中（可能是 refactor） |

**问题**：大量性能补丁标题**没有**这些词。比如：

- `"tcp: switch to rhashtable for ehash"`（标题无性能词，但 rhashtable 是性能优化）
- `"mm: use alloc_pages_bulk"`（bulk 是信号，但 `"mm: use order-0 pages for small allocs"` 就完全无关键词）

------

## 2. 正文（Commit Message Body）——第二信号，关键补充

正文里常有**设计动机**和**量化数据**，这是标题没有的：

表格





| 正文模式              | 示例                                                         | 说明         |
| :-------------------- | :----------------------------------------------------------- | :----------- |
| **性能声明句**        | `"This improves performance by ~15% on the benchmark..."`    | 直接声明     |
| **延迟/吞吐数据**     | `"reduces latency from 100us to 20us"`                       | 量化指标     |
| **瓶颈描述**          | `"The current implementation suffers from cache-line bouncing..."` | 问题诊断     |
| **Benchmark 引用**    | `"Tested with hackbench/schbench/fio/netperf"`               | 性能测试工具 |
| **Before/After 对比** | `"Before: X cycles per op, After: Y cycles"`                 | 数据对比     |
| **热路径声明**        | `"This is on the fast path of schedule()..."`                | 上下文说明   |
| **锁竞争描述**        | `"Eliminates the need to take the rq lock..."`               | 并发优化     |
| **内存序说明**        | `"Use READ_ONCE to avoid unnecessary barriers"`              | 内存优化     |

**抓取策略**：用正则/NER 提取 `"improve* by X%"`、`"reduce* latency"`、`"benchmark"`、`"cycles"` 等模式。

------

## 3. Diff 代码内容——最强信号，权重应最高

很多性能补丁在标题和正文里都不说"性能"，但**代码模式出卖了一切**。这是你最该投入的地方：

### 3.1 内核性能代码指纹（Code Fingerprints）

表格





| 代码模式                                      | 性能含义                   | 示例                              |
| :-------------------------------------------- | :------------------------- | :-------------------------------- |
| `+ likely()` / `+ unlikely()`                 | 分支预测优化               | `if (likely(ptr))`                |
| `+ READ_ONCE()` / `+ WRITE_ONCE()`            | 内存访问序优化，减少屏障   | `READ_ONCE(p->counter)`           |
| `+ per_cpu*()` / `+ this_cpu*()`              | 避免缓存竞争，per-cpu 优化 | `this_cpu_inc(stat)`              |
| `+ prefetch*()` / `+ prefetchw()`             | 预取优化                   | `prefetch(skb->data)`             |
| `+ static_branch_*()` / `+ jump_label`        | 条件分支运行时优化         | `static_branch_likely(&key)`      |
| `+ __always_inline`                           | 强制内联热函数             | `static __always_inline void f()` |
| `+ hlist_*` 替代 `list_*`                     | 遍历优化（head list 更小） | `hlist_for_each_entry`            |
| `+ alloc_pages_bulk()`                        | 批量分配减少锁竞争         | `alloc_pages_bulk()`              |
| `+ kmalloc_array()` 替代循环 `kmalloc()`      | 批量分配                   | 减少系统调用开销                  |
| `+ spin_lock_bh()` → `+ local_bh_disable()`   | 锁粒度优化                 | 减少锁持有时间                    |
| `- spin_lock()` `+ rcu_read_lock()`           | 锁→RCU 转换，读端无锁      | 经典性能优化                      |
| `+ mutex` → `+ rwsem` / `+ seqlock`           | 锁类型升级                 | 读多写少场景                      |
| `+ kfree_bulk()` / `+ kmem_cache_free_bulk()` | 批量释放                   | 减少锁竞争                        |
| `+ cpumask_*` 批量操作                        | CPU 掩码批量处理           | 减少遍历开销                      |
| `+ __percpu` 变量新增                         | per-cpu 数据结构设计       | 避免 false sharing                |
| `+ NAPI` / `+ busy_poll` / `+ XDP`            | 网络性能路径               | 网络子系统专有                    |
| `+ SLAB/SLUB` 调整                            | 分配器优化                 | `kmem_cache_create` 参数变化      |
| `+ workqueue` → `+ irq_work` / `+ tasklet`    | 下半部机制优化             | 延迟敏感路径                      |
| `+ batch` / `+ bulk` 变量或函数               | 批处理逻辑                 | `process_batch()`                 |

### 3.2 反模式（排除噪音）

表格





| 模式                           | 说明                             |
| :----------------------------- | :------------------------------- |
| `+ __init` / `+ __exit`        | 启动/卸载路径，非运行时性能      |
| `+ pr_err` / `+ printk`        | 增加日志，通常是 debug 或 bugfix |
| `+ WARN_ON` / `+ BUG_ON`       | 防御性代码，非性能               |
| 大量 `+ #ifdef CONFIG_DEBUG_*` | debug 代码，与性能无关           |

### 3.3 文件路径信号

修改以下文件高度暗示性能改动：

plain

复制

```plain
kernel/sched/       # 调度器热路径
mm/page_alloc.c     # 页面分配热路径
mm/slab.c / slub.c  # 分配器
net/core/dev.c      # 网络设备层
net/core/skbuff.c   # skb 分配
lib/radix-tree.c    # 基础数据结构
lib/rhashtable.c     # 哈希表
arch/x86/mm/        # TLB/页表优化
kernel/locking/     # 锁优化
```

------

## 4. 统计特征——辅助信号

表格





| 特征                                   | 性能含义         | 说明                             |
| :------------------------------------- | :--------------- | :------------------------------- |
| **删多增少**（-50, +10）               | 简化热路径       | 性能优化常伴随代码精简           |
| **修改 1 个核心文件，影响 10+ 调用点** | 基础数据结构优化 | 如 `list_head` 改动              |
| **新增 `.h` 中的 inline 函数**         | 头文件内联优化   | 热路径展开                       |
| **修改 `include/linux/` 基础类型**     | 广泛影响         | 可能是 `atomic_t` → `atomic64_t` |

------

## 5. 社区元数据——专家关联

表格





| 信号                            | 说明                                                         |
| :------------------------------ | :----------------------------------------------------------- |
| **Reviewed-by: Peter Zijlstra** | 调度器/锁性能专家                                            |
| **Reviewed-by: Mel Gorman**     | 内存管理性能专家                                             |
| **Reviewed-by: Eric Dumazet**   | 网络性能专家                                                 |
| **Tested-by: KernelCI / 0-day** | 自动化性能测试通过                                           |
| **关联 benchmark patch**        | 同一系列中有 `tools/testing/selftests/` 或 `perf bench` 修改 |

------

## 6. 综合识别策略（建议的打分模型）

Python

复制

```python
def classify_performance_patch(commit) -> float:
    score = 0.0
    
    # 1. 标题关键词 (权重 0.2)
    if matches_performance_keywords(commit.subject):
        score += 0.2
    
    # 2. 正文性能声明 (权重 0.15)
    if has_performance_claim(commit.body):  # "improve performance by X%"
        score += 0.15
    
    # 3. Diff 代码指纹 (权重 0.45) —— 最重要
    perf_patterns = count_performance_code_patterns(commit.diff)
    score += min(0.45, perf_patterns * 0.05)  # 每个模式 +0.05，封顶 0.45
    
    # 4. 文件路径 (权重 0.1)
    if touches_hot_path_files(commit.files):
        score += 0.1
    
    # 5. 统计特征 (权重 0.05)
    if is_simplification_heavy(commit.stats):  # 删多增少
        score += 0.05
    
    # 6. 专家关联 (权重 0.05)
    if reviewed_by_performance_expert(commit.reviewers):
        score += 0.05
    
    # 阈值
    if score >= 0.5:
        return "performance"
    elif score >= 0.3:
        return "probably_performance"
    else:
        return "other"
```

------

## 7. 一个真实案例的多源分析

**Commit**: `mm: use per-cpu list for page allocation` (虚构但典型)

表格





| 来源     | 内容                                                         | 性能信号强度           |
| :------- | :----------------------------------------------------------- | :--------------------- |
| 标题     | `mm: use per-cpu list for page allocation`                   | 中（`per-cpu` 是线索） |
| 正文     | `"This reduces contention on zone->lock in high allocation rate workloads..."` | 强（直接说减少锁竞争） |
| 正文     | `"Benchmark: hackbench -l 100000 improves by 12%"`           | 强（量化数据）         |
| Diff     | `+ this_cpu_add(zone->pages_allocated, 1)`                   | 强（per-cpu API）      |
| Diff     | `- spin_lock(&zone->lock)`（删除或缩小临界区）               | 强（锁优化指纹）       |
| 文件     | `mm/page_alloc.c`                                            | 强（热路径文件）       |
| Reviewer | `Reviewed-by: Mel Gorman`                                    | 中（内存性能专家）     |

**结论**：即使标题没有 `optim` 或 `speedup`，综合打分 **0.85+**，明确是性能 Patch。

------

## 总结

> **识别性能 Patch 不能靠"标题关键词匹配"这种单维度策略。正确的做法是：标题给初筛，正文给动机，diff 代码给铁证，文件路径给上下文，专家签名给背书。Diff 中的 `percpu`/`likely`/`READ_ONCE`/`alloc_pages_bulk`/锁转换等代码指纹，权重应该最高，因为代码不说谎。**