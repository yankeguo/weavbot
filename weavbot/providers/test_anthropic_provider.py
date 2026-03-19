from types import SimpleNamespace

from weavbot.agent.messages import ChatMessage
from weavbot.providers.anthropic_provider import AnthropicProvider


def test_parse_response_preserves_thinking_and_redacted_blocks():
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="internal", signature="sig-123"),
            SimpleNamespace(type="redacted_thinking", data="opaque"),
            SimpleNamespace(type="text", text="hello"),
        ],
        usage=SimpleNamespace(input_tokens=11, output_tokens=7),
        stop_reason="end_turn",
    )

    parsed = AnthropicProvider._parse_response(response)

    assert parsed.content == "hello"
    assert parsed.finish_reason == "stop"
    assert parsed.usage == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
    assert parsed.thinking_blocks == [
        {"type": "thinking", "thinking": "internal", "signature": "sig-123"},
        {"type": "redacted_thinking", "data": "opaque"},
    ]


def test_serialize_messages_keeps_only_valid_thinking_blocks():
    messages = [
        ChatMessage(
            role="assistant",
            content="answer",
            thinking_blocks=[
                {"type": "thinking", "thinking": "missing-signature"},
                {"type": "thinking", "thinking": "valid", "signature": "sig-1", "extra": "ignored"},
                {"type": "redacted_thinking", "data": "redacted-payload"},
                {"type": "unknown", "foo": "bar"},
            ],
        )
    ]

    system, serialized = AnthropicProvider._serialize_messages_anthropic(
        messages, use_cache_control=False
    )

    assert system == []
    assert serialized[0]["role"] == "assistant"
    assert serialized[0]["content"] == [
        {"type": "thinking", "thinking": "valid", "signature": "sig-1"},
        {"type": "redacted_thinking", "data": "redacted-payload"},
        {"type": "text", "text": "answer"},
    ]


def test_dashscope_base_disables_cache_control(monkeypatch):
    monkeypatch.delenv("WB_ANTHROPIC_CACHE_CONTROL", raising=False)
    provider = AnthropicProvider(
        api_key="test-key",
        api_base="https://coding.dashscope.aliyuncs.com/apps/anthropic",
    )

    assert provider._use_cache_control is False
    tools = provider._convert_tools(
        [
            {
                "function": {
                    "name": "read_file",
                    "description": "read",
                    "parameters": {"type": "object", "properties": {}},
                }
            }
        ],
        use_cache_control=provider._use_cache_control,
    )
    assert "cache_control" not in tools[0]


def test_redact_for_log_hides_sensitive_fields():
    payload = {
        "api_key": "secret-key",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "data": "a" * 1024}},
                    {"type": "thinking", "thinking": "work", "signature": "super-signature"},
                ],
            }
        ],
    }

    redacted = AnthropicProvider._redact_for_log(payload)
    assert redacted["api_key"] == "***redacted***"
    assert redacted["messages"][0]["content"][0]["source"]["data"].startswith("<base64:")
    assert redacted["messages"][0]["content"][1]["signature"].startswith("<signature:")
