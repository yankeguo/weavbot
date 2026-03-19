"""Context compaction helpers for token-budget-aware history rebuilding."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

from weavbot.agent.messages import ChatMessage

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
- Do NOT copy or summarize SKILL.md contents into the compact summary.
- If a future turn needs a skill, re-read the relevant SKILL.md on demand instead of relying on this summary.

Your summary should be comprehensive enough to provide context but concise enough to be quickly understood.

Do not respond to any questions in the conversation, only output the summary.
"""


@dataclass
class CompactResult:
    """Result of a successful context compaction."""

    summary: str
    seed_message: ChatMessage
    covered_messages: int
    estimated_before_tokens: int
    estimated_after_tokens: int


class ContextCompactor:
    """Compacts history when prompt budget cannot fit requested output tokens."""

    SEED_PREFIX = "[Context Compact Summary]"
    _BASE_MESSAGE_OVERHEAD_TOKENS = 24

    @staticmethod
    def estimate_tokens(
        messages: list[ChatMessage],
        *,
        estimate_multiplier: float = 1.0,
    ) -> int:
        """Estimate tokens conservatively across multilingual/tool-heavy payloads."""
        tokens = 0.0
        for m in messages:
            tokens += ContextCompactor._BASE_MESSAGE_OVERHEAD_TOKENS
            tokens += ContextCompactor._text_tokens(m.role)
            tokens += ContextCompactor._text_tokens(m.content or "")
            if m.media:
                tokens += 24 * len(m.media)
            if m.tool_calls:
                tc_data = [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in m.tool_calls
                ]
                tokens += ContextCompactor._json_tokens(tc_data) * 1.15
            if m.tool_name:
                tokens += ContextCompactor._text_tokens(m.tool_name)
            if m.tool_call_id:
                tokens += ContextCompactor._text_tokens(m.tool_call_id)
            if m.reasoning_content:
                tokens += ContextCompactor._text_tokens(m.reasoning_content)
            if m.thinking_blocks:
                tokens += ContextCompactor._json_tokens(m.thinking_blocks)
        multiplier = max(1.0, float(estimate_multiplier or 1.0))
        return max(max(1, len(messages)) * 12, int(tokens * multiplier))

    @staticmethod
    def can_fit(
        messages: list[ChatMessage],
        max_context: int,
        max_output_tokens: int,
        *,
        estimate_multiplier: float = 1.0,
        safety_tokens: int = 0,
        safety_ratio: float = 0.0,
    ) -> bool:
        """Check if prompt estimate + max output tokens stays within context window."""
        if max_context <= 0:
            return True
        reserve = max(0, int(safety_tokens)) + max(0, int(max_context * max(0.0, safety_ratio)))
        return (
            ContextCompactor.estimate_tokens(messages, estimate_multiplier=estimate_multiplier)
            + max(1, max_output_tokens)
            + reserve
            <= max_context
        )

    @staticmethod
    def shrink_messages_for_runtime(
        messages: list[ChatMessage],
        max_context: int,
        max_output_tokens: int,
        *,
        estimate_multiplier: float = 1.0,
        safety_tokens: int = 0,
        safety_ratio: float = 0.0,
    ) -> list[ChatMessage]:
        """Best-effort runtime shrinking for tool-heavy loops without rewriting session."""
        fit_kw = dict(
            estimate_multiplier=estimate_multiplier,
            safety_tokens=safety_tokens,
            safety_ratio=safety_ratio,
        )
        if ContextCompactor.can_fit(messages, max_context, max_output_tokens, **fit_kw):
            return messages
        if not messages:
            return messages

        system = messages[0] if messages[0].role == "system" else None
        rest = messages[1:] if system else messages
        turns = ContextCompactor._split_turns(rest)
        if not turns:
            return messages

        for keep in range(len(turns), 0, -1):
            kept = [m for turn in turns[-keep:] for m in turn]
            candidate = ([system] if system else []) + kept
            if ContextCompactor.can_fit(candidate, max_context, max_output_tokens, **fit_kw):
                dropped = len(rest) - len(kept)
                if dropped > 0:
                    logger.info(
                        "Runtime context shrink: dropped {} message(s) to fit budget", dropped
                    )
                return candidate

        latest_user = next((m for m in reversed(rest) if m.role == "user"), None)
        fallback = ([system] if system else []) + ([latest_user] if latest_user else [])
        if fallback:
            if ContextCompactor.can_fit(fallback, max_context, max_output_tokens, **fit_kw):
                logger.warning("Runtime context shrink fell back to latest user message only")
                return fallback

            base_budget = max(
                96,
                max_context
                - max(1, max_output_tokens)
                - max(0, int(safety_tokens))
                - max(0, int(max_context * max(0.0, safety_ratio))),
            )
            per_msg_chars = max(256, (base_budget * 2) // max(1, len(fallback)))
            for ratio in (1.0, 0.5, 0.25, 0.1):
                truncated = [
                    ContextCompactor._minimize_message_for_budget(
                        msg, max_chars=max(64, int(per_msg_chars * ratio))
                    )
                    for msg in fallback
                ]
                if ContextCompactor.can_fit(truncated, max_context, max_output_tokens, **fit_kw):
                    logger.warning("Runtime context shrink applied aggressive truncation")
                    return truncated
            logger.warning("Runtime context shrink exhausted aggressive truncation")
            return [
                ChatMessage(role="system", content="[System prompt truncated for context budget]")
                if i == 0 and msg.role == "system"
                else ChatMessage(role=msg.role, content="[truncated for context budget]")
                for i, msg in enumerate(fallback)
            ]
        return messages

    async def compact_session_to_new_start(
        self,
        session: Session,
        history: list[ChatMessage],
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
                    ChatMessage(role="system", content=COMPACTION_SYSTEM_PROMPT),
                    ChatMessage(role="user", content=user_prompt),
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

        seed_message = ChatMessage(
            role="user",
            content=f"{self.SEED_PREFIX}\n\n{summary}",
            is_compaction_seed=True,
            timestamp=datetime.now().isoformat(),
        )
        estimated_after = self.estimate_tokens([seed_message])

        return CompactResult(
            summary=summary,
            seed_message=seed_message,
            covered_messages=len(history),
            estimated_before_tokens=estimated_before_tokens,
            estimated_after_tokens=estimated_after,
        )

    @staticmethod
    def _split_turns(messages: list[ChatMessage]) -> list[list[ChatMessage]]:
        turns: list[list[ChatMessage]] = []
        current: list[ChatMessage] = []
        for m in messages:
            if m.role == "user" and current:
                turns.append(current)
                current = [m]
            else:
                current.append(m)
        if current:
            turns.append(current)
        return turns

    @staticmethod
    def _text_tokens(text: str) -> int:
        if not text:
            return 0
        ascii_chars = sum(1 for ch in text if ord(ch) < 128)
        non_ascii_chars = len(text) - ascii_chars
        return max(1, ascii_chars // 3 + non_ascii_chars)

    @staticmethod
    def _json_tokens(value: Any) -> int:
        try:
            payload = json.dumps(value, ensure_ascii=False)
        except Exception:
            payload = str(value)
        return ContextCompactor._text_tokens(payload) + max(1, len(payload) // 16)

    @staticmethod
    def _truncate_text(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        if max_chars <= 32:
            return text[: max(0, max_chars)]
        return text[: max_chars - 24] + "\n...[truncated]"

    @staticmethod
    def _minimize_message_for_budget(message: ChatMessage, max_chars: int) -> ChatMessage:
        msg = replace(message, reasoning_content=None, thinking_blocks=None)
        if msg.content:
            msg = replace(msg, content=ContextCompactor._truncate_text(msg.content, max_chars))
        if msg.tool_calls and len(msg.tool_calls) > 4:
            msg = replace(msg, tool_calls=msg.tool_calls[:4])
        return msg

    def _render_transcript(self, history: list[ChatMessage]) -> str:
        lines: list[str] = []
        for idx, msg in enumerate(history, start=1):
            role = msg.role.upper()
            content = msg.content or "(empty)"
            if msg.tool_calls:
                tc_data = [{"name": tc.name, "arguments": tc.arguments} for tc in msg.tool_calls]
                content += f"\n[tool_calls] {json.dumps(tc_data, ensure_ascii=False)}"
            lines.append(f"{idx}. {role}: {content}")
        return "\n\n".join(lines)
