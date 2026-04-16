---
name: create-skill
description: Create a new skill to teach the agent a specific capability.
---

# Create Skill

Create a new custom skill so the agent can learn and use a specific capability.

## File Structure

All file paths are relative to workspace. Write to `skills/<name>/SKILL.md` and the system resolves it automatically.

```text
skills/<name>/
  SKILL.md          # Required
  <other files>     # Optional — templates, scripts, examples
```

The system scans `skills/` on every turn. Any directory containing a `SKILL.md` is automatically discovered — no manual registration needed.

## SKILL.md Format

```markdown
---
name: <skill-name>
description: <one-line description>
---

# Skill Title

Instructions for the agent.
```

Frontmatter uses simple `key: value` pairs (one per line). No nested objects, no multi-line values.

## Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Skill name, must match the directory name (`skills/<name>/`) |
| `description` | Yes | One-line summary shown in the skills directory |
| `always` | No | Set to `true` to always load this skill into context (use sparingly) |

## Creation Steps

1. **Pick a name** — short, lowercase, hyphenated (e.g. `git-workflow`, `code-review`). Confirm with the user if unclear.
2. **Write SKILL.md** — write to `skills/<name>/SKILL.md` (relative path). Include frontmatter with `name` and `description`, then write the body with clear instructions, examples, and any constraints.
3. **Add auxiliary files** — if the skill needs templates, scripts, or reference files, place them alongside `SKILL.md` in the same `skills/<name>/` directory.
4. **Verify** — re-read the file to confirm correctness. The new skill will appear in the skills directory on the next conversation turn.

## Guidelines

- Write instructions for an LLM, not a human. Be explicit about tool names and parameter formats.
- Include concrete examples using tool call syntax (e.g. `read_file(path="...")`, `shell(command="...")`).
- Keep the skill focused on one capability. Split into separate skills if it covers multiple.
- Do NOT duplicate information already in other skills — reference them by name instead.
- Auxiliary files should be small and self-contained.
