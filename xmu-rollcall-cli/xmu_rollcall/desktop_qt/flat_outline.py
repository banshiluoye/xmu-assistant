"""A flat chapter outline which allocates visible cells on demand."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QFont, QIcon, QPalette, QPolygon
from PySide6.QtWidgets import (
    QAbstractItemView, QStyledItemDelegate, QStyle, QStyleOptionViewItem,
    QTableWidget, QTableWidgetItem,
)


class FlatOutlineItem:
    """The small QTreeWidgetItem-compatible surface used by chapter_tree."""

    def __init__(self, parent=None, texts=None):
        self._parent = parent._root if isinstance(parent, FlatOutlineWidget) else parent
        self._owner = self._parent._owner if self._parent is not None else None
        self._children = []
        self._values = {}
        self._expanded = False
        self._depth = 0
        self._flags = (Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                       | Qt.ItemFlag.ItemIsUserCheckable)
        if self._parent is not None:
            self._parent._children.append(self)
        for column, text in enumerate(texts or []):
            self._values[column, int(Qt.ItemDataRole.DisplayRole)] = str(text)

    def data(self, column, role):
        return self._values.get((column, int(role)))

    def setData(self, column, role, value):
        key = (column, int(role))
        if self._values.get(key) == value:
            return
        self._values[key] = value
        if self._owner is not None:
            self._owner._node_changed(self, column, int(role))

    def text(self, column):
        return self.data(column, Qt.ItemDataRole.DisplayRole) or ""

    def setText(self, column, text):
        self.setData(column, Qt.ItemDataRole.DisplayRole, str(text))

    def checkState(self, column):
        value = self.data(column, Qt.ItemDataRole.CheckStateRole)
        return Qt.CheckState.Unchecked if value is None else Qt.CheckState(value)

    def setCheckState(self, column, state):
        self.setData(column, Qt.ItemDataRole.CheckStateRole, Qt.CheckState(state).value)

    def icon(self, column):
        return self.data(column, Qt.ItemDataRole.DecorationRole) or QIcon()

    def setIcon(self, column, icon):
        self.setData(column, Qt.ItemDataRole.DecorationRole, QIcon(icon))

    def font(self, column):
        return self.data(column, Qt.ItemDataRole.FontRole) or QFont()

    def setFont(self, column, font):
        self.setData(column, Qt.ItemDataRole.FontRole, QFont(font))

    def sizeHint(self, column):
        return self.data(column, Qt.ItemDataRole.SizeHintRole) or QSize(-1, -1)

    def setSizeHint(self, column, size):
        self.setData(column, Qt.ItemDataRole.SizeHintRole, QSize(size))

    def toolTip(self, column):
        return self.data(column, Qt.ItemDataRole.ToolTipRole) or ""

    def setToolTip(self, column, text):
        self.setData(column, Qt.ItemDataRole.ToolTipRole, text)

    def flags(self):
        return self._flags

    def setFlags(self, flags):
        if flags != self._flags:
            self._flags = flags
            if self._owner is not None:
                self._owner._node_flags_changed(self)

    def child(self, index):
        return self._children[index] if 0 <= index < len(self._children) else None

    def childCount(self):
        return len(self._children)

    def parent(self):
        return self._parent if self._parent is not None and self._parent._parent is not None else None

    def isExpanded(self):
        return self._expanded

    def setExpanded(self, expanded):
        if self._owner is not None:
            self._owner._set_node_expanded(self, expanded)
        else:
            self._expanded = bool(expanded) and bool(self._children)


class _OutlineDelegate(QStyledItemDelegate):
    """Only indent the native first-column painting and draw a disclosure mark."""

    def paint(self, painter, option, index):
        view = self.parent()
        if index.row() >= len(view._nodes):
            return super().paint(painter, option, index)
        node = view._nodes[index.row()]
        full = QStyleOptionViewItem(option)
        self.initStyleOption(full, index)
        full.state &= ~QStyle.StateFlag.State_HasFocus
        style = full.widget.style() if full.widget else view.style()
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, full, painter, full.widget)
        content = QStyleOptionViewItem(full)
        content.rect.adjust(view._indentation * node._depth + view._disclosure_width, 0, 0, 0)
        if node._expanded:
            content.state |= QStyle.StateFlag.State_Open
        super().paint(painter, content, index)
        if node._children:
            center = view.disclosureRect(node).center()
            points = ([QPoint(-4, -2), QPoint(4, -2), QPoint(0, 3)] if node._expanded
                      else [QPoint(-2, -4), QPoint(-2, 4), QPoint(3, 0)])
            role = (QPalette.ColorRole.HighlightedText if full.state & QStyle.StateFlag.State_Selected
                    else QPalette.ColorRole.Text)
            group = (full.palette.currentColorGroup() if full.state & QStyle.StateFlag.State_Enabled
                     else QPalette.ColorGroup.Disabled)
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(full.palette.color(group, role))
            painter.drawPolygon(QPolygon([center + point for point in points]))
            painter.restore()

    def editorEvent(self, event, model, option, index):
        # Native checkbox hit testing must use the same indented rectangle.
        if index.row() < len(self.parent()._nodes):
            option = QStyleOptionViewItem(option)
            node = self.parent()._nodes[index.row()]
            option.rect.adjust(self.parent()._indentation * node._depth
                               + self.parent()._disclosure_width, 0, 0, 0)
        return super().editorEvent(event, model, option, index)


class FlatOutlineWidget(QTableWidget):
    localFilesDropped = Signal(list)
    outlineItemChanged = Signal(object, int)
    outlineCurrentItemChanged = Signal(object, object)
    outlineItemDoubleClicked = Signal(object, int)
    outlineExpanded = Signal(object)
    outlineCollapsed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(0, 3, parent)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self._root = FlatOutlineItem()
        self._root._owner = self
        self._nodes = []
        self._row_by_node = {}
        self._subtree_end = {}
        self._current_node = None
        self._committed = False
        self._native_update_depth = 0
        self._indentation = 26
        self._disclosure_width = 22
        self.horizontalHeader().hide()
        self.verticalHeader().hide()
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setIconSize(QSize(24, 24))
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setItemDelegate(QStyledItemDelegate(self))
        self.setItemDelegateForColumn(0, _OutlineDelegate(self))
        self.itemChanged.connect(self._native_item_changed)
        self.currentItemChanged.connect(self._native_current_changed)
        self.cellDoubleClicked.connect(self._native_double_clicked)

    def dragEnterEvent(self, event):
        if (event.possibleActions() & Qt.DropAction.CopyAction and event.mimeData().hasUrls()
                and any(url.isLocalFile() for url in event.mimeData().urls())):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths and event.possibleActions() & Qt.DropAction.CopyAction:
            event.setDropAction(Qt.DropAction.CopyAction)
            self.localFilesDropped.emit(paths)
            event.accept()
        else:
            event.ignore()

    def invisibleRootItem(self):
        return self._root

    def topLevelItem(self, index):
        return self._root.child(index)

    def topLevelItemCount(self):
        return self._root.childCount()

    def indentation(self):
        return self._indentation

    def setIndentation(self, value):
        self._indentation = max(0, int(value))
        self.viewport().update()

    def clear(self):
        self._native_update_depth += 1
        try:
            pending = list(self._root._children)
            while pending:
                node = pending.pop()
                node._owner = None
                pending.extend(node._children)
            self._root._owner = None
            self._nodes = []
            self._row_by_node = {}
            self._subtree_end = {}
            self._current_node = None
            self._committed = False
            super().clear()
            self.setRowCount(0)
            self._root = FlatOutlineItem()
            self._root._owner = self
        finally:
            self._native_update_depth -= 1

    def commit(self):
        """Allocate flat rows once after a logical tree build, never on disclosure."""
        previous_updates = self.updatesEnabled()
        previous_current = self._current_node
        self.setUpdatesEnabled(False)
        self._native_update_depth += 1
        try:
            self._nodes = []
            self._row_by_node = {}
            self._subtree_end = {}
            stack = [(node, 0) for node in reversed(self._root._children)]
            while stack:
                node, depth = stack.pop()
                node._owner, node._depth = self, depth
                self._row_by_node[node] = len(self._nodes)
                self._nodes.append(node)
                stack.extend((child, depth + 1) for child in reversed(node._children))
            ancestors = []
            for row, node in enumerate(self._nodes):
                while ancestors and ancestors[-1][1]._depth >= node._depth:
                    _, ancestor = ancestors.pop()
                    self._subtree_end[ancestor] = row
                ancestors.append((row, node))
            for _, node in ancestors:
                self._subtree_end[node] = len(self._nodes)
            self.setRowCount(0)
            self.setRowCount(len(self._nodes))
            for row, node in enumerate(self._nodes):
                parent = node._parent
                hidden = parent is not self._root and (
                    not parent._expanded or self.isRowHidden(self._row_by_node[parent]))
                self.setRowHidden(row, hidden)
                if not hidden:
                    self._materialize_row(node)
            self._committed = True
            self._current_node = None
            if previous_current in self._row_by_node:
                self.setCurrentItem(previous_current)
        finally:
            self._native_update_depth -= 1
            self.setUpdatesEnabled(previous_updates)

    refreshRows = commit

    def _materialize_row(self, node):
        row = self._row_by_node[node]
        if self.item(row, 0) is not None:
            return
        self._native_update_depth += 1
        try:
            for column in range(self.columnCount()):
                cell = QTableWidgetItem()
                cell.setFlags(node.flags())
                for (stored_column, role), value in node._values.items():
                    if stored_column == column:
                        cell.setData(role, value)
                self.setItem(row, column, cell)
            self._update_accessible_text(node)
            self._update_row_height(node)
        finally:
            self._native_update_depth -= 1

    def expandToDepth(self, depth):
        stack = [(node, 0) for node in reversed(self._root._children)]
        while stack:
            node, current_depth = stack.pop()
            node.setExpanded(current_depth <= depth)
            stack.extend((child, current_depth + 1) for child in reversed(node._children))

    def expandAll(self):
        self.expandToDepth(2 ** 31 - 1)

    def collapseAll(self):
        self.expandToDepth(-1)

    def currentItem(self):
        return self._current_node

    def setCurrentItem(self, node, column=0):
        row = self._row_by_node.get(node)
        if row is None:
            self.setCurrentCell(-1, -1)
            self.clearSelection()
            if self._current_node is not None:
                old, self._current_node = self._current_node, None
                self.outlineCurrentItemChanged.emit(None, old)
            return
        self._materialize_row(node)
        QTableWidget.setCurrentItem(self, self.item(row, column))
        if self._native_update_depth:
            self._current_node = node

    def scrollToItem(self, node, hint=QAbstractItemView.ScrollHint.EnsureVisible):
        row = self._row_by_node.get(node)
        if row is not None:
            QTableWidget.scrollToItem(self, self.item(row, 0), hint)

    def visualItemRect(self, node):
        row = self._row_by_node.get(node)
        return QTableWidget.visualItemRect(self, self.item(row, 0)) if row is not None else QRect()

    def disclosureRect(self, node):
        rect = self.visualItemRect(node)
        if rect.isEmpty() or not node._children:
            return QRect()
        return QRect(rect.left() + node._depth * self._indentation,
                     rect.top(), self._disclosure_width, rect.height())

    def toggleNode(self, node):
        self._set_node_expanded(node, not node.isExpanded())

    def _set_node_expanded(self, node, expanded):
        expanded = bool(expanded) and bool(node._children)
        if node._expanded == expanded:
            return
        node._expanded = expanded
        if not self._committed or node not in self._row_by_node:
            return
        row, end = self._row_by_node[node], self._subtree_end[node]
        current_row = self._row_by_node.get(self._current_node, -1)
        if not expanded and row < current_row < end:
            self.setCurrentItem(node)
        previous_updates = self.updatesEnabled()
        self.setUpdatesEnabled(False)
        try:
            for descendant_row in range(row + 1, end):
                descendant = self._nodes[descendant_row]
                parent = descendant._parent
                hidden = not parent._expanded or self.isRowHidden(self._row_by_node[parent])
                if self.isRowHidden(descendant_row) != hidden:
                    if not hidden:
                        self._materialize_row(descendant)
                    self.setRowHidden(descendant_row, hidden)
            self._update_accessible_text(node)
        finally:
            self.setUpdatesEnabled(previous_updates)
        self.viewport().update(self.visualItemRect(node))
        (self.outlineExpanded if expanded else self.outlineCollapsed).emit(node)

    def _update_accessible_text(self, node):
        row = self._row_by_node.get(node)
        if row is None or self.item(row, 0) is None:
            return
        text = f"{node.text(0)}，第 {node._depth + 1} 层"
        if node._children:
            text += "，已展开" if node._expanded else "，已收起"
        self._native_update_depth += 1
        try:
            self.item(row, 0).setData(Qt.ItemDataRole.AccessibleTextRole, text)
            self.item(row, 0).setData(Qt.ItemDataRole.AccessibleDescriptionRole,
                "左右方向键展开或收起目录；空格键切换勾选。" if node._children else "空格键切换勾选；回车键下载附件。")
        finally:
            self._native_update_depth -= 1

    def _update_row_height(self, node):
        height = max((node.sizeHint(column).height() for column in range(self.columnCount())), default=38)
        self.setRowHeight(self._row_by_node[node], height if height > 0 else 38)

    def _node_changed(self, node, column, role):
        if not self._committed or node not in self._row_by_node:
            return
        cell = self.item(self._row_by_node[node], column)
        if cell is None:
            self.outlineItemChanged.emit(node, column)
            return
        self._native_update_depth += 1
        try:
            cell.setData(role, node.data(column, role))
            if role == int(Qt.ItemDataRole.SizeHintRole):
                self._update_row_height(node)
            if column == 0 and role == int(Qt.ItemDataRole.DisplayRole):
                self._update_accessible_text(node)
        finally:
            self._native_update_depth -= 1
        self.outlineItemChanged.emit(node, column)

    def _node_flags_changed(self, node):
        if not self._committed or node not in self._row_by_node:
            return
        self._native_update_depth += 1
        try:
            for column in range(self.columnCount()):
                cell = self.item(self._row_by_node[node], column)
                if cell is not None:
                    cell.setFlags(node.flags())
        finally:
            self._native_update_depth -= 1

    def _native_item_changed(self, cell):
        if not self._native_update_depth and 0 <= cell.row() < len(self._nodes):
            node = self._nodes[cell.row()]
            # Only a checkbox is user-editable; text/status changes go via Node.
            state = cell.checkState()
            if cell.data(Qt.ItemDataRole.CheckStateRole) is not None and state != node.checkState(cell.column()):
                node.setCheckState(cell.column(), state)

    def _native_current_changed(self, cell, _previous):
        if self._native_update_depth:
            return
        node = self._nodes[cell.row()] if cell is not None and 0 <= cell.row() < len(self._nodes) else None
        if node is not self._current_node:
            previous, self._current_node = self._current_node, node
            self.outlineCurrentItemChanged.emit(node, previous)

    def _native_double_clicked(self, row, column):
        if 0 <= row < len(self._nodes):
            self.outlineItemDoubleClicked.emit(self._nodes[row], column)

    def mousePressEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and index.isValid() and index.column() == 0:
            node = self._nodes[index.row()]
            if self.disclosureRect(node).contains(event.position().toPoint()):
                self.toggleNode(node)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        if index.isValid() and index.column() == 0 and self.disclosureRect(self._nodes[index.row()]).contains(event.position().toPoint()):
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        node = self.currentItem()
        if node is not None and event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            if event.key() == Qt.Key.Key_Right:
                if node._children and not node._expanded:
                    node.setExpanded(True)
                elif node._children:
                    self.setCurrentItem(node.child(0))
            elif node._children and node._expanded:
                node.setExpanded(False)
            elif node.parent() is not None:
                self.setCurrentItem(node.parent())
            event.accept()
            return
        if node is not None and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if node._children:
                self.toggleNode(node)
            else:
                self.outlineItemDoubleClicked.emit(node, 0)
            event.accept()
            return
        super().keyPressEvent(event)
