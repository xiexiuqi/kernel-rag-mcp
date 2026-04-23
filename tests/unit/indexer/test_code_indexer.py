import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kernel_rag_mcp.indexer.code_indexer import CodeIndexer
from kernel_rag_mcp.indexer.parsers.tree_sitter_c import TreeSitterCParser


class TestCodeIndexer:
    def test_parse_c_file_with_functions(self):
        code = """
#include <linux/sched.h>

static void update_curr(struct cfs_rq *cfs_rq)
{
    struct sched_entity *curr = cfs_rq->curr;
    u64 now = rq_clock_task(rq_of(cfs_rq));
    u64 delta_exec;

    if (unlikely(!curr))
        return;

    delta_exec = now - curr->exec_start;
    if (unlikely((s64)delta_exec <= 0))
        return;

    curr->exec_start = now;
    curr->sum_exec_runtime += delta_exec;
    curr->vruntime += calc_delta_fair(delta_exec, curr);
}

struct task_struct *pick_next_task_fair(struct rq *rq)
{
    struct task_struct *p = NULL;
    return p;
}
"""
        parser = TreeSitterCParser()
        chunks = parser.parse_functions(code, file_path="kernel/sched/fair.c")

        assert len(chunks) == 2
        assert chunks[0].name == "update_curr"
        assert chunks[0].start_line == 4
        assert chunks[0].end_line == 20
        assert "sched_entity" in chunks[0].code

        assert chunks[1].name == "pick_next_task_fair"
        assert chunks[1].start_line == 22

    def test_parse_struct_definition(self):
        code = """
struct sched_entity {
    struct load_weight		load;
    struct rb_node			run_node;
    struct list_head		group_node;
    unsigned int			on_rq;

    u64					exec_start;
    u64					sum_exec_runtime;
    u64					vruntime;
    u64					prev_sum_exec_runtime;

    u64					nr_migrations;

#ifdef CONFIG_SMP
    struct sched_avg		avg;
#endif
};
"""
        parser = TreeSitterCParser()
        chunks = parser.parse_structs(code, file_path="include/linux/sched.h")

        assert len(chunks) == 1
        assert chunks[0].name == "sched_entity"
        assert chunks[0].start_line == 2
        assert "vruntime" in chunks[0].code
        assert "CONFIG_SMP" in chunks[0].code

    def test_extract_kconfig_conditions(self):
        code = """
#ifdef CONFIG_SMP
static void update_rq_clock(struct rq *rq)
{
    rq->clock = sched_clock();
}
#endif

#ifdef CONFIG_NUMA_BALANCING
void task_numa_work(struct callback_head *work)
{
    struct task_struct *p = current;
}
#endif
"""
        parser = TreeSitterCParser()
        conditions = parser.extract_kconfig_conditions(code)

        assert len(conditions) == 2
        assert conditions[0].condition == "CONFIG_SMP"
        assert conditions[0].start_line == 2
        assert conditions[1].condition == "CONFIG_NUMA_BALANCING"

    def test_line_number_accuracy(self):
        code = """1: #include <linux/kernel.h>
2:
3: void func_a(void)
4: {
5:     int x = 1;
6: }
7:
8: void func_b(void)
9: {
10:    int y = 2;
11: }
"""
        parser = TreeSitterCParser()
        chunks = parser.parse_functions(code, file_path="test.c")

        assert chunks[0].start_line == 3
        assert chunks[0].end_line == 6
        assert chunks[1].start_line == 8
        assert chunks[1].end_line == 11

    def test_macro_annotations(self):
        code = """
static inline struct task_struct *get_task_struct(struct task_struct *t)
{
    refcount_inc(&t->usage);
    return t;
}

#define container_of(ptr, type, member) ({ \
    void *__mptr = (void *)(ptr); \
    ((type *)(__mptr - offsetof(type, member))); })

static void *kmem_cache_alloc(struct kmem_cache *s, gfp_t gfpflags)
{
    return slab_alloc(s, gfpflags, _RET_IP_);
}
"""
        parser = TreeSitterCParser()
        chunks = parser.parse_functions(code, file_path="include/linux/kernel.h")
        macro_chunks = parser.parse_macros(code, file_path="include/linux/kernel.h")
        chunks.extend(macro_chunks)

        macro_chunk = [c for c in chunks if c.name == "container_of"]
        assert len(macro_chunk) == 1
        assert "从成员指针获取父结构体" in macro_chunk[0].annotations

    def test_index_file_with_multiple_chunks(self, tmp_path):
        code_file = tmp_path / "fair.c"
        code_file.write_text("""
#include <linux/sched.h>

static void update_curr(struct cfs_rq *cfs_rq)
{
    struct sched_entity *curr = cfs_rq->curr;
}

struct task_struct *pick_next_task_fair(struct rq *rq)
{
    return NULL;
}

struct sched_entity {
    struct load_weight load;
    u64 vruntime;
};
""")

        indexer = CodeIndexer()
        result = indexer.index_file(code_file)

        assert len(result.chunks) == 3
        assert result.file_path == str(code_file)
        assert all(c.start_line > 0 for c in result.chunks)
        assert all(c.end_line >= c.start_line for c in result.chunks)

    def test_pointer_based_indexing(self, tmp_path):
        code_file = tmp_path / "core.c"
        code_file.write_text("""
void schedule(void)
{
    struct task_struct *tsk = current;
    sched_submit_work(tsk);
    __schedule(SM_NONE);
    sched_update_worker(tsk);
}
""")

        indexer = CodeIndexer()
        result = indexer.index_file(code_file)

        assert len(result.chunks) == 1
        chunk = result.chunks[0]
        assert chunk.file_path == str(code_file)
        assert chunk.start_line == 2
        assert chunk.end_line == 8
        assert "schedule" in chunk.name
        assert not hasattr(chunk, "full_code_backup")

    def test_hot_path_file_detection(self):
        indexer = CodeIndexer()

        assert indexer.is_hot_path("kernel/sched/core.c") is True
        assert indexer.is_hot_path("mm/page_alloc.c") is True
        assert indexer.is_hot_path("net/core/dev.c") is True
        assert indexer.is_hot_path("drivers/usb/core.c") is False
        assert indexer.is_hot_path("kernel/irq/manage.c") is False

    def test_subsystem_extraction(self):
        indexer = CodeIndexer()

        assert indexer.get_subsystem("kernel/sched/core.c") == "sched"
        assert indexer.get_subsystem("mm/page_alloc.c") == "mm"
        assert indexer.get_subsystem("net/ipv4/tcp.c") == "net"
        assert indexer.get_subsystem("fs/ext4/inode.c") == "fs"


