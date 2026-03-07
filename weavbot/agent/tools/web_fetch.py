"""Web fetch tool: fetch URL content and extract readable text/markdown."""

import json
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from loguru import logger
from markdownify import markdownify

from weavbot.agent.tools.base import Tool

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5  # Limit redirects to prevent DoS attacks
DEFAULT_MAX_CHARS = 150_000


def _html_to_output(html: str, fmt: str) -> str:
    """Convert HTML to markdown or plain text."""
    if fmt == "markdown":
        return markdownify(html, heading_style="ATX").strip()
    return BeautifulSoup(html, "html.parser").get_text(separator="\n").strip()


def _validate_url(url: str) -> tuple[bool, str]:
    """Validate URL: must be http(s) with valid domain."""
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False, f"Only http/https allowed, got '{p.scheme or 'none'}'"
        if not p.netloc:
            return False, "Missing domain"
        return True, ""
    except Exception as e:
        return False, str(e)


class WebFetchTool(Tool):
    """Fetch and extract content from a URL using Readability."""

    name = "web_fetch"
    description = "Fetch URL and extract readable content (HTML → markdown/text)."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "fmt": {
                "type": "string",
                "enum": ["markdown", "text"],
                "default": "markdown",
                "description": "Output format: markdown or text (default: markdown)",
            },
            "max_chars": {
                "type": "integer",
                "minimum": 100,
                "default": DEFAULT_MAX_CHARS,
                "description": "Max characters to return (default: 150000)",
            },
        },
        "required": ["url"],
    }

    def __init__(self, max_chars: int = DEFAULT_MAX_CHARS, proxy: str | None = None):
        self.max_chars = max_chars
        self.proxy = proxy

    async def execute(
        self,
        url: str,
        fmt: str = "markdown",
        max_chars: int | None = None,
        **kwargs: Any,
    ) -> str:
        from readability import Document

        effective_max = max_chars if max_chars is not None else self.max_chars
        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            return json.dumps(
                {"error": f"URL validation failed: {error_msg}", "url": url},
                ensure_ascii=False,
            )

        try:
            logger.debug("WebFetch: {}", "proxy enabled" if self.proxy else "direct connection")
            async with httpx.AsyncClient(
                follow_redirects=True,
                max_redirects=MAX_REDIRECTS,
                timeout=30.0,
                proxy=self.proxy,
            ) as client:
                r = await client.get(url, headers={"User-Agent": USER_AGENT})
                r.raise_for_status()

            ctype = r.headers.get("content-type", "")

            if "application/json" in ctype:
                text = json.dumps(r.json(), indent=2, ensure_ascii=False)
                extractor = "json"
            elif "text/html" in ctype or r.text[:256].lower().startswith(("<!doctype", "<html")):
                doc = Document(r.text)
                content = _html_to_output(doc.summary(), fmt)
                text = f"# {doc.title()}\n\n{content}" if doc.title() else content
                extractor = "readability"
            else:
                text = r.text
                extractor = "raw"

            truncated = len(text) > effective_max
            if truncated:
                text = text[:effective_max]

            return json.dumps(
                {
                    "url": url,
                    "finalUrl": str(r.url),
                    "status": r.status_code,
                    "extractor": extractor,
                    "truncated": truncated,
                    "length": len(text),
                    "text": text,
                },
                ensure_ascii=False,
            )
        except httpx.ProxyError as e:
            logger.error("WebFetch proxy error for {}: {}", url, e)
            return json.dumps({"error": f"Proxy error: {e}", "url": url}, ensure_ascii=False)
        except Exception as e:
            logger.error("WebFetch error for {}: {}", url, e)
            return json.dumps({"error": str(e), "url": url}, ensure_ascii=False)
