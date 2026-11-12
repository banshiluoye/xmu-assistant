"""Native homework editor; uploads and final submission are distinct states."""
from __future__ import annotations

import base64
from dataclasses import replace
import hashlib
from pathlib import Path
import re
import threading
import time
import webbrowser

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QFont, QImage, QTextCharFormat, QTextListFormat
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
    QMessageBox, QPushButton, QProgressBar, QSplitter, QTextBrowser, QTextEdit, QVBoxLayout, QWidget)

from ..learning import LearningApi, LearningStore, base_url, user_attachments, generated_previews
from ..learning_html import clean_html, editor_html, submission_html
from ..draft_writer import DraftWriter
from .homework_widgets import attachment_item, attachment_list, build_answer_panel, panel_heading
from ..utils import clone_session
from ..worker_sessions import close_cloned_session


class HomeworkEditor(QTextEdit):
    filesDropped = Signal(object)

    def insertFromMimeData(self, source):
        if source.hasUrls() and any(url.isLocalFile() for url in source.urls()):
            self.filesDropped.emit([url.toLocalFile() for url in source.urls() if url.isLocalFile()])
        elif source.hasImage():
            self.insert_image(QImage(source.imageData()))
        elif source.hasHtml():
            self.textCursor().insertHtml(clean_html(source.html()))
        else:
            super().insertFromMimeData(source)

    def insert_image(self, image):
        if image.isNull():
            return
        if image.width() > 2400 or image.height() > 2400:
            image = image.scaled(2400, 2400, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        uri = "data:image/png;base64," + base64.b64encode(bytes(data)).decode()
        width = min(700, image.width())
        self.textCursor().insertHtml(f'<img src="{uri}" width="{width}">')


class HomeworkWindow(QDialog):
    result = Signal(object)

    def _post(self, kind, *values):
        self.result.emit((kind, *values))

    def __init__(self, host, task, data, store):
        super().__init__(host)
        self.host, self.task, self.data = host, task, data
        self.source_session = host.session
        self.store = store or LearningStore(host.account["id"])
        self.draft_writer = DraftWriter(self.store, self.store.draft_name(task), lambda error: self._post("save_error", str(error)))
        self.pending_files = []
        self.uploads = user_attachments(data["submission"])
        self.inline_images = {}
        self.busy = False
        self.operation = None
        self.valid = True
        self.cancel = threading.Event()
        self.setWindowTitle(task.title + " · 作业")
        self.setObjectName("HomeworkWindow")
        self.resize(1180, 900)
        self.setMinimumSize(940, 740)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.result.connect(self._on_result)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(20)
        context = QVBoxLayout()
        context.setSpacing(4)
        course_name = QLabel(task.course_name)
        course_name.setObjectName("HomeworkCourseName")
        course_name.setWordWrap(True)
        self.task_title = QLabel(task.title)
        self.task_title.setObjectName("HomeworkTaskTitle")
        self.task_title.setWordWrap(True)
        context.addWidget(course_name)
        context.addWidget(self.task_title)
        header_layout.addLayout(context, 1)
        header_tools = QWidget()
        header_tools.setObjectName("HomeworkHeaderTools")
        tools_layout = QHBoxLayout(header_tools)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(8)
        self.original_button = QPushButton("原平台打开")
        self.original_button.setObjectName("QuietButton")
        self.original_button.clicked.connect(lambda: webbrowser.open(task.url))
        self.reload_button = QPushButton("重读平台记录")
        self.reload_button.setObjectName("QuietButton")
        self.reload_button.clicked.connect(lambda: self._start_operation("reload"))
        tools_layout.addWidget(self.original_button)
        tools_layout.addWidget(self.reload_button)
        header_layout.addWidget(header_tools, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(header)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(16)
        self.requirement = requirement = QTextBrowser()
        requirement.setOpenExternalLinks(False)
        requirement.anchorClicked.connect(lambda url: webbrowser.open(url.toString()) if url.scheme() in {"https", "http"} else None)
        detail = data["detail"]
        requirement.setHtml(clean_html((detail.get("data") or {}).get("description", "")))
        requirement.document().setBaseUrl(QUrl(task.url))
        left = QWidget()
        left.setMinimumWidth(240)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        header = QWidget()
        header.setFixedHeight(44)
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.addWidget(panel_heading("作业要求"))
        left_layout.addWidget(header)
        left_layout.addWidget(requirement, 1)
        left_layout.addWidget(panel_heading("作业附件"))
        self.teacher_files = attachment_list()
        self.teacher_files.setAccessibleName("教师提供的作业附件")
        for file in detail.get("uploads", []):
            self.teacher_files.addItem(attachment_item(file.get("name") or "作业附件"))
        if not detail.get("uploads"):
            self.teacher_files.addItem("暂无作业附件")
            self.teacher_files.item(0).setFlags(Qt.ItemFlag.NoItemFlags)
        left_layout.addWidget(self.teacher_files)
        download = QPushButton("下载所选作业附件")
        download.setObjectName("QuietButton")
        download.setMinimumHeight(38)
        download.clicked.connect(self._download_teacher_file)
        left_layout.addWidget(download)
        split.addWidget(left)
        right = QWidget()
        right.setMinimumWidth(580)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        build_answer_panel(self, right_layout, HomeworkEditor)
        self.editor.setHtml(editor_html(data["submission"].get("comment") or ""))
        split.addWidget(right)
        split.setSizes([300, 820])
        layout.addWidget(split, 1)
        footer = QWidget()
        footer.setObjectName("HomeworkFooter")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(8)
        self.status = QLabel(self._receipt_text())
        self.status.setObjectName("HomeworkStatus")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        footer_layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.hide()
        footer_layout.addWidget(self.progress)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.draft_button = QPushButton("保存草稿")
        self.draft_button.setObjectName("SecondaryButton")
        self.draft_button.setMinimumWidth(112)
        self.draft_button.setToolTip("保存到平台草稿；编辑内容仍会自动保存在本机")
        self.draft_button.clicked.connect(lambda: self._start_operation("draft"))
        self.submit_button = QPushButton("交付作业")
        self.submit_button.setObjectName("PrimaryButton")
        self.submit_button.setMinimumWidth(148)
        self.submit_button.clicked.connect(self._confirm_submit)
        self.cancel_button = QPushButton("取消剩余操作")
        self.cancel_button.setObjectName("QuietButton")
        self.cancel_button.setEnabled(False)
        self.cancel_button.hide()
        self.cancel_button.clicked.connect(self.cancel.set)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        actions.addWidget(self.draft_button)
        actions.addWidget(self.submit_button)
        footer_layout.addLayout(actions)
        layout.addWidget(footer)
        draft = self.store.read(self.store.draft_name(task), {})
        if draft:
            # Old drafts can contain empty paragraphs whose Qt marker was
            # removed by earlier versions. Clear those only on load; typing a
            # deliberate newline must keep behaving like a normal text editor.
            self.editor.setHtml(editor_html(draft.get("html", "")))
            self.pending_files = draft.get("pending", [])
            self.uploads = user_attachments({"uploads": draft.get("uploads", self.uploads)})
            self.inline_images = draft.get("inline", {})
            self.status.setText("已恢复本地草稿；" + self._receipt_text())
        self._render_files()
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self._save_local)
        self.editor.textChanged.connect(lambda: self.save_timer.start(700))
        QApplication.instance().aboutToQuit.connect(self._save_before_quit)
        if data.get("group") or task.locked:
            self.submit_button.setEnabled(False)
            self.draft_button.setEnabled(False)
            self.upload_button.setEnabled(False)
            self.status.setText("该作业为分组作业或尚未解锁，可在此查看要求并保存本地草稿；请在原平台完成提交。")

    def _receipt_text(self):
        submission = self.data["submission"]
        if submission.get("id") is None:
            return "平台尚无提交记录；编辑内容会自动保存为本地草稿。"
        preview = " 平台另有正文预览文件。" if generated_previews(submission) else ""
        return f"平台记录：{'草稿' if submission.get('is_draft') else '已提交'}；时间：{submission.get('submitted_at') or submission.get('created_at') or '未提供'}；历史记录 {len(self.data.get('history', []))} 条。" + preview

    def _bold(self):
        self.editor.setFontWeight(QFont.Weight.Normal if self.editor.fontWeight() >= QFont.Weight.Bold else QFont.Weight.Bold)

    def _list(self):
        style = QTextListFormat()
        style.setStyle(QTextListFormat.Style.ListDisc)
        self.editor.textCursor().createList(style)

    def _link(self):
        url, ok = QInputDialog.getText(self, "插入链接", "https:// 地址")
        if ok and url.startswith(("https://", "http://")):
            char_format = QTextCharFormat()
            char_format.setAnchor(True)
            char_format.setAnchorHref(url)
            char_format.setFontUnderline(True)
            cursor = self.editor.textCursor()
            if cursor.hasSelection():
                cursor.mergeCharFormat(char_format)
            else:
                cursor.insertText(url, char_format)

    def _image(self):
        path, _ = QFileDialog.getOpenFileName(self, "插入图片", "", "图片 (*.png *.jpg *.jpeg *.webp *.gif)")
        if path:
            self.editor.insert_image(QImage(path))

    def _add_files(self, paths):
        if not self.valid:
            return
        if self.busy and self.operation != "upload":
            self.status.setText("正在处理提交，请完成后再添加附件。")
            return
        for filename in paths:
            path = str(Path(filename).resolve())
            if Path(path).is_file() and path not in self.pending_files:
                self.pending_files.append(path)
        self._render_files()
        self._save_local()
        if self.pending_files and not self.busy and not self.data.get("group") and not self.task.locked:
            self._start_operation("upload")

    def _render_files(self):
        self.file_list.clear()
        for upload in self.uploads:
            self.file_list.addItem(attachment_item(upload.get("name") or upload["id"], "已上传"))
        for path in self.pending_files:
            self.file_list.addItem(attachment_item(Path(path).name, "待上传", path))

    def _remove_file(self):
        row = self.file_list.currentRow()
        if row < 0 or self.busy:
            return
        if row < len(self.uploads):
            self.uploads.pop(row)
        else:
            self.pending_files.pop(row - len(self.uploads))
        self._render_files()
        self._save_local()

    def _save_local(self):
        # Qt document access stays on its owning thread; HTML sanitizing, JSON
        # encoding and all disk operations run on the coalescing writer instead.
        self.draft_writer.save({"html": self.editor.toHtml(), "pending": list(self.pending_files),
            "uploads": [dict(item) for item in self.uploads], "inline": {key: dict(value) for key, value in self.inline_images.items()}})

    def _confirm_submit(self):
        if not submission_html(self.editor.toHtml()) and not self.pending_files and not self.uploads:
            self.status.setText("请先填写答案或选择附件。")
            return
        message = f"课程：{self.task.course_name}\n作业：{self.task.title}\n附件：{len(self.uploads) + len(self.pending_files)} 个\n\n确认上传所选文件并正式提交当前答案？"
        if QMessageBox.question(self, "核对作业提交", message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self._start_operation("submit")

    def _set_busy(self, busy):
        self.busy = busy
        for control in (self.pick_button, self.remove_button, self.upload_button, self.draft_button, self.submit_button, self.reload_button):
            control.setEnabled(not busy and self.valid and not self.data.get("group") and not self.task.locked)
        self.editor.setReadOnly(busy or not self.valid)
        self.cancel_button.setEnabled(busy)
        self.cancel_button.setVisible(busy)
        self.progress.setVisible(busy)

    def _start_operation(self, operation):
        if self.busy or not self.valid or self.host.session is not self.source_session:
            return
        if operation != "reload" and (self.data.get("group") or self.task.locked):
            self.status.setText("此作业请在原平台完成提交；本地草稿会保留。")
            return
        self.operation = operation
        self._save_local()
        self.cancel.clear()
        self._set_busy(True)
        self.status.setText("正在读取平台记录…" if operation == "reload" else "正在处理附件；尚未正式提交。")
        raw_html = self.editor.toHtml()
        pending = list(self.pending_files)
        uploaded = [{"id": entry["id"], "name": entry.get("name", "附件")} for entry in self.uploads]
        inline = dict(self.inline_images)
        expected = self.data["submission"]
        def ensure():
            if self.cancel.is_set() or self.host.session is not self.source_session:
                raise RuntimeError("已停止后续操作；已发出的请求可能已生效，请重读平台记录。")
        def worker():
            session = None
            try:
                content = submission_html(raw_html)
                session = clone_session(self.source_session)
                api = LearningApi(session, ensure)
                if operation == "reload":
                    self._post("done", operation, api.homework(self.task))
                    return
                latest = api.homework(self.task)["submission"]
                if operation != "upload" and any(latest.get(key) != expected.get(key) for key in ("id", "submitted_at", "comment", "is_draft")):
                    raise RuntimeError("平台记录已变化，请先重读平台记录，核对后再提交。本地草稿仍保留。")
                for filename in pending:
                    ensure()
                    last = [0.0]
                    def progress(sent, size):
                        now = time.monotonic()
                        if now - last[0] > 0.15 or sent == size:
                            last[0] = now
                            self._post("progress", Path(filename).name, sent, size)
                    entry = api.upload_file(filename, progress)
                    uploaded.append(entry)
                    self._post("uploaded", filename, entry)
                if operation == "upload":
                    self._post("done", operation, None)
                    return
                prepared = content
                for uri in set(re.findall(r'src="(data:image/[^\"]+)"', content)):
                    ensure()
                    if uri not in inline:
                        encoded = uri.partition(",")[2]
                        raw = base64.b64decode(encoded, validate=True)
                        if len(raw) > 20 * 1024 * 1024:
                            raise ValueError("单张内嵌图片超过 20 MB，请缩小后重试。")
                        directory = self.store.directory / "inline"
                        directory.mkdir(parents=True, exist_ok=True)
                        path = directory / (hashlib.sha256(raw).hexdigest()[:24] + ".png")
                        path.write_bytes(raw)
                        entry = api.upload_file(path)
                        uploaded.append(entry)
                        inline[uri] = {"id": entry["id"], "name": entry["name"], "url": f"{base_url}/api/uploads/{entry['id']}/blob"}
                        self._post("inline", uri, inline[uri])
                    prepared = prepared.replace(uri, inline[uri]["url"])
                ensure()
                result = api.submit(self.task, prepared, uploaded, is_draft=operation == "draft")
                self._post("done", operation, result)
            except Exception as error:
                self._post("error", str(error))
            finally:
                if session is not None:
                    close_cloned_session(session, self.source_session)
        try:
            self.host._run_thread(worker)
        except Exception as error:
            self._set_busy(False)
            self.status.setText(f"无法启动后台任务：{error}")

    def _on_result(self, event):
        if not self.valid or self.host.session is not self.source_session:
            return
        if event[0] == "save_error":
            self.status.setText("本地草稿保存失败，请保留当前窗口并检查磁盘权限。")
        elif event[0] == "progress":
            self.progress.setRange(0, 100)
            self.progress.setValue(int(event[2] * 100 / max(1, event[3])))
            self.status.setText(f"正在上传 {event[1]}：{event[2]}/{event[3]} 字节；尚未正式提交。")
        elif event[0] == "uploaded":
            self.pending_files = [path for path in self.pending_files if path != event[1]]
            self.uploads.append(event[2])
            self._render_files()
            self._save_local()
        elif event[0] == "inline":
            self.inline_images[event[1]] = event[2]
            self.uploads.append(event[2])
            self._save_local()
        elif event[0] == "error":
            self._set_busy(False)
            self.status.setText(event[1])
            self._save_local()
        elif event[0] == "downloaded":
            self.status.setText("作业附件已保存到：" + event[1])
        elif event[0] == "download_error":
            self.status.setText("作业附件下载失败：" + event[1])
        elif event[0] == "done":
            self._set_busy(False)
            if event[1] == "upload":
                self.status.setText("附件已上传，尚未交付；核对文件后点击“交付作业”。")
                if self.pending_files and not self.cancel.is_set():
                    self._start_operation("upload")
            else:
                self.data = event[2]
                self.status.setText(("已回查平台记录；" if event[1] != "reload" else "已重读平台记录；") + self._receipt_text())
                if event[1] != "reload":
                    self._save_local()
                    state = "草稿" if self.data["submission"].get("is_draft") else "已提交"
                    self.host.learning_tasks[self.task.key] = replace(self.task, status=state)
                    self.host._render_learning_tasks()
                    self.host.refresh_learning_tasks(silent=True)

    def _download_teacher_file(self):
        row = self.teacher_files.currentRow()
        values = self.data["detail"].get("uploads", [])
        if row < 0 or row >= len(values) or not self.valid or self.busy:
            return
        directory = QFileDialog.getExistingDirectory(self, "保存作业附件到")
        if not directory:
            return
        from ..courseware import _courseware_items_from_detail, download_courseware
        detail = self.data["detail"]
        item = _courseware_items_from_detail(self.task.course_id, detail, {**detail, "uploads": [values[row]]}, {}, {})[0]
        source = self.source_session
        def download():
            session = clone_session(source)
            try:
                download_courseware(session, item, directory, should_cancel=lambda: self.host.session is not source)
                self._post("downloaded", directory)
            except Exception as error:
                self._post("download_error", str(error))
            finally:
                close_cloned_session(session, source)
        self.host._run_thread(download)

    def invalidate_session(self):
        self.cancel.set()
        self.save_timer.stop()
        self._save_local()
        self.valid = False
        self._set_busy(False)
        self.status.setText("登录会话已变更；草稿已保留，请关闭后从新账号的待办重新打开。")

    def _save_before_quit(self):
        if self.valid and self.host.session is self.source_session:
            self.save_timer.stop()
            self._save_local()

    def closeEvent(self, event):
        if self.busy:
            event.ignore()
            self.cancel.set()
            self.status.setText("已请求取消；等待当前请求结束后可关闭，草稿会保留。")
            return
        self._save_local()
        self.save_timer.stop()
        super().closeEvent(event)
