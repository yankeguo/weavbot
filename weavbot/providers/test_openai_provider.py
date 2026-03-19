from __future__ import annotations

from types import SimpleNamespace

import pytest

from weavbot.agent.messages import ChatMessage
from weavbot.providers.openai_provider import OpenAIProvider


def test_redact_for_log_masks_sensitive_fields():
    payload = {
        "api_key": "secret",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64," + ("a" * 512)},
                    }
                ],
            }
        ],
    }

    redacted = OpenAIProvider._redact_for_log(payload)
    assert redacted["api_key"] == "***redacted***"
    url = redacted["messages"][0]["content"][0]["image_url"]["url"]
    assert "<redacted 512 chars>" in url


def test_request_summary_counts_roles_tools_reasoning_and_media():
    summary = OpenAIProvider._request_summary(
        {
            "model": "gpt-test",
            "max_tokens": 128,
            "temperature": 0.1,
            "reasoning_effort": "low",
            "tools": [{"type": "function", "function": {"name": "echo"}}],
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,aaaa"},
                        }
                    ],
                },
            ],
        }
    )
    assert summary["model"] == "gpt-test"
    assert summary["has_tools"] is True
    assert summary["has_reasoning_effort"] is True
    assert summary["message_count"] == 3
    assert summary["role_counts"] == {"system": 1, "user": 2}
    assert summary["has_media"] is True


@pytest.mark.asyncio
async def test_chat_with_debug_logs_payload_and_error(monkeypatch):
    monkeypatch.setenv("WB_DEBUG_OPENAI", "1")
    provider = OpenAIProvider(
        api_key="test-key",
        api_base="https://example.com/v1",
        default_model="gpt-test",
    )

    class _FailingCompletions:
        async def create(self, **kwargs):
            raise RuntimeError("boom")

    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=_FailingCompletions()))

    debug_calls: list[str] = []
    error_calls: list[str] = []

    def _capture_debug(msg, *args, **kwargs):
        debug_calls.append(msg)

    def _capture_error(msg, *args, **kwargs):
        error_calls.append(msg)

    monkeypatch.setattr("weavbot.providers.openai_provider.logger.debug", _capture_debug)
    monkeypatch.setattr("weavbot.providers.openai_provider.logger.error", _capture_error)

    resp = await provider.chat(messages=[ChatMessage(role="user", content="hello")], temperature=0)

    assert resp.finish_reason == "error"
    assert resp.content is not None and "boom" in resp.content
    assert any("OpenAI payload summary" in m for m in debug_calls)
    assert any("OpenAI payload detail" in m for m in debug_calls)
    assert any("OpenAI failed payload detail" in m for m in debug_calls)
    assert any("OpenAI request failed" in m for m in error_calls)
