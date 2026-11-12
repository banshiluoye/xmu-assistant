"""PyInstaller launcher for the XMU Rollcall PySide6 desktop dashboard."""

import sys


def self_check(output, *, interactive_courseware=False):
    """Hidden offline packaging check; requires an explicit isolated config path."""
    import json
    import os
    from pathlib import Path
    import faulthandler
    trace = Path(str(output) + ".trace.txt").open("w", encoding="utf-8")
    trace.write("self-check entry\n")
    trace.flush()
    faulthandler.enable(file=trace)
    faulthandler.dump_traceback_later(20, repeat=True, file=trace)
    if not os.environ.get("XMU_ROLLCALL_CONFIG_DIR"):
        raise RuntimeError("Self-check requires an isolated XMU_ROLLCALL_CONFIG_DIR")
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QImageReader, QPalette
    from xmu_rollcall import __version__
    from xmu_rollcall.desktop_qt.app import DashboardWindow
    from xmu_rollcall.desktop_qt.homework_window import HomeworkWindow
    from xmu_rollcall import secrets
    from xmu_rollcall.desktop_qt.ui_components import file_icon_kind, resource_icon
    from xmu_rollcall.desktop_qt.theme import ui_colors
    from xmu_rollcall.desktop_qt.icons import app_asset_path
    from xmu_rollcall.learning import LearningStore, LearningTask
    from xmu_rollcall.courseware import CourseSummary, CoursewareItem
    import requests
    app = QApplication([])
    app.setStyle("Fusion")
    DashboardWindow._reconcile_startup_registration = lambda self, enabled: False
    DashboardWindow._setup_tray = lambda self: None
    DashboardWindow.auto_restore_current_session = lambda self: None
    DashboardWindow._run_thread = lambda *args, **kwargs: None
    window = DashboardWindow()
    window.runtime_timer.stop()
    window.session = requests.Session()
    window.account = {"id": "packaging-self-check"}
    task = LearningTask("fixture", "fixture", "Offline", "Self-check", "homework")
    store = LearningStore("packaging-self-check")
    data = {"detail": {"uploads": [], "data": {}}, "submission": {"id": None, "uploads": []}, "history": [], "group": False}
    store.write(store.draft_name(task), {"html": "<p><br></p>\n<p>&nbsp;</p>"})
    editor = HomeworkWindow(window, task, data, store)
    empty_ok = editor.editor.document().isEmpty() and editor.editor.toPlainText() == ""
    window._apply_theme("dark")
    dark_ok = window.radar_place_list.palette().color(QPalette.ColorRole.Base).name() == ui_colors("dark")["surface"]
    window._apply_theme("light")
    theme_ok = dark_ok and window.radar_place_list.palette().color(QPalette.ColorRole.Base).name() == ui_colors("light")["surface"]
    editor.editor.setPlainText("offline-draft-check")
    editor._save_local()
    editor.draft_writer.flush(5)
    draft_ok = "offline-draft-check" in store.read(store.draft_name(task), {}).get("html", "")
    editor.invalidate_session()
    editor.close()
    editor.draft_writer.flush(5)
    course = CourseSummary("fixture", "离线目录验证", window.courseware_academic_year_combo.currentText() + "-1")
    window._set_courseware_courses([course], "fixture")
    window.courseware_combo.blockSignals(True)
    window.courseware_combo.setCurrentText(course.display_name)
    window.courseware_combo.blockSignals(False)
    files = [CoursewareItem("fixture", str(i // 10), f"活动 {i // 10}", "material", f"章节 {i // 200}", "", str(i), str(i), f"文件-{i}.pdf", 1,
        "file", "", "ready", True, chapter_index=i // 200, activity_index=i // 10, module_id=str(i // 200)) for i in range(1200)]
    window._set_courseware_items(course, files)
    outline = window.courseware_tree
    chapter = outline.topLevelItem(0)
    chapter.setExpanded(False)
    disclosure_ok = outline.isRowHidden(1)
    chapter.setExpanded(True)
    disclosure_ok = disclosure_ok and not outline.isRowHidden(1)
    roundtrip = secrets.unprotect(secrets.protect("self-check")) == "self-check"
    formats = [bytes(value).decode() for value in QImageReader.supportedImageFormats()]
    report = {"version": __version__, "pages": list(window.nav_titles), "encryption_roundtrip": roundtrip,
              "image_formats": formats, "icon_available": not window.windowIcon().isNull(),
              "homework_editor": HomeworkWindow.__name__,
              "draft_background_roundtrip": draft_ok,
              "empty_draft_restored_empty": empty_ok,
              "theme_palette_roundtrip": theme_ok,
              "courseware_disclosure_roundtrip": disclosure_ok,
              "ui_indicator_assets": len(list(app_asset_path("ui_indicators").glob("*.png"))),
              "icon_assets_count": len(list(app_asset_path("file_icons").glob("*.png"))),
              "file_icons": {name: app_asset_path(f"file_icons/{file_icon_kind(name)}-24.png").is_file() and not resource_icon(file_icon_kind(name)).isNull() for name in
                  ("test.pdf", "test.docx", "test.xlsx", "test.pptx", "test.zip", "test.png", "test.mp4", "test.mp3", "test.py", "test.ipynb")}}
    Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if interactive_courseware:
        from PySide6.QtCore import QTimer
        from xmu_rollcall.ui_stall_watchdog import install_ui_watchdog
        window._show_page(2)
        window.setWindowTitle("虾大助手 - 离线课件交互验证")
        window.resize(1100, 680)
        window.runtime_timer.timeout.disconnect()
        install_ui_watchdog(app, window)
        window.runtime_timer.start(1000)
        window.show()
        QTimer.singleShot(0, window.showNormal)
        app.exec()
        return
    window.quitting = True
    window.close()
    app.quit()
    faulthandler.cancel_dump_traceback_later()
    trace.close()


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check(sys.argv[sys.argv.index("--self-check") + 1], interactive_courseware="--interactive-courseware" in sys.argv)
    else:
        from xmu_rollcall.desktop_qt.app import main
        main()
