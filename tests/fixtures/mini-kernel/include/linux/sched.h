#ifndef _LINUX_SCHED_H
#define _LINUX_SCHED_H

#include <linux/types.h>
#include <linux/list.h>
#include <linux/rbtree.h>

struct task_struct {
    pid_t pid;
    volatile long state;
    void *stack;
    struct list_head tasks;
    struct mm_struct *mm;
    struct sched_class *sched_class;
    struct sched_entity se;
    struct sched_rt_entity rt;
    struct sched_dl_entity dl;
    int prio;
    int static_prio;
    int normal_prio;
    unsigned int rt_priority;
};

struct sched_class {
    const struct sched_class *next;
    void (*enqueue_task) (struct rq *rq, struct task_struct *p, int flags);
    void (*dequeue_task) (struct rq *rq, struct task_struct *p, int flags);
    void (*yield_task)   (struct rq *rq);
    bool (*yield_to_task)(struct rq *rq, struct task_struct *p);
    void (*check_preempt_curr)(struct rq *rq, struct task_struct *p, int flags);
    struct task_struct *(*pick_next_task)(struct rq *rq);
    void (*put_prev_task)(struct rq *rq, struct task_struct *p);
    void (*set_curr_task)(struct rq *rq);
    void (*task_tick)(struct rq *rq, struct task_struct *p, int queued);
    void (*task_fork)(struct task_struct *p);
    void (*task_dead)(struct task_struct *p);
};

extern struct task_struct *current;

static inline struct task_struct *get_current(void)
{
    return current;
}

#define current get_current()

void schedule(void);
void scheduler_tick(void);

#endif
