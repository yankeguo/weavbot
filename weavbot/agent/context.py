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

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.memory = MemoryStore(workspace)
        self.skills = SkillsLoader(workspace)

    def _build_system_prompt(self) -> str:
        """Build the system prompt from identity, bootstrap files, skills, and memory."""
        sections = [
            self._build_identity_section(),
            self._load_bootstrap_files(),
            self._build_active_skills_section(),
            self._build_skills_directory_section(),
            self.memory.get_memory_context(),
        ]
        return "\n\n---\n\n".join(s for s in sections if s)

    def _build_active_skills_section(self) -> str:
        """Build the active (always-on) skills section."""
        names = self.skills.get_always_skills()
        if not names:
            return ""
        content = self.skills.load_skills_for_context(names)
        return f"# Active Skills\n\n{content}" if content else ""

    def _build_skills_directory_section(self) -> str:
        """Build the available-skills directory section."""
        summary = self.skills.build_skills_summary()
        if not summary:
            return ""
        return (
            "# Available Skills\n\n"
            "Before calling tools for reminders, memory, or any task that matches a skill: "
            "read that skill's SKILL.md with read_file first. Do not guess tool usage.\n\n"
            'Skills with available="false" need dependencies installed first '
            "- you can try installing them with apt/brew.\n\n"
            f"{summary}"
        )

    def _build_identity_section(self) -> str:
        """Build the core identity section."""
        workspace_path = str(self.workspace.expanduser().resolve())
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"

        return f"""You are weavbot, icon is 🧶, a helpful AI assistant.

## Runtime
{runtime}

## Workspace
Your workspace is at: {workspace_path}
- Long-term memory: {workspace_path}/MEMORY.md (write important facts here)
- History log: {workspace_path}/memory/YYYY-MM-DD.md (daily files, grep-searchable). Each entry starts with [YYYY-MM-DD HH:MM].
- Custom skills: {workspace_path}/skills/{{skill-name}}/SKILL.md

## Guidelines
- When a task matches a skill (cron, memory, etc.), read the skill's SKILL.md before using tools.
- State intent before tool calls, but NEVER predict or claim results before receiving them.
- Before modifying a file, read it first. Do not assume files or directories exist.
- After writing or editing a file, re-read it if accuracy matters.
- If a tool call fails, analyze the error before retrying with a different approach.
- Ask for clarification when the request is ambiguous.

Reply directly with text for conversations. Only use the 'message' tool to send to a specific chat channel."""

    @staticmethod
    def _build_runtime_context(channel: str | None, chat_id: str | None) -> str:
        """Build runtime metadata block wrapped in XML for injection before the user message."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = time.strftime("%Z") or "UTC"
        lines = [f"Current Time: {now} ({tz})"]
        if channel and chat_id:
            lines += [f"Channel: {channel}", f"Chat ID: {chat_id}"]
        body = "\n".join(lines)
        return f'<context role="metadata">\n{body}\n</context>'

    def _load_bootstrap_files(self) -> str:
        """Load all bootstrap files from workspace."""
        parts = []

        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f'<file source="{filename}">\n{content}\n</file>')

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
        merged_content = f"{runtime_ctx}\n{current_message}"

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
