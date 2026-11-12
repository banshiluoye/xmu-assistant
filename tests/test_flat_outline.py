"""Behavioral coverage for the table-backed chapter disclosure replacement."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QStyledItemDelegate

from xmu_rollcall.desktop_qt.flat_outline import FlatOutlineItem, FlatOutlineWidget


@pytest.fixture
def outline():
    app = QApplication.instance() or QApplication([])
    widget = FlatOutlineWidget()
    widget.resize(900, 600)
    chapter = FlatOutlineItem(widget.invisibleRootItem(), ["章节"])
    activity = FlatOutlineItem(chapter, ["课件活动"])
    leaf = FlatOutlineItem(activity, ["课件.pdf", "PDF", "可下载"])
    other = FlatOutlineItem(widget, ["另一个章节"])
    FlatOutlineItem(other, ["附件.zip", "ZIP"])
    for node in (chapter, activity, leaf, other, other.child(0)):
        node.setCheckState(0, Qt.CheckState.Unchecked)
        for column in range(3):
            node.setSizeHint(column, QSize(0, 44))
    widget.expandToDepth(1)
    widget.commit()
    widget.show()
    app.processEvents()
    yield widget, chapter, activity, leaf
    widget.close()
    widget.deleteLater()
    app.processEvents()


def test_commit_builds_flat_native_rows_and_retains_logical_data(outline):
    widget, chapter, activity, leaf = outline
    assert widget.topLevelItemCount() == 2
    assert widget.topLevelItem(0) is chapter
    assert activity.parent() is chapter
    assert leaf.parent() is activity
    assert widget.rowCount() == 5
    assert widget.item(2, 0).text() == "课件.pdf"
    assert widget.item(2, 1).text() == "PDF"
    assert widget.item(2, 2).text() == "可下载"
    assert type(widget.itemDelegate()) is QStyledItemDelegate
    assert widget.rowHeight(2) == 44
    assert "第 3 层" in widget.item(2, 0).data(Qt.ItemDataRole.AccessibleTextRole)


def test_disclosure_preserves_rows_model_selection_and_nested_state(outline):
    widget, chapter, activity, leaf = outline
    changed = QSignalSpy(widget.outlineItemChanged)
    current = QSignalSpy(widget.outlineCurrentItemChanged)
    inserted, removed = QSignalSpy(widget.model().rowsInserted), QSignalSpy(widget.model().rowsRemoved)
    reset = QSignalSpy(widget.model().modelReset)
    cells = [widget.item(row, 0) for row in range(widget.rowCount())]
    for _ in range(20):
        widget.toggleNode(chapter)
        assert widget.isRowHidden(1) and widget.isRowHidden(2)
        widget.toggleNode(chapter)
        assert not widget.isRowHidden(1) and not widget.isRowHidden(2)
    activity.setExpanded(False)
    chapter.setExpanded(False)
    chapter.setExpanded(True)
    assert not widget.isRowHidden(1) and widget.isRowHidden(2)
    assert cells == [widget.item(row, 0) for row in range(widget.rowCount())]
    assert changed.count() == current.count() == 0
    assert inserted.count() == removed.count() == reset.count() == 0
    assert "已展开" in widget.item(0, 0).data(Qt.ItemDataRole.AccessibleTextRole)


def test_arrow_click_does_not_select_or_check_a_directory(outline):
    widget, chapter, _activity, _leaf = outline
    changed = QSignalSpy(widget.outlineItemChanged)
    current = QSignalSpy(widget.outlineCurrentItemChanged)
    QTest.mouseClick(widget.viewport(), Qt.MouseButton.LeftButton, pos=widget.disclosureRect(chapter).center())
    QApplication.processEvents()
    assert not chapter.isExpanded()
    assert chapter.checkState(0) == Qt.CheckState.Unchecked
    assert changed.count() == current.count() == 0


def test_native_checks_and_node_status_changes_emit_compatible_signals(outline):
    widget, chapter, _activity, leaf = outline
    changed = QSignalSpy(widget.outlineItemChanged)
    leaf.setCheckState(0, Qt.CheckState.Checked)
    assert widget.item(2, 0).checkState() == Qt.CheckState.Checked
    assert changed.count() == 1 and changed.at(0) == [leaf, 0]
    widget.item(0, 0).setCheckState(Qt.CheckState.Checked)
    assert chapter.checkState(0) == Qt.CheckState.Checked
    assert changed.count() == 2 and changed.at(1) == [chapter, 0]
    leaf.setText(2, "下载成功")
    assert widget.item(2, 2).text() == "下载成功"
    assert changed.at(2) == [leaf, 2]
    widget.blockSignals(True)
    leaf.setCheckState(0, Qt.CheckState.Unchecked)
    widget.blockSignals(False)
    assert changed.count() == 3


def test_keyboard_moves_focus_expands_checks_and_activates_leaf(outline):
    widget, chapter, activity, leaf = outline
    widget.setCurrentItem(chapter)
    QTest.keyClick(widget, Qt.Key.Key_Left)
    assert not chapter.isExpanded()
    QTest.keyClick(widget, Qt.Key.Key_Right)
    assert chapter.isExpanded()
    QTest.keyClick(widget, Qt.Key.Key_Right)
    assert widget.currentItem() is activity
    widget.setCurrentItem(leaf)
    activated = QSignalSpy(widget.outlineItemDoubleClicked)
    QTest.keyClick(widget, Qt.Key.Key_Space)
    assert leaf.checkState(0) == Qt.CheckState.Checked
    QTest.keyClick(widget, Qt.Key.Key_Return)
    assert activated.count() == 1 and activated.at(0) == [leaf, 0]
    chapter.setExpanded(False)
    assert widget.currentItem() is chapter
    widget.setCurrentItem(None)
    assert widget.currentItem() is None


def test_mouse_checkbox_hit_area_matches_indentation(outline):
    widget, _chapter, activity, _leaf = outline
    # The native check box sits just after the custom indentation/disclosure.
    rect = widget.visualItemRect(activity)
    x = rect.left() + activity._depth * widget.indentation() + widget._disclosure_width + 10
    QTest.mouseClick(widget.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(x, rect.center().y()))
    QApplication.processEvents()
    assert activity.checkState(0) == Qt.CheckState.Checked
    assert activity.isExpanded()


def test_clear_disowns_old_nodes_and_allows_another_commit(outline):
    widget, chapter, _activity, _leaf = outline
    widget.clear()
    assert widget.rowCount() == widget.topLevelItemCount() == 0
    chapter.setText(0, "旧节点")
    fresh = FlatOutlineItem(widget, ["新章节"])
    FlatOutlineItem(fresh, ["新文件"])
    widget.expandAll()
    widget.commit()
    assert widget.rowCount() == 2 and widget.item(0, 0).text() == "新章节"
    assert not widget.isRowHidden(1)


def test_hidden_node_can_be_selected_and_keeps_updates_when_opened():
    app = QApplication.instance() or QApplication([])
    widget = FlatOutlineWidget()
    chapter = FlatOutlineItem(widget, ["章节"])
    activity = FlatOutlineItem(chapter, ["活动"])
    leaf = FlatOutlineItem(activity, ["附件.pdf", "PDF", "可下载"])
    leaf.setCheckState(0, Qt.CheckState.Unchecked)
    widget.expandToDepth(0)
    widget.commit()
    assert widget.isRowHidden(2) and widget.item(2, 0) is None
    leaf.setText(2, "下载成功")
    leaf.setCheckState(0, Qt.CheckState.Checked)
    widget.setCurrentItem(leaf)
    assert widget.currentItem() is leaf
    activity.setExpanded(True)
    assert widget.item(2, 2).text() == "下载成功"
    assert widget.item(2, 0).checkState() == Qt.CheckState.Checked
    widget.close()
    widget.deleteLater()
    app.processEvents()
