from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from rolemesh.core.registry_client import Message
import rolemesh.workers.message_worker as mw


def _msg(msg_id: str = "m1") -> Message:
    return Message(
        id=msg_id,
        from_agent="pm",
        to_agent="amp",
        content={"task": "review"},
        status="processing",
        created_at=0,
    )


def test_process_claimed_messages_marks_success_done(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(mw, "_handle", lambda msg, client, agent: (True, "ok"))

    mw._process_claimed_messages(client, "amp", [_msg()])

    client.ack_message.assert_called_once_with("m1", status="done")


def test_process_claimed_messages_marks_handler_error_failed(monkeypatch):
    client = MagicMock()

    def _boom(msg, client, agent):
        raise RuntimeError("handler exploded")

    monkeypatch.setattr(mw, "_handle", _boom)

    mw._process_claimed_messages(client, "amp", [_msg()])

    client.ack_message.assert_called_once_with("m1", status="failed")


def test_recover_stale_messages_resets_only_old_processing(tmp_path):
    from rolemesh.core.registry_client import RegistryClient

    client = RegistryClient(db_path=str(tmp_path / "registry.db"))
    try:
        conn = client._conn_ctx()
        conn.execute(
            """
            INSERT INTO messages (id, from_agent, to_agent, content, status, created_at, processed_at)
            VALUES
            ('stale', 'pm', 'amp', '{}', 'processing', 1, 10),
            ('fresh', 'pm', 'amp', '{}', 'processing', 1, 10000000000),
            ('other', 'pm', 'roki', '{}', 'processing', 1, 10)
            """
        )
        conn.commit()

        recovered = mw._recover_stale_messages(client, "amp", stale_sec=300)

        rows = {
            row["id"]: row["status"]
            for row in conn.execute("SELECT id, status FROM messages").fetchall()
        }
    finally:
        client.close()

    assert recovered == 1
    assert rows["stale"] == "pending"
    assert rows["fresh"] == "processing"
    assert rows["other"] == "processing"


def test_run_loop_survives_claim_exception(monkeypatch):
    client = MagicMock()
    client.claim_pending.side_effect = RuntimeError("db locked")
    monkeypatch.setattr(mw, "RegistryClient", lambda: client)
    monkeypatch.setattr(mw, "_recover_stale_messages", lambda client, agent, stale_sec: 0)

    sleeps: list[int] = []

    def _sleep(sec: int) -> None:
        sleeps.append(sec)
        raise KeyboardInterrupt

    monkeypatch.setattr(mw.time, "sleep", _sleep)

    with pytest.raises(KeyboardInterrupt):
        mw.run_loop(agent="amp", poll=1, stale_sec=60)

    assert sleeps == [1]
