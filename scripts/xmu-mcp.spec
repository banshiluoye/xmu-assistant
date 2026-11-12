"""Standalone STDIO MCP process; no Qt or embedded language model."""
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parent
a = Analysis(
    [str(root / 'scripts/xmu_mcp_launcher.py')],
    pathex=[str(root / 'xmu-rollcall-cli')],
    datas=collect_data_files('mcp'),
    hiddenimports=['win32crypt', 'pypdf'],
    excludes=['PySide6', 'PyQt6', 'PyQt5', 'tkinter', 'pytest', 'unittest', 'xmulogin', 'numpy', 'pandas', 'matplotlib'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='xmu-study-mcp-1.10.0',
          debug=False, strip=False, upx=False, console=True,
          icon=str(root / 'assets/xmu-assistant.ico'))
