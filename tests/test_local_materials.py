from pathlib import Path
from unittest.mock import patch

import pytest
from test_learning_ui import window  # noqa: F401

from xmu_rollcall.local_materials import LocalMaterialStore
from xmu_rollcall.mcp_bridge.storage import FileStore


@pytest.fixture
def library(tmp_path):
    return LocalMaterialStore("1", "user-a", tmp_path / "config")


def test_copy_reference_and_duplicate_import(library, tmp_path):
    source = tmp_path / "教材.pdf"
    source.write_bytes(b"original")
    root = tmp_path / "course"
    rows, errors = library.add([source], "c1", "课程", root, chapter="第一章")
    assert not errors
    row = rows[0]
    assert row["mode"] == "copy"
    target = Path(row["path"])
    assert target.is_relative_to(root) and target.read_bytes() == b"original"
    again, _ = library.add([source], "c1", "课程", root)
    assert again[0]["resource_id"] == row["resource_id"]
    assert len(library.items("c1")) == 1
    source.unlink()
    assert library.resolve(row["resource_id"]).is_file()
    library.remove(row["resource_id"])
    assert target.is_file() and library.items("c1") == []


def test_large_file_auto_reference_has_no_copy_or_hash(library, tmp_path):
    source = tmp_path / "大教材.pdf"
    with source.open("wb") as stream:
        stream.truncate(1024 * 1024 + 1)
    with patch("hashlib.file_digest", side_effect=AssertionError("must not hash")):
        rows, errors = library.add(
            [source], "c1", "课程", tmp_path / "course", threshold_mib=1
        )
    assert not errors and rows[0]["mode"] == "reference"
    assert rows[0]["path"] == str(source.resolve())
    assert not (tmp_path / "course").exists()
    assert library.read()["reference_threshold_mib"] == 1


def test_threshold_boundary_and_existing_course_file(library, tmp_path):
    source = tmp_path / "course/notes.txt"
    source.parent.mkdir()
    source.write_bytes(b"x" * 1024 * 1024)
    rows, errors = library.add([source], "c1", "课程", source.parent, threshold_mib=1)
    assert not errors and rows[0]["mode"] == "existing"
    assert len(list(source.parent.iterdir())) == 1


def test_reference_missing_relocate_and_account_isolation(library, tmp_path):
    source = tmp_path / "book.txt"
    source.write_text("content", encoding="utf-8")
    rows, _ = library.add([source], "c1", "课程", tmp_path / "course", mode="reference")
    key = rows[0]["resource_id"]
    moved = source.with_name("moved.txt")
    source.rename(moved)
    with pytest.raises(ValueError, match="重新定位"):
        library.resolve(key)
    library.relocate(key, moved)
    assert library.resolve(key) == moved
    assert LocalMaterialStore("1", "user-b", tmp_path / "config").items() == []


def test_mcp_reads_registered_original_without_copy_and_revokes_removed(
    library, tmp_path
):
    source = tmp_path / "textbook.md"
    source.write_text("期末60%，平时40%", encoding="utf-8")
    rows, _ = library.add([source], "c1", "课程", tmp_path / "course", mode="reference")
    store = FileStore(tmp_path / "mcp", library.resolve)
    file = store.register_local(rows[0])
    assert file["local_path"] == str(source)
    assert not (tmp_path / "mcp/textbook.md").exists()
    assert "期末60%" in store.read(file["file_id"])["text"]
    assert store.search("期末", "c1")["hits"]
    library.remove(rows[0]["resource_id"])
    with pytest.raises(ValueError):
        store.read(file["file_id"])


def test_large_mcp_reference_does_not_hash_or_parse(library, tmp_path):
    source = tmp_path / "large.pdf"
    with source.open("wb") as stream:
        stream.truncate(65 * 1024 * 1024)
    rows, _ = library.add([source], "c1", "课程", tmp_path / "course")
    store = FileStore(tmp_path / "mcp", library.resolve)
    with patch(
        "xmu_rollcall.mcp_bridge.storage.digest",
        side_effect=AssertionError("must not hash"),
    ):
        file = store.register_local(rows[0])
        assert file["sha256"] is None
        with pytest.raises(ValueError, match="64 MiB"):
            store.read(file["file_id"])


