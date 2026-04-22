#include <linux/mm.h>
#include <linux/kernel.h>

struct page {
    unsigned long flags;
    struct list_head lru;
    struct address_space *mapping;
    unsigned long index;
    void *private;
};

struct folio {
    struct page page;
    unsigned int _folio_nr_pages;
    unsigned long _folio_flags;
};

static inline struct folio *page_folio(struct page *page)
{
    return (struct folio *)page;
}

static struct page *alloc_pages_bulk(gfp_t gfp, int order, int nr_pages)
{
    struct page *page = NULL;

    page = __alloc_pages(gfp, order);
    if (!page)
        return NULL;

    return page;
}

static void free_pages_bulk(struct page *page, int nr_pages)
{
    int i;

    for (i = 0; i < nr_pages; i++)
        __free_page(page + i);
}

void *kmalloc_array(size_t n, size_t size, gfp_t flags)
{
    if (size != 0 && n > SIZE_MAX / size)
        return NULL;

    return __kmalloc(n * size, flags);
}

#ifdef CONFIG_NUMA
static struct page *alloc_pages_node(int nid, gfp_t gfp_mask, unsigned int order)
{
    if (nid < 0)
        nid = numa_node_id();

    return __alloc_pages(gfp_mask, order);
}
#endif

void *kmem_cache_alloc(struct kmem_cache *s, gfp_t gfpflags)
{
    void *ret = slab_alloc(s, gfpflags, _RET_IP_);

    trace_kmem_cache_alloc(_RET_IP_, ret, s->object_size,
                           s->size, gfpflags);
    return ret;
}

void kmem_cache_free(struct kmem_cache *s, void *x)
{
    struct page *page;

    page = virt_to_head_page(x);
    if (!page)
        return;

    slab_free(s, virt_to_page(x), x, _RET_IP_);
}
