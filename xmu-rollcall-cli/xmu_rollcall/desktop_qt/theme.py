"""Neutral native Qt styling, with the XMU crest blue reserved for emphasis."""
from __future__ import annotations

WINDOW_MIN_WIDTH = 1080
WINDOW_MIN_HEIGHT = 680

# Screen approximation sampled from the official crest artwork, not an
# officially specified RGB conversion of the university's print CMYK values.
# All UI blue variants are derived here; file icons retain their own colors.
ACCENT_BLUE = "#0169CC"


def _mix(first: str, second: str, fraction: float) -> str:
    channels = (
        round(int(first[index:index + 2], 16) * (1 - fraction)
              + int(second[index:index + 2], 16) * fraction)
        for index in (1, 3, 5)
    )
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def resolve_theme(theme_mode: str) -> str:
    """Resolve a saved setting without depending on the previous palette."""
    if theme_mode in ("light", "dark"):
        return theme_mode
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication

        scheme = getattr(QGuiApplication.styleHints(), "colorScheme", None)
        if callable(scheme):
            return "dark" if scheme() == Qt.ColorScheme.Dark else "light"
    except Exception:
        pass
    return "light"


def ui_colors(theme_mode: str = "system") -> dict[str, str]:
    """Shared colors for QSS and native widgets; no per-frame style updates."""
    dark = resolve_theme(theme_mode) == "dark"
    if dark:
        colors = {
            "root": "#141416", "surface": "#1c1c1f", "sidebar": "#18181b",
            "alternate": "#222225", "hover": "#29292e", "pressed": "#333339",
            "text": "#ededf0", "muted": "#a1a1aa", "placeholder": "#92929d",
            "line": "#343439", "control_line": "#4b4b53", "disabled": "#777780",
            "indicator_line": "#8c8c98",
            "scroll": "#55555f", "scroll_hover": "#73737d",
        }
        colors.update({
            "primary": ACCENT_BLUE,
            "primary_hover": _mix(ACCENT_BLUE, "#000000", 0.10),
            "primary_pressed": _mix(ACCENT_BLUE, "#000000", 0.20),
            "accent_text": _mix(ACCENT_BLUE, "#ffffff", 0.56),
        })
        colors["selected"] = _mix(colors["surface"], colors["primary"], 0.52)
        colors["selected_text"] = colors["text"]
    else:
        colors = {
            "root": "#f6f6f7", "surface": "#ffffff", "sidebar": "#fafafa",
            "alternate": "#fafafb", "hover": "#f0f0f2", "pressed": "#e6e6ea",
            "text": "#202124", "muted": "#64646d", "placeholder": "#71717b",
            "line": "#e0e0e5", "control_line": "#c6c6ce", "disabled": "#92929c",
            "indicator_line": "#8a8a94",
            "scroll": "#bdbdc5", "scroll_hover": "#94949e",
        }
        colors.update({
            "primary": ACCENT_BLUE,
            "primary_hover": _mix(ACCENT_BLUE, "#000000", 0.12),
            "primary_pressed": _mix(ACCENT_BLUE, "#000000", 0.22),
            "accent_text": ACCENT_BLUE,
        })
        colors["selected"] = _mix(colors["surface"], ACCENT_BLUE, 0.10)
        colors["selected_text"] = ACCENT_BLUE
    return {name: value.lower() for name, value in colors.items()}


