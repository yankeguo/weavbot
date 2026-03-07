"""Shell execution tool."""

import asyncio
import os
from typing import Any

from weavbot.agent.tools.base import Tool

_MAX_OUTPUT_LEN = 30_000

_DESCRIPTION = """Execute shell commands for terminal operations (git, npm, docker, etc.).
DO NOT use for file ops—prefer dedicated tools: glob_file (find files), grep_file (search content),
read_file (read), edit_file/write_file (edit/write).

Use workdir instead of cd. Quote paths with spaces (e.g. rm "path with spaces/file.txt").
Optional: timeout (seconds), workdir."""


class ShellTool(Tool):
    """Tool to execute shell commands."""

    def __init__(
        self,
        timeout: int = 60,
        working_dir: str | None = None,
        deny_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        restrict_to_workspace: bool = False,
        path_append: str = "",
    ):
        self.timeout = timeout
        self.working_dir = working_dir
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
                    "description": "The shell command to execute",
                },
                "workdir": {
                    "type": "string",
                    "description": "Working directory for the command. Use this instead of cd.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds. Overrides default if set.",
                },
            },
            "required": ["command"],
        }

    async def execute(
        self,
        command: str,
        workdir: str | None = None,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> str:
        cwd = workdir or self.working_dir or os.getcwd()
        effective_timeout = timeout if timeout is not None and timeout > 0 else self.timeout
        guard_error = self._guard_command(command, cwd)
        if guard_error:
            return guard_error
        
        env = os.environ.copy()
        if self.path_append:
            env["PATH"] = env.get("PATH", "") + os.pathsep + self.path_append

        try:
            process = await asyncio.create_subprocess_shell(
                command,
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
                result = result[:_MAX_OUTPUT_LEN] + f"\n... (truncated, {len(result) - _MAX_OUTPUT_LEN} more chars)"
            
            return result
            
        except Exception as e:
            return f"Error executing command: {str(e)}"

    def _guard_command(self, command: str, cwd: str) -> str | None:
        """Safety guard stub. deny_patterns, allow_patterns, restrict_to_workspace are accepted but not enforced."""
        return None
