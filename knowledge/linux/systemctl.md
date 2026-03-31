# systemctl — System and Service Manager

## Overview

`systemctl` is the primary command for managing systemd services, targets, and units on Linux systems.

## Common Commands

### Service Management

- `systemctl start <service>` — Start a service immediately
- `systemctl stop <service>` — Stop a running service
- `systemctl restart <service>` — Stop and restart a service
- `systemctl reload <service>` — Reload a service's configuration without restarting
- `systemctl enable <service>` — Enable a service to start at boot
- `systemctl disable <service>` — Prevent a service from starting at boot
- `systemctl status <service>` — Show the current status of a service

### Checking Status

```bash
# Show detailed status including recent log entries
systemctl status nginx

# Check if a service is active (running)
systemctl is-active nginx

# Check if a service is enabled (starts at boot)
systemctl is-enabled nginx

# Check if a service has failed
systemctl is-failed nginx
```

### Listing Services

```bash
# List all loaded units
systemctl list-units

# List only services
systemctl list-units --type=service

# List all installed unit files
systemctl list-unit-files

# List failed services
systemctl --failed
```

### System State

```bash
# Reboot the system
systemctl reboot

# Power off
systemctl poweroff

# Suspend
systemctl suspend

# Show default target (runlevel)
systemctl get-default

# Set default target
systemctl set-default multi-user.target
```

## Unit File Locations

- `/etc/systemd/system/` — Local configuration and custom units (highest priority)
- `/run/systemd/system/` — Runtime units
- `/usr/lib/systemd/system/` — Units installed by packages

## Creating a Custom Service

Create a file at `/etc/systemd/system/myapp.service`:

```ini
[Unit]
Description=My Application
After=network.target

[Service]
Type=simple
User=myapp
ExecStart=/usr/bin/myapp --config /etc/myapp/config.yaml
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then enable and start:

```bash
systemctl daemon-reload
systemctl enable --now myapp.service
```

## Troubleshooting

### Service won't start

1. Check status: `systemctl status myapp`
2. Check full logs: `journalctl -u myapp -e`
3. Verify unit file syntax: `systemd-analyze verify /etc/systemd/system/myapp.service`
4. Check dependencies: `systemctl list-dependencies myapp`

### Service keeps restarting

Check `Restart=` and `RestartSec=` in the unit file. Use `journalctl -u myapp --since "5 minutes ago"` to see crash logs.
