"""A short local feedback animation; no timer or effect remains after it ends."""
import os

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect


def animations_enabled():
    if os.name != 'nt':
        return False
    try:
        import ctypes
        from ctypes import wintypes
        enabled = wintypes.BOOL()
        # Read only: SPI_GETCLIENTAREAANIMATION, never change system settings.
        ok = ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
        return bool(ok and enabled.value)
    except (AttributeError, OSError):
        return False


def fade_feedback(widget):
    previous = getattr(widget, '_feedback_animation', None)
    if previous is not None:
        previous.stop()
        previous.deleteLater()
        widget._feedback_animation = None
        widget.setGraphicsEffect(None)
    if not animations_enabled():
        return
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b'opacity', widget)
    animation.setStartValue(0.65)
    animation.setEndValue(1.0)
    animation.setDuration(140)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    widget._feedback_animation = animation

    def finish():
        if getattr(widget, '_feedback_animation', None) is animation:
            widget._feedback_animation = None
            widget.setGraphicsEffect(None)
        animation.deleteLater()
    animation.finished.connect(finish)
    animation.start()
