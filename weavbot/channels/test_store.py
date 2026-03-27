import asyncio

import pytest

from weavbot.channels.store import ChannelStore, ChannelTarget


@pytest.mark.asyncio
async def test_channel_store_upsert_keeps_memory_consistent_when_write_fails(
    tmp_path, monkeypatch
) -> None:
    store = ChannelStore(tmp_path / "channels")
    key = "slack_C111_T333"

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("weavbot.channels.store.aiofiles.open", _boom)

    await store.upsert(
        key,
        ChannelTarget(
            channel="slack",
            chat_id="C111",
            metadata={"slack": {"thread_ts": "T333"}},
        ),
    )

    assert await store.resolve(key) is None
    assert not (tmp_path / "channels" / f"{key}.json").exists()


@pytest.mark.asyncio
async def test_channel_store_concurrent_upsert_and_resolve_same_key(tmp_path) -> None:
    store = ChannelStore(tmp_path / "channels")
    key = "slack_C111_T333"

    async def _write(chat_id: str) -> None:
        await store.upsert(
            key,
            ChannelTarget(
                channel="slack",
                chat_id=chat_id,
                metadata={"slack": {"thread_ts": "T333"}},
            ),
        )

    await asyncio.gather(
        _write("C111"),
        _write("C222"),
        _write("C333"),
    )
    resolved = await store.resolve(key)

    assert resolved is not None
    assert resolved.channel == "slack"
    assert resolved.chat_id in {"C111", "C222", "C333"}
    assert (tmp_path / "channels" / f"{key}.json").exists()
