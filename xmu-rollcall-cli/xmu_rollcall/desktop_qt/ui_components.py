"""Small native controls with consistent spacing, icons and popup focus painting."""
from functools import lru_cache
from pathlib import Path
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QListView,
    QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget)


def file_icon_kind(filename):
    suffix = Path(str(filename)).suffix.lower().lstrip(".")
    for kind, extensions in (
        ("pdf", {"pdf"}), ("word", {"doc", "docx", "odt", "rtf"}),
        ("table", {"xls", "xlsx", "xlsm", "csv", "ods"}), ("powerpoint", {"ppt", "pptx", "pptm", "odp"}),
        ("zip", {"zip", "rar", "7z", "tar", "gz", "bz2", "xz"}),
        ("image", {"png", "jpg", "jpeg", "gif", "bmp", "webp", "svg", "tif", "tiff", "ico"}),
        ("video", {"mp4", "mov", "avi", "mkv", "webm", "wmv", "flv", "m4v"}),
        ("audio", {"mp3", "wav", "flac", "aac", "ogg", "m4a", "wma"}),
        ("python", {"py", "pyw"}), ("jupyter", {"ipynb"}),
        ("xml", {"c", "cpp", "cc", "h", "hpp", "java", "js", "ts", "tsx", "jsx", "html", "css", "json", "xml", "yaml", "yml", "sql", "sh", "ps1", "go", "rs"}),
    ):
        if suffix in extensions:
            return kind
    return "document"


class QuietItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        clean = QStyleOptionViewItem(option)
        clean.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, clean, index)

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(34, size.height()))


def configure_combo_popups(parent):
    for combo in parent.findChildren(QComboBox):
        view = QListView(combo)
        view.setObjectName("ComboPopup")
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setItemDelegate(QuietItemDelegate(view))
        view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        combo.setView(view)
        container = view.parentWidget()
        if isinstance(container, QFrame):
            container.setFrameShape(QFrame.Shape.NoFrame)
            container.setObjectName("ComboPopupFrame")
        combo.setMaxVisibleItems(8)
        combo.setStyleSheet("QComboBox { combobox-popup: 0; }")


def labeled_field(label, control):
    group = QWidget()
    row = QHBoxLayout(group)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)
    text = QLabel(label)
    label_width = text.fontMetrics().horizontalAdvance(label) + 2
    text.setFixedWidth(label_width)
    row.addWidget(text)
    row.addWidget(control, 1)
    if control.minimumWidth() == control.maximumWidth():
        group.setFixedWidth(label_width + control.width() + 10)
    return group


@lru_cache(maxsize=32)
def resource_icon(kind, size=24):
    from .icons import app_asset_path
    name = {"file": "document", "activity": "folder-other"}.get(kind, kind)
    icon = QIcon()
    for pixels in (24, 48, 72):
        path = app_asset_path(f"file_icons/{name}-{pixels}.png")
        if path.exists():
            for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected):
                icon.addFile(str(path), QSize(pixels, pixels), mode)
        if kind == "folder":
            opened = app_asset_path(f"file_icons/folder-open-{pixels}.png")
            if opened.exists():
                for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected):
                    icon.addFile(str(opened), QSize(pixels, pixels), mode, QIcon.State.On)
    if not icon.isNull():
        return icon
    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor({"folder": "#50779d", "activity": "#d29b42", "video": "#43a484", "file": "#397ab2", "upload": "#1763a0"}.get(kind, "#397ab2"))
    painter.setPen(QPen(color, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "folder":
        path = QPainterPath(QPointF(3, 7))
        for x, y in [(9, 7), (11, 10), (21, 10), (21, 20), (3, 20), (3, 7)]:
            path.lineTo(x, y)
        painter.drawPath(path)
    elif kind == "video":
        painter.drawRoundedRect(QRectF(2, 5, 20, 15), 3, 3)
        triangle = QPainterPath(QPointF(10, 9))
        triangle.lineTo(16, 12.5)
        triangle.lineTo(10, 16)
        triangle.closeSubpath()
        painter.fillPath(triangle, color)
    else:
        path = QPainterPath(QPointF(5, 2))
        for x, y in [(14, 2), (20, 8), (20, 22), (5, 22), (5, 2)]:
            path.lineTo(x, y)
        painter.drawPath(path)
        painter.drawPolyline(QPolygonF([QPointF(14, 2), QPointF(14, 8), QPointF(20, 8)]))
        painter.drawLine(8, 12, 16, 12)
        painter.drawLine(8, 16, 14, 16)
        if kind == "upload":
            painter.drawLine(16, 18, 22, 18)
            painter.drawLine(19, 15, 19, 21)
    painter.end()
    return QIcon(canvas)
