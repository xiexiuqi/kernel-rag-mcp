import os
from pathlib import Path

KERNEL_REPO_PATH = Path(os.environ.get("KERNEL_REPO", "~/linux")).expanduser()
BASE_VERSION = "v6.19"
TARGET_VERSION = "v7.0-rc6"
TARGET_SUBSYSTEMS = ["kernel/sched", "mm", "net"]
FIXTURES_DIR = Path(__file__).parent / "fixtures"
MINI_KERNEL_DIR = FIXTURES_DIR / "mini-kernel"
SAMPLE_COMMITS_DIR = FIXTURES_DIR / "sample-commits"
PERFORMANCE_SCORE_THRESHOLD = 0.5
PERFORMANCE_PROBABLE_THRESHOLD = 0.3
INDEX_PERFORMANCE_TARGETS = {
    "full_index_time_gpu": 3600,
    "full_index_time_cpu": 28800,
    "incremental_update_time": 180,
    "query_latency_p95_baseline": 0.5,
    "query_latency_p95_delta": 0.8,
    "causal_graph_query_latency": 0.2,
}
PERFORMANCE_CODE_PATTERNS = [
    r"\+\s*likely\(",
    r"\+\s*unlikely\(",
    r"\+\s*READ_ONCE\(",
    r"\+\s*WRITE_ONCE\(",
    r"\+\s*per_cpu\(",
    r"\+\s*this_cpu\(",
    r"\+\s*prefetch\(",
    r"\+\s*prefetchw\(",
    r"\+\s*static_branch_",
    r"\+\s*__always_inline",
    r"\+\s*alloc_pages_bulk",
    r"\+\s*kmalloc_array",
    r"\-\s*spin_lock\(.*\)\n\+\s*rcu_read_lock",
    r"\+\s*kfree_bulk",
    r"\+\s*__percpu",
    r"\+\s*NAPI",
    r"\+\s*busy_poll",
    r"\+\s*XDP",
]
HOT_PATH_PATTERNS = [
    r"kernel/sched/.*",
    r"mm/page_alloc\.c",
    r"mm/slab\.c",
    r"mm/slub\.c",
    r"net/core/dev\.c",
    r"net/core/skbuff\.c",
    r"lib/radix-tree\.c",
    r"lib/rhashtable\.c",
    r"arch/x86/mm/.*",
    r"kernel/locking/.*",
]
PERFORMANCE_EXPERTS = [
    "Peter Zijlstra",
    "Mel Gorman",
    "Eric Dumazet",
    "Ingo Molnar",
    "Thomas Gleixner",
]
