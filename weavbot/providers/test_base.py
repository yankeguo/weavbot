from weavbot import __version__
from weavbot.providers.base import build_provider_headers


def test_build_provider_headers_has_defaults():
    headers = build_provider_headers()
    assert headers["User-Agent"] == f"weavbot/{__version__}"
    assert headers["HTTP-Referer"] == "https://yankeguo.github.io/weavbot"
    assert headers["X-OpenRouter-Title"] == "weavbot"


def test_build_provider_headers_allows_overrides():
    headers = build_provider_headers(
        {
            "User-Agent": "custom-ua/1.0",
            "X-OpenRouter-Title": "custom-title",
            "X-Custom": "yes",
        }
    )
    assert headers["User-Agent"] == "custom-ua/1.0"
    assert headers["HTTP-Referer"] == "https://yankeguo.github.io/weavbot"
    assert headers["X-OpenRouter-Title"] == "custom-title"
    assert headers["X-Custom"] == "yes"
