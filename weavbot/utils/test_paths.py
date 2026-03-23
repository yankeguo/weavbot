from pathlib import Path

from weavbot.config.loader import get_config_path
from weavbot.config.schema import Config
from weavbot.utils.helpers import ensure_data_path, ensure_workspace_path

DEFAULT_DATA_ROOT = Path("~/.weavbot")


def test_wb_home_defaults_to_home_dot_weavbot(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("WB_DATA_PATH", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert ensure_data_path() == DEFAULT_DATA_ROOT.expanduser()


def test_workspace_path_uses_wb_home_for_relative(monkeypatch, tmp_path: Path):
    wb_home = tmp_path / "wb"
    monkeypatch.setenv("WB_DATA_PATH", str(wb_home))
    assert ensure_workspace_path("workspace") == wb_home / "workspace"
    assert ensure_workspace_path("custom/ws") == wb_home / "custom" / "ws"


def test_workspace_path_keeps_absolute(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("WB_DATA_PATH", str(tmp_path / "wb"))
    absolute = tmp_path / "abs-workspace"
    assert ensure_workspace_path(str(absolute)) == absolute


def test_config_workspace_path_uses_relative_default(monkeypatch, tmp_path: Path):
    wb_home = tmp_path / "wb"
    monkeypatch.setenv("WB_DATA_PATH", str(wb_home))
    cfg = Config.model_validate({})
    assert cfg.agents.defaults.workspace == "workspace"
    assert cfg.workspace_path == wb_home / "workspace"


def test_get_config_path_uses_wb_home(monkeypatch, tmp_path: Path):
    wb_home = tmp_path / "my-home"
    monkeypatch.setenv("WB_DATA_PATH", str(wb_home))
    assert get_config_path() == wb_home / "config.json"
