"""Passive, bounded stall diagnostics without reading Qt objects off-thread."""
from __future__ import annotations

import sys
import faulthandler
import os
import threading
import time
import traceback

from .diag_log import log
from .config import CONFIG_DIR

_active = None


class UiStallWatchdog:
    def __init__(self, *, threshold=5.0, interval=2.0, writer=log):
        self.threshold, self.interval, self.writer = threshold, interval, writer
        self.gui_thread = threading.get_ident()
        self.last_beat = time.monotonic()
        self.last_probe = self.last_beat
        self.last_reported = None
        self.action = "Qt event loop"
        self.stopped = threading.Event()

    def beat(self):
        self.last_beat = time.monotonic()

    def note(self, action):
        self.action = action

    def probe(self, now=None):
        now = time.monotonic() if now is None else now
        # Suspend/resume or a globally paused process is not a UI-stall sample.
        if now - self.last_probe > max(15.0, self.interval * 4):
            self.last_beat = self.last_probe = now
            return
        self.last_probe = now
        heartbeat = self.last_beat
        if now - heartbeat < self.threshold or self.last_reported == heartbeat:
            return
        self.last_reported = heartbeat
        frame = sys._current_frames().get(self.gui_thread)
        if frame is not None:
            # Stack locations only: never inspect frame locals, editor text,
            # paths chosen by the user, session cookies or credentials.
            stack = "".join(traceback.format_stack(frame, limit=32))
            self.writer(f"UI_STALL {now - heartbeat:.1f}s; recent_action={self.action}\n{stack}")

    def _run(self):
        stream = None
        armed_heartbeat = None
        armed_at = 0.0
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            path = CONFIG_DIR / "ui-stall-stacks.log"
            stream = path.open("ab", buffering=0)
            while not self.stopped.is_set():
                now = time.monotonic()
                self.probe(now)
                # The C-level timer can dump stacks even when a native call
                # holds the GIL and this Python thread cannot run. Renew at
                # most once every four seconds, only after a fresh UI beat.
                if self.last_beat != armed_heartbeat and now - armed_at >= 4.0:
                    faulthandler.cancel_dump_traceback_later()
                    if os.fstat(stream.fileno()).st_size >= 1024 * 1024:
                        stream.close()
                        os.replace(path, path.with_name("ui-stall-stacks.log.1"))
                        stream = path.open("ab", buffering=0)
                    faulthandler.dump_traceback_later(8.0, repeat=False, file=stream)
                    armed_heartbeat, armed_at = self.last_beat, now
                if self.stopped.wait(self.interval):
                    break
        except Exception:
            # If the diagnostic file cannot be opened, retain the lightweight
            # Python sampler; diagnostics must never prevent application use.
            while not self.stopped.wait(self.interval):
                try:
                    self.probe()
                except Exception:
                    pass
        finally:
            faulthandler.cancel_dump_traceback_later()
            if stream is not None:
                stream.close()

    def start(self):
        threading.Thread(target=self._run, name="ui-stall-watchdog", daemon=True).start()

    def stop(self):
        self.stopped.set()


def install_ui_watchdog(app, window):
    global _active
    monitor = UiStallWatchdog()
    _active = monitor
    # Reuse the dashboard's existing one-second timer; no new GUI timer and no
    # animation/render loop. Disk writes happen only on an actual long stall.
    window.runtime_timer.timeout.connect(monitor.beat)
    app.aboutToQuit.connect(monitor.stop)
    monitor.start()
    return monitor


def note_ui_action(action):
    if _active is not None:
        _active.note(action)
