"""Large-outline selection and autosave must leave the Qt event loop usable."""
from threading import Event
from time import perf_counter
from unittest import mock
import pytest

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtWidgets import QApplication

from test_learning import TASK
from test_learning_fixes import load_resources
from test_learning_ui import window  # noqa: F401
from xmu_rollcall.courseware import CourseSummary
from xmu_rollcall.desktop_qt.course_picker import CoursePicker
from xmu_rollcall.desktop_qt.homework_window import HomeworkWindow
from xmu_rollcall.desktop_qt.ui_components import file_icon_kind, resource_icon
from xmu_rollcall.draft_writer import DraftWriter
from xmu_rollcall.learning import LearningStore, LearningTask


def homework_data():
    return {"detail": {"uploads": [{"id": 1, "name": "要求.pdf"}], "data": {}},
        "submission": {"id": None, "uploads": [{"id": i, "name": f"附件{i}.pdf"} for i in range(2, 7)]},
        "history": [], "group": False}


def test_progress_keeps_rows_checks_and_current_directory(window):
    load_resources(window)
    tree = window.courseware_tree
    chapter = tree.topLevelItem(0)
    tree.setCurrentItem(chapter)
    key = window._courseware_key(window.courseware_items[0])
    leaf = window._chapter_leaf_by_key[key]
    before = window._selected_courseware_rows()
    with mock.patch.object(window, "_refresh_courseware_table", side_effect=AssertionError("progress must not rebuild the table")):
        for _ in range(100):
            window._ev_courseware_download_progress(("courseware_download_progress", 1, 2, "文件.pdf", key))
        window._ev_courseware_download_item_done(("courseware_download_item_done", key, "下载成功"))
    assert window._chapter_leaf_by_key[key] is leaf
    assert tree.currentItem() is chapter
    assert window._selected_courseware_rows() == before
    assert window._chapter_leaf_by_key[key].text(2) == "下载成功"


def test_reload_preserves_checked_file_with_one_final_outline_sync(window):
    load_resources(window)
    course = window._selected_courseware_course()
    items = list(window.courseware_items)
    window._chapter_leaf_by_key[window._courseware_key(items[0])].setCheckState(0, Qt.CheckState.Checked)
    with mock.patch.object(window, "_sync_chapter_tree", wraps=window._sync_chapter_tree) as sync:
        window._set_courseware_items(course, list(reversed(items)))
    assert sync.call_count == 1
    assert window._selected_courseware_rows() == [1]
    assert not hasattr(window, "courseware_table")
    leaf = window._chapter_leaf_by_key[window._courseware_key(items[0])]
    assert leaf.checkState(0) == Qt.CheckState.Checked


def test_reload_selection_and_removed_check_follow_file_identity(window):
    load_resources(window)
    course = window._selected_courseware_course()
    first, second = window.courseware_items
    window.courseware_tree.setCurrentItem(window.courseware_tree.topLevelItem(0))
    window._set_courseware_items(course, [second, first])
    assert window._selected_courseware_rows() == [1]
    with mock.patch.object(window, "_start_courseware_download") as download:
        window.activate_selected_courseware()
    download.assert_called_once_with([first])
    window._chapter_leaf_by_key[window._courseware_key(first)].setCheckState(0, Qt.CheckState.Checked)
    with mock.patch.object(window, "_start_courseware_download") as download:
        window.download_selected_courseware()
    download.assert_called_once_with([first])
    window._set_courseware_items(course, [second])
    assert window._selected_courseware_rows() == []


def test_switch_course_drops_selection_before_new_data_arrives(window):
    load_resources(window)
    old = window.courseware_items[0]
    window._chapter_leaf_by_key[window._courseware_key(old)].setCheckState(0, Qt.CheckState.Checked)
    other = CourseSummary("other", "其他课程", window.courseware_academic_year_combo.currentText() + "-1")
    window._set_courseware_courses([window._selected_courseware_course(), other], "fixture")
    window.courseware_combo.setCurrentText(other.display_name)
    assert window.courseware_items == []
    assert window._selected_courseware_rows() == []
    assert not window._courseware_checked_keys