def stylesheet(theme_mode: str = "light") -> str:
    """One small native stylesheet for both themes; no browser/runtime library."""
    t = ui_colors(theme_mode)
    status = palette(theme_mode)
    from .icons import app_asset_path
    mode = resolve_theme(theme_mode)
    def arrow(direction, state="normal"):
        return app_asset_path(f"ui_indicators/{direction}-{mode}-{state}.png").as_posix()
    return f"""
    * {{ font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif; font-size: 13px; }}
    QMainWindow, QWidget#Root {{ background: {t["root"]}; color: {t["text"]}; }}
    QDialog, QMessageBox {{ background: {t["surface"]}; color: {t["text"]}; }}
    QLabel {{ color: {t["text"]}; background: transparent; }}
    QWidget#Sidebar {{ background: {t["sidebar"]}; border-right: 1px solid {t["line"]}; }}
    QLabel#Brand {{ color: {t["text"]}; font-size: 20px; font-weight: 600; }}
    QLabel#SidebarLogo, QLabel#IdentityLogo, QLabel#EmptyWatermark {{ background: transparent; }}
    QLabel#PageTitle, QLabel#IdentityTitle {{ color: {t["text"]}; font-size: 24px; font-weight: 600; }}
    QLabel#Subtle, QLabel#IdentitySubtitle, QLabel#InlineHint, QLabel#SignalLabel {{ color: {t["muted"]}; }}
    QLabel#IdentitySubtitle, QLabel#InlineHint {{ font-size: 12px; }}
    QLabel#StatusGood {{ color: {status["status_signed_fg"]}; font-weight: 600; }}
    QLabel#StatusWarn {{ color: {status["status_unknown_fg"]}; font-weight: 600; }}
    QLabel#HeroStatusWarn {{ color: {status["status_unsigned_fg"]}; background: {status["status_unsigned_bg"]}; border: 0; border-radius: 5px; padding: 5px 10px; font-weight: 600; }}
    QFrame#Panel, QFrame#IdentityPanel, QFrame#GuardianPanel, QFrame#ActionDock, QFrame#TimelinePanel {{ background: {t["surface"]}; border: 1px solid {t["line"]}; border-radius: 12px; }}
    QFrame#SignalPanel, QFrame#SignalTile {{ background: transparent; border: 0; }}
    QLabel#SignalValue {{ color: {t["text"]}; font-size: 18px; font-weight: 600; }}
    QLabel#DockTitle, QLabel#SectionTitle {{ color: {t["text"]}; font-size: 16px; font-weight: 600; }}
    QLabel#GuardTitle {{ color: {t["text"]}; font-size: 30px; font-weight: 600; }}
    QFrame#EmptyStateCard {{ background: {t["alternate"]}; border: 1px dashed {t["line"]}; border-radius: 12px; }}
    QLabel#EmptyStateText {{ color: {t["muted"]}; font-size: 14px; }}
    QLabel#NumberBadge {{ background: {t["hover"]}; color: {t["text"]}; border: 0; border-radius: 5px; padding: 2px 8px; font-size: 14px; font-weight: 600; }}

    QAbstractItemView {{ outline: 0; selection-background-color: {t["selected"]}; selection-color: {t["selected_text"]}; }}
    QListWidget, QTableWidget {{ background: {t["surface"]}; color: {t["text"]}; border: 1px solid {t["line"]}; border-radius: 6px; selection-background-color: {t["selected"]}; selection-color: {t["selected_text"]}; }}
    QListWidget::item:selected, QTableWidget::item:selected {{ background: {t["selected"]}; color: {t["selected_text"]}; border: 0; }}
    QListWidget::item:hover:!selected, QTableWidget::item:hover:!selected {{ background: {t["hover"]}; }}
    QListWidget#Navigation {{ background: transparent; color: {t["muted"]}; border: 0; outline: 0; }}
    QListWidget#Navigation::item {{ min-height: 36px; padding: 7px 12px; margin: 2px 10px; border: 0; border-radius: 6px; }}
    QListWidget#Navigation::item:hover:!selected {{ background: {t["hover"]}; color: {t["text"]}; }}
    QListWidget#Navigation::item:selected {{ background: {t["selected"]}; color: {t["selected_text"]}; border: 0; font-weight: 600; }}

    QPushButton {{ background: {t["surface"]}; color: {t["text"]}; border: 1px solid {t["control_line"]}; border-radius: 6px; padding: 8px 14px; min-height: 24px; }}
    QPushButton:hover {{ background: {t["hover"]}; border-color: {t["scroll"]}; }}
    QPushButton:pressed {{ background: {t["pressed"]}; }}
    QPushButton:focus {{ border-color: {t["primary"]}; }}
    QPushButton#PrimaryButton {{ background: {t["primary"]}; color: #ffffff; border-color: {t["primary"]}; font-weight: 700; }}
    QPushButton#PrimaryButton:hover {{ background: {t["primary_hover"]}; border-color: {t["primary_hover"]}; }}
    QPushButton#PrimaryButton:pressed {{ background: {t["primary_pressed"]}; border-color: {t["primary_pressed"]}; }}
    QPushButton#SecondaryButton {{ background: {t["surface"]}; color: {t["text"]}; border-color: {t["control_line"]}; font-weight: 500; }}
    QPushButton#SecondaryButton:hover {{ background: {t["hover"]}; }}
    QPushButton#QuietButton {{ background: transparent; border-color: transparent; color: {t["muted"]}; padding: 6px 10px; }}
    QPushButton#QuietButton:hover {{ background: {t["hover"]}; color: {t["text"]}; }}
    QPushButton#QuietButton:pressed {{ background: {t["pressed"]}; }}

    QLineEdit, QAbstractSpinBox, QComboBox {{ background: {t["surface"]}; color: {t["text"]}; placeholder-text-color: {t["placeholder"]}; border: 1px solid {t["control_line"]}; border-radius: 6px; padding: 6px 8px; min-height: 20px; selection-background-color: {t["selected"]}; selection-color: {t["selected_text"]}; }}
    QLineEdit:focus, QAbstractSpinBox:focus, QComboBox:focus {{ border-color: {t["primary"]}; }}
    QComboBox::drop-down {{ border: 0; width: 24px; }}
    QComboBox {{ padding-right: 28px; }}
    QComboBox::down-arrow {{ image: url("{arrow('down')}"); width: 12px; height: 12px; }}
    QComboBox::down-arrow:disabled {{ image: url("{arrow('down', 'disabled')}"); }}
    QAbstractSpinBox {{ padding-right: 28px; }}
    QAbstractSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 24px; height: 17px; border: 0; }}
    QAbstractSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 24px; height: 17px; border: 0; }}
    QAbstractSpinBox::up-arrow {{ image: url("{arrow('up')}"); width: 10px; height: 8px; }}
    QAbstractSpinBox::down-arrow {{ image: url("{arrow('down')}"); width: 10px; height: 8px; }}
    QAbstractSpinBox::up-arrow:disabled {{ image: url("{arrow('up', 'disabled')}"); }}
    QAbstractSpinBox::down-arrow:disabled {{ image: url("{arrow('down', 'disabled')}"); }}
    QComboBox QAbstractItemView, QListView#ComboPopup {{ background: {t["surface"]}; color: {t["text"]}; border: 0; padding: 4px; outline: 0; selection-background-color: {t["selected"]}; selection-color: {t["selected_text"]}; }}
    QComboBox QAbstractItemView::item, QListView#ComboPopup::item {{ border: 0; padding: 6px 12px; min-height: 24px; }}
    QComboBox QAbstractItemView::item:selected, QListView#ComboPopup::item:selected {{ background: {t["selected"]}; color: {t["selected_text"]}; border: 0; }}
    QFrame#ComboPopupFrame {{ background: {t["surface"]}; border: 1px solid {t["line"]}; border-radius: 6px; }}
    QCheckBox, QRadioButton {{ color: {t["text"]}; spacing: 8px; font-weight: 500; }}
    /* Fusion derives unchecked borders from Window and the OS color scheme,
       which can disagree with this app's theme. Style only the empty frame;
       leave checked/partial glyphs to the native style so ticks stay visible. */
    QCheckBox::indicator:unchecked, QAbstractItemView::indicator:unchecked {{ width: 12px; height: 12px; border: 1px solid {t["indicator_line"]}; background: {t["surface"]}; border-radius: 2px; }}
    QCheckBox::indicator:checked, QCheckBox::indicator:indeterminate, QAbstractItemView::indicator:checked, QAbstractItemView::indicator:indeterminate {{ width: 14px; height: 14px; }}

    QTableWidget {{ alternate-background-color: {t["alternate"]}; gridline-color: {t["line"]}; }}
    QTableWidget#TimelineTable {{ border: 0; border-top: 1px solid {t["line"]}; border-radius: 0; }}
    QHeaderView::section {{ background: {t["alternate"]}; color: {t["muted"]}; border: 0; border-bottom: 1px solid {t["line"]}; padding: 8px 10px; font-weight: 600; }}
    QTextEdit, QTextBrowser {{ background: {t["surface"]}; color: {t["text"]}; placeholder-text-color: {t["placeholder"]}; border: 1px solid {t["line"]}; border-radius: 6px; padding: 8px; selection-background-color: {t["selected"]}; selection-color: {t["selected_text"]}; }}
    QTableWidget#ChapterOutline {{ background: {t["surface"]}; color: {t["text"]}; border: 1px solid {t["line"]}; border-radius: 8px; padding: 10px; outline: 0; selection-background-color: {t["selected"]}; selection-color: {t["selected_text"]}; }}
    QTableWidget#ChapterOutline::item {{ border: 0; padding: 5px 4px; }}
    QTableWidget#ChapterOutline::item:hover:!selected {{ background: {t["hover"]}; }}
    QTableWidget#ChapterOutline::item:selected {{ background: {t["selected"]}; color: {t["selected_text"]}; border: 0; }}

    QDialog#CoursePicker, QDialog#HomeworkWindow {{ background: {t["surface"]}; color: {t["text"]}; }}
    QDialog#CoursePicker QListWidget {{ padding: 4px; }}
    QDialog#CoursePicker QListWidget::item {{ padding: 8px 10px; border: 0; }}
    QDialog#CoursePicker QListWidget::item:selected {{ background: {t["selected"]}; color: {t["selected_text"]}; border-radius: 4px; }}
    QFrame#HomeworkHeaderTools {{ background: transparent; border: 0; }}
    QLabel#HomeworkTaskTitle {{ color: {t["text"]}; font-size: 18px; font-weight: 600; }}
    QLabel#HomeworkCourseName, QLabel#HomeworkStatus {{ color: {t["muted"]}; font-size: 12px; }}
    QLabel#AnswerHeading {{ color: {t["text"]}; font-size: 15px; font-weight: 600; }}
    QFrame#AnswerPanel {{ background: {t["surface"]}; border: 1px solid {t["line"]}; border-radius: 6px; }}
    QFrame#AnswerPanel QTextEdit {{ border: 0; border-radius: 0; }}
    QFrame#AttachmentDropZone {{ background: {t["alternate"]}; border: 1px dashed {t["control_line"]}; border-radius: 8px; }}
    QFrame#AttachmentDropZone[dragActive="true"] {{ background: {t["selected"]}; border: 1px dashed {t["primary"]}; }}
    QFrame#AttachmentDropZone QLabel {{ background: transparent; border: 0; color: {t["muted"]}; }}
    QListWidget#SubmissionFiles {{ background: {t["surface"]}; color: {t["text"]}; border: 1px solid {t["line"]}; border-radius: 6px; padding: 5px; }}
    QListWidget#SubmissionFiles::item {{ padding: 6px 10px; border: 0; }}
    QListWidget#SubmissionFiles::item:hover:!selected {{ background: {t["hover"]}; }}
    QListWidget#SubmissionFiles::item:selected {{ background: {t["selected"]}; color: {t["selected_text"]}; border-radius: 4px; }}
    QToolButton#EditorTool {{ background: transparent; color: {t["text"]}; border: 0; border-radius: 4px; padding: 5px; min-width: 24px; min-height: 24px; }}
    QToolButton#EditorTool:hover, QToolButton#EditorTool:checked {{ background: {t["hover"]}; }}
    QScrollArea#SettingsScroll {{ border: 0; background: transparent; }}

    QMenu, QToolTip {{ background: {t["surface"]}; color: {t["text"]}; border: 1px solid {t["line"]}; border-radius: 5px; padding: 4px; }}
    QMenu::item {{ padding: 6px 16px; border-radius: 3px; }}
    QMenu::item:selected {{ background: {t["selected"]}; color: {t["selected_text"]}; }}
    QMenu::separator {{ height: 1px; background: {t["line"]}; margin: 4px 8px; }}
    QMenu::item:disabled {{ color: {t["disabled"]}; }}
    QScrollBar:vertical, QScrollBar:horizontal {{ background: {t["alternate"]}; border: 0; width: 11px; height: 11px; }}
    QScrollBar::handle {{ background: {t["scroll"]}; border-radius: 4px; min-height: 28px; min-width: 28px; }}
    QScrollBar::handle:hover {{ background: {t["scroll_hover"]}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QProgressBar {{ border: 0; background: {t["hover"]}; color: {t["text"]}; border-radius: 4px; text-align: center; }}
    QProgressBar::chunk {{ background: {t["selected"]}; border-radius: 4px; }}

    QLabel:disabled, QCheckBox:disabled, QRadioButton:disabled, QLineEdit:disabled, QAbstractSpinBox:disabled, QComboBox:disabled {{ color: {t["disabled"]}; }}
    QPushButton:disabled, QPushButton#PrimaryButton:disabled, QPushButton#SecondaryButton:disabled, QPushButton#QuietButton:disabled, QToolButton:disabled {{ color: {t["disabled"]}; background: {t["alternate"]}; border-color: {t["line"]}; }}
    """


