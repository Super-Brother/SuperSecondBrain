"""Tests for conversation persistence."""

from src.models.conversation import ConversationManager


def test_assistant_message_sources_round_trip(tmp_path):
    manager = ConversationManager(str(tmp_path / "conversations.db"))
    session_id = manager.create_session()
    sources = [
        {
            "title": "快速学习",
            "source": "/vault/快速学习.md",
            "score": 0.82,
        }
    ]

    manager.add_message(session_id, "assistant", "回答内容", metadata={"sources": sources})

    messages = manager.get_history(session_id)
    assert messages[0].metadata == {"sources": sources}
