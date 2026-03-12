"""Context compaction helpers for token-budget-aware history rebuilding."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from weavbot.providers.base import LLMProvider
    from weavbot.session.manager import Session


COMPACTION_SYSTEM_PROMPT = """You are a helpful AI assistant tasked with summarizing conversations.

When asked to summarize, provide a detailed but concise summary of the conversation.
Focus on information that would be helpful for continuing the conversation, including:
- What was done
- What is currently being worked on
- Which files are being modified
- What needs to be done next
- Key user requests, constraints, or preferences that should persist
- Important technical decisions and why they were made

Your summary should be comprehensive enough to provide context but concise enough to be quickly understood.

Do not respond to any questions in the conversation, only output the summary.
"""


@dataclass
class CompactResult:
    """Result of a successful context compaction."""

    summary: str
    seed_message: dict[str, Any]
    covered_messages: int
    estimated_before_tokens: int
    estimated_after_tokens: int


class ContextCompactor:
    """Compacts history when prompt budget cannot fit requested output tokens."""

    SEED_PREFIX = "[Context Compact Summary]"

    @staticmethod
    def estimate_tokens(messages: list[dict[str, Any]]) -> int:
        """Estimate tokens using a conservative char-based heuristic."""
        chars = 0
        for m in messages:
            chars += len(str(m.get("role", ""))) + 8
            chars += ContextCompactor._content_chars(m.get("content"))
            if (tool_calls := m.get("tool_calls")) is not None:
                chars += len(json.dumps(tool_calls, ensure_ascii=False))
            if (name := m.get("name")) is not None:
                chars += len(str(name))
            if (tool_call_id := m.get("tool_call_id")) is not None:
                chars += len(str(tool_call_id))
        # Roughly 4 chars/token, plus per-message framing overhead.
        return chars // 4 + max(1, len(messages)) * 8

    @staticmethod
    def can_fit(messages: list[dict[str, Any]], max_context: int, max_output_tokens: int) -> bool:
        """Check if prompt estimate + max output tokens stays within context window."""
        if max_context <= 0:
            return True
        return ContextCompactor.estimate_tokens(messages) + max(1, max_output_tokens) <= max_context

    @staticmethod
    def shrink_messages_for_runtime(
        messages: list[dict[str, Any]],
        max_context: int,
        max_output_tokens: int,
    ) -> list[dict[str, Any]]:
        """Best-effort runtime shrinking for tool-heavy loops without rewriting session."""
        if ContextCompactor.can_fit(messages, max_context, max_output_tokens):
            return messages
        if not messages:
            return messages

        system = messages[0] if messages[0].get("role") == "system" else None
        rest = messages[1:] if system else messages
        turns = ContextCompactor._split_turns(rest)
        if not turns:
            return messages

        # Keep newest turns first; gradually reduce old turns.
        for keep in range(len(turns), 0, -1):
            kept = [m for turn in turns[-keep:] for m in turn]
            candidate = ([system] if system else []) + kept
            if ContextCompactor.can_fit(candidate, max_context, max_output_tokens):
                dropped = len(rest) - len(kept)
                if dropped > 0:
                    logger.info(
                        "Runtime context shrink: dropped {} message(s) to fit budget", dropped
                    )
                return candidate

        # Last resort: keep system + latest user message only.
        latest_user = next((m for m in reversed(rest) if m.get("role") == "user"), None)
        fallback = ([system] if system else []) + ([latest_user] if latest_user else [])
        if fallback:
            if ContextCompactor.can_fit(fallback, max_context, max_output_tokens):
                logger.warning("Runtime context shrink fell back to latest user message only")
                return fallback

            # If still too large, aggressively truncate text content to avoid guaranteed context errors.
            budget = max(128, (max_context - max(1, max_output_tokens)) * 4)
            truncated = []
            for msg in fallback:
                item = dict(msg)
                content = item.get("content")
                if isinstance(content, str) and len(content) > budget // 2:
                    item["content"] = content[: budget // 2] + "\n...[truncated for context budget]"
                truncated.append(item)
            logger.warning("Runtime context shrink applied aggressive truncation")
            return truncated
        return messages

    async def compact_session_to_new_start(
        self,
        session: Session,
        history: list[dict[str, Any]],
        provider: LLMProvider,
        model: str,
        *,
        estimated_before_tokens: int,
        max_summary_tokens: int = 1200,
    ) -> CompactResult | None:
        """Summarize current history and return a seed message for a logical new session."""
        logger.debug("Compacting history for session: {session}", session=session)
        if not history:
            return None

        transcript = self._render_transcript(history)
        if not transcript.strip():
            return None

        user_prompt = (
            "Summarize the following conversation for context compaction.\n\n"
            "Output requirements:\n"
            "- Keep it concise but detailed enough to continue work immediately.\n"
            "- Preserve ongoing tasks, pending items, modified files, constraints/preferences, and key decisions.\n"
            "- Output only the summary text.\n\n"
            "Conversation transcript:\n"
            f"{transcript}"
        )

        try:
            response = await provider.chat(
                messages=[
                    {"role": "system", "content": COMPACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                model=model,
                max_tokens=max(256, max_summary_tokens),
            )
        except Exception:
            logger.exception("Context compaction call failed")
            return None

        summary = (response.content or "").strip()
        if not summary or response.finish_reason == "error":
            logger.warning("Context compaction returned empty/error response, skipping")
            return None

        seed_message = {
            "role": "user",
            "content": f"{self.SEED_PREFIX}\n\n{summary}",
            "timestamp": datetime.now().isoformat(),
        }
        estimated_after = self.estimate_tokens([seed_message])

        return CompactResult(
            summary=summary,
            seed_message=seed_message,
            covered_messages=len(history),
            estimated_before_tokens=estimated_before_tokens,
            estimated_after_tokens=estimated_after,
        )

    @staticmethod
    def _split_turns(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        turns: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        for m in messages:
            if m.get("role") == "user" and current:
                turns.append(current)
                current = [m]
            else:
                current.append(m)
        if current:
            turns.append(current)
        return turns

    @staticmethod
    def _content_chars(content: Any) -> int:
        if content is None:
            return 0
        if isinstance(content, str):
            return len(content)
        if isinstance(content, list):
            total = 0
            for item in content:
                if isinstance(item, dict):
                    typ = item.get("type")
                    if typ in ("text", "input_text", "output_text"):
                        total += len(str(item.get("text", "")))
                    elif typ == "image_url":
                        total += 16
                    else:
                        total += len(json.dumps(item, ensure_ascii=False))
                else:
                    total += len(str(item))
            return total
        if isinstance(content, dict):
            return len(json.dumps(content, ensure_ascii=False))
        return len(str(content))

    def _render_transcript(self, history: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for idx, msg in enumerate(history, start=1):
            role = str(msg.get("role", "unknown")).upper()
            content = self._content_to_text(msg.get("content"))
            if tool_calls := msg.get("tool_calls"):
                content += f"\n[tool_calls] {json.dumps(tool_calls, ensure_ascii=False)}"
            lines.append(f"{idx}. {role}: {content}")
        return "\n\n".join(lines)

    @staticmethod
    def _content_to_text(content: Any) -> str:
        if content is None:
            return "(empty)"
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    typ = item.get("type")
                    if typ in ("text", "input_text", "output_text"):
                        chunks.append(str(item.get("text", "")))
                    elif typ == "image_url":
                        chunks.append("[image]")
                    else:
                        chunks.append(json.dumps(item, ensure_ascii=False))
                else:
                    chunks.append(str(item))
            return "\n".join(c for c in chunks if c) or "(empty)"
        if isinstance(content, dict):
            return json.dumps(content, ensure_ascii=False)
        return str(content)