class TestCodeIndexerWithRealKernel:
    def test_index_sched_subsystem(self):
        from tests.conftest import KERNEL_REPO_PATH

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        indexer = CodeIndexer()
        sched_dir = KERNEL_REPO_PATH / "kernel/sched"

        if not sched_dir.exists():
            pytest.skip("sched subsystem not found")

        results = indexer.index_directory(sched_dir)

        assert len(results) > 0
        assert any("update_curr" in str(r.chunks) for r in results)
        assert all(r.file_path.startswith(str(sched_dir)) for r in results)

    def test_index_mm_subsystem(self):
        from tests.conftest import KERNEL_REPO_PATH

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        indexer = CodeIndexer()
        mm_dir = KERNEL_REPO_PATH / "mm"

        if not mm_dir.exists():
            pytest.skip("mm subsystem not found")

        results = indexer.index_directory(mm_dir)

        assert len(results) > 0
        assert any("page_alloc" in r.file_path for r in results)

    def test_index_net_subsystem(self):
        from tests.conftest import KERNEL_REPO_PATH

        if not KERNEL_REPO_PATH.exists():
            pytest.skip("Kernel repo not found at ~/linux")

        indexer = CodeIndexer()
        net_dir = KERNEL_REPO_PATH / "net"

        if not net_dir.exists():
            pytest.skip("net subsystem not found")

        results = indexer.index_directory(net_dir)

        assert len(results) > 0
        assert any("dev.c" in r.file_path or "skbuff.c" in r.file_path for r in results)
