"""Anthropic provider using the native anthropic SDK."""

from __future__ import annotations

from typing import Any

from anthropic import AsyncAnthropic

from weavbot.agent.messages import ChatMessage, ToolCallRequest
from weavbot.providers.base import (
    LLMProvider,
    LLMResponse,
    build_provider_headers,
)

_THINKING_BUDGET: dict[str, int] = {
    "low": 4096,
    "medium": 10000,
    "high": 32000,
}


class AnthropicProvider(LLMProvider):
    def __init__(
        self,
        api_key: str = "",
        api_base: str | None = None,
        default_model: str = "claude-sonnet-4-20250514",
        extra_headers: dict[str, str] | None = None,
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        kwargs: dict[str, Any] = {"api_key": api_key}
        if api_base:
            kwargs["base_url"] = api_base
        kwargs["default_headers"] = build_provider_headers(extra_headers)
        self._client = AsyncAnthropic(**kwargs)

    # ------------------------------------------------------------------
    # Tool conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for t in tools:
            func = t.get("function", {})
            entry: dict[str, Any] = {
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            }
            out.append(entry)
        if out:
            out[-1]["cache_control"] = {"type": "ephemeral"}
        return out

    # ------------------------------------------------------------------
    # ChatMessage → Anthropic wire format
    # ------------------------------------------------------------------

    @classmethod
    def _encode_media_blocks_anthropic(cls, media: list[str]) -> list[dict[str, Any]]:
        """Encode media file paths into Anthropic image source blocks.

        Only image/* MIME types are supported; other types are replaced with
        a text placeholder.
        """
        blocks: list[dict[str, Any]] = []
        for path in media:
            encoded = cls._encode_media_file(path)
            if encoded:
                mime, b64 = encoded
                if not mime.startswith("image/"):
                    blocks.append({"type": "text", "text": f"[unsupported media: {mime}]"})
                    continue
                blocks.append(
                    {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}}
                )
        return blocks

    @classmethod
    def _serialize_messages_anthropic(
        cls, messages: list[ChatMessage]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Convert ChatMessage list to Anthropic format.

        Returns (system_blocks, anthropic_messages).
        """
        system_blocks: list[dict[str, Any]] = []
        result: list[dict[str, Any]] = []

        i = 0
        while i < len(messages):
            msg = messages[i]

            if msg.role == "system":
                system_blocks.append(
                    {
                        "type": "text",
                        "text": msg.content or "",
                        "cache_control": {"type": "ephemeral"},
                    }
                )
                i += 1

            elif msg.role == "assistant":
                blocks: list[dict[str, Any]] = []
                if msg.thinking_blocks:
                    blocks.extend(msg.thinking_blocks)
                if msg.content:
                    blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        }
                    )
                if not blocks:
                    blocks = [{"type": "text", "text": ""}]
                result.append({"role": "assistant", "content": blocks})
                i += 1

            elif msg.role == "tool":
                tool_results: list[dict[str, Any]] = []
                while i < len(messages) and messages[i].role == "tool":
                    tm = messages[i]
                    media_blocks = cls._encode_media_blocks_anthropic(tm.media)
                    raw_content: str | list[dict[str, Any]] = tm.content or "(empty)"
                    if media_blocks:
                        content_parts: list[dict[str, Any]] = media_blocks
                        content_parts.append({"type": "text", "text": tm.content or "(empty)"})
                        raw_content = content_parts
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tm.tool_call_id or "",
                            "content": raw_content,
                        }
                    )
                    i += 1
                result.append({"role": "user", "content": tool_results})

            else:
                media_blocks = cls._encode_media_blocks_anthropic(msg.media)
                if media_blocks:
                    parts: list[dict[str, Any]] = media_blocks
                    if msg.content:
                        parts.append({"type": "text", "text": msg.content})
                    result.append({"role": "user", "content": parts})
                else:
                    result.append({"role": "user", "content": msg.content or "(empty)"})
                i += 1

        merged: list[dict[str, Any]] = []
        for m in result:
            if merged and merged[-1]["role"] == m["role"]:
                prev = merged[-1]["content"]
                cur = m["content"]
                if isinstance(prev, str):
                    prev = [{"type": "text", "text": prev}]
                if isinstance(cur, str):
                    cur = [{"type": "text", "text": cur}]
                merged[-1]["content"] = prev + cur
            else:
                merged.append(m)

        return system_blocks, merged

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        system_blocks, converted = self._serialize_messages_anthropic(messages)

        effective_max = max(1, max_tokens)

        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": converted,
            "max_tokens": effective_max,
        }

        if system_blocks:
            kwargs["system"] = system_blocks

        if reasoning_effort:
            budget = _THINKING_BUDGET.get(reasoning_effort, _THINKING_BUDGET["medium"])
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
            kwargs["max_tokens"] = max(effective_max, budget + 4096)
            kwargs["temperature"] = 1
        else:
            kwargs["temperature"] = temperature

        if tools:
            kwargs["tools"] = self._convert_tools(tools)
            kwargs["tool_choice"] = {"type": "auto"}

        try:
            async with self._client.messages.stream(**kwargs) as stream:
                response = await stream.get_final_message()
            return self._parse_response(response)
        except Exception as e:
            return LLMResponse(content=f"Error: {e}", finish_reason="error")

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(response: Any) -> LLMResponse:
        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []
        thinking_blocks: list[dict] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCallRequest(id=block.id, name=block.name, arguments=block.input)
                )
            elif block.type == "thinking":
                thinking_blocks.append({"type": "thinking", "thinking": block.thinking})

        usage: dict[str, int] = {}
        if response.usage:
            inp = response.usage.input_tokens
            out = response.usage.output_tokens
            usage = {"prompt_tokens": inp, "completion_tokens": out, "total_tokens": inp + out}

        finish = response.stop_reason or "stop"
        if finish == "end_turn":
            finish = "stop"
        elif finish == "tool_use":
            finish = "tool_calls"

        return LLMResponse(
            content="".join(text_parts) or None,
            tool_calls=tool_calls,
            finish_reason=finish,
            usage=usage,
            thinking_blocks=thinking_blocks or None,
        )

    def get_default_model(self) -> str:
        return self.default_model
