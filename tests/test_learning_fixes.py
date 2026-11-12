from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock

from PySide6.QtCore import QMimeData, QPoint, QRect, Qt, QUrl
from PySide6.QtWidgets import QApplication, QLabel, QTextEdit
import pytest

from test_learning import TASK, snapshot
from test_learning_ui import window  # noqa: F401
from xmu_rollcall.config import get_rollcall_settings, normalize_rollcall_settings
from xmu_rollcall.courseware import CourseSummary, CoursewareItem
from xmu_rollcall.desktop_qt.course_picker import CoursePicker
from xmu_rollcall.desktop_qt.homework_window import HomeworkWindow
from xmu_rollcall.learning import LearningApi, LearningStore, LearningTask, LOCAL_TZ, SubmissionUncertain
from xmu_rollcall.learning_html import submission_html


def load_resources(window):
    course = CourseSummary("1", "示例", window.courseware_academic_year_combo.currentText() + "-1")
    window._set_courseware_courses([course], "fixture")
    window.courseware_combo.blockSignals(True)
    window.courseware_combo.setCurrentText(course.display_name)
    window.courseware_combo.blockSignals(False)
    resources = [CoursewareItem("1", str(i), "活动" + str(i), "material", "章节" + str(i), "", str(i), str(i), "文件.pdf", 1, "file", "", "ready", True, chapter_index=i, activity_index=1, module_id=str(i)) for i in (1, 2)]
    window._set_courseware_items(course, resources)


def test_empty_qt_document_never_becomes_submission_body(window):
    editor = QTextEdit()
    assert submission_html(editor.toHtml()) == ""
    for value in ("<p><br /></p>", "<p>&nbsp;</p>", "<div>\u200b</div>", "<table><tr><td><br></td></tr></table>"):
        assert submission_html(value) == ""
    assert submission_html('<p><img src="https://example.test/image.png"></p>')


def test_attachment_only_submit_does_not_resend_platform_pdf():
    preview = {"id": 99, "name": "Text content(20261105140901).pdf", "source": "auto-generated-pdf"}
    before = snapshot("<p><br /></p>", record_id=1, uploads=[{"id": 8}, preview])
    after = snapshot("", record_id=2, uploads=[{"id": 8}])
    api = LearningApi(None)
    api.homework = mock.Mock(side_effect=[before, after])
    api.request = mock.Mock(return_value={})
    api.submit(TASK, "<p><br /></p>", [{"id": 8}, preview])
    payload = api.request.call_args.kwargs["json"]
    assert payload["comment"] == ""
    assert payload["uploads"] == [8]


def test_meaningful_body_accepts_platform_preview_but_does_not_hide_user_named_file():
    api = LearningApi(None)
    api.homework = mock.Mock(side_effect=[snapshot(), snapshot("<p>答案</p>", record_id=2, uploads=[{"id": 8}, {"id": 9, "source": "auto-generated-pdf"}])])
    api.request = mock.Mock(return_value={})
    api.submit(TASK, "<p>答案</p>", [{"id": 8, "name": "Text content.pdf", "source": ""}])
    assert api.request.call_args.kwargs["json"]["uploads"] == [8]


def test_empty_body_with_unexpected_generated_pdf_is_not_reported_success():
    api = LearningApi(None)
    api.homework = mock.Mock(side_effect=[snapshot(), snapshot("", record_id=2, uploads=[{"id": 8}, {"id": 9, "source": "auto-generated-pdf"}])])
    api.request = mock.Mock(return_value={})
    with pytest.raises(SubmissionUncertain):
        api.submit(TASK, "", [{"id": 8}])


def test_second_select_all_clears_selection_and_file_checks(window):
    load_resources(window)
    window.select_all_courseware()
    assert window._selected_courseware_rows() == [0, 1]
    window.select_all_courseware()
    assert window._selected_courseware_rows() == []
    assert all(item.checkState(0) == Qt.CheckState.Unchecked for item in window._chapter_leaf_by_key.values())
    assert window.courseware_tree.topLevelItemCount() == 2
    assert not window.courseware_tree.topLevelItem(0).icon(0).isNull()


