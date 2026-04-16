import asyncio
from pathlib import Path

import pytest

from weavbot.channels.state import ChannelStateStore


@pytest.fixture
def store(tmp_path: Path):
    return ChannelStateStore(path=tmp_path / "channels.json")


def test_get_returns_empty_dict_when_missing(store):
    assert asyncio.run(store.get("telegram", "123")) == {}


def test_set_and_get_round_trip(store):
    asyncio.run(store.set("telegram", "123", {"message_id": 42}))
    assert asyncio.run(store.get("telegram", "123")) == {"message_id": 42}


def test_update_merges_data(store):
    asyncio.run(store.set("wechat", "u1", {"account_key": "a"}))
    asyncio.run(store.update("wechat", "u1", {"context_token": "t1"}))
    assert asyncio.run(store.get("wechat", "u1")) == {"account_key": "a", "context_token": "t1"}


def test_remove_deletes_entry(store):
    asyncio.run(store.set("qq", "456", {"x": 1}))
    assert asyncio.run(store.get("qq", "456")) == {"x": 1}
    asyncio.run(store.remove("qq", "456"))
    assert asyncio.run(store.get("qq", "456")) == {}


def test_persists_to_disk(store):
    asyncio.run(store.set("slack", "c1", {"thread_ts": "99.0"}))
    asyncio.run(store.close())

    store2 = ChannelStateStore(path=store._path)
    assert asyncio.run(store2.get("slack", "c1")) == {"thread_ts": "99.0"}


def test_debounce_does_not_write_immediately(store):
    asyncio.run(store.set("telegram", "1", {"a": 1}))
    assert not store._path.exists()


def test_close_flushes_immediately(store):
    asyncio.run(store.set("telegram", "1", {"a": 1}))
    asyncio.run(store.close())
    assert store._path.exists()
    data = store._path.read_text("utf-8")
    assert '"telegram"' in data


def test_load_handles_corrupted_json(store):
    store._path.parent.mkdir(parents=True, exist_ok=True)
    store._path.write_text("{bad json", encoding="utf-8")
    store2 = ChannelStateStore(path=store._path)
    assert asyncio.run(store2.get("any", "any")) == {}


def test_load_normalizes_invalid_nested_types(store):
    store._path.parent.mkdir(parents=True, exist_ok=True)
    store._path.write_text(
        '{"wecom": {"chat1": "not-a-dict", "chat2": {"ok": true}}}', encoding="utf-8"
    )
    store2 = ChannelStateStore(path=store._path)
    assert asyncio.run(store2.get("wecom", "chat1")) == {}
    assert asyncio.run(store2.get("wecom", "chat2")) == {"ok": True}


def test_load_normalizes_invalid_top_level(store):
    store._path.parent.mkdir(parents=True, exist_ok=True)
    store._path.write_text('["not-a-dict"]', encoding="utf-8")
    store2 = ChannelStateStore(path=store._path)
    assert asyncio.run(store2.get("any", "any")) == {}
