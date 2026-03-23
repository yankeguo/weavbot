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
    monkeypatch.setattr(interactive_setup, "_ensure_fuzzy_mode", lambda: None)
    monkeypatch.setattr(
        interactive_setup,
        "_ask_fuzzy",
        lambda _message, _choices, _hint_text=None: next(
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
    monkeypatch.setattr(interactive_setup, "_ensure_fuzzy_mode", lambda: None)
    monkeypatch.setattr(
        interactive_setup,
        "_ask_fuzzy",
        lambda _message, _choices, _hint_text=None: next(
            c["value"] for c in _choices if c["value"][0] == "gpt-4o"
        ),
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
    monkeypatch.setattr(interactive_setup, "_ensure_fuzzy_mode", lambda: None)
    monkeypatch.setattr(interactive_setup, "_select_channel_realtime", lambda _console: 0)

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


def test_select_channel_realtime_falls_back_to_numbered(monkeypatch):
    monkeypatch.setattr(
        interactive_setup,
        "_ask_fuzzy",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("no tty")),
    )
    monkeypatch.setattr(interactive_setup.typer, "prompt", lambda *_args, **_kwargs: "2")

    picked = interactive_setup._select_channel_realtime(_make_console())
    assert picked == 1


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
    monkeypatch.setattr(interactive_setup, "_ensure_fuzzy_mode", lambda: None)
    monkeypatch.setattr(
        interactive_setup, "_ask_fuzzy", lambda _message, _choices, _hint_text=None: None
    )
    monkeypatch.setattr(interactive_setup, "_configure_channels", lambda data, _console: data)
    monkeypatch.setattr(interactive_setup, "_install_ripgrep", lambda _console: None)
    monkeypatch.setattr(interactive_setup, "_configure_autostart", lambda _console: None)

    original = Config()
    updated = interactive_setup.interactive_provider_setup(original, _make_console())

    assert updated is original


def test_select_provider_falls_back_when_fuzzy_unavailable(monkeypatch):
    monkeypatch.setattr(
        interactive_setup,
        "_ask_fuzzy",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("no tty")),
    )
    monkeypatch.setattr(interactive_setup.typer, "prompt", lambda *_args, **_kwargs: "1")
    providers = [
        {"id": "openai", "name": "OpenAI", "npm": "@ai-sdk/openai", "models": {"b": {}}},
    ]
    picked = interactive_setup._select_provider(providers, _make_console())
    assert picked is not None
    assert picked["id"] == "openai"


def test_select_model_falls_back_on_internal_error(monkeypatch):
    monkeypatch.setattr(
        interactive_setup,
        "_ask_fuzzy",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("boom")),
    )
    monkeypatch.setattr(interactive_setup.typer, "prompt", lambda *_args, **_kwargs: "2")

    provider = {
        "name": "OpenAI",
        "models": {
            "gpt-4o": {
                "id": "gpt-4o",
                "name": "GPT-4o",
                "limit": {"context": 128000},
            },
            "gpt-4o-mini": {
                "id": "gpt-4o-mini",
                "name": "GPT-4o mini",
                "limit": {"context": 128000, "output": 16384},
            },
        },
    }

    chosen = interactive_setup._select_model(provider, _make_console())
    assert chosen is not None
    model_id, _model_data = chosen
    assert model_id == "gpt-4o-mini"


def test_ask_fuzzy_raises_internal_error(monkeypatch):
    class _BrokenPrompt:
        def execute(self):
            raise ValueError("boom")

    class _BrokenInquirer:
        @staticmethod
        def fuzzy(**_kwargs):
            return _BrokenPrompt()

    monkeypatch.setattr(interactive_setup, "_ensure_fuzzy_mode", lambda: None)
    monkeypatch.setattr(interactive_setup, "inquirer", _BrokenInquirer)
    try:
        interactive_setup._ask_fuzzy("Provider", [{"name": "a", "value": 1}], None)
        assert False, "should raise ValueError"
    except ValueError as exc:
        assert "boom" in str(exc)


def test_fit_column_handles_wide_chars():
    text = "渠道选择非常长的名字"
    fitted = interactive_setup._fit_column(text, 10)

    assert interactive_setup._display_width(fitted) == 10
    assert fitted.rstrip().endswith("...")


