"""Spacious chapter/activity/file outline with synchronized download selection."""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHeaderView
from .flat_outline import FlatOutlineItem, FlatOutlineWidget
from .ui_components import file_icon_kind, resource_icon
from ..ui_stall_watchdog import note_ui_action
from .local_materials_ui import ROLE_LOCAL

ROLE_ROWS = Qt.ItemDataRole.UserRole
ROLE_FILE = int(Qt.ItemDataRole.UserRole) + 1
ROLE_LEVEL = int(Qt.ItemDataRole.UserRole) + 2


def set_outline_level(node, level):
    node.setData(0, ROLE_LEVEL, level)
    height = 54 if level == 0 else 44 if level in (1, 2) else 38
    for column in range(3):
        node.setSizeHint(column, QSize(0, height))


class ChapterTreeMixin:
    def _create_courseware_tree(self):
        tree = FlatOutlineWidget()
        tree.setObjectName("ChapterOutline")
        tree.horizontalHeader().setStretchLastSection(False)
        tree.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tree.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        tree.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        tree.setColumnWidth(1, 85)
        tree.setColumnWidth(2, 125)
        tree.setAccessibleName("按章节查找课件")
        tree.outlineCurrentItemChanged.connect(lambda item, _old: self._filter_courseware_branch(item))
        tree.outlineItemChanged.connect(self._chapter_checked)
        tree.outlineItemDoubleClicked.connect(self._activate_chapter_file)
        tree.outlineExpanded.connect(lambda _node: note_ui_action("courseware:expanded"))
        tree.outlineCollapsed.connect(lambda _node: note_ui_action("courseware:collapsed"))
        if hasattr(self, "add_local_materials"):
            tree.localFilesDropped.connect(self.add_local_materials)
        self.courseware_tree = tree
        self._chapter_leaf_by_key = {}
        self._chapter_check_mode = False
        self._courseware_checked_keys = set()
        self._courseware_selected_keys = set()
        self._courseware_current_key = None
        return tree

    def _rebuild_courseware_tree(self):
        if not hasattr(self, "courseware_tree"):
            return
        tree = self.courseware_tree
        old_expansion = ({key: node.isExpanded() for key, node in getattr(self, "_chapter_nodes_by_key", {}).items()}
                         if getattr(self, "_keep_courseware_expansion", False) else {})
        tree.blockSignals(True)
        tree.setUpdatesEnabled(False)
        tree.clear()
        self._chapter_leaf_by_key = {}
        root = tree.invisibleRootItem()
        nodes = {}
        branch_rows = {}
        def group(parent, key, text, level, icon):
            if key not in nodes:
                node = nodes[key] = FlatOutlineItem(parent, [text])
                branch_rows[key] = []
                set_outline_level(node, level)
                node.setToolTip(0, text)
                node.setIcon(0, resource_icon(icon))
                # Aggregate parent checks once per batch. Qt AutoTristate rescans
                # siblings on every leaf change, stalling large chapters.
                node.setFlags(node.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                node.setCheckState(0, Qt.CheckState.Unchecked)
                font = QFont(tree.font())
                font.setPixelSize(15 if level == 0 else 14)
                font.setBold(level == 0)
                node.setFont(0, font)
            return nodes[key]
        for row, item in enumerate(self.courseware_items):
            chapter_key = (item.module_id or item.module_name,)
            chapter = group(root, chapter_key, item.module_name or "未分组", 0, "folder")
            parent = chapter
            branch_keys = [chapter_key]
            if item.syllabus_name:
                section_key = chapter_key + (item.syllabus_id or item.syllabus_name,)
                parent = group(chapter, section_key, item.syllabus_name, 1, "folder")
                branch_keys.append(section_key)
            activity_key = chapter_key + ("activity", item.activity_id)
            activity = group(parent, activity_key, item.activity_title, 2, "video" if item.activity_type == "online_video" else "activity")
            branch_keys.append(activity_key)
            for key in branch_keys:
                branch_rows[key].append(row)
            leaf = FlatOutlineItem(activity, [item.filename or "平台入口", Path(item.filename).suffix.lstrip(".").upper() or "链接"])
            leaf.setData(0, ROLE_ROWS, [row])
            leaf.setData(0, ROLE_FILE, row)
            set_outline_level(leaf, 3)
            leaf.setIcon(0, resource_icon(file_icon_kind(item.filename)))
            leaf.setFlags(leaf.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            leaf.setCheckState(0, Qt.CheckState.Unchecked)
            leaf.setToolTip(0, item.filename or item.activity_title)
            self._chapter_leaf_by_key[self._courseware_key(item)] = leaf
        visible_local = getattr(self, "_visible_local_materials", lambda: [])()
        local_counts = {}
        for entry in visible_local:
            chapter_key = (entry.get("chapter_id") or entry.get("chapter") or "补充资料",)
            local_counts[chapter_key] = local_counts.get(chapter_key, 0) + 1
            chapter = group(root, chapter_key, entry.get("chapter") or "补充资料", 0, "folder")
            local_key = chapter_key + ("local-materials",)
            activity = group(chapter, local_key, "本地资料", 2, "folder")
            activity.setData(0, ROLE_LOCAL, "folder")
            leaf = FlatOutlineItem(activity, [entry["name"], Path(entry["name"]).suffix.lstrip(".").upper(),
                "引用原位置" if entry["mode"] == "reference" else "本地文件"])
            leaf.setData(0, ROLE_LOCAL, entry["resource_id"])
            leaf.setData(0, ROLE_ROWS, [])
            set_outline_level(leaf, 3)
            leaf.setFlags(leaf.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            leaf.setIcon(0, resource_icon(file_icon_kind(entry["name"])))
            leaf.setToolTip(0, entry["path"])
        for key, node in nodes.items():
            node.setData(0, ROLE_ROWS, branch_rows[key])
            if not branch_rows[key]:
                node.setFlags(node.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                node.setData(0, Qt.ItemDataRole.CheckStateRole, None)
            if len(key) == 1:
                local_count = local_counts.get(key, 0)
                node.setText(2, f"{len(branch_rows[key]) + local_count} 项资料")
        self._chapter_nodes_by_key = nodes
        self._chapter_groups = list(reversed(list(nodes.values())))
        # Keep small courses immediately browsable. For large courses, open
        # chapters and sections but materialize activity files only on demand.
        tree.expandToDepth(1 if len(self.courseware_items) <= 200 else 0)
        if len(self.courseware_items) > 200:
            for node in nodes.values():
                if node.data(0, ROLE_LEVEL) == 1:
                    node.setExpanded(True)
        tree.commit()
        if getattr(self, "_keep_courseware_expansion", False):
            for key, expanded in old_expansion.items():
                if key in nodes:
                    nodes[key].setExpanded(expanded)
        tree.blockSignals(False)
        tree.setUpdatesEnabled(True)
        if not getattr(self, "_defer_chapter_sync", False):
            self._sync_chapter_tree()

    def _chapter_checked(self, item, column):
        if column != 0:
            return
        state = item.checkState(0)
        if state == Qt.CheckState.PartiallyChecked:
            return
        keys = {self._courseware_key(self.courseware_items[row]) for row in item.data(0, ROLE_ROWS) or []
                if 0 <= row < len(self.courseware_items)}
        if state == Qt.CheckState.Checked:
            self._courseware_checked_keys.update(keys)
        else:
            self._courseware_checked_keys.difference_update(keys)
        self._chapter_check_mode = True
        self._courseware_selected_keys.clear()
        self._courseware_current_key = None
        self._sync_chapter_tree()

    def _activate_chapter_file(self, item, column):
        local_id = item.data(0, ROLE_LOCAL)
        if local_id and local_id != "folder":
            self._open_local_material(local_id)
            return
        row = item.data(0, ROLE_FILE)
        if row is not None and 0 <= row < len(self.courseware_items):
            self._start_courseware_download([self.courseware_items[row]])

    def _sync_chapter_tree(self):
        if not hasattr(self, "_chapter_leaf_by_key"):
            return
        tree = self.courseware_tree
        previous = tree.blockSignals(True)
        try:
            for row, item in enumerate(self.courseware_items):
                leaf = self._chapter_leaf_by_key.get(self._courseware_key(item))
                if leaf is None:
                    continue
                state = (Qt.CheckState.Checked if self._courseware_key(item) in self._courseware_checked_keys
                         else Qt.CheckState.Unchecked)
                if leaf.checkState(0) != state:
                    leaf.setCheckState(0, state)
                status = self.courseware_download_status.get(self._courseware_key(item), "可下载")
                if leaf.text(2) != status:
                    leaf.setText(2, status)
            for group in getattr(self, "_chapter_groups", []):
                states = {group.child(i).checkState(0) for i in range(group.childCount())
                          if group.child(i).flags() & Qt.ItemFlag.ItemIsUserCheckable}
                state = states.pop() if len(states) == 1 else Qt.CheckState.PartiallyChecked if states else Qt.CheckState.Unchecked
                if group.checkState(0) != state:
                    group.setCheckState(0, state)
        finally:
            tree.blockSignals(previous)

    def _filter_courseware_branch(self, node):
        if node is None:
            return
        self._courseware_current_local_id = None
        local_id = node.data(0, ROLE_LOCAL)
        if local_id:
            self._courseware_selected_keys = set()
            self._courseware_current_key = None
            if local_id != "folder":
                self._courseware_current_local_id = local_id
            self.courseware_summary.setText("本地补充资料；双击打开，重新定位或移除请用‘管理本地资料’。")
            return
        rows = set(node.data(0, ROLE_ROWS) or [])
        self._chapter_check_mode = False
        rows = {row for row in rows if 0 <= row < len(self.courseware_items)}
        self._courseware_selected_keys = {self._courseware_key(self.courseware_items[row]) for row in rows}
        self._courseware_current_key = self._courseware_key(self.courseware_items[min(rows)]) if rows else None
        self.courseware_summary.setText(f"所选目录 {len(rows)} 项资料；可直接下载，或勾选需要的附件。")
