/******************************************************************************
* Author: Samuel Jero <sjero@purdue.edu>
* TCP Congestion Control Proxy: Global Header
******************************************************************************/
#ifndef _SW_PROXY_H
#define _SW_PROXY_H
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <unistd.h>
#include <signal.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <errno.h>
#include <netdb.h>
#include <ifaddrs.h>
#include <pthread.h>


class Message{
	public:
		char *buff;
		int len;
		int alloc;
};

enum direction {
	NONE = 0,
	FORWARD = 1,
    BACKWARD = 2
};

class Iface;

class pkt_info {
	public:
		bool valid;
		Message msg;
		enum direction dir;
		int ip_type;
		timeval time;
		char *ip_src;
		char *ip_dst;
		char *mac_src;
		char *mac_dst;
		Iface *rcv;
		Iface *snd;
};

/* Get interface commands */
Iface *GetForwardInterface();
Iface *GetBackwardInterface();

/*debug printf
 * Levels:
 * 	0) Always print even if debug isn't specified
 *  1) Errors and warnings... Don't overload the screen with too much output
 *  2) Notes and per-packet processing info... as verbose as needed
 */
extern int proxy_debug;
void dbgprintf(int level, const char *fmt, ...);

#endif
