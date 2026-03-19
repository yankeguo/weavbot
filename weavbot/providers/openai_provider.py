"""OpenAI-compatible provider using the openai SDK directly."""

from __future__ import annotations

import json
from typing import Any

import json_repair
from openai import AsyncOpenAI

from weavbot.agent.messages import ChatMessage, ToolCallRequest
from weavbot.providers.base import (
    LLMProvider,
    LLMResponse,
    build_provider_headers,
)


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        api_key: str = "no-key",
        api_base: str = "http://localhost:8000/v1",
        default_model: str = "default",
        extra_headers: dict[str, str] | None = None,
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=api_base,
            default_headers=build_provider_headers(extra_headers),
        )

    @classmethod
    def _serialize_messages(cls, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        """Convert ChatMessage list to OpenAI-compatible wire format.

        Media file paths are base64-encoded into image_url content parts.
        Empty content is sanitized inline to avoid provider 400 errors.
        """
        result: list[dict[str, Any]] = []
        for msg in messages:
            d: dict[str, Any] = {"role": msg.role}

            if msg.media:
                parts: list[dict[str, Any]] = []
                for path in msg.media:
                    encoded = cls._encode_media_file(path)
                    if encoded:
                        mime, b64 = encoded
                        parts.append(
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
                        )
                if msg.content:
                    parts.append({"type": "text", "text": msg.content})
                d["content"] = parts if parts else (msg.content or "(empty)")
            elif not msg.content:
                d["content"] = None if msg.tool_calls else "(empty)"
            else:
                d["content"] = msg.content

            if msg.tool_calls:
                d["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in msg.tool_calls
                ]

            if msg.tool_call_id is not None:
                d["tool_call_id"] = msg.tool_call_id
            if msg.tool_name is not None:
                d["name"] = msg.tool_name
            if msg.reasoning_content is not None:
                d["reasoning_content"] = msg.reasoning_content
            if msg.thinking_blocks is not None:
                d["thinking_blocks"] = msg.thinking_blocks

            result.append(d)
        return result

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        serialized = self._serialize_messages(messages)
        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": serialized,
            "max_tokens": max(1, max_tokens),
            "temperature": temperature,
        }
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
        if tools:
            kwargs.update(tools=tools, tool_choice="auto")
        try:
            return self._parse(await self._client.chat.completions.create(**kwargs))
        except Exception as e:
            return LLMResponse(content=f"Error: {e}", finish_reason="error")

    def _parse(self, response: Any) -> LLMResponse:
        choice = response.choices[0]
        msg = choice.message
        tool_calls = [
            ToolCallRequest(
                id=tc.id,
                name=tc.function.name,
                arguments=json_repair.loads(tc.function.arguments)
                if isinstance(tc.function.arguments, str)
                else tc.function.arguments,
            )
            for tc in (msg.tool_calls or [])
        ]
        u = response.usage
        return LLMResponse(
            content=msg.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage={
                "prompt_tokens": u.prompt_tokens,
                "completion_tokens": u.completion_tokens,
                "total_tokens": u.total_tokens,
            }
            if u
            else {},
            reasoning_content=getattr(msg, "reasoning_content", None) or None,
        )

    def get_default_model(self) -> str:
        return self.default_model
