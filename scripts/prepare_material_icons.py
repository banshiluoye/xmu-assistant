"""Build tiny PNG resources from the selected Material Icon Theme SVG subset."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil

import requests

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "material-icon-svg"
DESTINATION = ROOT / "xmu-rollcall-cli" / "xmu_rollcall" / "assets" / "file_icons"
ICONS = ["folder", "folder-open", "folder-other", "pdf", "word", "table", "powerpoint", "zip", "image", "video", "audio", "python", "jupyter", "xml", "document"]


def download(name):
    path = SOURCE / (name + ".svg")
    if not path.exists():
        reference = ROOT.parent / "图标方案" / "A" / (name + ".svg")
        if reference.exists():
            shutil.copyfile(reference, path)
            return
        url = f"https://cdn.jsdelivr.net/npm/material-icon-theme@latest/icons/{name}.svg" if name in {"folder", "folder-open"} else "https://raw.githubusercontent.com/material-extensions/vscode-material-icon-theme/main/icons/" + name + ".svg"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        path.write_bytes(response.content)


def main():
    SOURCE.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(download, ICONS))
    license_path = SOURCE / "LICENSE.txt"
    if not license_path.exists():
        reference = ROOT.parent / "图标方案" / "A" / "LICENSE.txt"
        if reference.exists():
            shutil.copyfile(reference, license_path)
        else:
            response = requests.get("https://raw.githubusercontent.com/material-extensions/vscode-material-icon-theme/main/LICENSE", timeout=30)
            response.raise_for_status()
            license_path.write_bytes(response.content)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for name in ICONS:
        renderer = QSvgRenderer(str(SOURCE / (name + ".svg")))
        if not renderer.isValid():
            raise ValueError(name)
        for size in (24, 48, 72):
            image = QImage(size, size, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            renderer.render(painter, QRectF(0, 0, size, size))
            painter.end()
            if not image.save(str(DESTINATION / f"{name}-{size}.png")):
                raise OSError(name)
    shutil.copyfile(SOURCE / "LICENSE.txt", DESTINATION / "LICENSE-Material-Icon-Theme.txt")
    (DESTINATION / "ATTRIBUTION.txt").write_text("Material Icon Theme, Copyright (c) 2025 Material Extensions\nhttps://github.com/material-extensions/vscode-material-icon-theme\nMIT, see LICENSE-Material-Icon-Theme.txt\nSelected SVG assets rendered to transparent PNG at 24/48/72 px; shapes and colors unchanged.\nfolder.svg and folder-open.svg are generated assets from the official material-icon-theme npm package; other SVGs from the official repository.\n", encoding="utf-8")
    print("PNG assets:", len(ICONS) * 3, "bytes:", sum(path.stat().st_size for path in DESTINATION.iterdir()))
    app.quit()


if __name__ == "__main__":
    main()
