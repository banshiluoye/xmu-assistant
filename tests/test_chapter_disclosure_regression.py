from unittest import mock

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QStyledItemDelegate

from test_learning_fixes import load_resources
from test_learning_ui import window  # noqa: F401


def test_disclosure_clicks_keep_event_loop_alive_without_model_mutations(window):
    load_resources(window)
    window._show_page(2)
    window.show()
    tree = window.courseware_tree
    chapter = tree.topLevelItem(0)
    changes = QSignalSpy(tree.outlineItemChanged)
    current = QSignalSpy(tree.outlineCurrentItemChanged)
    expanded, collapsed = QSignalSpy(tree.outlineExpanded), QSignalSpy(tree.outlineCollapsed)
    first_cell = tree.item(0, 0)
    QApplication.processEvents()
    with mock.patch.object(window, "_refresh_courseware_table", side_effect=AssertionError("disclosure must not rebuild the table")), \
         mock.patch.object(window, "_sync_chapter_tree", side_effect=AssertionError("disclosure must not rescan checks")):
        for _ in range(60):
            before = chapter.isExpanded()
            tree.scrollToItem(chapter)
            rect = tree.disclosureRect(chapter)
            QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton,
                pos=rect.center())
            QApplication.processEvents()
            assert chapter.isExpanded() != before
            assert tree.item(0, 0) is first_cell
    assert expanded.count() == collapsed.count() == 30
    assert changes.count() == current.count() == 0


def test_outline_uses_flat_native_model_and_cached_heights(window):
    load_resources(window)
    tree = window.courseware_tree
    assert isinstance(tree.itemDelegateForIndex(tree.model().index(0, 1)), QStyledItemDelegate)
    # The visual file row is a root-level table index, while logical ancestry
    # remains available through the outline nodes.
    assert not tree.model().index(2, 0).parent().isValid()
    chapter = tree.topLevelItem(0)
    activity = chapter.child(0)
    leaf = activity.child(0)
    for item, height in [(chapter, 54), (activity, 44), (leaf, 38)]:
        assert all(item.sizeHint(column).height() == height for column in range(3))
