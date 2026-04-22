#include <linux/sched.h>
#include <linux/kernel.h>

struct sched_entity {
    struct load_weight load;
    struct rb_node run_node;
    struct list_head group_node;
    unsigned int on_rq;
    u64 exec_start;
    u64 sum_exec_runtime;
    u64 vruntime;
    u64 prev_sum_exec_runtime;
    u64 nr_migrations;
#ifdef CONFIG_SMP
    struct sched_avg avg;
#endif
};

struct cfs_rq {
    struct load_weight load;
    unsigned long runnable_weight;
    unsigned int nr_running;
    unsigned int h_nr_running;

#ifdef CONFIG_SMP
    u64 exec_clock;
    u64 min_vruntime;
#endif

    struct rb_root_cached tasks_timeline;
    struct sched_entity *curr;
    struct sched_entity *next;
    struct sched_entity *last;
    struct sched_entity *skip;
};

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

static struct task_struct *pick_next_task_fair(struct rq *rq)
{
    struct task_struct *p = NULL;
    struct cfs_rq *cfs_rq = &rq->cfs;
    struct sched_entity *se;

    if (!cfs_rq->nr_running)
        return NULL;

    se = pick_next_entity(cfs_rq);
    set_next_entity(cfs_rq, se);
    p = task_of(se);

    return p;
}

#ifdef CONFIG_SMP
static void update_rq_clock(struct rq *rq)
{
    rq->clock = sched_clock();
    rq->clock_task = rq->clock;
}
#endif

void scheduler_tick(void)
{
    int cpu = smp_processor_id();
    struct rq *rq = cpu_rq(cpu);
    struct task_struct *curr = rq->curr;

    update_rq_clock(rq);
    curr->sched_class->task_tick(rq, curr, 0);
}
