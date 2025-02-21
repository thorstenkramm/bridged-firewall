## Bridged Firewall explained with examples

### Why bridged and not nat-ed

If you are faced with the task of filtering network packets on an existing network without
changing the topology, a bridged firewall is your best, and often only, option.

Let's say you have a class C network, `like 192.168.178.0/24`, and you want to firewall port 22 of a single host.
and it's not possible to change the IP address of the host you want to protect,  install a bridged firewall. 

```text
┌─────────────────────────────┐
│  Network 192.168.178.0/24   │
│             │               │
│             │               │
│            wan              │
│             │               │
│     ┌───────┴──────────┐    │
│     │ Bridged Firewall │    │
│     └───────┬──────────┘    │
│             │               │
│            lan              │
│             │               │
│             ▼               │
│     ┌──────────────────┐    │
│     │      Host        │    │ 
│     │  192.168.178.50  │    │
│     └──────────────────┘    │
└─────────────────────────────┘
```

The bridge acts like an ethernet switch. But with the ability to filter packets.

### Rename network devices (optional)

Giving your network cards comprehensive names like "lan" and "wan" makes things easier.
It also prevents network card changing their names on distribution upgrades.

Below is an example of how to rename network devices based on their MAC address:

```bash
cat << EOF > /etc/udev/rules.d/10-network.rules
SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="<yo:ur:ma:c1>", NAME="wan"
SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="<yo:ur:ma:c2>", NAME="lan"
EOF
udevadm control --reload-rules
udevadm trigger
reboot
```

In this example, 'lan' is the device on which the devices protected by the firewall are located. 
And 'wan' is the whole network that all the devices are part of.

### Create a bridge

It is theoretically possible to create a bridge without assigning an IP address. This would require 
to perform all tasks with the keyboard and display connected to the device, or via a serial connection.
This wouldn't be a realistic scenario. So we assign an IP address to ssh into the machine.
It's like building a managed switch with a management interface.

Install required bridge utils:

    apt install bridge-utils

Create an "empty" bridge that has no devices connected:

   brctl addbr br0

Although it is possible to make all the changes to a bridge on the fly, we will not do so 
in order not to jeopardise our SSH connection.  
Configuring the bridge with a configuration file from the start also has the advantage that
your setup is reboot safe.

Assuming your are using ifupdown for network configuration, let's create a configuration that
- adds the two networks cards, named `lan` and `wan` to the bridge. (This is like plugin them into a switch)
- assign the bridge an IP address. (This is like adding an invisible device to the switch and give it an IP address)

Your `/etc/network/interfaces` could look like this:

```text
# The loopback interface
auto lo
iface lo inet loopback

# The WAN interface
auto wan
iface wan inet manual

# The LAN interface
auto lan
iface lan inet manual

# The bridge interface
auto br0
iface br0 inet static
    bridge_ports wan lan
    address 192.168.178.140/24
    netmask 255.255.255.0
    gateway 192.168.178.1
```

After a reboot you should be able to log in via SSH as you did before.

### Packet filtering

#### Activate bridge packet filtering

🧨 It's important to note that **bridged traffic by default bypasses the iptables FORWARD chain completely**.
This is why any DROP policies would not have any effect.
The bridge is handling packets at layer 2 before they could reach the iptables filtering at layer 3.

To make bridged traffic pass through iptables, you need to enable bridge netfilter.

```bash
# Load the required kernel module
echo "br_netfilter" > /etc/modules-load.d/br_netfilter.conf
modprobe br_netfilter

# Activate bridge filtering
cat << EOF > /etc/sysctl.d/98-bridge-netfilter.conf
net.bridge.bridge-nf-call-iptables=1
net.bridge.bridge-nf-call-ip6tables=1
EOF
sysctl -p
```

#### Use iptables to control who can pass the bridge
If you haven't tinkered with firewall rules yet, the bridge will let pass all packets as it were an unmanaged switch.

**🔔 Pay attention to ipv6:** Even if the device running the bridge has no ipv6 configured, the bridge will
let ipv6 packets pass unfiltered. This can become a serious security issue, if don't manage ipv6 filtering.

All filtering is done via the iptables and ip6tables forward chain.

Let's close the bridge. Nothing will go through it. This will not affect your SSH connection as these packets only
flow through the input chain.

    # Reset all rules (ipv4 and ipv6)
    iptables -F
    ip6tables -F

    # Close the forward chains  (ipv4 and ipv6)
    iptables -P FORWARD DROP
    ip6tables -P FORWARD DROP

Now try to ping or ssh into the protected device from a device on the "wan". It will fail. The firewall is in place 🎉.
The filtering is bi-directional! The device behind the firewall is completely cut off from the network.

From now on we concentrate on ipv4 filtering. As long as we keep the ipv6 forwarding closed, we are safe.

Remember that TCP is a game of sending messages and receiving responses. Both need to flow through our bridged firewall.
If you allow a packet to flow from the WAN to the LAN, you must also allow the response to flow in the opposite direction.
You could do this on a rule-by-rule basis, but you don't have to. The kernel's netfilter logic - also known as iptables - can
can allow all responses belonging to a connection initiated by allowed connections.

    # Allow established and related packet. 
    # Required because all responses must flow through the forward chain.
    iptables -I FORWARD -m physdev --physdev-is-bridged -m state --state ESTABLISHED,RELATED -j ACCEPT

