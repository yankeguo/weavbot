"""Base LLM provider interface."""

from __future__ import annotations

import base64
import mimetypes
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from weavbot import __version__
from weavbot.agent.messages import ChatMessage, ToolCallRequest  # noqa: F401 - re-export

DEFAULT_PROVIDER_HEADERS: dict[str, str] = {
    "User-Agent": f"weavbot/{__version__}",
    "HTTP-Referer": "https://yankeguo.github.io/weavbot",
    "X-OpenRouter-Title": "weavbot",
}


def build_provider_headers(extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    """Build default provider headers with user overrides."""
    headers = dict(DEFAULT_PROVIDER_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    return headers


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    reasoning_content: str | None = None
    thinking_blocks: list[dict] | None = None

    @property
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls."""
        return len(self.tool_calls) > 0


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    Implementations should handle the specifics of each provider's API
    while maintaining a consistent interface.
    """

    def __init__(self, api_key: str | None = None, api_base: str | None = None):
        self.api_key = api_key
        self.api_base = api_base

    @staticmethod
    def _encode_media_file(path: str) -> tuple[str, str] | None:
        """Read a media file and return (mime_type, base64_data), or None on failure."""
        p = Path(path)
        if not p.is_file():
            logger.debug("Media file not found, skipping: {}", path)
            return None
        mime, _ = mimetypes.guess_type(str(p))
        if not mime:
            logger.debug("Cannot determine MIME type, skipping: {}", path)
            return None
        try:
            b64 = base64.b64encode(p.read_bytes()).decode()
            return mime, b64
        except Exception:
            logger.debug("Failed to read media file, skipping: {}", path)
            return None

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        """
        Send a chat completion request.

        Args:
            messages: List of ChatMessage objects.
            tools: Optional list of tool definitions.
            model: Model identifier (provider-specific).
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.

        Returns:
            LLMResponse with content and/or tool calls.
        """
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        """Get the default model for this provider."""
        pass
