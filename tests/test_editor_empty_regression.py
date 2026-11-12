"""Qt empty paragraphs stay empty across local draft persistence and restore."""
from unittest import mock

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QTextEdit
import pytest

from test_learning import TASK, snapshot
from test_learning_ui import window  # noqa: F401
from xmu_rollcall.desktop_qt.homework_window import HomeworkWindow
from xmu_rollcall.learning import LearningApi, LearningStore
from xmu_rollcall.learning_html import clean_html, editor_html, submission_html


def homework_data(comment=""):
    return {"detail": {"uploads": [], "data": {}}, "submission": {"id": None, "comment": comment, "uploads": []}, "history": [], "group": False}


def close_editor(editor):
    editor.close()
    editor.draft_writer.flush(5)


@pytest.mark.parametrize("answer", ["", "答案\n\n第二段", "\n答案\n", "第一行\n第二行\n\n\n末行"])
def test_qt_html_roundtrip_preserves_empty_blocks_and_intentional_newlines(window, answer):
    edit = QTextEdit()
    edit.setPlainText(answer)
    for _ in range(4):
        cleaned = clean_html(edit.toHtml())
        edit.setHtml(cleaned)
        assert edit.toPlainText() == answer
        assert edit.document().isEmpty() == (answer == "")


@pytest.mark.parametrize("blank", ["", "\n\n", "<p><br></p>", "\n\n<p><br></p>\n<p><br></p>", "<p>&nbsp;</p>", "<div>\u200b\ufeff</div>"])
def test_legacy_blank_draft_opens_as_a_genuinely_empty_editor(window, tmp_path, blank):
    store = LearningStore("empty-legacy", tmp_path)
    store.write(store.draft_name(TASK), {"html": blank, "uploads": [{"id": 3, "name": "报告.pdf"}]})
    editor = HomeworkWindow(window, TASK, homework_data(), store)
    try:
        assert editor.editor.toPlainText() == ""
        assert editor.editor.document().isEmpty()
        assert editor.editor.textCursor().position() == 0
        assert editor.editor.placeholderText()
        assert editor.file_list.count() == 1
        assert submission_html(editor.editor.toHtml()) == ""
        window._run_thread.assert_not_called()
    finally:
        close_editor(editor)


def test_platform_empty_comment_opens_without_phantom_newline(window, tmp_path):
    editor = HomeworkWindow(window, TASK, homework_data("<p><br></p>"), LearningStore("platform-empty", tmp_path))
    try:
        assert editor.editor.document().isEmpty()
        assert editor.editor.toPlainText() == ""
    finally:
        close_editor(editor)


def test_typing_newlines_is_untouched_and_new_answer_survives_disk_restore(window, tmp_path):
    store = LearningStore("real-answer", tmp_path)
    editor = HomeworkWindow(window, TASK, homework_data(), store)
    editor.editor.insertPlainText("\n\n")
    assert editor.editor.toPlainText() == "\n\n"
    answer = "\n答案第一段\n\n答案第二段\n"
    editor.editor.setPlainText(answer)
    editor.editor.selectAll()
    editor.editor.setFontWeight(QFont.Weight.Bold)
    close_editor(editor)
    restored = HomeworkWindow(window, TASK, homework_data(), store)
    try:
        assert restored.editor.toPlainText() == answer
        cursor = restored.editor.textCursor()
        cursor.setPosition(1)
        cursor.movePosition(cursor.MoveOperation.NextCharacter, cursor.MoveMode.KeepAnchor)
        assert cursor.charFormat().fontWeight() >= QFont.Weight.Bold
    finally:
        close_editor(restored)


def test_image_only_draft_remains_real_content(window, tmp_path):
    store = LearningStore("image-draft", tmp_path)
    image = '<p><img src="https://example.test/figure.png" alt="图"></p>'
    store.write(store.draft_name(TASK), {"html": image})
    with mock.patch("xmu_rollcall.desktop_qt.homework_window.LearningApi") as api:
        editor = HomeworkWindow(window, TASK, homework_data(), store)
    try:
        assert not editor.editor.document().isEmpty()
        assert "\ufffc" in editor.editor.toPlainText()
        assert "figure.png" in submission_html(editor.editor.toHtml())
        api.assert_not_called()
    finally:
        close_editor(editor)


def test_empty_paragraph_marker_does_not_allow_other_qt_css(window):
    html = clean_html('<p style="-qt-paragraph-type:empty;-qt-user-state:10;background-image:url(https://example.test/image)"><br></p>')
    assert '-qt-paragraph-type:empty' in html
    assert '-qt-user-state' not in html and 'background-image' not in html


def test_native_empty_paragraphs_restore_without_adding_soft_breaks(window, tmp_path):
    answer = '<p style="-qt-paragraph-type:empty"><br></p><p><b>答案</b></p><p style="-qt-paragraph-type:empty"><br></p><p>第二段</p><p style="-qt-paragraph-type:empty"><br></p>'
    editor = HomeworkWindow(window, TASK, homework_data(answer), LearningStore("platform-paragraphs", tmp_path))
    try:
        assert editor.editor.toPlainText() == "\n答案\n\n第二段\n"
        assert '<b>答案</b>' in editor_html(answer)
    finally:
        close_editor(editor)


@pytest.mark.parametrize("soft_breaks", [1, 2])
def test_soft_breaks_inside_an_empty_paragraph_are_not_guessed_away(window, soft_breaks):
    original = QTextEdit()
    original.setPlainText("开始\n" + "\u2028" * soft_breaks + "\n结束")
    restored = QTextEdit()
    restored.setHtml(editor_html(clean_html(original.toHtml())))
    assert restored.toPlainText() == original.toPlainText()


def test_platform_submission_receipt_does_not_depend_on_qt_private_styles(window):
    editor = QTextEdit()
    editor.setPlainText("答案\n\n第二段")
    raw = editor.toHtml()
    canonical = submission_html(raw)
    assert "-qt-paragraph-type" in clean_html(raw)
    assert "-qt-paragraph-type" not in canonical
    api = LearningApi(None)
    api.homework = mock.Mock(side_effect=[snapshot(), snapshot(canonical, record_id=2)])
    api.request = mock.Mock(return_value={})
    receipt = api.submit(TASK, raw, [])
    assert api.request.call_args.kwargs["json"]["comment"] == canonical
    assert receipt["submission"]["id"] == 2
