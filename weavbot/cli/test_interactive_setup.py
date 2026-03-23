import io

from rich.console import Console

from weavbot.cli import interactive_setup
from weavbot.config.schema import Config


def _make_console() -> Console:
    return Console(file=io.StringIO(), force_terminal=False, width=120)


def test_interactive_setup_persists_channel_only_changes(monkeypatch):
    """Channel-only edits must mark config as changed."""

    monkeypatch.setattr(interactive_setup, "_fetch_providers", lambda _console: None)
    monkeypatch.setattr(interactive_setup, "_install_ripgrep", lambda _console: None)
    monkeypatch.setattr(interactive_setup, "_configure_autostart", lambda _console: None)

    def _mutate_channels(data: dict, _console: Console) -> dict:
        telegram = data.setdefault("channels", {}).setdefault("telegram", {})
        telegram["enabled"] = True
        telegram["token"] = "bot-token-123"
        return data

    monkeypatch.setattr(interactive_setup, "_configure_channels", _mutate_channels)

    original = Config()
    updated = interactive_setup.interactive_provider_setup(original, _make_console())

    assert updated.channels.telegram.enabled is True
    assert updated.channels.telegram.token == "bot-token-123"


def test_interactive_setup_keeps_original_config_when_no_changes(monkeypatch):
    """No provider/channel changes should keep the original config object."""

    monkeypatch.setattr(interactive_setup, "_fetch_providers", lambda _console: None)
    monkeypatch.setattr(interactive_setup, "_configure_channels", lambda data, _console: data)
    monkeypatch.setattr(interactive_setup, "_install_ripgrep", lambda _console: None)
    monkeypatch.setattr(interactive_setup, "_configure_autostart", lambda _console: None)

    original = Config()
    updated = interactive_setup.interactive_provider_setup(original, _make_console())

    assert updated is original


def test_select_provider_realtime_path(monkeypatch):
    monkeypatch.setattr(interactive_setup, "_inquirer_enabled", lambda: True)
    monkeypatch.setattr(
        interactive_setup,
        "_ask_fuzzy",
        lambda _message, _choices: next(
            c["value"] for c in _choices if c["value"]["id"] == "openai"
        ),
    )

    providers = [
        {"id": "anthropic", "name": "Anthropic", "npm": "@ai-sdk/anthropic", "models": {"a": {}}},
        {"id": "openai", "name": "OpenAI", "npm": "@ai-sdk/openai", "models": {"b": {}}},
    ]

    chosen = interactive_setup._select_provider(providers, _make_console())
    assert chosen is not None
    assert chosen["id"] == "openai"


def test_select_model_realtime_path(monkeypatch):
    monkeypatch.setattr(interactive_setup, "_inquirer_enabled", lambda: True)
    monkeypatch.setattr(
        interactive_setup,
        "_ask_fuzzy",
        lambda _message, _choices: next(c["value"] for c in _choices if c["value"][0] == "gpt-4o"),
    )

    provider = {
        "name": "OpenAI",
        "models": {
            "gpt-4o-mini": {
                "id": "gpt-4o-mini",
                "name": "GPT-4o mini",
                "limit": {"context": 128000},
            },
            "gpt-4o": {
                "id": "gpt-4o",
                "name": "GPT-4o",
                "limit": {"context": 128000, "output": 16384},
            },
        },
    }

    chosen = interactive_setup._select_model(provider, _make_console())
    assert chosen is not None
    model_id, _model_data = chosen
    assert model_id == "gpt-4o"


def test_configure_channels_realtime_path(monkeypatch):
    monkeypatch.setattr(interactive_setup, "_inquirer_enabled", lambda: True)
    monkeypatch.setattr(interactive_setup, "_select_channel_realtime", lambda _console: 0)
    monkeypatch.setattr(interactive_setup.typer, "confirm", lambda _message, default=False: True)

    values = iter(["telegram-token"])
    monkeypatch.setattr(
        interactive_setup.typer,
        "prompt",
        lambda *_args, **_kwargs: next(values),
    )

    data: dict = {}
    updated = interactive_setup._configure_channels(data, _make_console())

    assert updated["channels"]["telegram"]["enabled"] is True
    assert updated["channels"]["telegram"]["token"] == "telegram-token"
    assert "discord" not in updated["channels"]


def test_interactive_setup_keeps_original_when_realtime_provider_cancelled(monkeypatch):
    raw = {
        "openai": {
            "npm": "@ai-sdk/openai",
            "id": "openai",
            "name": "OpenAI",
            "models": {
                "gpt-4o-mini": {
                    "id": "gpt-4o-mini",
                    "name": "GPT-4o mini",
                    "tool_call": True,
                }
            },
        }
    }

    monkeypatch.setattr(interactive_setup, "_fetch_providers", lambda _console: raw)
    monkeypatch.setattr(interactive_setup, "_inquirer_enabled", lambda: True)
    monkeypatch.setattr(interactive_setup, "_ask_fuzzy", lambda _message, _choices: None)
    monkeypatch.setattr(interactive_setup, "_configure_channels", lambda data, _console: data)
    monkeypatch.setattr(interactive_setup, "_install_ripgrep", lambda _console: None)
    monkeypatch.setattr(interactive_setup, "_configure_autostart", lambda _console: None)

    original = Config()
    updated = interactive_setup.interactive_provider_setup(original, _make_console())

    assert updated is original


def test_select_provider_falls_back_to_legacy_on_prompt_error(monkeypatch):
    monkeypatch.setattr(interactive_setup, "_inquirer_enabled", lambda: True)
    monkeypatch.setattr(
        interactive_setup, "_ask_fuzzy", lambda _message, _choices: interactive_setup._PROMPT_ERROR
    )

    # Legacy path uses typer.prompt for number selection.
    monkeypatch.setattr(interactive_setup.typer, "prompt", lambda _message, default="": "2")

    providers = [
        {"id": "anthropic", "name": "Anthropic", "npm": "@ai-sdk/anthropic", "models": {"a": {}}},
        {"id": "openai", "name": "OpenAI", "npm": "@ai-sdk/openai", "models": {"b": {}}},
    ]

    chosen = interactive_setup._select_provider(providers, _make_console())
    assert chosen is not None
    assert chosen["id"] == "openai"


def test_configure_channels_falls_back_to_legacy_on_prompt_error(monkeypatch):
    monkeypatch.setattr(interactive_setup, "_inquirer_enabled", lambda: True)
    monkeypatch.setattr(
        interactive_setup,
        "_select_channel_realtime",
        lambda _console: interactive_setup._PROMPT_ERROR,
    )
    monkeypatch.setattr(interactive_setup.typer, "confirm", lambda _message, default=False: True)

    # First prompt is legacy numeric channel selection, second is channel token input.
    values = iter(["1", "telegram-token"])
    monkeypatch.setattr(
        interactive_setup.typer,
        "prompt",
        lambda *_args, **_kwargs: next(values),
    )

    data: dict = {}
    updated = interactive_setup._configure_channels(data, _make_console())

    assert updated["channels"]["telegram"]["enabled"] is True
    assert updated["channels"]["telegram"]["token"] == "telegram-token"


def test_fit_column_handles_wide_chars():
    text = "渠道选择非常长的名字"
    fitted = interactive_setup._fit_column(text, 10)

    assert interactive_setup._display_width(fitted) == 10
    assert fitted.rstrip().endswith("...")
