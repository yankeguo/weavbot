"""Anthropic provider using the native anthropic SDK."""

from __future__ import annotations

import re
from typing import Any

import json_repair
from anthropic import AsyncAnthropic

from weavbot.providers.base import LLMProvider, LLMResponse, ToolCallRequest

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
        if extra_headers:
            kwargs["default_headers"] = extra_headers
        self._client = AsyncAnthropic(**kwargs)

    # ------------------------------------------------------------------
    # Message / tool conversion (OpenAI format → Anthropic format)
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

    @staticmethod
    def _convert_image_url_to_anthropic(block: dict[str, Any]) -> dict[str, Any]:
        """Convert OpenAI image_url block to Anthropic image block."""
        if block.get("type") != "image_url":
            return block
        url = (block.get("image_url") or {}).get("url", "")
        if not url.startswith("data:"):
            return block
        match = re.match(r"data:([^;]+);base64,(.+)", url, re.DOTALL)
        if not match:
            return {"type": "text", "text": "[image: invalid data URL]"}
        media_type, b64 = match.group(1), match.group(2)
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64},
        }

    @classmethod
    def _convert_image_blocks(cls, blocks: list[Any]) -> list[Any]:
        """Convert OpenAI image_url blocks in a list to Anthropic image format."""
        return [
            cls._convert_image_url_to_anthropic(b) if isinstance(b, dict) else b for b in blocks
        ]

    @classmethod
    def _convert_messages(
        cls, messages: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Split system prompts and convert messages to Anthropic format.

        Returns (system_blocks, anthropic_messages).
        """
        system_blocks: list[dict[str, Any]] = []
        result: list[dict[str, Any]] = []

        i = 0
        while i < len(messages):
            msg = messages[i]
            role = msg.get("role")

            if role == "system":
                content = msg.get("content", "")
                if isinstance(content, str):
                    system_blocks.append(
                        {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
                    )
                elif isinstance(content, list):
                    for item in content:
                        block = (
                            dict(item)
                            if isinstance(item, dict)
                            else {"type": "text", "text": str(item)}
                        )
                        if not any(b.get("cache_control") for b in system_blocks):
                            pass
                        system_blocks.append(block)
                    if system_blocks:
                        system_blocks[-1] = {
                            **system_blocks[-1],
                            "cache_control": {"type": "ephemeral"},
                        }
                i += 1

            elif role == "assistant":
                blocks: list[dict[str, Any]] = []

                thinking = msg.get("thinking_blocks")
                if thinking:
                    for tb in thinking:
                        blocks.append(tb)

                text = msg.get("content")
                if text:
                    if isinstance(text, str):
                        blocks.append({"type": "text", "text": text})
                    elif isinstance(text, list):
                        blocks.extend(text)

                for tc in msg.get("tool_calls", []):
                    func = tc.get("function", {})
                    args = func.get("arguments", {})
                    if isinstance(args, str):
                        args = json_repair.loads(args)
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": func.get("name", ""),
                            "input": args,
                        }
                    )

                if not blocks:
                    blocks = [{"type": "text", "text": ""}]

                result.append({"role": "assistant", "content": blocks})
                i += 1

            elif role == "tool":
                tool_results: list[dict[str, Any]] = []
                while i < len(messages) and messages[i].get("role") == "tool":
                    tm = messages[i]
                    raw_content = tm.get("content") or "(empty)"
                    if isinstance(raw_content, list):
                        raw_content = cls._convert_image_blocks(raw_content)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tm.get("tool_call_id", ""),
                            "content": raw_content,
                        }
                    )
                    i += 1
                result.append({"role": "user", "content": tool_results})

            else:
                content = msg.get("content", "")
                if isinstance(content, str):
                    result.append({"role": "user", "content": content or "(empty)"})
                elif isinstance(content, list):
                    result.append({"role": "user", "content": cls._convert_image_blocks(content)})
                else:
                    result.append({"role": "user", "content": str(content) or "(empty)"})
                i += 1

        # Anthropic requires alternating user/assistant roles — merge consecutive same-role msgs
        merged: list[dict[str, Any]] = []
        for m in result:
            if merged and merged[-1]["role"] == m["role"]:
                prev = merged[-1]["content"]
                cur = m["content"]
                if isinstance(prev, str):
                    prev = [{"type": "text", "text": prev}]
                elif isinstance(prev, list):
                    prev = cls._convert_image_blocks(prev)
                if isinstance(cur, str):
                    cur = [{"type": "text", "text": cur}]
                elif isinstance(cur, list):
                    cur = cls._convert_image_blocks(cur)
                merged[-1]["content"] = prev + cur
            else:
                merged.append(m)

        return system_blocks, merged

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        sanitized = self._sanitize_empty_content(messages)
        system_blocks, converted = self._convert_messages(sanitized)

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
