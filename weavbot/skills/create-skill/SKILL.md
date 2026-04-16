---
name: create-skill
description: Create a new skill to teach the agent a specific capability.
---

# Create Skill

Create a new skill so the agent can learn and use a specific capability.

## File Structure

Every skill lives under `skills/<name>/` and must contain a `SKILL.md`:

```text
skills/<name>/
  SKILL.md          # Required — skill definition
  <other files>     # Optional — templates, scripts, examples
```

## SKILL.md Format

The file MUST have a YAML frontmatter block followed by Markdown content:

```markdown
---
name: <skill-name>
description: <one-line description of what the skill does>
---

# Skill Title

Instructions for the agent. Write clearly and concisely.

## When to Use

Describe the scenarios that trigger this skill.

## Instructions

Step-by-step guide for the agent to follow.

## Examples

Concrete examples showing tool calls or expected behavior.
```

## Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Skill name, must match the directory name (`skills/<name>/`) |
| `description` | Yes | One-line summary shown in the skills directory |
| `always` | No | Set to `true` to always load this skill into context (use sparingly) |

## Path Convention

Use **relative paths** when writing files. The `skills/<name>/` directory is relative to workspace — write it as `skills/<name>/SKILL.md` and the system resolves it against workspace automatically. No need to construct or guess absolute paths.

The system scans `skills/` under workspace on startup. Any directory containing a `SKILL.md` is automatically discovered and listed in the skills directory. No manual registration needed.

## Creation Steps

1. **Pick a name** — short, lowercase, hyphenated (e.g. `git-workflow`, `code-review`). Confirm with the user if unclear.
2. **Create directory and write SKILL.md** — write to `skills/<name>/SKILL.md` (relative path). Include frontmatter with `name` and `description`, then write the body with clear instructions, examples, and any constraints.
3. **Add auxiliary files** — if the skill needs templates, scripts, or reference files, place them alongside `SKILL.md` in the same `skills/<name>/` directory. Reference them by relative path in the skill body (e.g. `skills/<name>/template.txt`).
4. **Verify** — re-read the file to confirm correctness. The new skill will appear in the skills directory on the next conversation turn.

## Guidelines

- Write instructions for an LLM, not a human. Be explicit about tool names and parameter formats.
- Include concrete examples using tool call syntax (e.g. `read_file(path="...")`, `shell(command="...")`).
- Keep the skill focused on one capability. Split into separate skills if it covers multiple.
- Do NOT duplicate information already in other skills — reference them by name instead.
- Auxiliary files should be small and self-contained. Large binary files should not be stored in skills.
