"""Small-window filter layout and bounded feedback motion regressions."""
from unittest import mock

from PySide6.QtCore import QPoint, QRect
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from test_learning_ui import window  # noqa: F401
from xmu_rollcall.desktop_qt.motion import fade_feedback


def test_learning_filters_do_not_overlap_at_minimum_width(window):
    window._show_page(window.nav_titles.index('学习待办'))
    window.resize(1080, 680)
    window.show()
    QApplication.processEvents()
    controls = [window.learning_search, window.learning_course_button,
                window.learning_type, window.learning_status, window.learning_deadline]
    boxes = [QRect(control.mapTo(window, QPoint()), control.size()) for control in controls]
    assert all(not first.intersects(second) for index, first in enumerate(boxes) for second in boxes[index + 1:])
    assert all(window.rect().contains(box) for box in boxes)


def test_feedback_animation_releases_effect_and_honors_reduced_motion():
    app = QApplication.instance() or QApplication([])
    label = QLabel('操作已完成')
    with mock.patch('xmu_rollcall.desktop_qt.motion.animations_enabled', return_value=True):
        fade_feedback(label)
        fade_feedback(label)
        assert label._feedback_animation is not None
        QTest.qWait(230)
        assert label._feedback_animation is None
        assert label.graphicsEffect() is None
    with mock.patch('xmu_rollcall.desktop_qt.motion.animations_enabled', return_value=False):
        fade_feedback(label)
        assert label._feedback_animation is None
        assert label.graphicsEffect() is None
    label.deleteLater()
    app.processEvents()