def test_unchecking_last_file_does_not_fall_back_to_old_row_selection(window):
    load_resources(window)
    chapter = window.courseware_tree.topLevelItem(0)
    window.courseware_tree.setCurrentItem(chapter)
    leaf = chapter.child(0).child(0)
    leaf.setCheckState(0, Qt.CheckState.Checked)
    leaf.setCheckState(0, Qt.CheckState.Unchecked)
    assert window._selected_courseware_rows() == []


def test_filters_do_not_overlap_at_supported_window_widths(window):
    window._show_page(1)
    window.show()
    for width in (1100, 1440):
        window.resize(width, 820)
        QApplication.processEvents()
        controls = [window.academic_year_combo, window.semester_combo, window.time_range_combo]
        boxes = [QRect(item.mapTo(window, QPoint()), item.size()) for item in controls]
        assert all(not first.intersects(second) for index, first in enumerate(boxes) for second in boxes[index + 1:])
        for control in controls:
            label = control.parentWidget().findChild(QLabel)
            label_box = QRect(label.mapTo(window, QPoint()), label.size())
            assert not label_box.intersects(QRect(control.mapTo(window, QPoint()), control.size()))


def test_large_course_picker_is_bounded_searchable_and_retains_selection(window):
    dialog = CoursePicker(window, {str(i): f"课程{i:03d}" for i in range(120)}, set())
    dialog.show()
    QApplication.processEvents()
    assert dialog.height() <= 580
    assert dialog.list.count() == 120
    assert dialog.list.verticalScrollBar().maximum() > 0
    dialog.search.setText("课程119")
    assert sum(not dialog.list.item(row).isHidden() for row in range(120)) == 1
    dialog._toggle_visible(False)
    dialog.accept()
    assert len(dialog.selection) == 119 and "119" not in dialog.selection
    dialog.close()


def test_reminder_default_and_minutes_hours_days_save(window):
    assert get_rollcall_settings({})["learning_reminder_minutes"] == 4320
    assert normalize_rollcall_settings({"learning_reminder_minutes": -1})["learning_reminder_minutes"] == 1
    window._load_rollcall_settings({"rollcall_settings": {"learning_reminder_minutes": 4320}})
    assert window.learning_reminder_spin.value() == 3
    assert window.learning_reminder_unit.currentData() == 1440
    window.learning_reminder_unit.setCurrentIndex(window.learning_reminder_unit.findData(60))
    window.learning_reminder_spin.setValue(2)
    account = {"id": window.account["id"], "rollcall_settings": {}}
    config = {"accounts": [account], "current_account_id": account["id"]}
    with mock.patch("xmu_rollcall.desktop_qt.app.load_config", return_value=config), mock.patch("xmu_rollcall.desktop_qt.app.save_config"):
        window._save_rollcall_strategy_settings()
    assert account["rollcall_settings"]["learning_reminder_minutes"] == 120


def test_three_day_reminder_fires_for_deadline_two_days_away(window, tmp_path):
    task = LearningTask("8", "9", "示例", "临期作业", "homework", (datetime.now(LOCAL_TZ) + timedelta(days=2)).isoformat())
    window.learning_tasks = {task.key: task}
    window._learning_store = LearningStore("test-reminder", tmp_path)
    token = object()
    window._learning_jobs["todos"] = token
    with mock.patch.object(window, "_notify_learning") as notify:
        window._ev_learning_result(("learning_result", "todos", window.session, token, {"ok": True, "value": [task]}))
    notify.assert_called_once()
    assert "临期" in notify.call_args.args[0]


def test_attachment_drop_queues_upload_without_formal_submission(window, tmp_path):
    path = tmp_path / "唯一附件.pdf"
    path.write_bytes(b"fixture")
    data = {"detail": {"uploads": [], "data": {}}, "submission": {"id": None, "uploads": []}, "history": [], "group": False}
    editor = HomeworkWindow(window, TASK, data, LearningStore("drop", tmp_path))
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    event = SimpleNamespace(mimeData=lambda: mime, acceptProposedAction=mock.Mock(), ignore=mock.Mock())
    with mock.patch.object(LearningApi, "submit") as submit:
        editor.drop_zone.dropEvent(event)
    assert editor.pending_files == [str(path.resolve())]
    assert editor.operation == "upload" and editor.busy
    assert editor.file_list.count() == 1
    assert submission_html(editor.editor.toHtml()) == ""
    submit.assert_not_called()
    event.acceptProposedAction.assert_called_once()
    editor.invalidate_session()
    editor.close()