def test_manual_parent_checks_propagate_and_become_partial(window):
    load_resources(window)
    # Merge both resources into one chapter, preserving two activities.
    from dataclasses import replace
    window.courseware_items = [replace(item, module_id="same", module_name="同一章节") for item in window.courseware_items]
    window._refresh_courseware_table()
    window._rebuild_courseware_tree()
    chapter = window.courseware_tree.topLevelItem(0)
    chapter.setCheckState(0, Qt.CheckState.Checked)
    assert window._selected_courseware_rows() == [0, 1]
    chapter.child(0).child(0).setCheckState(0, Qt.CheckState.Unchecked)
    assert chapter.checkState(0) == Qt.CheckState.PartiallyChecked
    assert window._selected_courseware_rows() == [1]
    chapter.setCheckState(0, Qt.CheckState.Unchecked)
    assert window._selected_courseware_rows() == []


@pytest.mark.parametrize("with_section", [False, True])
def test_large_collapsed_activity_materializes_checked_and_updated_files(window, with_section):
    from dataclasses import replace
    load_resources(window)
    course = window._selected_courseware_course()
    sample = window.courseware_items[0]
    items = [replace(sample, upload_id=str(i), reference_id=str(i), activity_id=str(i // 10),
                     activity_title=f"活动 {i // 10}", module_id="one", module_name="章节",
                     syllabus_name="小节" if with_section else "", syllabus_id="section" if with_section else "")
             for i in range(201)]
    window._set_courseware_items(course, items)
    tree = window.courseware_tree
    parent = tree.topLevelItem(0).child(0)
    if with_section:
        assert parent.isExpanded()
    activity = parent.child(0) if with_section else parent
    leaf = activity.child(0)
    row = tree._row_by_node[leaf]
    assert not activity.isExpanded() and tree.isRowHidden(row)
    assert tree.item(row, 0) is None
    window.select_all_courseware()
    key = window._courseware_key(items[0])
    window.courseware_download_status[key] = "下载成功"
    window._update_courseware_status(key)
    assert leaf.checkState(0) == Qt.CheckState.Checked
    activity.setExpanded(True)
    assert not tree.isRowHidden(row)
    assert tree.item(row, 0).checkState() == Qt.CheckState.Checked
    assert tree.item(row, 2).text() == "下载成功"
    assert len(window._selected_courseware_rows()) == 201


def test_course_picker_retains_platform_order_instead_of_alphabetizing(window):
    term = window.courseware_academic_year_combo.currentText() + "-1"
    courses = [CourseSummary(str(i), title, term) for i, title in enumerate(["Z课程", "B课程", "A课程"])]
    window._set_courseware_courses(courses, "fixture")
    task = LearningTask("old", "other", "旧课程", "任务", "homework")
    window.learning_tasks = {task.key: task}
    names = window._learning_course_names()
    picker = CoursePicker(window, names, set())
    assert [picker.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(picker.list.count())] == ["0", "1", "2", "other"]
    picker.close()


def test_slow_autosave_does_not_block_events_and_keeps_latest_snapshot(window, tmp_path):
    store = LearningStore("slow-disk", tmp_path)
    editor = HomeworkWindow(window, TASK, homework_data(), store)
    started, release = Event(), Event()
    original_write = store.write
    writes = []
    def slow_write(name, snapshot):
        writes.append(snapshot["html"])
        started.set()
        assert release.wait(5)
        original_write(name, snapshot)
    try:
        with mock.patch.object(store, "write", side_effect=slow_write):
            editor.editor.setPlainText("第一版")
            start = perf_counter()
            editor._save_local()
            assert perf_counter() - start < 0.5
            assert started.wait(3)
            events = []
            QTimer.singleShot(0, lambda: events.append("responsive"))
            QApplication.processEvents()
            assert events == ["responsive"]
            editor.editor.setPlainText("第二版")
            editor._save_local()
            editor.editor.setPlainText("最终版本")
            editor._save_local()
            release.set()
            editor.draft_writer.flush(5)
        saved = store.read(store.draft_name(TASK))
        assert "最终版本" in saved["html"]
        assert len(writes) == 2
    finally:
        release.set()
        editor.draft_writer.flush(5)
        editor.close()
        editor.draft_writer.flush(5)


def test_writer_recovers_after_error_and_reports_it(tmp_path):
    store = LearningStore("writer-errors", tmp_path)
    errors = []
    writer = DraftWriter(store, "draft", errors.append)
    with mock.patch.object(store, "write", side_effect=OSError("disk")):
        writer.save({"html": "<p>初稿</p>"})
        writer.flush(5)
    assert len(errors) == 1
    writer.save({"html": "<p>重试</p>"})
    writer.flush(5)
    assert "重试" in store.read("draft")["html"]


def test_homework_panels_align_and_lists_fit_three_files(window, tmp_path):
    editor = HomeworkWindow(window, TASK, homework_data(), LearningStore("layout", tmp_path))
    editor.show()
    def box(widget):
        return QRect(widget.mapTo(editor, QPoint()), widget.size())
    for width, height in [(960, 790), (1180, 900)]:
        editor.resize(width, height)
        QApplication.processEvents()
        assert box(editor.requirement).top() == box(editor.answer_panel).top()
        assert box(editor.requirement).bottom() == box(editor.drop_zone).bottom()
        assert box(editor.teacher_files).top() == box(editor.file_list).top()
        assert box(editor.teacher_files).bottom() == box(editor.file_list).bottom()
        assert editor.file_list.viewport().rect().contains(editor.file_list.visualItemRect(editor.file_list.item(2)))
        assert editor.file_list.visualItemRect(editor.file_list.item(3)).top() >= editor.file_list.viewport().height()
        assert editor.drop_zone.height() >= 160
    editor.close()
    editor.draft_writer.flush(5)


def test_reopening_homework_reuses_editor_with_unsaved_content(window, tmp_path):
    editor = HomeworkWindow(window, TASK, homework_data(), LearningStore("reuse", tmp_path))
    editor.editor.setPlainText("保留正在编辑的内容")
    window._homework_windows.append(editor)
    editor.close()
    with mock.patch.object(window, "_selected_learning_task", return_value=TASK), mock.patch.object(window, "_start_learning_job") as job:
        window.open_learning_task()
    job.assert_not_called()
    assert editor.isVisible()
    assert editor.editor.toPlainText() == "保留正在编辑的内容"
    editor.close()
    editor.draft_writer.flush(5)


def test_selected_icon_subset_has_type_coverage_and_real_assets(window):
    from xmu_rollcall.desktop_qt.icons import app_asset_path
    types = {"a.PDF": "pdf", "a.docx": "word", "a.xlsx": "table", "a.pptx": "powerpoint", "a.zip": "zip",
        "a.png": "image", "a.mp4": "video", "a.mp3": "audio", "a.py": "python", "a.ipynb": "jupyter", "a.cpp": "xml", "a.unknown": "document"}
    for name, kind in types.items():
        assert file_icon_kind(name) == kind
        assert app_asset_path(f"file_icons/{kind}-24.png").is_file()
        assert not resource_icon(kind).pixmap(24, 24).isNull()
        icon = resource_icon(kind)
        assert icon.pixmap(24, 24, mode=icon.Mode.Normal).toImage() == icon.pixmap(24, 24, mode=icon.Mode.Selected).toImage()
    folder = resource_icon("folder")
    assert folder.pixmap(24, 24, state=folder.State.Off).toImage() != folder.pixmap(24, 24, state=folder.State.On).toImage()