# Semantic colors remain separate from brand emphasis. All existing public
# palette keys are retained for status badges, table groups and tutorial HTML.
_STATUS_COLORS = {
    "light": {
        "status_unsigned_fg": "#8a1c1c", "status_unsigned_bg": "#fde8e8",
        "status_unknown_fg": "#8a5a00", "status_unknown_bg": "#fff4ce",
        "status_signed_fg": "#166534", "status_signed_bg": "#e7f6ec",
        "status_none_fg": "#64646d", "status_none_bg": "#efeff2",
        "cw_downloading": "#8a5a00", "cw_success": "#087443",
        "cw_failed": "#b42318", "warn_accent": "#b42318",
    },
    "dark": {
        "status_unsigned_fg": "#f2a9a4", "status_unsigned_bg": "#3d2427",
        "status_unknown_fg": "#e3b45f", "status_unknown_bg": "#3b3120",
        "status_signed_fg": "#8fd6a2", "status_signed_bg": "#1d3527",
        "status_none_fg": "#a1a1aa", "status_none_bg": "#2a2a2f",
        "cw_downloading": "#e3b45f", "cw_success": "#79cf92",
        "cw_failed": "#f08a80", "warn_accent": "#f2a9a4",
    },
}


def _extended_colors(mode):
    t = ui_colors(mode)
    return {
        **_STATUS_COLORS[mode],
        "group_row_bg": t["alternate"], "group_row_fg": t["text"],
        "empty_text": t["muted"], "cw_ready": t["accent_text"],
        "tutorial_text": t["text"], "tutorial_nav_bg": t["alternate"],
        "tutorial_nav_border": t["line"],
    }


