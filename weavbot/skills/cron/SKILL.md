---
name: cron
description: Schedule reminders and recurring tasks.
---

# Cron

Use `add_cron`, `list_cron`, and `remove_cron` to schedule reminders and manage recurring tasks.

## Three Modes

1. **Reminder** - message is sent directly to user
2. **Task** - message is a task description, agent executes and sends result
3. **One-time** - runs once at a specific time, then auto-deletes

## Examples

Fixed reminder:

```text
add_cron(message="Time to take a break!", interval=1200)
```

Dynamic task (agent executes each time):

```text
add_cron(message="Check yankeguo/weavbot GitHub stars and report", interval=600)
```

One-time scheduled task (compute ISO datetime from current time):

```text
add_cron(message="Remind me about the meeting", at="<ISO datetime>")
```

Timezone-aware cron:

```text
add_cron(message="Morning standup", expr="0 9 * * 1-5", tz="America/Vancouver")
```

List/remove:

```text
list_cron()
remove_cron(job_id="abc123")
```

## Time Expressions

| User says | Parameters |
| --------- | ---------- |
| every 20 minutes | interval: 1200 |
| every hour | interval: 3600 |
| every day at 8am | expr: "0 8 ** *" |
| weekdays at 5pm | expr: "0 17 ** 1-5" |
| 9am Vancouver time daily | expr: "0 9 ** *", tz: "America/Vancouver" |
| at a specific time | at: ISO datetime string (compute from current time) |

## Timezone

Use `tz` with `expr` to schedule in a specific IANA timezone. Without `tz`, the server's local timezone is used.
