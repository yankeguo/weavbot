"""Tests for StreamingMarkdownFilter."""

from weavbot.channels.wechat.markdown_filter import StreamingMarkdownFilter


def test_plain_text_passthrough():
    f = StreamingMarkdownFilter()
    assert f.feed("hello world") + f.flush() == "hello world"


def test_cjk_italic_stripped():
    f = StreamingMarkdownFilter()
    assert f.feed("*你好*") + f.flush() == "你好"


def test_non_cjk_italic_preserved():
    f = StreamingMarkdownFilter()
    assert f.feed("*hello*") + f.flush() == "*hello*"


def test_bold_preserved():
    f = StreamingMarkdownFilter()
    assert f.feed("**hello**") + f.flush() == "**hello**"


def test_bold3_cjk_stripped():
    f = StreamingMarkdownFilter()
    assert f.feed("***你好***") + f.flush() == "你好"


def test_bold3_non_cjk_preserved():
    f = StreamingMarkdownFilter()
    assert f.feed("***hello***") + f.flush() == "***hello***"


def test_image_removed():
    f = StreamingMarkdownFilter()
    assert f.feed("hello ![alt](url) world") + f.flush() == "hello  world"


def test_heading_h5_stripped():
    f = StreamingMarkdownFilter()
    assert f.feed("##### title\n") + f.flush() == "title\n"


def test_heading_h6_stripped():
    f = StreamingMarkdownFilter()
    assert f.feed("###### title\n") + f.flush() == "title\n"


def test_horizontal_rule_preserved():
    f = StreamingMarkdownFilter()
    assert f.feed("---\n") + f.flush() == "---\n"


def test_code_fence_preserved():
    f = StreamingMarkdownFilter()
    text = "```python\nprint(1)\n```\n"
    assert f.feed(text) + f.flush() == text


def test_tilde_passthrough():
    # Upstream drops ~ chars only when they precede a pattern slice; in a
    # standalone string they pass through.
    f = StreamingMarkdownFilter()
    assert f.feed("~~hello~~") + f.flush() == "~~hello~~"


def test_blockquote_passthrough():
    # Upstream treats > as a regular character, not a filtered marker.
    f = StreamingMarkdownFilter()
    assert f.feed("> quote\n") + f.flush() == "> quote\n"


def test_mixed_streaming():
    f = StreamingMarkdownFilter()
    out = ""
    out += f.feed("hel")
    out += f.feed("lo *")
    out += f.feed("你好* world")
    out += f.flush()
    assert out == "hello 你好 world"
