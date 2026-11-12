"""Coalesced local draft writes; no disk access on the Qt event thread."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from .learning_html import clean_html

# Serial writes also preserve order when a later editor saves the same task.
# Executor threads finish pending writes during normal Python process exit.
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="local-draft")


class DraftWriter:
    def __init__(self, store, name, on_error):
        self.store, self.name, self.on_error = store, name, on_error
        self._lock = Lock()
        self._pending = None
        self._future = None

    def save(self, snapshot):
        """Accept an owned snapshot, retaining only the newest pending edit."""
        with self._lock:
            self._pending = snapshot
            if self._future is None or self._future.done():
                self._future = _EXECUTOR.submit(self._drain)

    def _drain(self):
        while True:
            with self._lock:
                snapshot, self._pending = self._pending, None
                if snapshot is None:
                    # Set under the same lock as save(): no lost last edit.
                    self._future = None
                    return
            try:
                snapshot["html"] = clean_html(snapshot["html"])
                self.store.write(self.name, snapshot)
            except Exception as error:
                try:
                    self.on_error(error)
                except RuntimeError:
                    # A closed application may already have destroyed Qt objects.
                    pass

    def flush(self, timeout=None):
        """For non-UI shutdown tools/tests only; UI calls must never wait."""
        with self._lock:
            future = self._future
        if future is not None:
            future.result(timeout=timeout)
