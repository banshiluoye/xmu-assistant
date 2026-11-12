"""The approved neutral surface keeps brand emphasis readable and lightweight."""
import re

from xmu_rollcall.desktop_qt.theme import PALETTES, palette, stylesheet, ui_colors


def luminance(color):
    channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    values = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return sum(value * weight for value, weight in zip(values, (0.2126, 0.7152, 0.0722)))


def contrast(first, second):
    bright, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (bright + 0.05) / (dark + 0.05)


def test_neutral_surfaces_and_legible_active_states():
    for mode in ("light", "dark"):
        colors = ui_colors(mode)
        for name in ("root", "surface", "sidebar", "alternate", "hover", "pressed", "text", "muted", "placeholder", "line"):
            channels = [int(colors[name][index:index + 2], 16) for index in (1, 3, 5)]
            assert max(channels) - min(channels) <= 12, (mode, name)
        for foreground, background in [("text", "surface"), ("muted", "surface"), ("placeholder", "surface"), ("selected_text", "selected")]:
            assert contrast(colors[foreground], colors[background]) >= 4.5, (mode, foreground)
        for button in ("primary", "primary_hover", "primary_pressed"):
            assert contrast("#ffffff", colors[button]) >= 4.5, (mode, button)
        assert contrast(colors["accent_text"], colors["surface"]) >= 4.5


def test_neutral_sidebar_and_static_styles_have_no_old_decorative_effects():
    for mode in ("light", "dark"):
        css = stylesheet(mode)
        assert "gradient" not in css
        assert "animation" not in css
        assert "transition" not in css
        sidebar = re.search(r"QWidget#Sidebar \{(.*?)\}", css).group(1)
        assert f"background: {ui_colors(mode)['sidebar']}" in sidebar
        assert "border-left: 4px" not in css
        assert 'QListWidget#SubmissionFiles' in css and "padding: 5px" in css


def test_status_semantics_and_public_keys_remain_available():
    expected = {"status_unsigned_fg", "status_unsigned_bg", "status_unknown_fg", "status_unknown_bg", "status_signed_fg", "status_signed_bg",
        "status_none_fg", "status_none_bg", "group_row_bg", "group_row_fg", "empty_text", "cw_ready", "cw_downloading", "cw_success", "cw_failed",
        "warn_accent", "tutorial_text", "tutorial_nav_bg", "tutorial_nav_border"}
    for mode in ("light", "dark"):
        assert set(PALETTES[mode]) == expected
        colors = palette(mode)
        for state in ("unsigned", "signed", "unknown", "none"):
            assert contrast(colors[f"status_{state}_fg"], colors[f"status_{state}_bg"]) >= 4.5
