"""Cached, native line icons for desktop navigation; no SVG runtime required."""
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _draw(painter, name):
    def line(x1, y1, x2, y2):
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    if name == "首页":
        path = QPainterPath(QPointF(3, 10))
        for x, y in ((12, 3), (21, 10), (19, 10), (19, 21), (14, 21), (14, 14), (10, 14), (10, 21), (5, 21), (5, 10)):
            path.lineTo(x, y)
        painter.drawPath(path)
    elif name == "课程课件":
        path = QPainterPath(QPointF(3, 6))
        for x, y in ((9, 6), (11, 8), (21, 8), (21, 20), (3, 20), (3, 6)):
            path.lineTo(x, y)
        painter.drawPath(path)
    elif name == "雷达坐标":
        path = QPainterPath(QPointF(12, 22))
        path.cubicTo(8, 17, 5, 14, 5, 10)
        path.cubicTo(5, 1, 19, 1, 19, 10)
        path.cubicTo(19, 14, 16, 17, 12, 22)
        painter.drawPath(path)
        painter.drawEllipse(QRectF(9.5, 7, 5, 5))
    elif name == "通知":
        path = QPainterPath(QPointF(4, 18))
        for x, y in ((6, 15), (6, 10)):
            path.lineTo(x, y)
        path.cubicTo(6, 2, 18, 2, 18, 10)
        for x, y in ((18, 15), (20, 18), (4, 18)):
            path.lineTo(x, y)
        painter.drawPath(path)
        painter.drawArc(QRectF(10, 18, 4, 4), 180 * 16, 180 * 16)
    elif name == "教程":
        path = QPainterPath(QPointF(12, 6))
        for x, y in ((3, 4), (3, 19), (12, 21), (21, 19), (21, 4), (12, 6), (12, 21)):
            path.lineTo(x, y)
        painter.drawPath(path)
    elif name == "策略":
        for y, center in ((6, 9), (12, 16), (18, 7)):
            line(3, y, center - 2.5, y)
            line(center + 2.5, y, 21, y)
            painter.drawEllipse(QRectF(center - 2.5, y - 2.5, 5, 5))
    elif name == "签到情况":
        painter.drawRoundedRect(QRectF(4, 5, 16, 16), 2, 2)
        line(8, 3, 8, 7)
        line(16, 3, 16, 7)
        line(4, 10, 20, 10)
        line(8, 15, 11, 18)
        line(11, 18, 16, 13)
    else:
        painter.drawRoundedRect(QRectF(4, 3, 16, 18), 2, 2)
        for y in (8, 13, 18):
            line(8, y, 9, y)
            line(12, y, 16, y)


@lru_cache(maxsize=24)
def navigation_icon(name, foreground, accent, disabled):
    icon = QIcon()
    for mode, color in ((QIcon.Mode.Normal, foreground), (QIcon.Mode.Active, foreground),
                        (QIcon.Mode.Selected, accent), (QIcon.Mode.Disabled, disabled)):
        for pixels in (20, 40, 60):
            canvas = QPixmap(pixels, pixels)
            canvas.fill(Qt.GlobalColor.transparent)
            painter = QPainter(canvas)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.scale(pixels / 24, pixels / 24)
            painter.setPen(QPen(QColor(color), 1.6, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            _draw(painter, name)
            painter.end()
            icon.addPixmap(canvas, mode)
    return icon
