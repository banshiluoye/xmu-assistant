"""Bounded, searchable multi-course selection instead of a screen-filling menu."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QVBoxLayout)
from .ui_components import QuietItemDelegate


class CoursePicker(QDialog):
    def __init__(self, parent, courses, selected):
        super().__init__(parent)
        self.setObjectName("CoursePicker")
        self.setWindowTitle("选择课程")
        self.resize(460, 480)
        self.setMinimumSize(380, 360)
        self.setMaximumSize(620, 580)
        self.courses = dict(courses)
        self.selection = set(selected)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        self.search = QLineEdit()
        self.search.setPlaceholderText("输入课程名筛选")
        self.search.setAccessibleName("搜索课程")
        layout.addWidget(self.search)
        row = QHBoxLayout()
        self.select_visible = QCheckBox("全选当前结果")
        self.count = QLabel()
        row.addWidget(self.select_visible)
        row.addStretch()
        row.addWidget(self.count)
        layout.addLayout(row)
        self.list = QListWidget()
        self.list.setItemDelegate(QuietItemDelegate(self.list))
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for course_id, title in courses.items():
            item = QListWidgetItem(title, self.list)
            item.setData(Qt.ItemDataRole.UserRole, course_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if not selected or course_id in selected else Qt.CheckState.Unchecked)
            item.setToolTip(title)
        layout.addWidget(self.list, 1)
        actions = QHBoxLayout()
        all_courses = QPushButton("全部课程")
        cancel = QPushButton("取消")
        self.apply_button = QPushButton("应用筛选")
        self.apply_button.setObjectName("PrimaryButton")
        all_courses.clicked.connect(self._all_courses)
        cancel.clicked.connect(self.reject)
        self.apply_button.clicked.connect(self.accept)
        actions.addWidget(all_courses)
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(self.apply_button)
        layout.addLayout(actions)
        self.search.textChanged.connect(self._filter)
        self.select_visible.clicked.connect(self._toggle_visible)
        self.list.itemChanged.connect(lambda *_: self._update_count())
        self._update_count()

    def _filter(self, text):
        for row in range(self.list.count()):
            item = self.list.item(row)
            item.setHidden(text.casefold() not in item.text().casefold())
        self._update_count()

    def _toggle_visible(self, checked):
        self.list.blockSignals(True)
        for row in range(self.list.count()):
            item = self.list.item(row)
            if not item.isHidden():
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.list.blockSignals(False)
        self._update_count()

    def _update_count(self):
        checked = sum(self.list.item(row).checkState() == Qt.CheckState.Checked for row in range(self.list.count()))
        visible = [self.list.item(row) for row in range(self.list.count()) if not self.list.item(row).isHidden()]
        self.count.setText(f"已选 {checked} / {self.list.count()} 门")
        self.apply_button.setEnabled(checked > 0 or not self.courses)
        self.select_visible.setChecked(bool(visible) and all(item.checkState() == Qt.CheckState.Checked for item in visible))
        self.select_visible.setEnabled(bool(visible))

    def _all_courses(self):
        self.selection = set()
        super().accept()

    def accept(self):
        values = {self.list.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.list.count()) if self.list.item(row).checkState() == Qt.CheckState.Checked}
        if not values and self.courses:
            return
        self.selection = set() if values == set(self.courses) else values
        super().accept()
