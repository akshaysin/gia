# journalctl — Systemd Journal Query

## Overview

`journalctl` is the tool for querying the systemd journal, which collects logs from all systemd services, the kernel, and other sources.

## Basic Usage

```bash
# Show all journal entries
journalctl

# Show entries from the current boot
journalctl -b

# Show entries from the previous boot
journalctl -b -1

# Follow new entries in real-time (like tail -f)
journalctl -f
```

## Filtering by Service

```bash
# Show logs for a specific unit/service
journalctl -u nginx

# Show logs for multiple services
journalctl -u nginx -u php-fpm

# Combine with follow
journalctl -u nginx -f
```

## Time-based Filtering

```bash
# Since a specific time
journalctl --since "2024-01-15 10:00:00"

# Since a relative time
journalctl --since "1 hour ago"
journalctl --since "30 minutes ago"

# Time range
journalctl --since "2024-01-15" --until "2024-01-16"

# Today's logs only
journalctl --since today
```

## Priority Filtering

Priorities: emerg (0), alert (1), crit (2), err (3), warning (4), notice (5), info (6), debug (7)

```bash
# Show only errors and above
journalctl -p err

# Show warnings and above
journalctl -p warning

# Show a range of priorities
journalctl -p warning..err
```

## Output Formatting

```bash
# Short format (default)
journalctl -o short

# JSON output
journalctl -o json

# JSON, one entry per line (useful for piping)
journalctl -o json-pretty

# Verbose — show all fields
journalctl -o verbose

# Show only the message text
journalctl -o cat
```

## Kernel Messages

```bash
# Show kernel messages (like dmesg)
journalctl -k

# Kernel messages from current boot
journalctl -k -b
```

## Disk Usage

```bash
# Show journal disk usage
journalctl --disk-usage

# Limit journal size
journalctl --vacuum-size=500M

# Remove entries older than 2 weeks
journalctl --vacuum-time=2weeks
```

## Troubleshooting Tips

- If a service won't start, always check `journalctl -u <service> -e` first
- Use `-e` to jump to the end of the log
- Use `--no-pager` to avoid paging when piping to other commands
- Use `-n 50` to show only the last 50 entries
