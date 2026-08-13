#!/bin/sh
# Locked-down entrypoint for the scaife-viewer container.
#
# On start:
#   1. As root (via compose's `user: "0"` + cap_add: NET_ADMIN), install
#      OUTPUT firewall rules that only permit traffic to Docker-private
#      networks. All other outbound is REJECTed at the kernel level.
#   2. Drop privileges to the `scaife` user and exec the standard
#      deploy/entrypoint.sh so migrations, prepare_atlas_db, and gunicorn
#      run as non-root.
set -e

echo "[entrypoint-locked] installing outbound firewall rules"

# Default policies stay ACCEPT (we filter with explicit rules).
iptables -F OUTPUT

# Allow loopback (127.0.0.0/8) — Django hits its own worker sockets.
iptables -A OUTPUT -o lo -j ACCEPT

# Allow return traffic for inbound connections (host -> :8000 replies).
iptables -A OUTPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT

# Allow all Docker-private subnets — sv-postgres, sv-elasticsearch,
# morpheus, and Docker's embedded DNS at 127.0.0.11 all live here.
iptables -A OUTPUT -d 127.0.0.0/8      -j ACCEPT
iptables -A OUTPUT -d 172.16.0.0/12    -j ACCEPT
iptables -A OUTPUT -d 10.0.0.0/8       -j ACCEPT
iptables -A OUTPUT -d 192.168.0.0/16   -j ACCEPT
iptables -A OUTPUT -d 169.254.0.0/16   -j ACCEPT

# Everything else — the public internet — is rejected. `--reject-with
# icmp-net-unreachable` gives calling code a fast, unambiguous failure.
iptables -A OUTPUT -j REJECT --reject-with icmp-net-unreachable

echo "[entrypoint-locked] outbound firewall active; dropping to scaife"

# su-exec preserves environment and exec()s into a lower-privilege
# process — after this line, we are the `scaife` user without NET_ADMIN.
exec su-exec scaife:scaife deploy/entrypoint.sh "$@"
