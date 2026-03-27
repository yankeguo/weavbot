import asyncio

import pytest

from weavbot.channels.store import ChannelEndpoint, ChannelStore


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
        ChannelEndpoint(
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
            ChannelEndpoint(
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


@pytest.mark.asyncio
async def test_most_recent_session_key_prefers_latest_upsert(tmp_path) -> None:
    store = ChannelStore(tmp_path / "channels")
    await store.upsert(
        "slack_older",
        ChannelEndpoint(channel="slack", chat_id="C1", metadata={}),
    )
    await asyncio.sleep(0.02)
    await store.upsert(
        "slack_newer",
        ChannelEndpoint(channel="slack", chat_id="C2", metadata={}),
    )
    assert await store.most_recent_session_key(enabled_channels={"slack"}) == "slack_newer"


@pytest.mark.asyncio
async def test_most_recent_session_key_skips_internal_and_cli(tmp_path) -> None:
    store = ChannelStore(tmp_path / "channels")
    await store.upsert(
        "cron_job1",
        ChannelEndpoint(channel="slack", chat_id="C9", metadata={}),
    )
    await asyncio.sleep(0.02)
    await store.upsert(
        "slack_user",
        ChannelEndpoint(channel="slack", chat_id="C1", metadata={}),
    )
    assert await store.most_recent_session_key(enabled_channels={"slack"}) == "slack_user"
