"""Startup recovery policy; all timers and preferences belong to the GUI thread."""
from __future__ import annotations

from PySide6.QtCore import QTimer

from ..config import CONFIG_LOCK, get_current_account, load_config, save_config


class AutomaticSessionMixin:
    def _init_automatic_session(self):
        self._auto_login_blocked = False
        self._session_transition = False
        self._auto_restore_backoff = 5
        self._auto_restore_retry_timer = QTimer(self)
        self._auto_restore_retry_timer.setSingleShot(True)
        self._auto_restore_retry_timer.timeout.connect(self.auto_restore_current_session)

    def _save_session_preferences(self, *, auto_login=None, monitor=None):
        try:
            with CONFIG_LOCK:
                config = load_config()
                account = get_current_account(config)
                if not account or (self.account and str(account["id"]) != str(self.account["id"])):
                    return
                if auto_login is not None:
                    account["auto_login_enabled"] = auto_login
                if monitor is not None:
                    account["monitor_on_startup"] = monitor
                save_config(config)
                if self.account:
                    self.account.update({key: account[key] for key in ("auto_login_enabled", "monitor_on_startup") if key in account})
        except Exception as error:
            self.log(f"自动恢复设置未能保存：{error}")

    def _queue_auto_restore(self, delay=None):
        if self.quitting or self._auto_login_blocked or self.session is not None:
            return
        seconds = delay if delay is not None else self._auto_restore_backoff
        self._auto_restore_retry_timer.start(int(seconds * 1000))
        self._auto_restore_backoff = min(300, self._auto_restore_backoff * 2)

    def _session_restored(self):
        self._auto_login_blocked = False
        self._auto_restore_retry_timer.stop()
        self._auto_restore_backoff = 5
        if self.account.get("monitor_on_startup", False):
            source = self.session
            QTimer.singleShot(0, lambda: self.start_monitor() if self.session is source and self.account else None)
