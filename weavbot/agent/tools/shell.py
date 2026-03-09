"""Shell execution tool."""

import asyncio
import os
import shlex
import sys
from pathlib import Path
from typing import Any

from weavbot.agent.tools.base import Tool

_MAX_OUTPUT_LEN = 30_000

_IS_WINDOWS = sys.platform == "win32"

_DEFAULT_ENTRYPOINT = (
    "powershell.exe -NoProfile -NonInteractive -Command" if _IS_WINDOWS else "/bin/bash -c"
)

if _IS_WINDOWS:
    _DESCRIPTION = """Execute shell commands for terminal operations (git, npm, docker, etc.).
DO NOT use for file ops—prefer dedicated tools: glob_file (find files), grep_file (search content),
read_file (read), edit_file/write_file (edit/write).

Use workdir instead of cd. Quote paths with spaces (e.g. rm "path with spaces/file.txt").
Optional: timeout (seconds), workdir, entrypoint (command prefix, default 'powershell.exe -NoProfile -NonInteractive -Command', e.g. 'cmd.exe /c', 'pwsh.exe -NoProfile -Command')."""

    _ENTRYPOINT_PARAM_DESC = (
        "Entrypoint command prefix, e.g. 'powershell.exe -NoProfile -NonInteractive -Command', "
        "'cmd.exe /c'. Default: 'powershell.exe -NoProfile -NonInteractive -Command'."
    )
else:
    _DESCRIPTION = """Execute shell commands for terminal operations (git, npm, docker, etc.).
DO NOT use for file ops—prefer dedicated tools: glob_file (find files), grep_file (search content),
read_file (read), edit_file/write_file (edit/write).

Use workdir instead of cd. Quote paths with spaces (e.g. rm "path with spaces/file.txt").
Optional: timeout (seconds), workdir, entrypoint (command prefix, default '/bin/bash -c', e.g. '/bin/sh -c', '/bin/zsh -c')."""

    _ENTRYPOINT_PARAM_DESC = (
        "Entrypoint command prefix, e.g. '/bin/bash -c', '/bin/sh -c', '/bin/zsh -c'. "
        "Default: '/bin/bash -c'."
    )


class ShellTool(Tool):
    """Tool to execute shell commands."""

    def __init__(
        self,
        workspace: Path,
        timeout: int = 60,
        deny_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        restrict_to_workspace: bool = False,
        path_append: str = "",
    ):
        self.workspace = workspace
        self.timeout = timeout
        self.deny_patterns = deny_patterns or []
        self.allow_patterns = allow_patterns or []
        self.restrict_to_workspace = restrict_to_workspace
        self.path_append = path_append

    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return _DESCRIPTION

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "workdir": {
                    "type": "string",
                    "description": "Working directory for the command. Use this instead of cd.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (overrides default)",
                },
                "entrypoint": {
                    "type": "string",
                    "description": _ENTRYPOINT_PARAM_DESC,
                },
            },
            "required": ["command"],
        }

    async def execute(
        self,
        command: str,
        workdir: str | None = None,
        timeout: int | None = None,
        entrypoint: str | None = None,
        **kwargs: Any,
    ) -> str:
        if workdir:
            wd = Path(workdir).expanduser()
            if not wd.is_absolute():
                wd = self.workspace / wd
            cwd = str(wd.resolve())
        else:
            cwd = str(self.workspace)
        effective_timeout = timeout if timeout is not None and timeout > 0 else self.timeout
        guard_error = self._guard_command(command, cwd)
        if guard_error:
            return guard_error

        env = os.environ.copy()
        if self.path_append:
            env["PATH"] = env.get("PATH", "") + os.pathsep + self.path_append

        effective_entrypoint = entrypoint or _DEFAULT_ENTRYPOINT
        entrypoint_args = shlex.split(effective_entrypoint, posix=not _IS_WINDOWS) + [command]

        try:
            process = await asyncio.create_subprocess_exec(
                *entrypoint_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=effective_timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                # Wait for the process to fully terminate so pipes are
                # drained and file descriptors are released.
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                return f"Error: Command timed out after {effective_timeout} seconds"

            output_parts = []

            if stdout:
                output_parts.append(stdout.decode("utf-8", errors="replace"))

            if stderr:
                stderr_text = stderr.decode("utf-8", errors="replace")
                if stderr_text.strip():
                    output_parts.append(f"STDERR:\n{stderr_text}")

            if process.returncode != 0:
                output_parts.append(f"\nExit code: {process.returncode}")

            result = "\n".join(output_parts) if output_parts else "(no output)"

            # Truncate very long output
            if len(result) > _MAX_OUTPUT_LEN:
                result = (
                    result[:_MAX_OUTPUT_LEN]
                    + f"\n... (truncated, {len(result) - _MAX_OUTPUT_LEN} more chars)"
                )

            return result

        except Exception as e:
            return f"Error executing command: {str(e)}"

    def _guard_command(self, command: str, cwd: str) -> str | None:
        """Safety guard stub. deny_patterns, allow_patterns, restrict_to_workspace are accepted but not enforced."""
        return None
