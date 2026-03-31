# firewall-cmd — Firewalld Command Reference

## Overview

`firewall-cmd` is the command-line client for firewalld, the dynamic firewall manager on Fedora, RHEL, and CentOS.

## Zones

Firewalld uses zones to define trust levels for network connections.

```bash
# List all available zones
firewall-cmd --get-zones

# Get the default zone
firewall-cmd --get-default-zone

# Set the default zone
firewall-cmd --set-default-zone=public

# List active zones and their interfaces
firewall-cmd --get-active-zones
```

## Managing Ports

```bash
# Open a port (runtime only — lost on reload/reboot)
firewall-cmd --add-port=8080/tcp

# Open a port permanently
firewall-cmd --add-port=8080/tcp --permanent
firewall-cmd --reload

# Open a range of ports
firewall-cmd --add-port=3000-3100/tcp --permanent

# Remove a port
firewall-cmd --remove-port=8080/tcp --permanent
firewall-cmd --reload

# List open ports
firewall-cmd --list-ports
```

## Managing Services

```bash
# Allow a predefined service
firewall-cmd --add-service=http --permanent
firewall-cmd --add-service=https --permanent
firewall-cmd --reload

# Remove a service
firewall-cmd --remove-service=http --permanent

# List allowed services
firewall-cmd --list-services

# List all predefined services
firewall-cmd --get-services
```

## Rich Rules

For more complex rules:

```bash
# Allow traffic from a specific IP
firewall-cmd --add-rich-rule='rule family="ipv4" source address="192.168.1.100" accept' --permanent

# Block traffic from a specific IP
firewall-cmd --add-rich-rule='rule family="ipv4" source address="10.0.0.5" drop' --permanent

# Allow a port only from a specific subnet
firewall-cmd --add-rich-rule='rule family="ipv4" source address="192.168.1.0/24" port port="3306" protocol="tcp" accept' --permanent

# List rich rules
firewall-cmd --list-rich-rules
```

## Port Forwarding

```bash
# Forward port 80 to port 8080 on the same machine
firewall-cmd --add-forward-port=port=80:proto=tcp:toport=8080 --permanent

# Forward port 80 to another machine
firewall-cmd --add-forward-port=port=80:proto=tcp:toport=80:toaddr=192.168.1.50 --permanent

# Enable masquerading (required for forwarding to another machine)
firewall-cmd --add-masquerade --permanent

firewall-cmd --reload
```

## Troubleshooting

### Check current rules

```bash
# Full dump of current configuration
firewall-cmd --list-all

# Check a specific zone
firewall-cmd --zone=public --list-all
```

### Firewalld won't start

```bash
systemctl status firewalld
journalctl -u firewalld -e
```

### Changes not taking effect

Always run `firewall-cmd --reload` after making `--permanent` changes. Runtime changes are immediate but temporary.
