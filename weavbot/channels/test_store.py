from pathlib import Path

from weavbot.channels.store import ChannelStore, ChannelTarget


def test_channel_store_upsert_keeps_memory_consistent_when_write_fails(
    tmp_path, monkeypatch
) -> None:
    store = ChannelStore(tmp_path / "channels")
    key = "slack_C111_T333"

    def _boom(self: Path, data: str, encoding: str = "utf-8") -> int:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", _boom)

    store.upsert(
        key,
        ChannelTarget(
            channel="slack",
            chat_id="C111",
            metadata={"slack": {"thread_ts": "T333"}},
        ),
    )

    assert store.resolve(key) is None
    assert not (tmp_path / "channels" / f"{key}.json").exists()
