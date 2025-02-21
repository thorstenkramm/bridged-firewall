#!/bin/sh
set -e
#
# This script is executed before ipv4 and ipv6 rules are loaded into iptables
#


# TCP hardening
sysctl -w net.ipv4.tcp_syncookies=1
sysctl -w net.ipv4.tcp_max_syn_backlog=2048
sysctl -w net.ipv4.tcp_synack_retries=2
sysctl -w net.ipv4.tcp_syn_retries=5
