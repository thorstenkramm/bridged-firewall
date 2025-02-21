#!/bin/bash

RULES_V4="/etc/firewall/rules.v4"
RULES_V6="/etc/firewall/rules.v6"
PRE_RULES="/etc/firewall/pre-rules.sh"

validate_firewall() {
    if iptables-restore -t < "$RULES_V4";then 
        echo "IPv4 rules are valid."
    else
        echo "IPv4 rules $RULES_V4 contain errors."
        return 1
    fi
    if ip6tables-restore -t < "$RULES_V6"; then
        echo "IPv6 rules are valid."
    else
        echo "IPv6 rules $RULES_V6 contain errors."
        return 1
    fi
}

start_firewall() {
    # First validate the rules
    if ! validate_firewall; then
        echo "Firewall rules validation failed. Not loading rules."
        exit 1
    fi

    if [ -x "$PRE_RULES" ]; then
        if "$PRE_RULES";then
            true
        else
            echo "Pre-rules $PRE_RULES script failed. Exiting"
            exit 2
        fi
    else
        echo "Pre-rules $PRE_RULES script not found or not executable. Skipping."
    fi
    iptables-restore < "$RULES_V4" && echo "IPv4 rules loaded."
    ip6tables-restore < "$RULES_V6" && echo "IPv6 rules loaded."
}

stop_firewall() {
    iptables -P INPUT ACCEPT
    iptables -P FORWARD ACCEPT
    iptables -P OUTPUT ACCEPT
    iptables -F
    ip6tables -P INPUT ACCEPT
    ip6tables -P FORWARD ACCEPT
    ip6tables -P OUTPUT ACCEPT
    ip6tables -F
    echo "Firewall rules cleared and policies set to ACCEPT."
}

restart_firewall() {
    validate_firewall && start_firewall
}

case "$1" in
    start)
        start_firewall
        ;;
    stop)
        stop_firewall
        ;;
    validate)
        validate_firewall
        ;;
    restart)
        restart_firewall
        ;;
    *)
        echo "Usage: $0 {start|stop|validate|restart}"
        exit 1
        ;;
esac
