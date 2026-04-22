#include <linux/net.h>
#include <linux/skbuff.h>
#include <linux/kernel.h>

struct sk_buff {
    union {
        struct {
            struct sk_buff *next;
            struct sk_buff *prev;
        };
        struct rb_node rbnode;
    };
    struct sock *sk;
    struct net_device *dev;
    unsigned int len;
    unsigned int data_len;
    __u16 mac_len;
    __u16 hdr_len;
};

static inline struct sk_buff *skb_alloc(gfp_t priority)
{
    return __alloc_skb(0, priority, 0, NUMA_NO_NODE);
}

static inline void skb_free(struct sk_buff *skb)
{
    if (!skb)
        return;
    kfree_skb(skb);
}

static int tcp_sendmsg(struct sock *sk, struct msghdr *msg, size_t size)
{
    struct tcp_sock *tp = tcp_sk(sk);
    struct sk_buff *skb;
    int err;

    if (unlikely(sk->sk_state == TCP_CLOSE))
        return -EPIPE;

    skb = skb_alloc(sk->sk_allocation);
    if (!skb)
        return -ENOBUFS;

    err = tcp_add_data_len(sk, size);
    if (err) {
        skb_free(skb);
        return err;
    }

    return tcp_push(sk, msg, size);
}

static int tcp_recvmsg(struct sock *sk, struct msghdr *msg,
                       size_t len, int nonblock, int flags,
                       int *addr_len)
{
    struct tcp_sock *tp = tcp_sk(sk);
    int copied = 0;

    if (sk->sk_state == TCP_LISTEN)
        return -ENOTCONN;

    do {
        struct sk_buff *skb = tcp_recv_skb(sk, tp, flags);
        if (!skb)
            break;

        copied += skb_copy_datagram_msg(skb, 0, msg, len - copied);
        skb_free(skb);
    } while (copied < len);

    return copied;
}

#ifdef CONFIG_NET_RX_BUSY_POLL
static inline bool sk_busy_loop(struct sock *sk, int nonblock)
{
    if (!sock_flag(sk, SOCK_BUSY_POLL))
        return false;

    return sk_ll_busy(sk) || sk_rx_busy(sk);
}
#endif
