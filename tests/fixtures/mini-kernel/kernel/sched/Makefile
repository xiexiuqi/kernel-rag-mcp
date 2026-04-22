obj-y += core.o fair.o rt.o deadline.o stop_task.o
obj-y += pelt.o

obj-$(CONFIG_SMP) += cpudeadline.o topology.o
obj-$(CONFIG_SCHED_AUTOGROUP) += autogroup.o
obj-$(CONFIG_SCHEDSTATS) += stats.o
obj-$(CONFIG_SCHED_DEBUG) += debug.o

obj-$(CONFIG_SCHED_CORE) += sched_core.o

ifdef CONFIG_FUNCTION_TRACER
CFLAGS_REMOVE_cputime.o = -pg
endif
