#ifndef _LINUX_NET_H
#define _LINUX_NET_H

#include <linux/types.h>
#include <linux/socket.h>

struct sock;
struct sk_buff;
struct net_device;

enum sock_type {
    SOCK_STREAM = 1,
    SOCK_DGRAM  = 2,
    SOCK_RAW    = 3,
    SOCK_RDM    = 4,
    SOCK_SEQPACKET = 5,
    SOCK_DCCP   = 6,
    SOCK_PACKET = 10,
};

struct sock {
    struct sock_common __sk_common;
    struct sk_buff_head receive_queue;
    struct sk_buff_head write_queue;
    void (*sk_data_ready)(struct sock *sk);
    void (*sk_write_space)(struct sock *sk);
    int sk_allocation;
    int sk_state;
};

#define TCP_ESTABLISHED 1
#define TCP_SYN_SENT    2
#define TCP_SYN_RECV    3
#define TCP_FIN_WAIT1   4
#define TCP_FIN_WAIT2   5
#define TCP_TIME_WAIT   6
#define TCP_CLOSE       7
#define TCP_CLOSE_WAIT  8
#define TCP_LAST_ACK    9
#define TCP_LISTEN      10
#define TCP_CLOSING     11

static inline struct sock *sk_alloc(struct net *net, int family,
                                    gfp_t priority, struct proto *prot)
{
    return kzalloc(prot->obj_size, priority);
}

void sk_free(struct sock *sk);

#ifdef CONFIG_NET_RX_BUSY_POLL
bool sk_busy_loop(struct sock *sk, int nonblock);
#endif

#endif
