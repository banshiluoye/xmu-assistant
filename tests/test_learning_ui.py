import os
from dataclasses import replace
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
import pytest
import requests
from xmu_rollcall.courseware import CourseSummary, CoursewareItem
from xmu_rollcall.desktop_qt.app import DashboardWindow
from xmu_rollcall.desktop_qt.homework_window import HomeworkWindow
from xmu_rollcall.learning import LearningStore, LearningTask


@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    with mock.patch.object(DashboardWindow, "_run_thread"), mock.patch.object(DashboardWindow, "auto_restore_current_session"), \
         mock.patch.object(DashboardWindow, "_reconcile_startup_registration", return_value=False), mock.patch.object(DashboardWindow, "_setup_tray"):
        value = DashboardWindow()
        value.runtime_timer.stop()
        value.session = requests.Session()
        value.account = {"id": "test-learning", "rollcall_settings": {"poll_interval_seconds": 45}}
        yield value
        value.quitting = True
        value.close()
        value.deleteLater()
        app.processEvents()


def test_chapter_selects_its_attachments_and_keeps_outline_visible(window):
    course = CourseSummary("1", "示例", window.courseware_academic_year_combo.currentText() + "-1")
    window._set_courseware_courses([course], "fixture")
    window.courseware_combo.blockSignals(True)
    window.courseware_combo.setCurrentText(course.display_name)
    window.courseware_combo.blockSignals(False)
    values = [CoursewareItem("1", str(i), "活动" + str(i), "material", "章节" + str(i), "", str(i), str(i), "文件.pdf", 1, "file", "", "ready", True, chapter_index=i, activity_index=1, module_id=str(i)) for i in (1, 2)]
    window._set_courseware_items(course, values)
    window.courseware_tree.setCurrentItem(window.courseware_tree.topLevelItem(0))
    assert window._selected_courseware_rows() == [0]
    assert window.courseware_tree.topLevelItemCount() == 2
    assert window.courseware_tree.topLevelItem(0).text(0) != "全部课件"
    window.courseware_tree.setCurrentItem(window.courseware_tree.topLevelItem(1))
    assert window._selected_courseware_rows() == [1]


def test_multicourse_filters_and_shared_frequency(window):
    first = LearningTask("1", "a", "A课程", "作业", "homework")
    second = LearningTask("2", "b", "B课程", "测验", "exam")
    window.learning_tasks = {first.key: first, second.key: second}
    window._learning_courses = {"a", "b"}
    window.learning_type.setCurrentIndex(window.learning_type.findData("exam"))
    assert window._filtered_learning_tasks() == [second]
    assert window._learning_interval() == 45
    window.account["rollcall_settings"]["poll_interval_seconds"] = 60
    assert window._learning_interval() == 60


def test_disappeared_todo_is_unknown_not_submitted_and_late_results_are_ignored(window, tmp_path):
    task = LearningTask("1", "a", "A", "作业", "homework")
    window.learning_tasks = {task.key: task}
    window._learning_store = LearningStore("test", tmp_path)
    token = object()
    window._learning_jobs["todos"] = token
    window._ev_learning_result(("learning_result", "todos", window.session, token, {"ok": True, "value": []}))
    assert window.learning_tasks[task.key].status == "待核实"
    window._ev_learning_result(("learning_result", "todos", requests.Session(), token, {"ok": True, "value": [task]}))
    assert window.learning_tasks[task.key].status == "待核实"


def test_disappeared_homework_is_verified_against_course_records(window, tmp_path):
    task = LearningTask("1", "a", "A", "作业", "homework")
    window.learning_tasks = {task.key: task}
    window._learning_store = LearningStore("test-verify", tmp_path)
    token = object()
    window._learning_jobs["todos"] = token
    window._ev_learning_result(("learning_result", "todos", window.session, token, {"ok": True, "value": []}))
    assert window.learning_tasks[task.key].status == "待核实"
    verify_token = window._learning_jobs.get("verify")
    assert verify_token is not None
    window._ev_learning_result((
        "learning_result", "verify", window.session, verify_token,
        {"ok": True, "value": {task.key: "已提交"}},
    ))
    assert window.learning_tasks[task.key].status == "已提交"


def test_stale_todo_payload_does_not_downgrade_confirmed_submission(window):
    task = LearningTask("1", "a", "A", "作业", "homework", status="已提交")
    window.learning_tasks = {task.key: task}
    token = object()
    window._learning_jobs["todos"] = token
    window._ev_learning_result((
        "learning_result", "todos", window.session, token,
        {"ok": True, "value": [replace(task, status="未完成")]},
    ))
    assert window.learning_tasks[task.key].status == "已提交"


def test_verify_is_not_repeated_for_same_course_in_one_session(window, tmp_path):
    task = LearningTask("1", "a", "A", "作业", "homework")
    window.learning_tasks = {task.key: task}
    window._learning_store = LearningStore("test-verify-once", tmp_path)
    token = object()
    window._learning_jobs["todos"] = token
    window._ev_learning_result(("learning_result", "todos", window.session, token, {"ok": True, "value": []}))
    assert "verify" in window._learning_jobs
    window._learning_jobs.pop("verify", None)
    second = object()
    window._learning_jobs["todos"] = second
    window._ev_learning_result(("learning_result", "todos", window.session, second, {"ok": True, "value": []}))
    assert "verify" not in window._learning_jobs


def test_tray_quit_schedules_forced_exit(window):
    window.quitting = False
    window.tray_icon = mock.Mock()
    window.stop_monitor = mock.Mock()
    with mock.patch("xmu_rollcall.desktop_qt.tray.threading.Timer") as timer_cls, \
         mock.patch("xmu_rollcall.desktop_qt.tray.QApplication.quit") as quit_app:
        window._quit_from_tray()
    timer_cls.assert_called_once()
    timer = timer_cls.return_value
    assert timer.daemon is True
    timer.start.assert_called_once()
    window.stop_monitor.assert_called_once()
    window.tray_icon.hide.assert_called_once()
    quit_app.assert_called_once()


def test_editor_keeps_local_draft_and_does_not_submit_on_open(window, tmp_path):
    task = LearningTask("1", "a", "课程", "作业", "homework")
    store = LearningStore("test", tmp_path)
    data = {"detail": {"uploads": [], "data": {"description": "<p>要求</p>"}}, "submission": {"id": None, "uploads": []}, "history": [], "group": False}
    editor = HomeworkWindow(window, task, data, store)
    editor.editor.setPlainText("本地答案")
    editor._save_local()
    editor.draft_writer.flush(5)
    assert "本地答案" in store.read(store.draft_name(task))["html"]
    window._run_thread.assert_not_called()
    editor.invalidate_session()
    assert not editor.submit_button.isEnabled()
    assert editor.editor.isReadOnly()
    editor.close()
