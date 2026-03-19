from weavbot.agent.messages import ChatMessage


def test_from_dict_handles_legacy_tool_call_arguments_json_string():
    msg = ChatMessage.from_dict(
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path":"a.txt"}'},
                }
            ],
        }
    )
    assert len(msg.tool_calls) == 1
    tc = msg.tool_calls[0]
    assert tc.id == "call_1"
    assert tc.name == "read_file"
    assert tc.arguments == {"path": "a.txt"}


def test_from_dict_handles_legacy_name_media_and_string_bool():
    msg = ChatMessage.from_dict(
        {
            "role": "tool",
            "content": "ok",
            "name": "shell",
            "media": "/tmp/a.png",
            "is_compaction_seed": "false",
        }
    )
    assert msg.tool_name == "shell"
    assert msg.media == ["/tmp/a.png"]
    assert msg.is_compaction_seed is False


def test_from_dict_extracts_text_from_content_blocks():
    msg = ChatMessage.from_dict(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "line1"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abcd"}},
                {"type": "text", "text": "line2"},
            ],
        }
    )
    assert msg.content == "line1\nline2"