Let's allow ICMP ping:

    iptables -A FORWARD -m physdev --physdev-is-bridged -p icmp --icmp-type echo-request -j ACCEPT

Let's allow SSH to the protected device:

    iptables -A FORWARD -m physdev --physdev-is-bridged -d 192.168.178.50 -p tcp --dport 22 -j ACCEPT

Now you should be able to SSH access to the protected device. You can use all iptables filters you already know from
nat-ed firewalls. If you want to allow SSH from a single box only, try this:

    iptables -A FORWARD -m physdev --physdev-is-bridged -d 192.168.178.50 -s 192.168.178.30 -p tcp --dport 22 -j ACCEPT

The devices behind the firewall don't have access to the surrounding network yet. Except for ICMP ping. 
So let's enable unfiltered wan access for the protected devices. Bare in mind, it's ipv4 only, as we keep the ipv6 still closed.

    # Give devices behind firewall unfiltered ipv4 access to the wan
    iptables -I FORWARD -m physdev --physdev-in lan --physdev-out wan --physdev-is-bridged -j ACCEPT

### Create persisting reboot-safe rules

To create persisting rules that will be loaded on boot, `ufw` falls short. It's not designed for this task.

Let's create a script that validates and loads iptables rules:

```bash
curl https://raw.githubusercontent.com/thorstenkramm/bridged-firewall/refs/heads/main/firewall.sh > /usr/local/sbin/firewall
chmod 0700 /usr/local/sbin/firewall
mkdir /etc/firewall/
chmod 0700 /etc/firewall

# Create ipv4 rules
cat << EOF > /etc/firewall/rules.v4
# ipv4 rules loaded into iptables
*filter
:INPUT ACCEPT [0:0]
:FORWARD DROP [0:0]
:OUTPUT ACCEPT [0:0]

# Allow related packets
-I FORWARD -m physdev --physdev-is-bridged -m state --state ESTABLISHED,RELATED -j ACCEPT
COMMIT
EOF

# Create ipv6 rules
cat << EOF > /etc/firewall/rules.v6
# ipv6 rules loaded into iptables
*filter
:INPUT ACCEPT [0:0]
:FORWARD DROP [0:0]
:OUTPUT ACCEPT [0:0]
COMMIT
EOF

# Create pre-rules
cat << EOF > /etc/firewall/pre-rules.sh
#!/bin/sh -e
modprobe br_netfilter
sysctl net.bridge.bridge-nf-call-iptables=1
sysctl net.bridge.bridge-nf-call-ip6tables=1
EOF

chmod 0600 /etc/firewall/*
```

The above examples are very basic and the do not filter anything on the incoming chain. You must adapt the rules to your needs!

Finally create a systemd service to control the firewall: 

```bash
cat << EOF > /etc/systemd/system/firewall.service
[Unit]
Description=Firewall Rules Service
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/firewall start
ExecStop=/usr/local/sbin/firewall stop
ExecReload=/usr/local/sbin/firewall restart

[Install]
WantedBy=multi-user.target
EOF
```

And load it on boot:

    systemctl enable --now firewall

### Extend firewall rules with jinja

Many iptables based firewalls are implemented as simple bash scripts executing the `iptables` command countless times
as shown in the below example:

    #!/bin/bash
    iptables -F
    iptables -P FORWARD DROP 
    iptables -A FORWARD -m physdev --physdev-is-bridged -p icmp --icmp-type echo-request -j ACCEPT
    # ... more rules to load

The advantage of this solution is, you can use shell variables and you can add basic logic like if-else or loops.

The downside is, you cannot test the entire rule set before activating it. One iptables command may succeed, another may
fail. Using `set -e` might make things worse. Loading the rules can stop at some point leaving crucial rules at the 
bottom of the file unloaded.

Loading rules – as shown above – from an iptables readable file has the downside that variables are not supported.

Adding jinja support to your firewall rules compensates for the disadvantage of the missing variables support.

Rules can be written like this:

    -A INPUT -p tcp -s {{ bastion_host }} --dport 22 -j ACCEPT
    -A INPUT -p tcp -s {{ api.client }} --dport {{ api.port }} -j ACCEPT

Jinja will render the rules before loading into iptables. This allows validation of the entire file before activating.

#### Install firewall with Jinja support

Download a python version of the previously suggested bash version of a firewall script.

    curl https://raw.githubusercontent.com/thorstenkramm/bridged-firewall/refs/heads/main/firewall.py > /usr/local/sbin/firewall
    chmod 0700 /usr/local/sbin/firewall

Install required python modules:

    apt-get install python3-yaml python3-jinja2

Create a yaml file `/etc/firewall/vars.yml` to define variables:

```yaml
#
# Variables to be used in /etc/firewall/rules.v4 and /etc/firewall/rules.v6
#
bastion_hosts:
  - 192.168.1.1
  - 10.100.200.1
api:
  client: 192.168.99.99
  port: 8080
```

To get a preview of the rules use `firewall --render`.

```bash
$ firewall --render

=== IPv4 Rules ===
-A INPUT -p tcp --dport 22 -s 192.168.1.1 -j ACCEPT
-A INPUT -p tcp --dport 22 -s 10.100.200.1 -j ACCEPT
-A INPUT -p tcp -s 192.168.99.99 --dport 8080 -j ACCEPT
```