PALETTES = {mode: _extended_colors(mode) for mode in ("light", "dark")}


def palette(theme_mode: str = "system") -> dict[str, str]:
    """Extended status palette used by the existing page mixins."""
    return PALETTES[resolve_theme(theme_mode)]


def qpalette(theme_mode: str = "system"):
    """Fully specify every native role and state, independent of prior themes."""
    from PySide6.QtGui import QColor, QPalette

    t = ui_colors(theme_mode)
    dark = resolve_theme(theme_mode) == "dark"
    colors = {
        "Window": t["root"], "WindowText": t["text"],
        "Base": t["surface"], "AlternateBase": t["alternate"],
        "ToolTipBase": t["surface"], "ToolTipText": t["text"],
        "Text": t["text"], "PlaceholderText": t["placeholder"],
        "Button": t["surface"], "ButtonText": t["text"],
        "BrightText": "#ffffff", "Link": t["accent_text"],
        "LinkVisited": t["accent_text"], "Highlight": t["selected"],
        "HighlightedText": t["selected_text"], "Accent": t["primary"],
        "Light": t["surface"], "Midlight": t["alternate"],
        "Dark": "#101012" if dark else "#94949e",
        "Mid": t["control_line"], "Shadow": "#000000" if dark else "#8b8b95",
    }
    result = QPalette()
    for name, value in colors.items():
        role = getattr(QPalette.ColorRole, name, None)
        if role is not None:
            result.setColor(role, QColor(value))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        result.setColor(QPalette.ColorGroup.Disabled, role, QColor(t["disabled"]))
    result.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(t["alternate"]))
    result.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(t["alternate"]))
    return result


def light_qpalette():
    return qpalette("light")


def dark_qpalette():
    return qpalette("dark")
