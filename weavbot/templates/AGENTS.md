# Agent Instructions

## Scheduled Reminders

Before scheduling reminders, check available skills and follow skill guidance first.
Use the built-in `cron` tool to create/list/remove jobs (do not call `weavbot cron` via `shell`).
Get USER_ID and CHANNEL from the current session (e.g., `8281248569` and `telegram` from `telegram:8281248569`).

**Do NOT just write reminders to MEMORY.md** — that won't trigger actual notifications.

## Heartbeat Tasks

`HEARTBEAT.md` is checked on the configured heartbeat interval. Use file tools to manage periodic tasks:

- **Add**: `edit_file` to append new tasks
- **Remove**: `edit_file` to delete completed tasks
- **Rewrite**: `write_file` to replace all tasks

When the user asks for a recurring/periodic task, update `HEARTBEAT.md` instead of creating a one-time cron reminder.

## Tool Usage Notes

- Use `grep_file` for text search — do not use `grep` via `shell`.
- Use `glob_file` to find files by name pattern — do not use `find` via `shell`.
- Prefer `edit_file` over `write_file` for partial modifications.

## Temporary Files

- **Location:** All temporary files must be placed under the `temp/YYYY/MM/DD/` subdirectory.
- **Prohibited:** Do not create temporary files directly in the workspace root.
- **Reason:** Date-based hierarchy enables automated cleanup and management in the future.
- **Examples:**
  - ✅ `temp/2026/03/03/screenshot.png`
  - ❌ `temp/screenshot.png` (placed directly under temp)
  - ❌ `screenshot.png` (placed directly in the workspace root)
