---
name: memory
description: Two-layer memory system with grep-based recall.
always: true
---

# Memory

## Structure

- `MEMORY.md` — Long-term facts (preferences, project context, relationships). Always loaded into your context.
- `memory/YYYY-MM-DD.md` — Daily history logs. NOT loaded into context. Search with `grep_file`. Each entry starts with [YYYY-MM-DD HH:MM].

## Search Past Events

```
grep_file(pattern="keyword", path="memory")
```

Use the `grep_file` tool (regex-based). Combine patterns with regex: `grep_file(pattern="meeting|deadline", path="memory")`

## When to Update MEMORY.md

Keep entries concise. Do not copy or paraphrase SKILL content—store only factual information.

Write important facts immediately using `edit_file` or `write_file`:

- User preferences ("I prefer dark mode")
- Project context ("The API uses OAuth2")
- Relationships ("Alice is the project lead")

## Auto-consolidation

Old conversations are automatically summarized and appended to today's `memory/YYYY-MM-DD.md` when the session grows large. Long-term facts are extracted to `MEMORY.md`. You don't need to manage this.

For other tasks (reminders, cron, etc.), read the corresponding skill's SKILL.md first.
