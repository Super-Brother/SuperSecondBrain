"""Tests for conversation persistence."""

from concurrent.futures import ThreadPoolExecutor

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


def test_session_title_generated_from_first_user_message(tmp_path):
    manager = ConversationManager(str(tmp_path / "conversations.db"))
    session_id = manager.create_session()

    manager.add_message(session_id, "user", "  如何设计 RAG 会话管理？  ")

    session = manager.list_sessions()[0]
    assert session["title"] == "如何设计 RAG 会话管理"


def test_manual_title_is_not_overwritten_by_later_user_message(tmp_path):
    manager = ConversationManager(str(tmp_path / "conversations.db"))
    session_id = manager.create_session()

    manager.rename_session(session_id, "我的项目规划")
    manager.add_message(session_id, "user", "这条消息不应该覆盖标题")

    session = manager.list_sessions()[0]
    assert session["title"] == "我的项目规划"


def test_archive_filter_and_restore_session(tmp_path):
    manager = ConversationManager(str(tmp_path / "conversations.db"))
    session_id = manager.create_session()
    manager.add_message(session_id, "user", "归档测试")

    manager.archive_session(session_id)

    assert manager.list_sessions() == []
    archived = manager.list_sessions(archived=True)
    assert len(archived) == 1
    assert archived[0]["session_id"] == session_id
    assert archived[0]["archived_at"] is not None

    manager.restore_session(session_id)

    assert manager.list_sessions()[0]["session_id"] == session_id
    assert manager.list_sessions(archived=True) == []


def test_conversation_manager_supports_background_thread_access(tmp_path):
    manager = ConversationManager(str(tmp_path / "conversations.db"))
    session_id = manager.create_session()

    def add_and_read():
        manager.add_message(session_id, "user", "飞书后台线程消息")
        return manager.get_history(session_id)

    with ThreadPoolExecutor(max_workers=1) as executor:
        messages = executor.submit(add_and_read).result()

    assert messages[0].content == "飞书后台线程消息"
