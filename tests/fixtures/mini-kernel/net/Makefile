obj-y := core/ ipv4/ ipv6/ unix/ packet/

obj-$(CONFIG_INET) += tcp.o udp.o icmp.o
obj-$(CONFIG_NETFILTER) += netfilter/
obj-$(CONFIG_NET_RX_BUSY_POLL) += busy_poll.o

obj-$(CONFIG_XDP_SOCKETS) += xsk.o
obj-$(CONFIG_TLS) += tls.o
