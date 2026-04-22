#ifndef _LINUX_MM_H
#define _LINUX_MM_H

#include <linux/types.h>
#include <linux/list.h>

struct page;
struct folio;
struct kmem_cache;

typedef unsigned long gfp_t;

#define GFP_KERNEL  (__GFP_RECLAIM | __GFP_IO | __GFP_FS)
#define GFP_ATOMIC  (__GFP_HIGH)

#define NUMA_NO_NODE    (-1)

struct page *alloc_pages(gfp_t gfp, unsigned int order);
void __free_pages(struct page *page, unsigned int order);

static inline void __free_page(struct page *page)
{
    __free_pages(page, 0);
}

void *kmalloc(size_t size, gfp_t flags);
void kfree(const void *objp);
void *kmem_cache_alloc(struct kmem_cache *, gfp_t);
void kmem_cache_free(struct kmem_cache *, void *);

static inline void *kzalloc(size_t size, gfp_t flags)
{
    return kmalloc(size, flags | __GFP_ZERO);
}

#ifdef CONFIG_NUMA
struct page *alloc_pages_node(int nid, gfp_t gfp_mask, unsigned int order);
#endif

#endif
