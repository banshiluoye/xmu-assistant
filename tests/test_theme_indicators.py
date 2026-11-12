"""Native checked glyphs and empty frames remain visible in both app themes."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (QApplication, QCheckBox, QStyle, QStyleOptionButton,
    QStyleOptionViewItem, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
import pytest

from test_theme_monochrome import contrast
from xmu_rollcall.desktop_qt.theme import qpalette, stylesheet, ui_colors


def brightest_ink_contrast(image, rect, base):
    # Restrict to the indicator, excluding text labels and table selection.
    return max(contrast(image.pixelColor(x, y).name(), base)
               for x in range(max(0, rect.left()), min(image.width(), rect.right() + 1))
               for y in range(max(0, rect.top()), min(image.height(), rect.bottom() + 1)))


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_checkboxes_and_table_indicators_render_visible_frames_and_ticks(mode, tmp_path):
    app = QApplication.instance() or QApplication([])
    previous_palette, previous_css = QPalette(app.palette()), app.styleSheet()
    app.setStyle("Fusion")
    app.setPalette(qpalette(mode))
    app.setStyleSheet(stylesheet(mode))
    host = QWidget()
    host.resize(420, 280)
    layout = QVBoxLayout(host)
    checks = []
    states = [Qt.CheckState.Unchecked, Qt.CheckState.Checked, Qt.CheckState.PartiallyChecked]
    for state in states:
        check = QCheckBox("状态")
        check.setTristate(True)
        check.setCheckState(state)
        layout.addWidget(check)
        checks.append(check)
    table = QTableWidget(3, 1)
    table.horizontalHeader().hide()
    table.verticalHeader().hide()
    table.setShowGrid(False)
    for row, state in enumerate(states):
        item = QTableWidgetItem("状态")
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(state)
        table.setItem(row, 0, item)
        table.setRowHeight(row, 36)
    layout.addWidget(table)
    host.show()
    try:
        QApplication.processEvents()
        host.grab().save(str(tmp_path / f"indicators-{mode}.png"))
        colors = ui_colors(mode)
        for row, check in enumerate(checks):
            option = QStyleOptionButton()
            check.initStyleOption(option)
            rect = check.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, check)
            assert brightest_ink_contrast(check.grab().toImage(), rect, colors["surface"]) >= 3, (mode, row, "checkbox")
        for row in range(3):
            index = table.model().index(row, 0)
            option = QStyleOptionViewItem()
            option.initFrom(table)
            table.itemDelegate().initStyleOption(option, index)
            option.rect = table.visualRect(index)
            option.widget = table
            rect = table.style().subElementRect(QStyle.SubElement.SE_ItemViewItemCheckIndicator, option, table)
            assert not rect.isEmpty()
            assert brightest_ink_contrast(table.viewport().grab().toImage(), rect, colors["surface"]) >= 3, (mode, row, "table")
    finally:
        host.close()
        app.setPalette(previous_palette)
        app.setStyleSheet(previous_css)
