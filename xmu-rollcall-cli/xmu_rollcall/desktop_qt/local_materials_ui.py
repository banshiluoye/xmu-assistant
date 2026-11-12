"""Native local-course-material controls. File I/O runs on the existing worker pool."""

from __future__ import annotations

from pathlib import Path
import uuid

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QHBoxLayout,
)

from ..local_materials import LocalMaterialStore

ROLE_LOCAL = int(Qt.ItemDataRole.UserRole) + 90


class LocalMaterialsMixin:
    def _visible_local_materials(self):
        account = self.account or {}
        course = self._selected_courseware_course()
        if not course or str(account.get("id")) != getattr(
            self, "_local_material_owner", None
        ):
            return []
        return [
            r
            for r in getattr(self, "_local_material_rows", [])
            if r["course_id"] == course.course_id
        ]

    def _local_store(self, account=None):
        account = account or self.account or {}
        return LocalMaterialStore(account.get("id", ""), account.get("username", ""))

    def add_local_materials(self, filenames=None):
        course = self._selected_courseware_course()
        if not course or not self.account:
            QMessageBox.information(self, "选择课程", "请先选择要添加资料的课程。")
            return
        if getattr(self, "_local_import_busy", False):
            return
        if not filenames:
            filenames, _ = QFileDialog.getOpenFileNames(self, "添加课程本地资料")
        if not filenames:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("添加本地资料")
        dialog.setMinimumWidth(440)
        layout = QVBoxLayout(dialog)
        note = QLabel(
            f"已选择 {len(filenames)} 个文件。资料仅保存在本机，不上传教学平台。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        chapter = QComboBox()
        chapter.addItem("补充资料", ("补充资料", ""))
        seen = set()
        for item in self.courseware_items:
            key = (item.module_name, item.module_id)
            if item.module_name and key not in seen:
                seen.add(key)
                chapter.addItem(item.module_name, key)
        mode = QComboBox()
        mode.addItem("复制到课程目录", "copy")
        mode.addItem("引用原位置", "reference")
        threshold = QSpinBox()
        threshold.setRange(1, 2048)
        threshold.setSuffix(" MiB")
        threshold.setValue(
            self._local_store().read().get("reference_threshold_mib", 50)
        )
        form.addRow("归入章节", chapter)
        form.addRow("导入方式", mode)
        form.addRow("超过此大小自动引用", threshold)
        layout.addLayout(form)
        hint = QLabel(
            "大文件只记录位置；原文件移动后可重新定位。移除条目不会删除文件。"
        )
        hint.setWordWrap(True)
        hint.setObjectName("Subtle")
        layout.addWidget(hint)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("添加")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            dialog.deleteLater()
            return
        if not self.account:
            dialog.deleteLater()
            return
        account = dict(self.account)
        store = self._local_store(account)
        from ..learning_paths import existing_directory

        course_directory = existing_directory(
            Path(self.courseware_download_dir.text()).expanduser(),
            self._local_course_directory_name(course),
        )
        chapter_name, chapter_id = chapter.currentData()
        self._local_import_busy = True
        self.courseware_summary.setText("正在添加本地资料；大文件自动保留在原位置…")
        selected_mode, threshold_value = mode.currentData(), threshold.value()
        dialog.deleteLater()

        def ensure():
            if str((self.account or {}).get("id")) != str(account["id"]):
                raise ValueError("账号已切换，停止后续导入")

        def worker():
            try:
                added, errors = store.add(
                    filenames,
                    course.course_id,
                    course.title,
                    course_directory,
                    chapter=chapter_name,
                    chapter_id=chapter_id,
                    mode=selected_mode,
                    threshold_mib=threshold_value,
                    ensure=ensure,
                )
                message = f"已添加 {len(added)} 项本地资料，引用 {sum(r['mode'] == 'reference' for r in added)} 项"
                if errors:
                    message += f"；{len(errors)} 项未添加：" + "；".join(
                        f"{r['name']}：{r['error']}" for r in errors[:3]
                    )
                self._emit(
                    (
                        "local_materials",
                        str(account["id"]),
                        course.course_id,
                        store.items(course.course_id),
                        message,
                        True,
                    )
                )
            except Exception as error:
                self._emit(
                    (
                        "local_materials",
                        str(account["id"]),
                        course.course_id,
                        [],
                        f"添加失败：{error}",
                        True,
                    )
                )

        self._run_thread(worker)

    @staticmethod
    def _local_course_directory_name(course):
        from ..learning_paths import directory_name

        return directory_name(course.display_name)

    def _request_local_materials(self, course):
        if not self.account:
            return
        account = dict(self.account)
        token = uuid.uuid4().hex
        self._local_load_token = token

        def worker():
            try:
                rows = self._local_store(account).items(course.course_id)
                message = ""
            except Exception as error:
                rows, message = [], f"本地资料清单读取失败：{error}"
            self._emit(
                (
                    "local_materials",
                    str(account["id"]),
                    course.course_id,
                    rows,
                    message,
                    False,
                    token,
                )
            )

        self._run_thread(worker)

    def _ev_local_materials(self, event):
        if event[5]:
            self._local_import_busy = False
        course = self._selected_courseware_course()
        if (
            not self.account
            or str(self.account["id"]) != event[1]
            or not course
            or course.course_id != event[2]
        ):
            return
        if len(event) > 6 and event[6] != getattr(self, "_local_load_token", None):
            return
        changed = (getattr(self, "_local_material_rows", []) != event[3]
                   or getattr(self, "_local_material_owner", None) != event[1])
        self._local_material_rows = event[3]
        self._local_material_owner = event[1]
        if changed:
            self._keep_courseware_expansion = True
            try:
                self._rebuild_courseware_tree()
            finally:
                self._keep_courseware_expansion = False
            self._refresh_courseware_empty_state()
        if event[4]:
            self.courseware_summary.setText(event[4])

    def _open_local_material(self, resource_id, folder=False):
        account = dict(self.account or {})
        store = self._local_store(account)

        def worker():
            try:
                target = store.resolve(resource_id)
                path, error = str(target.parent if folder else target), ""
            except (OSError, ValueError) as exception:
                path, error = "", str(exception)
            self._emit(("local_material_open", str(account.get("id")), path, error))

        self._run_thread(worker)

    def _ev_local_material_open(self, event):
        if str((self.account or {}).get("id")) != event[1]:
            return
        if event[3]:
            QMessageBox.information(self, "资料暂不可用", event[3])
        else:
            self._open_path(Path(event[2]))

    def manage_local_materials(self):
        course = self._selected_courseware_course()
        if not course or not self.account:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("管理本地资料")
        dialog.resize(660, 370)
        layout = QVBoxLayout(dialog)
        listing = QListWidget()
        layout.addWidget(listing)
        status = QLabel("移除只取消课程关联，保留硬盘上的文件。")
        status.setWordWrap(True)
        layout.addWidget(status)
        actions = QHBoxLayout()

        def refresh():
            listing.clear()
            for row in self._local_store().items(course.course_id):
                listing.addItem(
                    f"{row['name']}  ·  {row['chapter']}  ·  {'引用原位置' if row['mode'] == 'reference' else '本地文件'}"
                )
                item = listing.item(listing.count() - 1)
                item.setData(Qt.ItemDataRole.UserRole, row["resource_id"])
                item.setToolTip(row["path"])

        def selected():
            item = listing.currentItem()
            return item.data(Qt.ItemDataRole.UserRole) if item else None

        def remove():
            if selected():
                self._local_store().remove(selected())
                refresh()
                self._request_local_materials(course)

        def relocate():
            key = selected()
            if key:
                filename, _ = QFileDialog.getOpenFileName(dialog, "重新定位资料")
                if filename:
                    try:
                        self._local_store().relocate(key, filename)
                        refresh()
                        self._request_local_materials(course)
                    except (OSError, ValueError) as error:
                        status.setText(str(error))

        for title, callback in (
            (
                "打开",
                lambda: self._open_local_material(selected()) if selected() else None,
            ),
            (
                "所在文件夹",
                lambda: self._open_local_material(selected(), folder=True) if selected() else None,
            ),
            ("重新定位", relocate),
            ("移除条目", remove),
        ):
            button = QPushButton(title)
            button.clicked.connect(callback)
            actions.addWidget(button)
        close = QPushButton("关闭")
        close.clicked.connect(dialog.accept)
        actions.addStretch()
        actions.addWidget(close)
        layout.addLayout(actions)
        refresh()
        dialog.exec()
        dialog.deleteLater()
