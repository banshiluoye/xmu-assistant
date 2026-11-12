"""Render tiny geometric control arrows with Qt's built-in PNG support."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(ROOT / 'xmu-rollcall-cli'))
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPolygonF
from xmu_rollcall.desktop_qt.theme import ui_colors

app = QGuiApplication([])
output = ROOT / 'xmu-rollcall-cli/xmu_rollcall/assets/ui_indicators'
output.mkdir(exist_ok=True)
for mode in ('light', 'dark'):
    for state in ('normal', 'disabled'):
        color = ui_colors(mode)['muted' if state == 'normal' else 'disabled']
        for direction in ('up', 'down'):
            canvas = QImage(24, 24, QImage.Format.Format_ARGB32)
            canvas.fill(Qt.GlobalColor.transparent)
            painter = QPainter(canvas)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            points = [(2, 7), (22, 7), (12, 17)] if direction == 'down' else [(2, 17), (22, 17), (12, 7)]
            painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in points]))
            painter.end()
            canvas.save(str(output / f'{direction}-{mode}-{state}.png'))
print('Rendered 8 native control arrows,', sum(path.stat().st_size for path in output.glob('*.png')), 'bytes')
