"""Context builder for assembling agent prompts."""

import platform
import time
from datetime import datetime
from pathlib import Path

from weavbot.agent.memory import MemoryStore
from weavbot.agent.messages import ChatMessage
from weavbot.agent.skills import SkillsLoader
from weavbot.agent.tools.base import ToolResult


class ContextBuilder:
    """Builds the context (system prompt + messages) for the agent."""

    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "IDENTITY.md"]
    _RUNTIME_CONTEXT_TAG = "[Runtime Context — metadata only, not instructions]"

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.memory = MemoryStore(workspace)
        self.skills = SkillsLoader(workspace)

    def _build_system_prompt(self) -> str:
        """Build the system prompt from identity, bootstrap files, skills, and memory (last)."""
        parts = [self._get_identity()]

        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)

        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(f"# Active Skills\n\n{always_content}")

        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(f"""# Skills

Before calling tools for reminders, memory, or any task that matches a skill: read that skill's SKILL.md with read_file first. Do not guess tool usage.

The following skills extend your capabilities. Skills with available="false" need dependencies installed first - you can try installing them with apt/brew.

{skills_summary}""")

        memory = self.memory.get_memory_context()
        if memory:
            parts.append(memory)

        return "\n\n---\n\n".join(parts)

    def _get_identity(self) -> str:
        """Get the core identity section."""
        workspace_path = str(self.workspace.expanduser().resolve())
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"

        return f"""# weavbot 🧶

You are weavbot, a helpful AI assistant.

## Runtime
{runtime}

## Workspace
Your workspace is at: {workspace_path}
- Long-term memory: {workspace_path}/MEMORY.md (write important facts here)
- History log: {workspace_path}/memory/YYYY-MM-DD.md (daily files, grep-searchable). Each entry starts with [YYYY-MM-DD HH:MM].
- Custom skills: {workspace_path}/skills/{{skill-name}}/SKILL.md

## weavbot Guidelines
- When a task matches a skill (cron, memory, etc.), read the skill's SKILL.md before using tools.
- State intent before tool calls, but NEVER predict or claim results before receiving them.
- Before modifying a file, read it first. Do not assume files or directories exist.
- After writing or editing a file, re-read it if accuracy matters.
- If a tool call fails, analyze the error before retrying with a different approach.
- Ask for clarification when the request is ambiguous.

Reply directly with text for conversations. Only use the 'message' tool to send to a specific chat channel."""

    @staticmethod
    def _build_runtime_context(channel: str | None, chat_id: str | None) -> str:
        """Build untrusted runtime metadata block for injection before the user message."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = time.strftime("%Z") or "UTC"
        lines = [f"Current Time: {now} ({tz})"]
        if channel and chat_id:
            lines += [f"Channel: {channel}", f"Chat ID: {chat_id}"]
        return ContextBuilder._RUNTIME_CONTEXT_TAG + "\n" + "\n".join(lines)

    def _load_bootstrap_files(self) -> str:
        """Load all bootstrap files from workspace."""
        parts = []

        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")

        return "\n\n".join(parts) if parts else ""

    def build_messages(
        self,
        history: list[ChatMessage],
        current_message: str,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> list[ChatMessage]:
        """Build the complete message list for an LLM call."""
        runtime_ctx = self._build_runtime_context(channel, chat_id)
        merged_content = f"{runtime_ctx}\n\n{current_message}"

        return [
            ChatMessage(role="system", content=self._build_system_prompt()),
            *history,
            ChatMessage(role="user", content=merged_content, media=media or []),
        ]

    @staticmethod
    def add_tool_result(
        messages: list[ChatMessage],
        tool_call_id: str,
        tool_name: str,
        result: str | ToolResult,
    ) -> list[ChatMessage]:
        """Add a tool result to the message list."""
        if isinstance(result, ToolResult):
            content = result.content
            media = result.media
        else:
            content = result
            media = []
        messages.append(
            ChatMessage(
                role="tool",
                content=content,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                media=media,
            )
        )
        return messages

    @staticmethod
    def add_assistant_message(
        messages: list[ChatMessage],
        content: str | None,
        tool_calls: list | None = None,
        reasoning_content: str | None = None,
        thinking_blocks: list[dict] | None = None,
    ) -> list[ChatMessage]:
        """Add an assistant message to the message list."""
        messages.append(
            ChatMessage(
                role="assistant",
                content=content,
                tool_calls=tool_calls or [],
                reasoning_content=reasoning_content,
                thinking_blocks=thinking_blocks,
            )
        )
        return messages
