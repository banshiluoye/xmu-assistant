"""The homework workspace keeps one primary action and an attachment-first layout."""
from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication, QPushButton

from test_learning import TASK
from test_learning_ui import window  # noqa: F401
from xmu_rollcall.desktop_qt.homework_window import HomeworkWindow
from xmu_rollcall.learning import LearningStore


def data():
    return {"detail": {"uploads": [{"id": 1, "name": "实验要求.pdf"}], "data": {"description": "<p>提交实验报告与源码。</p>"}},
        "submission": {"id": None, "comment": "", "uploads": [{"id": i, "name": f"附件{i}.pdf"} for i in range(2, 7)]},
        "history": [], "group": False}


def close_editor(editor):
    editor.close()
    editor.draft_writer.flush(5)


def test_homework_header_tools_are_separate_from_commit_actions(window, tmp_path):
    editor = HomeworkWindow(window, TASK, data(), LearningStore("minimal-layout", tmp_path))
    editor.show()
    QApplication.processEvents()
    try:
        def box(widget):
            return QRect(widget.mapTo(editor, QPoint()), widget.size())
        assert box(editor.original_button).bottom() < box(editor.requirement).top()
        assert box(editor.reload_button).bottom() < box(editor.answer_panel).top()
        assert box(editor.draft_button).top() > box(editor.file_list).bottom()
        assert editor.submit_button.objectName() == "PrimaryButton"
        assert editor.draft_button.objectName() == "SecondaryButton"
        assert editor.submit_button.width() < editor.width() / 3
        assert not editor.cancel_button.isVisible()
        assert editor.editor.document().isEmpty()
    finally:
        close_editor(editor)


def test_body_expands_on_request_and_restores_attachment_focus(window, tmp_path):
    editor = HomeworkWindow(window, TASK, data(), LearningStore("body-layout", tmp_path))
    editor.show()
    QApplication.processEvents()
    try:
        original_body = editor.answer_panel.height()
        original_drop = editor.drop_zone.height()
        assert original_body <= 175
        assert original_drop > original_body
        expand = next(button for button in editor.findChildren(QPushButton) if button.text() == "展开正文")
        expand.click()
        QApplication.processEvents()
        assert editor.answer_panel.height() > original_body
        assert editor.drop_zone.height() >= 160
        expand.click()
        QApplication.processEvents()
        assert editor.answer_panel.height() <= 175
        assert editor.drop_zone.height() >= original_drop
        editor._set_busy(True)
        assert editor.cancel_button.isVisible() and editor.cancel_button.isEnabled()
        editor._set_busy(False)
        assert not editor.cancel_button.isVisible()
    finally:
        close_editor(editor)