def test_copy_conflict_does_not_overwrite_and_errors_preserve_manifest(
    library, tmp_path
):
    a, b = tmp_path / "a/book.txt", tmp_path / "b/book.txt"
    for p, text in ((a, "first"), (b, "second")):
        p.parent.mkdir()
        p.write_text(text)
    rows, errors = library.add(
        [a, b, tmp_path / "missing"], "c1", "课程", tmp_path / "course"
    )
    assert len(rows) == 2 and len(errors) == 1
    assert rows[0]["path"] != rows[1]["path"]
    assert Path(rows[0]["path"]).read_text() == "first"
    assert len(library.items("c1")) == 2


def test_large_pdf_reads_only_requested_page_without_hash(
    library, tmp_path, monkeypatch
):
    from types import SimpleNamespace

    source = tmp_path / "textbook.pdf"
    with source.open("wb") as stream:
        stream.write(b"%PDF-")
        stream.truncate(65 * 1024 * 1024)
    rows, _ = library.add([source], "c1", "课程", tmp_path / "course")
    store = FileStore(tmp_path / "mcp", library.resolve)
    page = SimpleNamespace(extract_text=lambda: "第二页教材原文")
    monkeypatch.setattr(
        "pypdf.PdfReader",
        lambda stream: SimpleNamespace(is_encrypted=False, pages=[None, page]),
    )
    with patch(
        "xmu_rollcall.mcp_bridge.storage.digest",
        side_effect=AssertionError("must not hash"),
    ):
        file = store.register_local(rows[0])
        read = store.read(file["file_id"], unit=2)
    assert read["text"] == "第二页教材原文"
    assert read["locator"] == "第 2 页"
    assert "未全文索引" in read["note"]


def test_native_tree_locals_do_not_join_platform_download_selection(
    window, monkeypatch
):
    from PySide6.QtCore import Qt
    from xmu_rollcall.courseware import CourseSummary, CoursewareItem
    from xmu_rollcall.desktop_qt.local_materials_ui import ROLE_LOCAL

    def unexpected(*args, **kwargs):
        raise AssertionError(args[2] if len(args) > 2 else "unexpected dialog")

    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.information", unexpected)
    course = CourseSummary(
        "c1", "课程", window.courseware_academic_year_combo.currentText() + "-1"
    )
    window._set_courseware_courses([course], "fixture")
    window.courseware_combo.blockSignals(True)
    window.courseware_combo.setCurrentText(course.display_name)
    window.courseware_combo.blockSignals(False)
    window._local_material_owner = str(window.account["id"])
    window._local_material_rows = [
        {
            "resource_id": "local1",
            "course_id": "c1",
            "name": "教材.pdf",
            "chapter": "补充资料",
            "mode": "reference",
            "path": "D:/book.pdf",
        }
    ]
    item = CoursewareItem(
        "c1",
        "1",
        "活动",
        "material",
        "章节",
        "",
        "1",
        "1",
        "课件.pdf",
        1,
        "file",
        "",
        "ready",
        True,
    )
    window._set_courseware_items(course, [item])
    root = window.courseware_tree.topLevelItem(1)
    leaf = root.child(0).child(0)
    assert leaf.data(0, ROLE_LOCAL) == "local1"
    assert not leaf.flags() & Qt.ItemFlag.ItemIsUserCheckable
    window.select_all_courseware()
    assert window._selected_courseware_rows() == [0]
    window._filter_courseware_branch(leaf)
    assert window._courseware_current_local_id == "local1"


def test_brand_png_has_real_transparency_and_alpha_edges():
    from PySide6.QtGui import QImage
    root=Path(__file__).resolve().parents[1]
    paths=[root/"assets/xmu-university.png",root/"xmu-rollcall-cli/xmu_rollcall/assets/xmu-university.png",
           root/"android/app/src/main/res/drawable-nodpi/xmu_assistant_mark.png"]
    for path in paths:
        image=QImage(str(path))
        assert not image.isNull() and image.hasAlphaChannel()
        assert image.pixelColor(0,0).alpha()==0
        assert any(image.pixelColor(image.width()//2,y).alpha()>0 for y in range(image.height()))
