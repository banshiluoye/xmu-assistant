"""Learning inbox, independent polling and session-scoped background reads."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import time
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                              QDialog, QMessageBox, QPushButton, QVBoxLayout, QWidget)

from ..learning import LearningApi, LearningStore, LearningTask, LOCAL_TZ, TASK_TYPES
from ..notifications import NotificationMessage
from ..utils import SessionExpiredError, changed_session_cookies, clone_session, snapshot_session_cookies
from ..worker_sessions import close_cloned_session
from .ui_components import labeled_field


class LearningPageMixin:
    def _build_learning_page(self):
        self.learning_tasks = {}
        self._learning_jobs = {}
        self._learning_next_poll = 0
        self._learning_failures = 0
        self._learning_last_sync = ""
        self._learning_store = None
        self._learning_courses = set()
        self._learning_notified = set()
        self._learning_loading = False
        self._learning_verify_attempts = set()
        self._homework_windows = []
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.learning_search = QLineEdit()
        self.learning_search.setPlaceholderText("搜索待办或课程")
        self.learning_search.setAccessibleName("搜索学习待办")
        self.learning_search.setMinimumWidth(180)
        self.learning_course_button = QPushButton()
        self.learning_course_button.setText("全部课程")
        self.learning_course_button.setMinimumWidth(125)
        self.learning_course_button.clicked.connect(self._choose_learning_courses)
        self.learning_type = QComboBox()
        self.learning_type.addItem("全部类型", "")
        for value, label in TASK_TYPES.items():
            self.learning_type.addItem(label, value)
        self.learning_status = QComboBox()
        self.learning_status.addItems(["全部状态", "未完成", "已提交", "草稿", "待核实"])
        self.learning_deadline = QComboBox()
        self.learning_deadline.addItems(["未过期", "全部截止时间", "24 小时内", "7 天内", "已逾期", "无截止时间"])
        toolbar.addWidget(self.learning_search, 1)
        toolbar.addWidget(self.learning_course_button)
        refresh = QPushButton("立即刷新")
        refresh.clicked.connect(lambda: self.refresh_learning_tasks())
        toolbar.addWidget(refresh)
        layout.addLayout(toolbar)
        filters = QHBoxLayout()
        filters.setSpacing(18)
        for label, control in (("类型", self.learning_type), ("状态", self.learning_status), ("截止", self.learning_deadline)):
            control.setMinimumWidth(125)
            filters.addWidget(labeled_field(label, control), 1)
        layout.addLayout(filters)
        options = QHBoxLayout()
        options.setSpacing(14)
        self.learning_auto_check = QCheckBox("后台刷新（沿用监控频率）")
        self.learning_auto_check.setChecked(True)
        self.learning_notify_check = QCheckBox("新增与临期提醒")
        self.learning_notify_check.setChecked(True)
        self.learning_interval_label = QLabel()
        self.learning_interval_label.setObjectName("Subtle")
        options.addWidget(self.learning_auto_check)
        options.addWidget(self.learning_notify_check)
        options.addWidget(self.learning_interval_label)
        options.addStretch()
        history = QPushButton("读取所选课程作业状态")
        history.setObjectName("QuietButton")
        history.setToolTip("在课程筛选中选一门课程，读取包含已提交作业的完整列表")
        history.clicked.connect(self._load_learning_history)
        options.addWidget(history)
        layout.addLayout(options)
        self.learning_summary = QLabel("登录后自动同步待办。已提交作业可通过“读取所选课程作业状态”查询。")
        self.learning_summary.setWordWrap(True)
        self.learning_summary.setObjectName("Subtle")
        layout.addWidget(self.learning_summary)
        self.learning_table = self._make_table(("课程", "待办", "类型", "截止时间", "状态"), (200, 420, 80, 170, 100))
        for column, width in ((0, 160), (2, 70), (3, 135), (4, 100)):
            self.learning_table.setColumnWidth(column, width)
        self.learning_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.learning_table.cellDoubleClicked.connect(lambda *_: self.open_learning_task())
        layout.addWidget(self.learning_table, 1)
        actions = QHBoxLayout()
        edit = QPushButton("查看 / 交作业")
        edit.setObjectName("PrimaryButton")
        edit.clicked.connect(self.open_learning_task)
        original = QPushButton("默认浏览器打开")
        original.clicked.connect(lambda: self.open_learning_task(browser=True))
        actions.addStretch()
        original.setObjectName("QuietButton")
        actions.addWidget(original)
        actions.addWidget(edit)
        layout.addLayout(actions)
        for control in (self.learning_type, self.learning_status, self.learning_deadline):
            control.currentIndexChanged.connect(self._learning_filter_changed)
        self.learning_search.textChanged.connect(self._learning_filter_changed)
        self.learning_auto_check.toggled.connect(self._learning_filter_changed)
        self.learning_notify_check.toggled.connect(self._learning_filter_changed)
        return page

    def _learning_preferences(self):
        return {"courses": sorted(self._learning_courses), "kind": self.learning_type.currentData(),
                "status": self.learning_status.currentText(), "deadline": self.learning_deadline.currentText(),
                "search": self.learning_search.text(), "enabled": self.learning_auto_check.isChecked(),
                "notify": self.learning_notify_check.isChecked(), "deadline_filter_version": 2}

    def _learning_filter_changed(self, *_):
        self._render_learning_tasks()
        if self._learning_store and not self._learning_loading:
            try:
                self._learning_store.write("settings", self._learning_preferences())
            except OSError as error:
                self.learning_summary.setText(f"筛选设置保存失败：{error}")

    def _reset_learning_session(self, *, logged_in=False):
        self._learning_jobs = {}
        self.learning_tasks = {}
        self._learning_store = None
        self._learning_notified = set()
        self._learning_last_sync = ""
        self._learning_next_poll = 0
        self._learning_failures = 0
        self._learning_verify_attempts = set()
        for window in self._homework_windows:
            window.invalidate_session()
        self._homework_windows = []
        self._learning_loading = True
        try:
            settings = {}
            if logged_in:
                self._learning_store = LearningStore(self.account["id"])
                cached = self._learning_store.read("tasks", {})
                self._learning_last_sync = cached.get("last_sync", "")
                self._learning_notified = set(cached.get("notified", []))
                for value in cached.get("tasks", []):
                    try:
                        item = LearningTask(**value)
                        self.learning_tasks[item.key] = item
                    except (TypeError, ValueError):
                        continue
                settings = self._learning_store.read("settings", {})
            self._learning_courses = set(settings.get("courses", []))
            self.learning_course_button.setText("全部课程" if not self._learning_courses else f"已选 {len(self._learning_courses)} 门")
            self.learning_search.setText(settings.get("search", ""))
            self.learning_type.setCurrentIndex(max(0, self.learning_type.findData(settings.get("kind", ""))))
            self.learning_status.setCurrentText(settings.get("status", "全部状态"))
            deadline = settings.get("deadline", "未过期")
            if settings.get("deadline_filter_version", 0) < 2 and deadline == "全部截止时间":
                deadline = "未过期"
            self.learning_deadline.setCurrentText(deadline)
            self.learning_auto_check.setChecked(settings.get("enabled", True))
            self.learning_notify_check.setChecked(settings.get("notify", True))
        finally:
            self._learning_loading = False
        self._render_learning_tasks()
        if logged_in:
            self.refresh_learning_tasks(silent=True)
        else:
            self.learning_summary.setText("登录后自动同步待办。")

    def _learning_course_names(self):
        # Follow the courseware selector's platform order and current filters;
        # cached todo-only courses follow afterward in their original order.
        names = {}
        for index in range(self.courseware_combo.count()):
            course = self.courseware_course_by_display.get(self.courseware_combo.itemText(index))
            if course:
                names[course.course_id] = course.title
        for course in self.courseware_courses:
            names.setdefault(course.course_id, course.title)
        for item in self.learning_tasks.values():
            names.setdefault(item.course_id, item.course_name)
        return names

    def _choose_learning_courses(self):
        from .course_picker import CoursePicker
        picker = CoursePicker(self, self._learning_course_names(), self._learning_courses)
        if picker.exec() == QDialog.DialogCode.Accepted:
            self._learning_courses = picker.selection
            self.learning_course_button.setText("全部课程" if not picker.selection else f"已选 {len(picker.selection)} 门")
            self._learning_filter_changed()

    def _select_learning_course(self, course_id, checked):
        if course_id is None:
            self._learning_courses.clear()
        elif checked:
            self._learning_courses.add(course_id)
        else:
            self._learning_courses.discard(course_id)
        self.learning_course_button.setText("全部课程" if not self._learning_courses else f"已选 {len(self._learning_courses)} 门")
        self._learning_filter_changed()

    def _filtered_learning_tasks(self):
        now = datetime.now(LOCAL_TZ)
        search = self.learning_search.text().strip().casefold()
        result = []
        for item in self.learning_tasks.values():
            if self._learning_courses and item.course_id not in self._learning_courses:
                continue
            if self.learning_type.currentData() and item.kind != self.learning_type.currentData():
                continue
            if self.learning_status.currentText() != "全部状态" and item.status != self.learning_status.currentText():
                continue
            if search and search not in (item.title + " " + item.course_name).casefold():
                continue
            due = item.due
            limit = self.learning_deadline.currentText()
            if limit == "未过期" and due is not None and due < now:
                continue
            if limit in ("24 小时内", "7 天内") and (due is None or not now <= due <= now + timedelta(days=1 if limit == "24 小时内" else 7)):
                continue
            if limit == "已逾期" and (due is None or due >= now):
                continue
            if limit == "无截止时间" and due is not None:
                continue
            result.append(item)
        return sorted(result, key=lambda item: (item.due is None, item.due or datetime.max.replace(tzinfo=LOCAL_TZ), item.course_name, item.title))

    def _render_learning_tasks(self):
        values = self._filtered_learning_tasks()
        self._set_table_rows(self.learning_table,
            [(item.course_name, item.title, TASK_TYPES.get(item.kind, item.kind), item.due.strftime("%m-%d %H:%M") if item.due else "无截止时间", item.status + (" · 未解锁" if item.locked else "")) for item in values],
            [item.key for item in values], centered_columns=(2, 3, 4), status_column=4)
        count = sum(item.status == "未完成" for item in values)
        if hasattr(self, "learning_shortcut"):
            self.learning_shortcut.setText(f"学习待办 {count}")
        if "学习待办" in self.nav_titles:
            self.nav.item(self.nav_titles.index("学习待办")).setText(f"学习待办 ({count})")

    def _tick_learning(self):
        interval = self._learning_interval()
        self.learning_interval_label.setText(f"每 {interval} 秒")
        if self.session and self.learning_auto_check.isChecked() and time.monotonic() >= self._learning_next_poll:
            self.refresh_learning_tasks(silent=True)

    def _learning_interval(self):
        from ..config import get_rollcall_settings
        return get_rollcall_settings(self.account)["poll_interval_seconds"] if self.account else self._current_poll_interval()

    def _start_learning_job(self, kind, operation):
        if not self.session or kind in self._learning_jobs:
            return False
        source = self.session
        token = object()
        self._learning_jobs[kind] = token
        def worker():
            session = None
            try:
                session = clone_session(source)
                before = snapshot_session_cookies(session)
                payload = {"ok": True, "value": operation(LearningApi(session))}
                payload["cookie_changes"] = changed_session_cookies(before, snapshot_session_cookies(session))
            except Exception as error:
                payload = {"ok": False, "message": str(error), "expired": isinstance(error, SessionExpiredError)}
            finally:
                if session is not None:
                    close_cloned_session(session, source)
            self._emit(("learning_result", kind, source, token, payload))
        try:
            self._run_thread(worker)
        except Exception:
            self._learning_jobs.pop(kind, None)
            raise
        return True

    def refresh_learning_tasks(self, silent=False):
        if not self._require_login(silent=silent):
            return
        if not silent:
            # 手动刷新允许重新核对上次未能读取的课程记录；后台轮询沿用本会话
            # 已尝试过的课程，避免每个周期重复请求。
            self._learning_verify_attempts.clear()
        self._learning_next_poll = time.monotonic() + self._learning_interval()
        if self._start_learning_job("todos", lambda api: api.todos()):
            self.learning_summary.setText("正在同步待办；保留上次结果。")

    def _load_learning_history(self):
        if len(self._learning_courses) != 1:
            QMessageBox.information(self, "选择课程", "请在课程筛选中只选择一门课，再读取其完整作业状态。")
            return
        course_id = next(iter(self._learning_courses))
        name = self._learning_course_names().get(course_id, course_id)
        self._start_learning_job("history", lambda api: api.homework_list(course_id, name))
        self.learning_summary.setText("正在读取所选课程的完整作业状态。")

    def _selected_learning_task(self):
        row = self.learning_table.currentRow()
        cell = self.learning_table.item(row, 0) if row >= 0 else None
        return self.learning_tasks.get(cell.data(Qt.ItemDataRole.UserRole)) if cell else None

    def open_learning_task(self, _checked=False, *, browser=False):
        task = self._selected_learning_task()
        if task is None:
            self._show_toast("请先选择一项待办", ok=False)
            return
        if browser or task.kind != "homework":
            if not webbrowser.open(task.url):
                self._show_toast("无法打开默认浏览器", ok=False)
            return
        for window in self._homework_windows:
            if window.valid and window.task.key == task.key:
                window.show()
                window.raise_()
                window.activateWindow()
                return
        self._start_learning_job("detail", lambda api: (task, api.homework(task)))
        self.learning_summary.setText("正在读取作业要求与提交记录。")

    def _ev_learning_result(self, event):
        kind, source, token, payload = event[1:5]
        if self.session is not source or self._learning_jobs.get(kind) is not token:
            return
        self._learning_jobs.pop(kind, None)
        if not payload["ok"]:
            self.learning_summary.setText(f"同步未完成：{payload['message']}；上次成功：{self._learning_last_sync or '尚未同步'}")
            if kind == "todos":
                self._learning_failures += 1
                self._learning_next_poll = time.monotonic() + max(self._learning_interval(), min(300, 5 * 2 ** min(self._learning_failures, 6)))
            if payload.get("expired"):
                self.logout(expired=True)
            return
        if changes := payload.get("cookie_changes"):
            self._sync_shared_session(source, changes)
        if kind == "detail":
            from .homework_window import HomeworkWindow
            task, data = payload["value"]
            for window in self._homework_windows:
                if window.valid and window.task.key == task.key:
                    window.show()
                    window.raise_()
                    window.activateWindow()
                    return
            window = HomeworkWindow(self, task, data, self._learning_store)
            self._homework_windows.append(window)
            window.show()
            self.learning_summary.setText("已读取作业要求与提交记录。")
            return
        if kind == "verify":
            self._apply_learning_verification(payload["value"])
            return
        values = payload["value"]
        before = dict(self.learning_tasks)
        unknown = []
        if kind == "todos":
            self._learning_failures = 0
            keys = {item.key for item in values}
            for key, value in list(self.learning_tasks.items()):
                if key in keys or value.status not in ("未完成", "待核实"):
                    continue
                replacement = value if value.status == "待核实" else replace(value, status="待核实")
                self.learning_tasks[key] = replacement
                unknown.append(replacement)
            # 待办接口不携带完整提交状态：已由平台记录确认的提交/草稿不能被
            # 一次过期的待办结果退回「未完成」，否则下一轮就会误标待核实。
            for item in values:
                current = self.learning_tasks.get(item.key)
                if current is not None and current.status in ("已提交", "草稿") and item.status == "未完成":
                    continue
                self.learning_tasks[item.key] = item
            self._learning_last_sync = datetime.now(LOCAL_TZ).strftime("%m-%d %H:%M:%S")
        else:
            self.learning_tasks.update({item.key: item for item in values})
        self._render_learning_tasks()
        if kind == "todos" and before and self.learning_notify_check.isChecked():
            now = datetime.now(LOCAL_TZ)
            messages = []
            for item in self._filtered_learning_tasks():
                if item.status != "未完成":
                    continue
                from ..config import get_rollcall_settings
                lead_minutes = get_rollcall_settings(self.account)["learning_reminder_minutes"]
                reason = "新增" if item.key not in before else "临期" if item.due and now < item.due <= now + timedelta(minutes=lead_minutes) else None
                fingerprint = f"{item.key}:{item.deadline}:{reason}" + (f":{lead_minutes}" if reason == "临期" else "")
                if reason and fingerprint not in self._learning_notified:
                    self._learning_notified.add(fingerprint)
                    messages.append(f"{reason}：{item.course_name} / {item.title}")
            if messages:
                self._notify_learning("\n".join(messages[:6]))
        self._save_learning_tasks()
        self.learning_summary.setText(f"显示 {len(self._filtered_learning_tasks())} 项；上次成功同步：{self._learning_last_sync}。待核实表示已不在待办中，且未能从平台作业记录确认提交状态。")
        if kind == "todos" and unknown:
            self._verify_learning_missing(unknown)

    def _save_learning_tasks(self):
        if not self._learning_store:
            return
        try:
            self._learning_store.save_tasks(
                list(self.learning_tasks.values()),
                last_sync=self._learning_last_sync,
                notified=sorted(self._learning_notified)[-2000:],
            )
        except OSError as error:
            self.log(f"待办缓存保存失败：{error}")

    def _verify_learning_missing(self, tasks):
        """Read the course homework list before calling a disappeared task unknown.

        待办列表只列出未完成项，作业提交后会直接消失；仅凭消失无法区分
        「已提交」和「被移除」，所以对每门课补一次只读作业列表，按平台
        记录更新状态。每门课程本次会话最多自动核对一次，手动刷新可重试。
        """
        if not tasks or not self.session or "verify" in self._learning_jobs:
            return
        grouped = {}
        for task in tasks:
            if task.kind != "homework" or task.course_id in self._learning_verify_attempts:
                continue
            name, keys = grouped.setdefault(task.course_id, (task.course_name, []))
            keys.append(task.key)
        if not grouped:
            return
        self._learning_verify_attempts.update(grouped)

        def operation(api):
            statuses = {}
            for course_id, (course_name, _keys) in grouped.items():
                try:
                    statuses.update({item.key: item.status for item in api.homework_list(course_id, course_name)})
                except SessionExpiredError:
                    # 会话过期必须交给统一重登流程，不能伪装成「核对失败」。
                    raise
                except Exception:
                    # 单门课程失败不阻断其它课程；仍未核对的项保留「待核实」。
                    continue
            return statuses

        if self._start_learning_job("verify", operation):
            self.learning_summary.setText(f"待办中已消失的 {len(tasks)} 项作业正在读取平台记录核实…")

    def _apply_learning_verification(self, statuses):
        updated = 0
        for key, status in statuses.items():
            task = self.learning_tasks.get(key)
            if task is None or task.status == status:
                continue
            self.learning_tasks[key] = replace(task, status=status)
            updated += 1
        self._render_learning_tasks()
        self._save_learning_tasks()
        if statuses:
            self.learning_summary.setText(
                f"已读取平台作业记录核对 {len(statuses)} 项；更新 {updated} 项状态；"
                f"上次成功同步：{self._learning_last_sync}。"
            )
        else:
            self.learning_summary.setText("未能读取平台作业记录；待核实项保持不变，可手动刷新或读取所选课程作业状态。")

    def _notify_learning(self, text):
        from ..config import get_notification_settings, load_config
        settings = get_notification_settings(load_config())
        message = NotificationMessage("厦大助手 学习待办", text)
        if settings["system"]["enabled"]:
            self._show_system_notification(message.title, message.body)
        if settings["pushplus"]["enabled"] or settings["qq_mail"]["enabled"]:
            self._send_external_notification(message, settings=settings)
