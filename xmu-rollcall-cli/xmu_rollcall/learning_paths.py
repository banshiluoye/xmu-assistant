"""Readable, bounded Windows directory names for downloaded courseware.

The on-disk layout stays shallow on purpose: course -> chapter -> file.  A
platform section is folded into the chapter label instead of adding another
level, and legacy numbered directories (``01 第一章``) are reused so repeated
downloads never create a second tree beside the old one.
"""
from __future__ import annotations

from pathlib import Path
import re


def directory_name(value: str, fallback: str = "未命名", limit: int = 55) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value)).strip(" .")
    value = value[:limit].rstrip(" .") or fallback
    if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", value):
        value = "_" + value
    return value


def chapter_name(item) -> str:
    """One readable directory name for the platform chapter (and section)."""
    module = str(getattr(item, "module_name", "") or "").strip()
    section = str(getattr(item, "syllabus_name", "") or "").strip()
    label = module
    if section and section != module:
        label = f"{module} - {section}" if module else section
    return directory_name(label, "未分组", limit=80)


def courseware_directory(item) -> Path:
    """Relative download directory for one courseware item (a single level)."""
    return Path(chapter_name(item))


# Kept for callers written against the old name; the value is now the chapter
# directory rather than a chapter/section/activity tree.
activity_directory = courseware_directory


def existing_directory(parent: Path, name: str, *, alternatives: tuple[str, ...] = ()) -> Path:
    """Reuse a matching directory under *parent* rather than adding a duplicate.

    Older releases prefixed folder names with numeric positions (``01 第一章``)
    and could format the term spacing differently, so an exact-name check alone
    would leave two copies after an update.  Matching ignores those legacy
    prefixes, repeated whitespace and letter case.  ``alternatives`` covers the
    old module-level folder when the new label also contains a section name.
    """
    target = parent / name
    try:
        if target.is_dir():
            return target
        children = sorted(parent.iterdir(), key=lambda child: child.name)
    except OSError:
        return target
    wanted = {_normalized(name), *(_normalized(value) for value in alternatives)}
    for child in children:
        if child.is_dir() and _normalized(_unprefixed(child.name)) in wanted:
            return child
    return target


def resolve_courseware_directory(parent: Path, item) -> Path:
    """Resolve the shallow chapter folder, reusing a legacy module/section tree."""
    module = str(getattr(item, "module_name", "") or "").strip()
    section = str(getattr(item, "syllabus_name", "") or "").strip()
    alternatives = []
    if module and section and section != module:
        alternatives.append(directory_name(module, "未分组", limit=80))
    elif section and not module:
        alternatives.append(directory_name(section, "未分组", limit=80))
    return existing_directory(parent, chapter_name(item), alternatives=tuple(alternatives))


_NUMERIC_PREFIX = re.compile(r"^\d{1,3}\s+")


def _unprefixed(name: str) -> str:
    return _NUMERIC_PREFIX.sub("", name, count=1)


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()
