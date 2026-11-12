"""课程课件页混入（从 app.py 第三刀拆分，机械搬移不改逻辑）。

DashboardWindow 通过继承本混入获得课程课件页能力；方法体逐字保留搬移前的实现，
依赖的实例属性（courseware_* 控件与状态/session/account）与宿主回调
（_academic_year_options/_run_thread/_emit/_show_toast/
_update_nav_badges/_open_path/_ui_palette/log）仍由 DashboardWindow 持有。
事件处理器 _ev_courseware_* 与 _EVENT_HANDLERS 表仍留在 app.py（分发表单一来源）。
"""

from __future__ import annotations

import time
import webbrowser
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..courseware import (
    DownloadCancelledError,
    CourseSummary,
    CoursewareItem,
    download_courseware,
    fetch_courses,
    fetch_courseware,
    sanitize_filename,
)
from ..notifications import friendly_error_message
from ..utils import clone_session
from ..worker_sessions import close_cloned_session
from .core import current_academic_year_label
from .icons import app_asset_path
from .chapter_tree import ChapterTreeMixin
from .local_materials_ui import LocalMaterialsMixin
from ..learning_paths import directory_name, existing_directory, resolve_courseware_directory
from .ui_components import labeled_field


_DOWNLOAD_SOURCE_UNSET = object()
_QUERY_SOURCE_UNSET = object()


