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
- Do NOT copy or summarize SKILL.md contents into the compact summary.
- If a future turn needs a skill, re-read the relevant SKILL.md on demand instead of relying on this summary.

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
    _BASE_MESSAGE_OVERHEAD_TOKENS = 24

    @staticmethod
    def estimate_tokens(
        messages: list[dict[str, Any]],
        *,
        estimate_multiplier: float = 1.0,
    ) -> int:
        """Estimate tokens conservatively across multilingual/tool-heavy payloads."""
        tokens = 0.0
        for m in messages:
            tokens += ContextCompactor._BASE_MESSAGE_OVERHEAD_TOKENS
            tokens += ContextCompactor._text_tokens(str(m.get("role", "")))
            tokens += ContextCompactor._content_tokens(m.get("content"))
            if (tool_calls := m.get("tool_calls")) is not None:
                # Tool payloads often include JSON strings and can spike quickly.
                tokens += ContextCompactor._json_tokens(tool_calls) * 1.15
            if (name := m.get("name")) is not None:
                tokens += ContextCompactor._text_tokens(str(name))
            if (tool_call_id := m.get("tool_call_id")) is not None:
                tokens += ContextCompactor._text_tokens(str(tool_call_id))
            if (reasoning_content := m.get("reasoning_content")) is not None:
                tokens += ContextCompactor._content_tokens(reasoning_content)
            if (thinking_blocks := m.get("thinking_blocks")) is not None:
                tokens += ContextCompactor._json_tokens(thinking_blocks)
        multiplier = max(1.0, float(estimate_multiplier or 1.0))
        return max(max(1, len(messages)) * 12, int(tokens * multiplier))

    @staticmethod
    def can_fit(
        messages: list[dict[str, Any]],
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
        messages: list[dict[str, Any]],
        max_context: int,
        max_output_tokens: int,
        *,
        estimate_multiplier: float = 1.0,
        safety_tokens: int = 0,
        safety_ratio: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Best-effort runtime shrinking for tool-heavy loops without rewriting session."""
        if ContextCompactor.can_fit(
            messages,
            max_context,
            max_output_tokens,
            estimate_multiplier=estimate_multiplier,
            safety_tokens=safety_tokens,
            safety_ratio=safety_ratio,
        ):
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
            if ContextCompactor.can_fit(
                candidate,
                max_context,
                max_output_tokens,
                estimate_multiplier=estimate_multiplier,
                safety_tokens=safety_tokens,
                safety_ratio=safety_ratio,
            ):
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
            if ContextCompactor.can_fit(
                fallback,
                max_context,
                max_output_tokens,
                estimate_multiplier=estimate_multiplier,
                safety_tokens=safety_tokens,
                safety_ratio=safety_ratio,
            ):
                logger.warning("Runtime context shrink fell back to latest user message only")
                return fallback

            # If still too large, aggressively trim all large fields.
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
                if ContextCompactor.can_fit(
                    truncated,
                    max_context,
                    max_output_tokens,
                    estimate_multiplier=estimate_multiplier,
                    safety_tokens=safety_tokens,
                    safety_ratio=safety_ratio,
                ):
                    logger.warning("Runtime context shrink applied aggressive truncation")
                    return truncated
            logger.warning("Runtime context shrink exhausted aggressive truncation")
            return [
                {"role": "system", "content": "[System prompt truncated for context budget]"}
                if i == 0 and msg.get("role") == "system"
                else {"role": msg.get("role", "user"), "content": "[truncated for context budget]"}
                for i, msg in enumerate(fallback)
            ]
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
            "is_compaction_seed": True,
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

    @staticmethod
    def _text_tokens(text: str) -> int:
        if not text:
            return 0
        ascii_chars = sum(1 for ch in text if ord(ch) < 128)
        non_ascii_chars = len(text) - ascii_chars
        # ASCII compresses better than CJK. Use conservative estimate.
        return max(1, ascii_chars // 3 + non_ascii_chars)

    @staticmethod
    def _json_tokens(value: Any) -> int:
        try:
            payload = json.dumps(value, ensure_ascii=False)
        except Exception:
            payload = str(value)
        # JSON punctuation and escaped content add overhead.
        return ContextCompactor._text_tokens(payload) + max(1, len(payload) // 16)

    @staticmethod
    def _content_tokens(content: Any) -> int:
        if content is None:
            return 0
        if isinstance(content, str):
            return ContextCompactor._text_tokens(content)
        if isinstance(content, list):
            total = 0
            for item in content:
                if isinstance(item, dict):
                    typ = item.get("type")
                    if typ in ("text", "input_text", "output_text"):
                        total += ContextCompactor._text_tokens(str(item.get("text", "")))
                    elif typ == "image_url":
                        total += 24
                    else:
                        total += ContextCompactor._json_tokens(item)
                else:
                    total += ContextCompactor._text_tokens(str(item))
            return total
        if isinstance(content, dict):
            return ContextCompactor._json_tokens(content)
        return ContextCompactor._text_tokens(str(content))

    @staticmethod
    def _truncate_text(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        if max_chars <= 32:
            return text[: max(0, max_chars)]
        return text[: max_chars - 24] + "\n...[truncated]"

    @staticmethod
    def _truncate_content(content: Any, max_chars: int) -> Any:
        if content is None:
            return None
        if isinstance(content, str):
            return ContextCompactor._truncate_text(content, max_chars)
        if isinstance(content, list):
            out: list[Any] = []
            budget = max_chars
            for item in content:
                if budget <= 0:
                    break
                if isinstance(item, dict):
                    typ = item.get("type")
                    if typ in ("text", "input_text", "output_text"):
                        text = str(item.get("text", ""))
                        trimmed = ContextCompactor._truncate_text(text, max(32, budget))
                        out.append({**item, "text": trimmed})
                        budget -= len(trimmed)
                    elif typ == "image_url":
                        out.append({"type": "text", "text": "[media]"})
                        budget -= 16
                    else:
                        dumped = ContextCompactor._truncate_text(
                            json.dumps(item, ensure_ascii=False), max(32, budget)
                        )
                        out.append({"type": "text", "text": dumped})
                        budget -= len(dumped)
                else:
                    text = ContextCompactor._truncate_text(str(item), max(32, budget))
                    out.append(text)
                    budget -= len(text)
            return out
        if isinstance(content, dict):
            dumped = ContextCompactor._truncate_text(
                json.dumps(content, ensure_ascii=False), max_chars
            )
            return {"type": "text", "text": dumped}
        return ContextCompactor._truncate_text(str(content), max_chars)

    @staticmethod
    def _trim_tool_calls(tool_calls: Any, max_chars: int) -> Any:
        if not isinstance(tool_calls, list):
            return tool_calls
        trimmed: list[dict[str, Any]] = []
        remaining = max_chars
        for call in tool_calls[:4]:
            if remaining <= 0:
                break
            if not isinstance(call, dict):
                continue
            function = call.get("function")
            fn_name = ""
            fn_args: Any = ""
            if isinstance(function, dict):
                fn_name = str(function.get("name", ""))
                fn_args = function.get("arguments", "")
            arg_text = (
                fn_args if isinstance(fn_args, str) else json.dumps(fn_args, ensure_ascii=False)
            )
            arg_limit = max(32, remaining // 2)
            arg_text = ContextCompactor._truncate_text(arg_text, arg_limit)
            item = {
                "id": call.get("id"),
                "type": call.get("type", "function"),
                "function": {"name": fn_name, "arguments": arg_text},
            }
            trimmed.append(item)
            remaining -= len(fn_name) + len(arg_text) + 16
        return trimmed

    @staticmethod
    def _minimize_message_for_budget(message: dict[str, Any], max_chars: int) -> dict[str, Any]:
        item = dict(message)
        # Drop regenerable reasoning payload first.
        item.pop("reasoning_content", None)
        item.pop("thinking_blocks", None)
        if "content" in item:
            item["content"] = ContextCompactor._truncate_content(item.get("content"), max_chars)
        if "tool_calls" in item:
            item["tool_calls"] = ContextCompactor._trim_tool_calls(
                item.get("tool_calls"), max(64, max_chars // 2)
            )
        return item

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
