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
