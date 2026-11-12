"""User-added course files: small account-scoped manifests, no scanning or hashing."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import uuid

from .config import get_config_dir
from .learning_paths import directory_name

DEFAULT_REFERENCE_MIB = 50
_LOCK = threading.RLock()


class LocalMaterialStore:
    def __init__(self, account_id, username="", directory=None):
        owner = hashlib.sha256(f"{account_id}:{username}".encode()).hexdigest()[:24]
        self.directory = Path(directory or get_config_dir()) / "local-materials" / owner
        self.path = self.directory / "library.json"

    @contextmanager
    def transaction(self):
        with _LOCK:
            self.directory.mkdir(parents=True, exist_ok=True)
            with (self.directory / "library.lock").open("a+b") as lock:
                if lock.tell() == 0:
                    lock.write(b"0")
                    lock.flush()
                lock.seek(0)
                if os.name == "nt":
                    import msvcrt

                    try:
                        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    except OSError:
                        raise ValueError(
                            "资料清单正由另一个窗口更新，请稍后重试"
                        ) from None
                else:
                    import fcntl

                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    data = self.read()
                    yield data
                    self._save(data)
                finally:
                    if os.name == "nt":
                        lock.seek(0)
                        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(lock, fcntl.LOCK_UN)

    def read(self):
        if not self.path.exists():
            return {
                "schema": 1,
                "reference_threshold_mib": DEFAULT_REFERENCE_MIB,
                "courses": {},
            }
        if self.path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("本地资料清单过大，请先备份并检查清单")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("schema") != 1 or not isinstance(data.get("courses"), dict):
            raise ValueError("本地资料清单格式无效，已保留原文件")
        return data

    def _save(self, data):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.directory, delete=False
            ) as file:
                temporary = Path(file.name)
                json.dump(data, file, ensure_ascii=False)
            os.replace(temporary, self.path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    def items(self, course_id=""):
        courses = self.read()["courses"]
        if course_id:
            return list(courses.get(str(course_id), []))
        return [row for values in courses.values() for row in values]

    def get(self, resource_id):
        row = next((r for r in self.items() if r["resource_id"] == resource_id), None)
        if row is None:
            raise ValueError("本地资料已移除，请重新读取清单")
        return row

    def resolve(self, resource_id):
        row = self.get(resource_id)
        path = Path(row["path"])
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            raise ValueError(
                "资料文件已移动、删除或所在磁盘未连接，请重新定位"
            ) from None
        if str(resolved) != row["path"] or not resolved.is_file():
            raise ValueError("资料位置已变化，请在助手中重新定位")
        return resolved

    def add(
        self,
        filenames,
        course_id,
        course_title,
        course_directory,
        *,
        chapter="补充资料",
        chapter_id="",
        mode="copy",
        threshold_mib=DEFAULT_REFERENCE_MIB,
        ensure=lambda: None,
    ):
        if mode not in {"copy", "reference"} or not 1 <= threshold_mib <= 2048:
            raise ValueError("导入模式或自动引用阈值无效")
        course_directory = Path(course_directory).resolve()
        added, errors = [], []
        for filename in filenames:
            ensure()
            copied = None
            try:
                source = Path(filename).resolve(strict=True)
                if not source.is_file():
                    raise ValueError("请选择普通文件")
                size = source.stat().st_size
                duplicate = next(
                    (
                        r
                        for r in self.items(str(course_id))
                        if r.get("source_path") == str(source)
                        and r.get("source_bytes") == size
                        and r.get("source_mtime_ns") == source.stat().st_mtime_ns
                    ),
                    None,
                )
                if duplicate and Path(duplicate["path"]).is_file():
                    added.append(duplicate)
                    continue
                if mode == "reference" or size > threshold_mib * 1024 * 1024:
                    target, selected_mode = source, "reference"
                    reason = "超过自动引用阈值" if mode == "copy" else "用户选择引用"
                elif source.is_relative_to(course_directory):
                    target, selected_mode, reason = (
                        source,
                        "existing",
                        "已在课程目录，未重复复制",
                    )
                else:
                    target_dir = course_directory / directory_name(chapter) / "本地资料"
                    target_dir.mkdir(parents=True, exist_ok=True)
                    if not target_dir.resolve().is_relative_to(course_directory):
                        raise ValueError("目标目录位置已变化，请重新选择下载目录")
                    target = target_dir / directory_name(source.name, "资料", 180)
                    counter = 1
                    while target.exists():
                        target = (
                            target_dir
                            / f"{source.stem[:140]} ({counter}){source.suffix[:20]}"
                        )
                        counter += 1
                    # Create exclusively and copy in bounded chunks on the caller's worker.
                    with source.open("rb") as reader, target.open("xb") as writer:
                        copied = target
                        total = 0
                        while chunk := reader.read(1024 * 1024):
                            ensure()
                            total += len(chunk)
                            if total > threshold_mib * 1024 * 1024:
                                raise OverflowError("复制期间文件增大")
                            writer.write(chunk)
                    if source.stat().st_size != total:
                        raise ValueError("文件在复制期间发生变化，请重试")
                    target, selected_mode, reason = (
                        target.resolve(),
                        "copy",
                        "已复制到课程目录",
                    )
                ensure()
                row = {
                    "resource_id": uuid.uuid4().hex,
                    "course_id": str(course_id),
                    "course_title": course_title,
                    "chapter": chapter or "补充资料",
                    "chapter_id": str(chapter_id),
                    "name": source.name,
                    "path": str(target),
                    "mode": selected_mode,
                    "reason": reason,
                    "bytes": target.stat().st_size,
                    "source_path": str(source),
                    "source_bytes": size,
                    "source_mtime_ns": source.stat().st_mtime_ns,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                with self.transaction() as data:
                    rows = data["courses"].setdefault(str(course_id), [])
                    duplicate = next(
                        (r for r in rows if r["path"] == row["path"]), None
                    )
                    if not duplicate:
                        rows.append(row)
                    data["reference_threshold_mib"] = threshold_mib
                added.append(duplicate or row)
            except OverflowError:
                if copied:
                    copied.unlink(missing_ok=True)
                # A file growing past the threshold is also automatically referenced.
                more, failed = self.add(
                    [filename],
                    course_id,
                    course_title,
                    course_directory,
                    chapter=chapter,
                    chapter_id=chapter_id,
                    mode="reference",
                    threshold_mib=threshold_mib,
                    ensure=ensure,
                )
                added.extend(more)
                errors.extend(failed)
            except (OSError, ValueError) as error:
                if copied:
                    copied.unlink(missing_ok=True)
                errors.append({"name": Path(filename).name, "error": str(error)})
        return added, errors

    def remove(self, resource_id):
        with self.transaction() as data:
            for course, rows in data["courses"].items():
                data["courses"][course] = [
                    r for r in rows if r["resource_id"] != resource_id
                ]
        # Removal deliberately never deletes a user's file.

    def relocate(self, resource_id, filename):
        path = Path(filename).resolve(strict=True)
        if not path.is_file():
            raise ValueError("请选择普通文件")
        with self.transaction() as data:
            for rows in data["courses"].values():
                for row in rows:
                    if row["resource_id"] == resource_id:
                        row.update(
                            path=str(path),
                            name=path.name,
                            bytes=path.stat().st_size,
                            mode="reference",
                            reason="重新定位",
                        )
                        return row
            raise ValueError("资料条目不存在")