def test_interactive_setup_skips_provider_on_ctrl_c(monkeypatch):
    raw = {
        "openai": {
            "npm": "@ai-sdk/openai",
            "id": "openai",
            "name": "OpenAI",
            "models": {
                "gpt-4o-mini": {"id": "gpt-4o-mini", "name": "GPT-4o mini", "tool_call": True}
            },
        }
    }
    monkeypatch.setattr(interactive_setup, "_fetch_providers", lambda _console: raw)
    monkeypatch.setattr(
        interactive_setup,
        "_select_provider",
        lambda _providers, _console: interactive_setup._PROMPT_CTRL_C,
    )
    monkeypatch.setattr(interactive_setup, "_configure_channels", lambda data, _console: data)
    monkeypatch.setattr(interactive_setup, "_install_ripgrep", lambda _console: None)
    monkeypatch.setattr(interactive_setup, "_configure_autostart", lambda _console: None)

    original = Config()
    updated = interactive_setup.interactive_provider_setup(original, _make_console())
    assert updated is original


def test_interactive_setup_model_ctrl_c_goes_back_to_provider(monkeypatch):
    raw = {
        "a": {
            "npm": "@ai-sdk/openai",
            "id": "openai-a",
            "name": "OpenAI A",
            "models": {"m1": {"id": "m1", "name": "Model 1", "tool_call": True}},
        },
        "b": {
            "npm": "@ai-sdk/openai",
            "id": "openai-b",
            "name": "OpenAI B",
            "models": {"m2": {"id": "m2", "name": "Model 2", "tool_call": True}},
        },
    }
    monkeypatch.setattr(interactive_setup, "_fetch_providers", lambda _console: raw)
    monkeypatch.setattr(interactive_setup, "_install_ripgrep", lambda _console: None)
    monkeypatch.setattr(interactive_setup, "_configure_autostart", lambda _console: None)
    monkeypatch.setattr(interactive_setup, "_configure_channels", lambda data, _console: data)

    selected_providers = iter(
        [
            {
                "id": "openai-a",
                "name": "OpenAI A",
                "npm": "@ai-sdk/openai",
                "api": None,
                "models": {},
            },
            {
                "id": "openai-b",
                "name": "OpenAI B",
                "npm": "@ai-sdk/openai",
                "api": None,
                "models": {},
            },
        ]
    )
    monkeypatch.setattr(
        interactive_setup, "_select_provider", lambda _providers, _console: next(selected_providers)
    )

    selected_models = iter([interactive_setup._PROMPT_CTRL_C, ("m2", {"limit": {}})])
    monkeypatch.setattr(
        interactive_setup, "_select_model", lambda _provider, _console: next(selected_models)
    )

    prompts = iter(["sk-test-key"])
    monkeypatch.setattr(
        interactive_setup.typer,
        "prompt",
        lambda *_args, **_kwargs: next(prompts),
    )
    monkeypatch.setattr(interactive_setup.typer, "confirm", lambda _message, default=True: True)

    updated = interactive_setup.interactive_provider_setup(Config(), _make_console())
    assert updated.agents.defaults.provider == "openai-b"
    assert updated.agents.defaults.model == "m2"


def test_configure_channels_skips_on_ctrl_c(monkeypatch):
    monkeypatch.setattr(interactive_setup, "_ensure_fuzzy_mode", lambda: None)
    monkeypatch.setattr(
        interactive_setup,
        "_select_channel_realtime",
        lambda _console: interactive_setup._PROMPT_CTRL_C,
    )
    data: dict = {}
    updated = interactive_setup._configure_channels(data, _make_console())
    assert updated == {}


def test_configure_channels_no_confirm_gate(monkeypatch):
    monkeypatch.setattr(interactive_setup, "_ensure_fuzzy_mode", lambda: None)
    monkeypatch.setattr(interactive_setup, "_select_channel_realtime", lambda _console: 0)
    monkeypatch.setattr(
        interactive_setup.typer,
        "confirm",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("confirm should not be called")
        ),
    )
    monkeypatch.setattr(
        interactive_setup.typer, "prompt", lambda *_args, **_kwargs: "telegram-token"
    )

    data: dict = {}
    updated = interactive_setup._configure_channels(data, _make_console())
    assert updated["channels"]["telegram"]["enabled"] is True
