"""Attachment-first answer area and a compact native rich-text toolbar."""
from html import escape
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextListFormat, QTextTableFormat
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QListWidget, QListWidgetItem, QPushButton, QToolButton, QVBoxLayout, QWidget)
from .ui_components import QuietItemDelegate, file_icon_kind, resource_icon


def dropped_files(event):
    mime = event.mimeData()
    return [url.toLocalFile() for url in mime.urls() if url.isLocalFile()] if mime.hasUrls() else []


class DropFilesMixin:
    def dragEnterEvent(self, event):
        if dropped_files(event):
            event.acceptProposedAction()
            self.setProperty("dragActive", True)
            self.style().unpolish(self)
            self.style().polish(self)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if dropped_files(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setProperty("dragActive", False)
        self.style().unpolish(self)
        self.style().polish(self)
        event.accept()

    def dropEvent(self, event):
        files = dropped_files(event)
        self.setProperty("dragActive", False)
        self.style().unpolish(self)
        self.style().polish(self)
        if files:
            self.filesDropped.emit(files)
            event.acceptProposedAction()
        else:
            event.ignore()


class AttachmentDropZone(DropFilesMixin, QFrame):
    filesDropped = Signal(object)


class AttachmentList(DropFilesMixin, QListWidget):
    filesDropped = Signal(object)


class AttachmentDelegate(QuietItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(40, option.fontMetrics.height() + 16))


def attachment_list(*, accept_drops=False):
    widget = AttachmentList()
    widget.setObjectName("SubmissionFiles")
    widget.setIconSize(QSize(24, 24))
    widget.setUniformItemSizes(True)
    widget.setItemDelegate(AttachmentDelegate(widget))
    widget.setAcceptDrops(accept_drops)
    widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    widget.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
    widget.setTextElideMode(Qt.TextElideMode.ElideMiddle)
    widget.setFixedHeight(3 * max(40, widget.fontMetrics().height() + 16) + 12)
    return widget


def attachment_item(name, status="", tooltip=""):
    item = QListWidgetItem(resource_icon(file_icon_kind(name)), str(name) + ("  · " + status if status else ""))
    item.setToolTip(tooltip or str(name))
    return item


def panel_heading(text):
    heading = QLabel(text)
    heading.setObjectName("AnswerHeading")
    heading.setFixedHeight(24)
    return heading


def build_answer_panel(window, layout, editor_class):
    from .ui_components import configure_combo_popups
    header = QWidget()
    header.setFixedHeight(44)
    top = QHBoxLayout(header)
    top.setContentsMargins(0, 0, 0, 0)
    heading = panel_heading("写作业")
    top.addWidget(heading)
    top.addStretch()
    expand = QPushButton("展开正文")
    expand.setObjectName("QuietButton")
    expand.setToolTip("需要较长的在线文字答案时展开编辑区")
    top.addWidget(expand)
    layout.addWidget(header)

    window.answer_panel = QFrame()
    window.answer_panel.setObjectName("AnswerPanel")
    body_layout = QVBoxLayout(window.answer_panel)
    body_layout.setContentsMargins(6, 4, 6, 2)
    body_layout.setSpacing(2)
    toolbar = QHBoxLayout()
    toolbar.setSpacing(1)
    window.editor = editor_class()
    window.editor.setAccessibleName("作业答案富文本编辑区")
    window.editor.setPlaceholderText("可选：在这里填写文字答案。只交附件时可以留空。")
    window.editor.setMinimumHeight(95)
    window.editor.filesDropped.connect(window._add_files)
    styles = QComboBox()
    styles.addItems(["正文", "标题 1", "标题 2"])
    styles.setFixedWidth(90)
    def heading_style(index):
        cursor = window.editor.textCursor()
        block = QTextBlockFormat()
        block.setHeadingLevel(index)
        cursor.mergeBlockFormat(block)
        char = QTextCharFormat()
        char.setFontPointSize(12 if index == 0 else 18 if index == 1 else 15)
        char.setFontWeight(QFont.Weight.Normal if index == 0 else QFont.Weight.Bold)
        cursor.mergeCharFormat(char)
        window.editor.setFocus()
    styles.activated.connect(heading_style)
    toolbar.addWidget(styles)
    def ordered_list():
        style = QTextListFormat()
        style.setStyle(QTextListFormat.Style.ListDecimal)
        window.editor.textCursor().createList(style)
    def strike():
        char = QTextCharFormat()
        char.setFontStrikeOut(not window.editor.currentCharFormat().fontStrikeOut())
        window.editor.mergeCurrentCharFormat(char)
    def quote():
        block = QTextBlockFormat()
        block.setIndent(1)
        window.editor.textCursor().mergeBlockFormat(block)
    def code():
        cursor = window.editor.textCursor()
        cursor.insertHtml("<pre>" + escape(cursor.selectedText() or "代码") + "</pre>")
    def table():
        rows, ok = QInputDialog.getInt(window, "插入表格", "行数", 2, 1, 20)
        if ok:
            columns, ok = QInputDialog.getInt(window, "插入表格", "列数", 2, 1, 10)
            if ok:
                style = QTextTableFormat()
                style.setBorder(1)
                style.setCellPadding(5)
                window.editor.textCursor().insertTable(rows, columns, style)
    tools = [
        ("B", "加粗", window._bold), ("I", "斜体", lambda: window.editor.setFontItalic(not window.editor.fontItalic())),
        ("U", "下划线", lambda: window.editor.setFontUnderline(not window.editor.fontUnderline())),
        ("S", "删除线", strike), ("1.", "编号列表", ordered_list), ("列表", "项目列表", window._list),
        ("引用", "引用", quote), ("代码", "代码块", code), ("表格", "表格", table),
        ("链接", "插入链接", window._link), ("图片", "插入图片", window._image),
    ]
    for text, tooltip, callback in tools:
        tool = QToolButton()
        tool.setObjectName("EditorTool")
        tool.setText(text)
        tool.setToolTip(tooltip)
        tool.setAccessibleName(tooltip)
        font = tool.font()
        font.setBold(text == "B")
        font.setItalic(text == "I")
        font.setUnderline(text == "U")
        tool.setFont(font)
        tool.clicked.connect(lambda _checked=False, action=callback: action())
        toolbar.addWidget(tool)
    toolbar.addStretch()
    body_layout.addLayout(toolbar)
    body_layout.addWidget(window.editor, 1)
    window.answer_panel.setMaximumHeight(175)
    def toggle_answer():
        expanded = expand.text() == "展开正文"
        window.answer_panel.setMaximumHeight(16777215 if expanded else 175)
        layout.setStretchFactor(window.answer_panel, 1 if expanded else 0)
        layout.setStretchFactor(window.drop_zone, 0 if expanded else 1)
        expand.setText("收起正文" if expanded else "展开正文")
    expand.clicked.connect(toggle_answer)
    layout.addWidget(window.answer_panel)

    layout.addWidget(panel_heading("上传附件"))
    window.drop_zone = AttachmentDropZone()
    window.drop_zone.setObjectName("AttachmentDropZone")
    window.drop_zone.setAcceptDrops(True)
    window.drop_zone.setMinimumHeight(160)
    window.drop_zone.filesDropped.connect(window._add_files)
    drop_layout = QVBoxLayout(window.drop_zone)
    drop_layout.setContentsMargins(16, 16, 16, 16)
    drop_layout.setSpacing(10)
    drop_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window.pick_button = QPushButton("添加文件")
    window.pick_button.setIcon(resource_icon("upload"))
    window.pick_button.setIconSize(QSize(24, 24))
    window.pick_button.setMinimumSize(165, 44)
    window.pick_button.clicked.connect(lambda: window._add_files(QFileDialog.getOpenFileNames(window, "选择作业附件")[0]))
    drop_layout.addWidget(window.pick_button, 0, Qt.AlignmentFlag.AlignHCenter)
    tip = QLabel("或将文件拖到这里 · 支持多个附件\n附件会自动上传，核对后再交付作业")
    tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
    tip.setMinimumWidth(360)
    tip.setWordWrap(True)
    drop_layout.addWidget(tip)
    layout.addWidget(window.drop_zone, 1)
    layout.addWidget(panel_heading("已上传 / 待上传附件"))
    window.file_list = attachment_list(accept_drops=True)
    window.file_list.setAccessibleName("作业附件与上传状态")
    window.file_list.filesDropped.connect(window._add_files)
    layout.addWidget(window.file_list)
    actions = QHBoxLayout()
    window.remove_button = QPushButton("移除所选附件")
    window.remove_button.setObjectName("QuietButton")
    window.remove_button.clicked.connect(window._remove_file)
    window.upload_button = QPushButton("重试上传")
    window.upload_button.setObjectName("QuietButton")
    window.upload_button.clicked.connect(lambda: window._start_operation("upload"))
    window.remove_button.setMinimumHeight(38)
    window.upload_button.setMinimumHeight(38)
    actions.addWidget(window.remove_button)
    actions.addStretch()
    actions.addWidget(window.upload_button)
    layout.addLayout(actions)
    configure_combo_popups(window.answer_panel)
