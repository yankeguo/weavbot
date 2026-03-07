"""Tool to search file contents using ripgrep (regex)."""

import asyncio
import re
from pathlib import Path
from typing import Any

from weavbot.agent.tools.base import Tool
from weavbot.agent.tools.filesystem import _resolve_path

_LIMIT = 100
_MAX_LINE_LENGTH = 2000

_DESCRIPTION = """Fast content search tool that works with any codebase size.
Searches file contents using regular expressions.
Supports full regex syntax (e.g. "log.*Error", "function\\s+\\w+", etc.).
Filter files by pattern with the include parameter (e.g. "*.js", "*.{ts,tsx}").
Returns file paths and line numbers with at least one match sorted by modification time.
Use this tool when you need to find files containing specific patterns.
If you need to identify/count the number of matches within files, use the exec tool with `rg` (ripgrep) directly. Do NOT use grep.
When you are doing an open-ended search that may require multiple rounds of globbing and grepping, use the spawn tool instead."""


class GrepFileTool(Tool):
    """Tool to search file contents using ripgrep."""

    def __init__(self, workspace: Path | None = None, allowed_dir: Path | None = None):
        self._workspace = workspace
        self._allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        return "grep_file"

    @property
    def description(self) -> str:
        return _DESCRIPTION

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The regex pattern to search for in file contents",
                },
                "path": {
                    "type": "string",
                    "description": "The directory to search in. Defaults to workspace.",
                },
                "include": {
                    "type": "string",
                    "description": "File pattern to include in the search (e.g. \"*.js\", \"*.{ts,tsx}\")",
                },
            },
            "required": ["pattern"],
        }

    async def execute(
        self,
        pattern: str,
        path: str | None = None,
        include: str | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            if not pattern:
                return "Error: pattern is required"

            search_path_str = path if path is not None else "."
            base = _resolve_path(search_path_str, self._workspace, self._allowed_dir)

            if not base.exists():
                return f"Error: Directory not found: {search_path_str}"
            if not base.is_dir():
                return f"Error: Not a directory: {search_path_str}"

            search_path = str(base.resolve())
            args = [
                "rg",
                "-nH",
                "--hidden",
                "--no-messages",
                "--field-match-separator=|",
                "--regexp",
                pattern,
            ]
            if include:
                args.extend(["--glob", include])
            args.append(search_path)

            try:
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=search_path,
                )
                stdout, stderr = await proc.communicate()
            except FileNotFoundError:
                return (
                    "Error: ripgrep (rg) is not installed. "
                    "Install it (e.g. brew install ripgrep) to use grep_file."
                )

            output = stdout.decode("utf-8", errors="replace")
            error_output = stderr.decode("utf-8", errors="replace")
            exit_code = proc.returncode

            # Exit codes: 0 = matches found, 1 = no matches, 2 = errors (may still have output)
            if exit_code == 1 or (exit_code == 2 and not output.strip()):
                return "No files found"

            if exit_code not in (0, 2):
                return f"Error: ripgrep failed: {error_output}"

            has_errors = exit_code == 2

            # Handle both Unix (\n) and Windows (\r\n) line endings
            lines = re.split(r"\r?\n", output.strip())

            matches: list[tuple[str, int, int, str]] = []  # path, mtime, lineNum, lineText
            for line in lines:
                if not line:
                    continue
                parts = line.split("|", 2)
                if len(parts) < 3:
                    continue
                file_path, line_num_str, line_text = parts
                try:
                    line_num = int(line_num_str, 10)
                except ValueError:
                    continue
                try:
                    stat = Path(file_path).stat()
                    mtime = int(stat.st_mtime)
                except OSError:
                    continue
                matches.append((file_path, mtime, line_num, line_text))

            matches.sort(key=lambda x: x[1], reverse=True)

            truncated = len(matches) > _LIMIT
            final_matches = matches[:_LIMIT]

            if not final_matches:
                return "No files found"

            total = len(matches)
            output_lines = [f"Found {total} matches" + (f" (showing first {_LIMIT})" if truncated else "")]

            current_file = ""
            for fp, _mtime, ln, text in final_matches:
                if text and len(text) > _MAX_LINE_LENGTH:
                    text = text[: _MAX_LINE_LENGTH] + "..."
                if current_file != fp:
                    if current_file:
                        output_lines.append("")
                    current_file = fp
                    output_lines.append(f"{fp}:")
                output_lines.append(f"  Line {ln}: {text}")

            if truncated:
                output_lines.append("")
                output_lines.append(
                    f"(Results truncated: showing {_LIMIT} of {total} matches ({total - _LIMIT} hidden). "
                    "Consider using a more specific path or pattern.)"
                )

            if has_errors:
                output_lines.append("")
                output_lines.append("(Some paths were inaccessible and skipped)")

            return "\n".join(output_lines)

        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error: {str(e)}"
