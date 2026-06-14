"""Regression checks for the embedded notes UI."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api.static import HTML_TEMPLATE


def test_note_detail_breadcrumb_links_each_folder_level_to_note_list():
    assert "function showNotesFolder(encodedFolder)" in HTML_TEMPLATE
    assert "function renderNoteBreadcrumb(note)" in HTML_TEMPLATE
    assert "showNotesFolder('${encodedPath}')" in HTML_TEMPLATE
    assert '<span class="truncate">${escapeHtml(note.folder)}</span>' not in HTML_TEMPLATE


def test_notes_ui_renders_explorer_tree_with_folder_and_note_nodes():
    assert "function loadNotesTree()" in HTML_TEMPLATE
    assert "function renderNotesTree(nodes" in HTML_TEMPLATE
    assert "function renderNotesTreeNode(node" in HTML_TEMPLATE
    assert "node.type === 'folder'" in HTML_TEMPLATE
    assert "node.type === 'note'" in HTML_TEMPLATE
    assert "toggleNotesTreeFolder(" in HTML_TEMPLATE
    assert "showNoteDetail(encodeURIComponent(node.relative_path))" in HTML_TEMPLATE
    assert "renderNotesEmptyState(" in HTML_TEMPLATE


def test_session_management_ui_includes_rename_archive_and_restore_actions():
    assert "let sessionArchiveFilter = 'active';" in HTML_TEMPLATE
    assert "function setSessionArchiveFilter(filter)" in HTML_TEMPLATE
    assert "function getSessionTitle(s)" in HTML_TEMPLATE
    assert "function renameSession(sessionId)" in HTML_TEMPLATE
    assert "function archiveSession(sessionId)" in HTML_TEMPLATE
    assert "function restoreSession(sessionId)" in HTML_TEMPLATE
    assert "PATCH" in HTML_TEMPLATE
    assert "?archived=" in HTML_TEMPLATE
    assert "确定要删除会话" in HTML_TEMPLATE


def test_new_chat_switches_back_to_chat_view_from_notes_view():
    start = HTML_TEMPLATE.index("async function newChat()")
    end = HTML_TEMPLATE.index("function renderWelcomeMessage()", start)
    new_chat_body = HTML_TEMPLATE[start:end]

    assert "showChatView();" in new_chat_body
    assert "renderWelcomeMessage();" in new_chat_body


def test_notes_search_uses_modal_instead_of_tree_keyword_filter():
    assert 'id="notesSearchModal"' in HTML_TEMPLATE
    assert 'id="notesSearchModalInput"' in HTML_TEMPLATE
    assert "function openNotesSearchModal()" in HTML_TEMPLATE
    assert "function closeNotesSearchModal()" in HTML_TEMPLATE
    assert "async function runNotesModalSearch()" in HTML_TEMPLATE
    assert "function renderNotesSearchResults(" in HTML_TEMPLATE
    assert "function openNoteFromSearch(" in HTML_TEMPLATE

    assert "/api/v1/notes?keyword=" in HTML_TEMPLATE
    assert "/api/v1/notes/keyword-search?q=" in HTML_TEMPLATE

    start = HTML_TEMPLATE.index("async function searchNotes()")
    end = HTML_TEMPLATE.index("function clearNotesFilters()", start)
    search_notes_body = HTML_TEMPLATE[start:end]
    assert "openNotesSearchModal();" in search_notes_body
    assert "setNotesFilter" not in search_notes_body
    assert "notesState.keyword" not in search_notes_body
