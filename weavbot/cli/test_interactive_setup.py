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
