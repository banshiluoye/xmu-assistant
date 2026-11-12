"""Actual widgets must recover their colors after light/dark round trips."""
from unittest import mock

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QDialog, QDoubleSpinBox, QLabel, QMenu, QMessageBox, QPushButton, QToolTip
import pytest

from test_learning import TASK
from test_learning_fixes import load_resources
from test_learning_ui import window  # noqa: F401
from xmu_rollcall.desktop_qt.homework_window import HomeworkWindow
from xmu_rollcall.desktop_qt.theme import dark_qpalette, light_qpalette, qpalette, ui_colors
from xmu_rollcall.learning import LearningStore
from xmu_rollcall.learning import LearningTask


@pytest.fixture(autouse=True)
def restore_application_theme():
    app = QApplication.instance() or QApplication([])
    palette, tooltip, stylesheet = QPalette(app.palette()), QPalette(QToolTip.palette()), app.styleSheet()
    yield
    app.setPalette(palette)
    QToolTip.setPalette(tooltip)
    app.setStyleSheet(stylesheet)


def test_palettes_are_independent_of_previous_theme_and_cover_state_groups():
    app = QApplication.instance()
    light = light_qpalette()
    app.setPalette(dark_qpalette())
    assert light_qpalette() == light
    for mode in ("light", "dark"):
        app.setPalette(qpalette(mode))
        result = qpalette("light")
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
            for role in QPalette.ColorRole:
                if role not in (QPalette.ColorRole.NoRole, QPalette.ColorRole.NColorRoles):
                    assert result.color(group, role) == light.color(group, role)


def test_theme_roundtrips_update_existing_radar_controls_and_popup_palette(window):
    app = QApplication.instance()
    window._show_page(window.nav_titles.index("雷达坐标"))
    window.show()
    radar_label = next(label for label in window.findChildren(QLabel) if label.text() == "预置地点")
    window.radar_place_list.clear()
    window.radar_place_list.addItem("这门课还没有坐标")
    window.radar_place_list.setCurrentRow(0)
    QApplication.processEvents()
    for mode in ("light", "dark", "light") * 4:
        window._apply_theme(mode)
        QApplication.processEvents()
        colors = ui_colors(mode)
        assert window.radar_place_list.palette().color(QPalette.ColorRole.Base).name() == colors["surface"]
        assert window.radar_place_list.palette().color(QPalette.ColorRole.Text).name() == colors["text"]
        assert radar_label.palette().color(QPalette.ColorRole.WindowText).name() == colors["text"]
        assert app.palette().color(QPalette.ColorRole.Highlight).name() == colors["selected"]
        assert app.palette().color(QPalette.ColorRole.HighlightedText).name() == colors["selected_text"]
        assert QToolTip.palette().color(QPalette.ColorRole.ToolTipBase).name() == colors["surface"]
        assert window.radar_custom_name.palette().color(QPalette.ColorRole.PlaceholderText).name() == colors["placeholder"]
        assert window.radar_place_list.currentRow() == 0


def test_native_popups_and_disabled_controls_recover_after_switch(window):
    dialog, menu, message = QDialog(window), QMenu(window), QMessageBox(window)
    menu.addAction("菜单项")
    message.setText("提示正文")
    label, button, spin = QLabel("不可用", dialog), QPushButton("不可用", dialog), QDoubleSpinBox(dialog)
    label.setEnabled(False)
    button.setEnabled(False)
    for mode in ("light", "dark", "light"):
        window._apply_theme(mode)
        QApplication.processEvents()
        colors = ui_colors(mode)
        for widget in (dialog, menu, message, label, button, spin):
            widget.ensurePolished()
        assert dialog.palette().color(QPalette.ColorRole.WindowText).name() == colors["text"]
        assert menu.palette().color(QPalette.ColorRole.Text).name() == colors["text"]
        assert message.palette().color(QPalette.ColorRole.Window).name() == colors["surface"]
        assert label.palette().color(QPalette.ColorRole.WindowText).name() == colors["disabled"]
        assert button.palette().color(QPalette.ColorRole.ButtonText).name() == colors["disabled"]
        assert spin.palette().color(QPalette.ColorRole.Base).name() == colors["surface"]


def test_open_homework_follows_switch_without_touching_answer_or_attachments(window, tmp_path):
    data = {"detail": {"uploads": [{"id": 1, "name": "要求.pdf"}], "data": {}},
        "submission": {"id": None, "uploads": [{"id": 2, "name": "报告.pdf"}]}, "history": [], "group": False}
    editor = HomeworkWindow(window, TASK, data, LearningStore("theme-editor", tmp_path))
    editor.editor.setPlainText("仍在编辑的答案\n第二行")
    editor.teacher_files.setCurrentRow(0)
    editor.file_list.setCurrentRow(0)
    editor.show()
    try:
        for mode in ("dark", "light", "dark", "light"):
            window._apply_theme(mode)
            QApplication.processEvents()
            colors = ui_colors(mode)
            assert editor.editor.toPlainText() == "仍在编辑的答案\n第二行"
            assert editor.file_list.currentRow() == 0
            assert editor.teacher_files.currentRow() == 0
            assert editor.file_list.palette().color(QPalette.ColorRole.Base).name() == colors["surface"]
            assert editor.teacher_files.palette().color(QPalette.ColorRole.Text).name() == colors["text"]
            assert editor.editor.palette().color(QPalette.ColorRole.Text).name() == colors["text"]
            assert editor.editor.palette().color(QPalette.ColorRole.PlaceholderText).name() == colors["placeholder"]
    finally:
        editor.close()
        editor.draft_writer.flush(5)


def test_theme_switch_preserves_courseware_tree_state_and_existing_rows(window):
    load_resources(window)
    chapter = window.courseware_tree.topLevelItem(0)
    window.courseware_tree.setCurrentItem(chapter)
    chapter.setExpanded(False)
    checkbox = window._chapter_leaf_by_key[window._courseware_key(window.courseware_items[0])]
    from PySide6.QtCore import Qt
    checkbox.setCheckState(0, Qt.CheckState.Checked)
    with mock.patch.object(window, "_refresh_courseware_table", side_effect=AssertionError("theme must not rebuild courseware rows")):
        for mode in ("dark", "light"):
            window._apply_theme(mode)
            QApplication.processEvents()
            assert window._chapter_leaf_by_key[window._courseware_key(window.courseware_items[0])] is checkbox
            assert checkbox.checkState(0) == Qt.CheckState.Checked
            assert window.courseware_tree.currentItem() is chapter
            assert not chapter.isExpanded()


def test_theme_switch_refreshes_learning_status_cells_without_losing_selection(window):
    tasks = [LearningTask(str(index), 'fixture', '课程', f'作业{index}', 'homework', status=status)
             for index, status in enumerate(('未完成', '已提交', '草稿', '待核实'))]
    window.learning_tasks = {task.key: task for task in tasks}
    window._render_learning_tasks()
    window.learning_table.selectRow(1)
    current = window.learning_table.item(1, 0)
    for mode in ('dark', 'light', 'dark'):
        window._apply_theme(mode)
        QApplication.processEvents()
        expected = window._ui_palette()
        assert window.learning_table.item(1, 0) is current
        assert window.learning_table.currentRow() == 1
        for row in range(window.learning_table.rowCount()):
            assert window.learning_table.item(row, 4).background().color().name() == expected['status_signed_bg' if tasks[row].status == '已提交' else 'status_none_bg']
