from pathlib import Path

from weavbot.channels.wechat.accounts import (
    list_account_credentials,
    load_sync_buf,
    save_account_credentials,
    save_sync_buf,
)


def test_sync_buf_round_trip(tmp_path: Path):
    save_sync_buf(tmp_path, "acc-a", "cursor-1")
    assert load_sync_buf(tmp_path, "acc-a") == "cursor-1"


def test_load_sync_buf_handles_invalid_json(tmp_path: Path):
    path = tmp_path / "acc-a.sync.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{bad json", encoding="utf-8")
    assert load_sync_buf(tmp_path, "acc-a") == ""


def test_load_sync_buf_handles_non_string_value(tmp_path: Path):
    path = tmp_path / "acc-a.sync.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"get_updates_buf": 123}', encoding="utf-8")
    assert load_sync_buf(tmp_path, "acc-a") == ""


def test_list_account_credentials_skips_bad_files(tmp_path: Path):
    save_account_credentials(
        tmp_path,
        "acc-a",
        account_id="a@im.bot",
        token="token-a",
        user_id="u-a",
    )
    bad = tmp_path / "accounts" / "bad.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{oops", encoding="utf-8")

    rows = list_account_credentials(tmp_path)
    assert rows == [
        {
            "key": "acc-a",
            "account_id": "a@im.bot",
            "user_id": "u-a",
        }
    ]