class CoursewarePageMixin(LocalMaterialsMixin, ChapterTreeMixin):
    REQUIRED_HOST_ATTRS: tuple[str, ...] = (
        "_academic_year_options",
        "_courseware_selected_keys",
        "_create_courseware_tree",
        "_emit",
        "_open_path",
        "_rebuild_courseware_tree",
        "_require_login",
        "_run_thread",
        "_show_toast",
        "_sync_chapter_tree",
        "_ui_palette",
        "_update_nav_badges",
        "account",
        "courseware_tree",
        "log",
        "session",
    )

    """课程课件页构建、刷新 worker、下载链路与表格渲染（无自有状态，全部经由宿主窗口）。"""

    def _legacy_courseware_table(self):
        """Optional table for standalone legacy hosts without an outline."""
        return getattr(self, "courseware_table")

    def _build_courseware_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        toolbar = QWidget()
        toolbar.setObjectName("FilterBar")
        toolbar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(12)
        self.courseware_academic_year_combo = QComboBox()
        self.courseware_academic_year_combo.addItems(self._academic_year_options())
        self.courseware_academic_year_combo.setCurrentText(current_academic_year_label())
        self.courseware_academic_year_combo.setFixedWidth(160)
        self.courseware_semester_combo = QComboBox()
        self.courseware_semester_combo.addItems(("全部", "第一学期", "第二学期", "第三学期"))
        self.courseware_semester_combo.setFixedWidth(130)
        self.courseware_combo = QComboBox()
        self.courseware_combo.setMinimumWidth(200)
        refresh_courses = QPushButton("刷新课程")
        refresh_items = QPushButton("刷新课件")
        self.courseware_summary = QLabel("登录后自动读取课程和课件。")
        self.courseware_summary.setObjectName("Subtle")
        self.courseware_summary.setWordWrap(True)
        self.courseware_summary.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        first_row = QHBoxLayout()
        first_row.setSpacing(22)
        first_row.addWidget(labeled_field("学年", self.courseware_academic_year_combo))
        first_row.addWidget(labeled_field("学期", self.courseware_semester_combo))
        first_row.addStretch()
        first_row.addWidget(refresh_courses)
        toolbar_layout.addLayout(first_row)
        second_row = QHBoxLayout()
        second_row.addWidget(labeled_field("课程", self.courseware_combo), 1)
        second_row.addWidget(refresh_items)
        add_local = QPushButton("添加本地资料")
        add_local.clicked.connect(lambda: self.add_local_materials())
        second_row.addWidget(add_local)
        manage_local = QPushButton("管理本地资料")
        manage_local.clicked.connect(self.manage_local_materials)
        second_row.addWidget(manage_local)
        toolbar_layout.addLayout(second_row)
        layout.addWidget(toolbar)
        layout.addWidget(self.courseware_summary)

        layout.addWidget(self._create_courseware_tree(), 1)
        self.courseware_empty_frame = QFrame()
        self.courseware_empty_frame.setObjectName("EmptyStateCard")
        empty_layout = QVBoxLayout(self.courseware_empty_frame)
        empty_layout.setContentsMargins(18, 18, 18, 18)
        empty_layout.setSpacing(8)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.courseware_empty_logo = QLabel()
        self.courseware_empty_logo.setObjectName("EmptyWatermark")
        self.courseware_empty_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.courseware_empty_logo.setFixedSize(78, 78)
        empty_logo = QPixmap(str(app_asset_path("xmu-assistant-mark.png")))
        if not empty_logo.isNull():
            self.courseware_empty_logo.setPixmap(
                empty_logo.scaled(
                    70,
                    70,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            opacity = QGraphicsOpacityEffect(self.courseware_empty_logo)
            opacity.setOpacity(0.18)
            self.courseware_empty_logo.setGraphicsEffect(opacity)
        self.courseware_empty_hint = QLabel("登录后会自动读取课程，也可以点击刷新课程。")
        self.courseware_empty_hint.setObjectName("EmptyStateText")
        self.courseware_empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.courseware_empty_logo)
        empty_layout.addWidget(self.courseware_empty_hint)
        layout.addWidget(self.courseware_empty_frame)

        actions = QHBoxLayout()
        download_button = QPushButton("下载所选")
        download_button.setObjectName("PrimaryButton")
        download_button.setToolTip("下载当前选中的课件；需要全部下载时先点全选。")
        cancel_button = QPushButton("取消下载")
        cancel_button.setObjectName("QuietButton")
        cancel_button.clicked.connect(self.cancel_courseware_download)
        select_all_button = QPushButton("全选 / 取消全选")
        select_all_button.setToolTip("选中当前课程下读取到的所有课件。")
        open_button = QPushButton("打开所选资料")
        open_button.setObjectName("QuietButton")
        choose_button = QPushButton("选择目录")
        self.courseware_download_dir = QLineEdit(str(Path.home() / "Downloads" / "XMU-Courseware"))
        actions.addWidget(download_button)
        actions.addWidget(cancel_button)
        actions.addWidget(select_all_button)
        actions.addWidget(open_button)
        actions.addStretch()
        layout.addLayout(actions)
        destination = QHBoxLayout()
        destination.setSpacing(10)
        path_label = QLabel("保存到")
        path_label.setObjectName("Subtle")
        destination.addWidget(path_label)
        destination.addWidget(self.courseware_download_dir, 1)
        destination.addWidget(choose_button)
        layout.addLayout(destination)

        # 信号槽集中连接（B5）：仅位置收拢至 build 尾，连接序与语义不变
        self.courseware_academic_year_combo.currentTextChanged.connect(
            lambda _text: self._apply_courseware_course_filters()
        )
        self.courseware_semester_combo.currentTextChanged.connect(lambda _text: self._apply_courseware_course_filters())
        self.courseware_combo.currentTextChanged.connect(lambda _text: self.refresh_selected_courseware(silent=True))
        refresh_courses.clicked.connect(self.refresh_courseware_courses)
        refresh_items.clicked.connect(self.refresh_selected_courseware)
        download_button.clicked.connect(self.download_selected_courseware)
        select_all_button.clicked.connect(self.select_all_courseware)
        open_button.clicked.connect(self.open_selected_courseware)
        choose_button.clicked.connect(self.choose_courseware_download_dir)
        return page

    def _short_courseware_error(self, error) -> str:
        raw = str(error or "")
        lowered = raw.lower()
        if any(keyword in lowered for keyword in ("timeout", "timed out", "connection", "network", "dns", "proxy")):
            return "网络失败"
        if any(keyword in lowered for keyword in ("401", "403", "unauthorized", "forbidden", "permission")):
            return "登录过期"
        if any(keyword in raw for keyword in ("登录态", "无权访问", "权限", "拒绝")):
            return "登录过期"
        if any(keyword in lowered for keyword in ("404", "not found")):
            return "平台未提供地址"
        if any(keyword in raw for keyword in ("资源", "地址", "reference_id", "签名", "未返回", "缺少", "失效")):
            return "平台未提供地址"
        message = friendly_error_message(error, "courseware")
        if "网络" in message:
            return "网络失败"
        if "权限" in message or "登录已过期" in message:
            return "登录过期"
        if any(word in message for word in ("资源", "地址", "提供")):
            return "平台未提供地址"
        return "下载失败"

    def refresh_courseware_courses(self, silent=False):
        if not self._require_login(silent=silent):
            return
        if self.courseware_courses_refresh_in_progress:
            return
        self.courseware_courses_refresh_in_progress = True
        self.courseware_summary.setText("正在读取课程列表...")
        self.log("开始读取课件课程列表。")
        self._run_thread(
            self._courseware_courses_worker, silent, self.session,
            str((self.account or {}).get("id") or ""),
        )

    def _courseware_courses_worker(
        self, silent=False, worker_source_session=_QUERY_SOURCE_UNSET, worker_account_id=None,
    ):
        # 账号快照：同 _course_rollcalls_worker（体检报告 P1-2）
        if worker_account_id is None:
            worker_account_id = str((self.account or {}).get("id") or "")
        # 克隆会话：与签到情况 worker 并发启动（_refresh_after_login），
        # 不能直接共用主 Session（requests.Session 非线程安全）
        if worker_source_session is _QUERY_SOURCE_UNSET:
            worker_source_session = self.session
        worker_session = None
        try:
            worker_session = clone_session(worker_source_session) if worker_source_session is not None else None
            if worker_session is None:
                self._emit(("courseware_courses_error", "登录状态已变更，请重新登录。", silent, worker_account_id, worker_source_session))
                return
            courses, source = fetch_courses(worker_session)
            self._emit(("courseware_courses", courses, source, worker_account_id, worker_source_session))
        except Exception as exc:
            self._emit(("courseware_courses_error", str(exc), silent, worker_account_id, worker_source_session))
        finally:
            close_cloned_session(worker_session, worker_source_session)

    def refresh_selected_courseware(self, silent=False):
        if not self._require_login(silent=silent):
            return
        course = self._selected_courseware_course()
        if not course:
            self._reset_courseware_selection_prompt()
            if not silent:
                QMessageBox.information(self, "未选择课程", "请先选择一门课程。")
            return
        if getattr(self, "_local_material_course_id", None) != course.course_id:
            self._local_material_rows = []
            self._local_material_course_id = course.course_id
        # 切课时旧请求可能仍占用读取门；先移除旧课程行，避免其文件被下载到新课程目录。
        if any(item.course_id != course.course_id for item in self.courseware_items):
            self.courseware_items = []
            self.courseware_download_status = {}
            self._refresh_courseware_table()
            self._update_nav_badges()
        if self.courseware_refresh_in_progress:
            return
        # 课件读取门空闲后再补本地资料，避免切课瞬间排队一批马上会用旧课程
        # 结果覆盖的本地资料读取。
        self._request_local_materials(course)
        self.courseware_refresh_in_progress = True
        self.courseware_summary.setText(f"正在读取《{course.title}》课件...")
        self.log(f"开始读取课程课件：{course.title}。")
        self._run_thread(
            self._courseware_worker, course, silent, self.session,
            str((self.account or {}).get("id") or ""),
        )

    def _courseware_worker(
        self, course: CourseSummary, silent=False,
        worker_source_session=_QUERY_SOURCE_UNSET, worker_account_id=None,
    ):
        # 账号快照：课件详情是 8 线程池逐活动抓取，大课程可跑几十秒，
        # 晚到结果据此被 handler 丢弃（P1-2，同 courseware_courses 范式）；
        # 先于会话克隆取（同 _courseware_courses_worker）——会话为 None 的早退
        # 分支也要携带，空串会被 late_worker_result_accepted 视为接受
        if worker_account_id is None:
            worker_account_id = str((self.account or {}).get("id") or "")
        # 克隆会话：fetch_courseware 入口的活动列表/modules 请求不走其内部
        # 线程级 clone，在此隔离主 Session（同 _courseware_courses_worker 纪律）
        if worker_source_session is _QUERY_SOURCE_UNSET:
            worker_source_session = self.session
        worker_session = None
        try:
            worker_session = clone_session(worker_source_session) if worker_source_session is not None else None
            if worker_session is None:
                self._emit(("courseware_error", "登录状态已变更，请重新登录。", silent, worker_account_id, worker_source_session))
                return
            # Keep modules caching scoped to the stable GUI session while this
            # worker uses a detached clone for network safety.
            worker_session._xmu_modules_cache_scope = worker_source_session
            self._emit(("courseware", course, fetch_courseware(worker_session, course.course_id), worker_account_id, worker_source_session))
        except Exception as exc:
            self._emit(("courseware_error", str(exc), silent, worker_account_id, worker_source_session))
        finally:
            close_cloned_session(worker_session, worker_source_session)

    def choose_courseware_download_dir(self):
        selected = QFileDialog.getExistingDirectory(
            self,
            "选择课件下载目录",
            self.courseware_download_dir.text() or str(Path.home()),
        )
        if selected:
            self.courseware_download_dir.setText(selected)

    def download_selected_courseware(self):
        rows = self._selected_courseware_rows()
        if not rows:
            QMessageBox.information(self, "未选择", "请先选择课件，或点击全选后再下载。")
            return
        selected_items = [self.courseware_items[row] for row in rows if row < len(self.courseware_items)]
        self._start_courseware_download(selected_items)

    def select_all_courseware(self):
        if not self.courseware_items:
            QMessageBox.information(self, "没有课件", "当前课程还没有读取到课件。")
            return
        if hasattr(self, "courseware_tree"):
            keys = {self._courseware_key(item) for item in self.courseware_items}
            already_all = keys <= self._courseware_checked_keys
            self._courseware_checked_keys = set() if already_all else keys
            self._courseware_selected_keys.clear()
            self._courseware_current_key = None
            self._chapter_check_mode = True
            self._sync_chapter_tree()
            self.courseware_tree.clearSelection()
            self.courseware_tree.setCurrentItem(None)
            text = "已取消全选" if already_all else f"已全选 {len(self.courseware_items)} 条课件，点击下载开始处理。"
            self.courseware_summary.setText(text)
            self._show_toast(text)
            return
        rows = [row for row in range(self._legacy_courseware_table().rowCount()) if not self._legacy_courseware_table().isRowHidden(row)]
        already_all = bool(rows) and all(self._legacy_courseware_table().item(row, 0).checkState() == Qt.CheckState.Checked for row in rows if self._legacy_courseware_table().item(row, 0))
        state = Qt.CheckState.Unchecked if already_all else Qt.CheckState.Checked
        for row in rows:
            if self._legacy_courseware_table().isRowHidden(row):
                continue
            checkbox = self._legacy_courseware_table().item(row, 0)
            if checkbox:
                checkbox.setCheckState(state)
        self._legacy_courseware_table().clearSelection()
        self._legacy_courseware_table().setCurrentCell(-1, -1)
        self._sync_chapter_tree()
        self.courseware_tree.clearSelection()
        self.courseware_tree.setCurrentItem(None)
        text = "已取消全选" if already_all else f"已全选 {len(rows)} 条课件，点击下载开始处理。"
        self.courseware_summary.setText(text)
        self._show_toast(text)

    def _selected_courseware_rows(self) -> list[int]:
        if hasattr(self, "courseware_tree"):
            keys = self._courseware_checked_keys
            if not keys and not self._chapter_check_mode:
                keys = self._courseware_selected_keys
            return [row for row, item in enumerate(self.courseware_items) if self._courseware_key(item) in keys]
        rows = {
            row
            for row in range(self._legacy_courseware_table().rowCount())
            if self._legacy_courseware_table().item(row, 0)
            and not self._legacy_courseware_table().isRowHidden(row)
            and self._legacy_courseware_table().item(row, 0).checkState() == Qt.CheckState.Checked
        }
        if rows or getattr(self, "_chapter_check_mode", False):
            return sorted(rows)
        rows = {
            index.row()
            for index in self._legacy_courseware_table().selectionModel().selectedRows()
            if index.row() >= 0 and not self._legacy_courseware_table().isRowHidden(index.row())
        }
        if not rows and self._legacy_courseware_table().currentRow() >= 0 and not self._legacy_courseware_table().isRowHidden(self._legacy_courseware_table().currentRow()):
            rows.add(self._legacy_courseware_table().currentRow())
        return sorted(rows)

    def activate_selected_courseware(self):
        if getattr(self, "_courseware_current_local_id", None):
            self._open_local_material(self._courseware_current_local_id)
            return
        row = (getattr(self, "_courseware_row_by_key", {}).get(self._courseware_current_key, -1)
               if hasattr(self, "courseware_tree") else self._legacy_courseware_table().currentRow())
        if row < 0 or row >= len(self.courseware_items):
            return
        item = self.courseware_items[row]
        self._start_courseware_download([item])

    def open_selected_courseware(self):
        if getattr(self, "_courseware_current_local_id", None):
            self._open_local_material(self._courseware_current_local_id)
            return
        row = (getattr(self, "_courseware_row_by_key", {}).get(self._courseware_current_key, -1)
               if hasattr(self, "courseware_tree") else self._legacy_courseware_table().currentRow())
        if row < 0 or row >= len(self.courseware_items):
            QMessageBox.information(self, "未选择", "请先选择一个课件活动。")
            return
        item = self.courseware_items[row]
        url = item.entry_url
        if not webbrowser.open(url):
            QMessageBox.critical(self, "打开失败", "无法调用系统浏览器打开平台页面。")

    def _start_courseware_download(self, items: list[CoursewareItem]):
        if self.courseware_download_in_progress:
            QMessageBox.information(self, "正在下载", "请等待当前下载任务完成。")
            return
        course = self._selected_courseware_course()
        if not course:
            return
        if not items:
            return
        if any(item.course_id != course.course_id for item in items):
            QMessageBox.warning(self, "课件已变更", "所选课件不属于当前课程，请等待列表刷新后重新选择。")
            return
        if not self.courseware_download_dir.text().strip():
            # 空目录文本：Path("")/课程名 得相对路径，会在启动目录（开始菜单启动
            # 时可能是系统目录）静默建目录写文件——前置拦截
            QMessageBox.warning(self, "下载目录为空", "请先在上方填写下载目录。")
            return
        self.courseware_download_in_progress = True
        batch_token = object()
        worker_account_id = str((self.account or {}).get("id") or "")
        worker_source_session = self.session
        self.courseware_download_batch_token = batch_token
        for item in items:
            self.courseware_download_status[self._courseware_key(item)] = "下载中"
        self._refresh_courseware_table()
        self._update_nav_badges()
        destination = existing_directory(Path(self.courseware_download_dir.text()), directory_name(course.display_name))
        self.courseware_summary.setText(f"准备处理 {len(items)} 个课件...")
        self._show_toast(f"开始处理 {len(items)} 个课件")
        self._run_thread(
            self._courseware_download_worker,
            items,
            destination,
            batch_token,
            worker_account_id,
            worker_source_session,
        )

    def cancel_courseware_download(self):
        if not self.courseware_download_in_progress:
            self._show_toast("当前没有下载任务")
            return
        self.courseware_download_batch_token = None
        self.courseware_download_in_progress = False
        for key, status in self.courseware_download_status.items():
            if status == "下载中":
                self.courseware_download_status[key] = "已取消"
        self._refresh_courseware_table()
        self._update_nav_badges()
        self.courseware_summary.setText("已取消下载；已完成文件保留，可重新下载")
        self._show_toast("已取消下载")

    def _courseware_download_worker(
        self,
        items: list[CoursewareItem],
        destination: Path,
        batch_token=None,
        worker_account_id: str | None = None,
        worker_source_session=_DOWNLOAD_SOURCE_UNSET,
    ):
        downloaded = []
        entries = []
        errors = []
        raw_errors = []
        # 会话与账号快照（与 _answer_worker 同范式）：下载全程用克隆会话——独立
        # cookiejar，不与 GUI 线程/其它 worker 竞争写主 jar；账号 id 快照用于逐项
        # 校验，防止登出在途时误报失败、换号后用新账号会话续下旧账号课件（跨账号污染）。
        # 批次级 clone 用完即弃：不做模块级缓存（D4 教训——模块级会话会滞留旧 cookie）。
        # 账号 id 必须先于 clone 读取（clone_session 在锁内复制 cookiejar，是毫秒级
        # 窗口）：倒序时换号插在中间会得到「旧账号会话 + 新账号 id」，逐项守卫放行 →
        # 用旧账号会话续下旧账号课件并把旧 cookie merge 进新账号主会话（跨账号污染）。
        if worker_account_id is None:
            worker_account_id = str((self.account or {}).get("id") or "")
        if worker_source_session is _DOWNLOAD_SOURCE_UNSET:
            worker_source_session = self.session
        worker_session = None
        clone_error = None
        try:
            # Explicit None means this batch has no source session; never fall
            # back to a newer self.session after account switching.
            worker_session = (
                clone_session(worker_source_session)
                if worker_source_session is not None
                else None
            )
        except Exception as exc:
            clone_error = exc
            name = "课件下载初始化"
            errors.append(f"{name}：{friendly_error_message(exc, 'courseware')}")
            raw_errors.append(f"{name}：{exc}")
        if clone_error is not None:
            # Do not enter the item loop with an uninitialized worker session;
            # the batch still closes through the same events as normal failure.
            self._emit((
                "merge_session_cookies", worker_session, worker_account_id, batch_token,
            ))
            self._emit((
                "courseware_download_done", batch_token, worker_account_id,
                downloaded, entries, errors, destination, raw_errors,
            ))
            return
        try:
            for index, item in enumerate(items, start=1):
                key = self._courseware_key(item)
                self._emit((
                    "courseware_download_progress", batch_token, worker_account_id,
                    index, len(items), item.filename or item.activity_title, key,
                ))
                # 逐项校验登录状态：网络提交不可中断，只能在每项开始前拦截。
                if (
                    worker_session is None
                    or self.session is None
                    or self.session is not worker_source_session
                    or batch_token is not getattr(self, "courseware_download_batch_token", None)
                    or str((self.account or {}).get("id") or "") != worker_account_id
                ):
                    name = item.filename or item.activity_title
                    errors.append(f"{name}：已取消（登录状态已变更）")
                    self._emit((
                        "courseware_download_item_done", batch_token, worker_account_id,
                        key, "已取消（登录状态已变更）",
                    ))
                    continue
                try:
                    def cancelled():
                        return (
                            self.session is not worker_source_session
                            or batch_token is not self.courseware_download_batch_token
                            or str((self.account or {}).get("id") or "") != worker_account_id
                        )

                    last_progress_at = 0.0

                    def progress(downloaded_bytes, total_bytes):
                        nonlocal last_progress_at
                        now = time.monotonic()
                        if now - last_progress_at < 0.15 and downloaded_bytes != total_bytes:
                            return
                        last_progress_at = now
                        self._emit((
                            "courseware_download_progress", batch_token, worker_account_id,
                            index, len(items), item.filename or item.activity_title, key,
                            downloaded_bytes, total_bytes,
                        ))

                    target = download_courseware(
                        worker_session, item, resolve_courseware_directory(destination, item),
                        progress_callback=progress, should_cancel=cancelled,
                    )
                    if target.suffix.lower() == ".url":
                        entries.append(target)
                    else:
                        downloaded.append(target)
                    self._emit((
                        "courseware_download_item_done", batch_token, worker_account_id,
                        key, "下载成功",
                    ))
                except DownloadCancelledError:
                    self._emit((
                        "courseware_download_item_done", batch_token, worker_account_id,
                        key, "已取消",
                    ))
                    break
                except Exception as exc:
                    name = item.filename or item.activity_title
                    errors.append(f"{name}：{friendly_error_message(exc, 'courseware')}")
                    raw_errors.append(f"{name}：{exc}")
                    self._emit((
                        "courseware_download_item_done", batch_token, worker_account_id,
                        key, f"下载失败：{self._short_courseware_error(exc)}",
                    ))
        finally:
            # Session.close releases sockets but preserves its CookieJar for
            # the queued GUI merge, including when the batch is stale.
            close_cloned_session(worker_session, worker_source_session)
            # M4：无论成功还是中途异常都必须发出完成事件（GUI 据此复位
            # courseware_download_in_progress），否则异常逃逸会让后续下载永久被拦。
            # 先合并克隆内新增/旋转的 cookie 回主会话（GUI 单点写），再发完成事件。
            self._emit((
                "merge_session_cookies", worker_session, worker_account_id, batch_token,
            ))
            self._emit((
                "courseware_download_done", batch_token, worker_account_id,
                downloaded, entries, errors, destination, raw_errors,
            ))

    def _show_courseware_download_result(self, downloaded, entries, errors, destination):
        title = "部分下载失败" if errors else "下载完成"
        icon = QMessageBox.Icon.Warning if errors else QMessageBox.Icon.Information
        message = QMessageBox(icon, title, "", QMessageBox.StandardButton.Ok, self)
        message.setText(f"文件 {len(downloaded)} 个，入口 {len(entries)} 个，失败 {len(errors)} 个。")
        details = ""
        if errors:
            details = "\n".join(errors[:20])
            message.setInformativeText("有些课件没有成功处理，下面列出了原因。")
            message.setDetailedText(details)
        else:
            message.setInformativeText(f"已保存到：\n{destination}")
        open_button = message.addButton("打开下载目录", QMessageBox.ButtonRole.ActionRole)
        message.exec()
        if message.clickedButton() is open_button:
            self._open_path(destination)

    def _selected_courseware_course(self) -> CourseSummary | None:
        return self.courseware_course_by_display.get(self.courseware_combo.currentText())

    def _courseware_course_matches_filters(self, course: CourseSummary) -> bool:
        academic_year = self.courseware_academic_year_combo.currentText().strip()
        if academic_year and academic_year not in course.term and academic_year not in course.search_text:
            return False

        semester = self.courseware_semester_combo.currentText().strip()
        semester_code = course.semester_code or course.term
        if semester == "第一学期":
            return semester_code.endswith("-1")
        if semester == "第二学期":
            return semester_code.endswith("-2")
        if semester == "第三学期":
            return semester_code.endswith("-3")
        return True

    def _refresh_courseware_course_combo(self, previous: str = "") -> list[str]:
        self.courseware_course_by_display = {}
        displays = []
        for course in self.courseware_courses:
            if not self._courseware_course_matches_filters(course):
                continue
            display = course.display_name
            if display in self.courseware_course_by_display:
                display = f"{display}  ({course.course_id})"
            self.courseware_course_by_display[display] = course
            displays.append(display)

        self.courseware_combo.blockSignals(True)
        self.courseware_combo.clear()
        self.courseware_combo.addItem("请选择课程")
        self.courseware_combo.addItems(displays)
        if previous in self.courseware_course_by_display:
            self.courseware_combo.setCurrentText(previous)
        self.courseware_combo.blockSignals(False)
        return displays

    def _apply_courseware_course_filters(self):
        previous = self.courseware_combo.currentText()
        displays = self._refresh_courseware_course_combo(previous)
        if not self._selected_courseware_course():
            self._reset_courseware_selection_prompt()
        self.log(f"课件课程筛选完成，当前显示 {len(displays)} 门。")

    def _courseware_can_download(self, item: CoursewareItem) -> bool:
        return bool(item.entry_url) or bool(item.upload_id)

    def _set_courseware_courses(self, courses: list[CourseSummary], source: str):
        previous = self.courseware_combo.currentText()
        self.courseware_courses = courses
        displays = self._refresh_courseware_course_combo(previous)

        self.log(f"课件课程列表读取完成，共 {len(courses)} 门，当前筛选 {len(displays)} 门；接口：{source}")
        if self._selected_courseware_course():
            self.courseware_summary.setText(f"共 {len(courses)} 门课程；当前显示 {len(displays)} 门")
        else:
            self._reset_courseware_selection_prompt()
        self._refresh_courseware_empty_state()

    def _set_courseware_items(self, course: CourseSummary, items: list[CoursewareItem]):
        selected = self._selected_courseware_course()
        if not selected:
            self._refresh_courseware_empty_state()
            return
        if selected.course_id != course.course_id:
            self.refresh_selected_courseware(silent=True)
            return
        self.courseware_items = items
        self.courseware_download_status = {}
        # Both operations update the empty state. Defer outline synchronization
        # until the new table and new outline refer to the same item sequence.
        self._defer_chapter_sync = True
        try:
            self._refresh_courseware_table()
            self._rebuild_courseware_tree()
        finally:
            self._defer_chapter_sync = False
        direct = sum(1 for item in items if item.upload_id and item.upload_status == "ready")
        entries = sum(1 for item in items if not item.upload_id and item.entry_url)
        missing = sum(1 for item in items if not item.upload_id and not item.entry_url)
        self.courseware_summary.setText(f"已读取 {len(items)} 条课件；可直接下载 {direct} 条；需保存入口 {entries} 条；受限 {missing} 条")
        self.log(f"课程课件读取完成：{course.title}，共 {len(items)} 条，直接下载 {direct} 条，入口 {entries} 条。")
        self._refresh_courseware_empty_state()
        self._update_nav_badges()

    def _refresh_courseware_table(self):
        self._courseware_row_by_key = {self._courseware_key(item): row for row, item in enumerate(self.courseware_items)}
        if hasattr(self, "courseware_tree"):
            keys = self._courseware_row_by_key.keys()
            self._courseware_checked_keys.intersection_update(keys)
            self._courseware_selected_keys.intersection_update(keys)
            if self._courseware_current_key not in keys:
                self._courseware_current_key = None
            self._refresh_courseware_empty_state()
            return
        type_names = {
            "material": "资料",
            "online_video": "视频",
            "slide": "课件",
            "web_link": "链接",
            "page": "页面",
            "scorm": "SCORM",
            "h5_courseware": "H5课件",
        }
        # 旧表保存自身的稳定标识；此时 courseware_items 可能已经被新列表替换，
        # 不能再用旧行号索引新列表，否则重排/删除会把用户选择转移到别的文件。
        checked_keys = set()
        selected_keys = set()
        current_key = None
        current_column = self._legacy_courseware_table().currentColumn()
        selected_rows = {index.row() for index in self._legacy_courseware_table().selectionModel().selectedRows()}
        for row in range(self._legacy_courseware_table().rowCount()):
            cell = self._legacy_courseware_table().item(row, 0)
            if cell is None:
                continue
            key = cell.data(Qt.ItemDataRole.UserRole)
            if cell.checkState() == Qt.CheckState.Checked:
                checked_keys.add(key)
            if row in selected_rows:
                selected_keys.add(key)
            if row == self._legacy_courseware_table().currentRow():
                current_key = key
        # 一次 setRowCount 预留全部行后直接 setItem：逐行 insertRow 会让 Qt 每行
        # 内部重排（O(n²)）——下载批次里每次进度/完成事件都整表重建，100 项课件即
        # 200 次 × O(n²) 的行插入；首页事件表已是 setRowCount(n)+setItem 的 O(n) 版。
        self._legacy_courseware_table().setRowCount(len(self.courseware_items))
        self._legacy_courseware_table().clearSelection()
        self._legacy_courseware_table().setCurrentCell(-1, -1)
        for row_index, item in enumerate(self.courseware_items):
            key = self._courseware_key(item)
            checkbox = QTableWidgetItem("")
            checkbox.setData(Qt.ItemDataRole.UserRole, key)
            checkbox.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            checkbox.setCheckState(
                Qt.CheckState.Checked
                if key in checked_keys
                else Qt.CheckState.Unchecked
            )
            checkbox.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._legacy_courseware_table().setItem(row_index, 0, checkbox)

            # The visible outline already owns these details. Keep only the
            # selection cell in the hidden backing table when it exists; hosts
            # without an outline retain the original complete table.
            if not hasattr(self, "courseware_tree"):
                values = (item.module_name, item.activity_title, item.filename or "-",
                    type_names.get(item.activity_type, item.media_type or item.activity_type or "-"),
                    self.courseware_download_status.get(key, "可下载"))
                for column, value in enumerate(values, start=1):
                    cell = QTableWidgetItem(str(value))
                    if column in (1, 4, 5):
                        cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if column == 5:
                        cell.setForeground(QColor(self._courseware_status_color(str(value))))
                    self._legacy_courseware_table().setItem(row_index, column, cell)
            if key == current_key:
                self._legacy_courseware_table().setCurrentCell(
                    row_index, max(0, current_column), QItemSelectionModel.SelectionFlag.NoUpdate,
                )
            if key in selected_keys:
                self._legacy_courseware_table().selectionModel().select(
                    self._legacy_courseware_table().model().index(row_index, 0),
                    QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
                )
        self._refresh_courseware_empty_state()

    def _update_courseware_status(self, key):
        """Update one status cell without rebuilding rows or changing selection."""
        row = getattr(self, "_courseware_row_by_key", {}).get(key)
        status = self.courseware_download_status.get(key, "可下载")
        if row is not None and hasattr(self, "courseware_table"):
            cell = self._legacy_courseware_table().item(row, 5)
            if cell is not None:
                cell.setText(status)
                cell.setForeground(QColor(self._courseware_status_color(status)))
        leaf = getattr(self, "_chapter_leaf_by_key", {}).get(key)
        if leaf is not None and leaf.text(2) != status:
            previous = self.courseware_tree.blockSignals(True)
            try:
                leaf.setText(2, status)
            finally:
                self.courseware_tree.blockSignals(previous)

    def _refresh_courseware_empty_state(self):
        if not hasattr(self, "courseware_empty_hint"):
            return
        if self.courseware_refresh_in_progress or self.courseware_courses_refresh_in_progress:
            text = "正在读取课程课件，请稍候。"
        elif not self.account:
            text = "登录后会自动读取课程，也可以点击刷新课程。"
        elif not self.courseware_courses:
            text = "还没有读取到课程，请点击刷新课程或稍后再试。"
        elif not self._selected_courseware_course():
            text = "请选择课程"
        elif not self.courseware_items and not getattr(self, "_local_material_rows", []):
            text = "这门课暂时没有读取到课件。"
        else:
            text = ""
        self.courseware_empty_hint.setText(text)
        self.courseware_empty_frame.setVisible(bool(text))
        if hasattr(self, "courseware_table"):
            self._legacy_courseware_table().hide()
        if hasattr(self, "courseware_tree"):
            self.courseware_tree.setVisible(not bool(text) or bool(self.courseware_items))
            if not getattr(self, "_defer_chapter_sync", False):
                self._sync_chapter_tree()

    def _reset_courseware_selection_prompt(self):
        if not hasattr(self, "courseware_combo"):
            return
        if self.courseware_combo.count() and self.courseware_combo.currentIndex() != 0:
            self.courseware_combo.blockSignals(True)
            self.courseware_combo.setCurrentIndex(0)
            self.courseware_combo.blockSignals(False)
        self.courseware_items = []
        self._local_material_rows = []
        self._courseware_current_local_id = None
        self.courseware_download_status = {}
        self._refresh_courseware_table()
        self.courseware_summary.setText("请选择课程")
        self._rebuild_courseware_tree()
        self._update_nav_badges()

    def _courseware_key(self, item: CoursewareItem) -> str:
        return f"{item.course_id}:{item.activity_id}:{item.upload_id}:{item.filename}"

    def _courseware_status_color(self, status: str) -> str:
        pal = self._ui_palette()
        if status.startswith("下载失败") or status.startswith("已取消"):
            # 已取消（登录状态已变更）不是可下载态：回落绿色会伪装成可下载，
            # 与失败同用警示色，提示需要重新发起下载
            return pal["cw_failed"]
        return {
            "可下载": pal["cw_ready"],
            "下载中": pal["cw_downloading"],
            "下载成功": pal["cw_success"],
            "下载失败": pal["cw_failed"],
        }.get(status, pal["cw_ready"])
