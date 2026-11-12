"""Account-scoped workspaces and incremental text caches."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid
from contextlib import contextmanager

from .documents import extract_document


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


@contextmanager
def workspace_lock(root):
    """A nonblocking OS lock also serializes different AI clients/processes."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".bridge.lock").open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise ValueError(
                    "另一个 AI 客户端正在操作此账号，请稍后重试查询"
                ) from None
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ValueError(
                    "另一个 AI 客户端正在操作此账号，请稍后重试查询"
                ) from None
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


class FileStore:
    def __init__(self, root, local_resolver=None):
        self.local_resolver = local_resolver
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.state = self.root / ".bridge"
        self.state.mkdir(exist_ok=True)
        self.manifest_path = self.state / "files.json"
        self.files = (
            json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if self.manifest_path.exists()
            else {}
        )

    def inside(self, relative):
        path = Path(relative)
        if (
            path.is_absolute()
            or not path.parts
            or any(p in {"..", ".bridge"} or ":" in p for p in path.parts)
        ):
            raise ValueError(
                "路径必须在当前账号工作目录内，不能包含 ..、盘符或内部状态目录"
            )
        target = (self.root / path).resolve()
        if not target.is_relative_to(self.root) or target == self.root:
            raise ValueError("路径超出工作目录")
        return target

    def register(self, path, **source):
        path = Path(path).resolve()
        if (
            not path.is_relative_to(self.root)
            or path.is_relative_to(self.state)
            or not path.is_file()
        ):
            raise ValueError("只能登记当前账号工作目录内的普通文件")
        relative = path.relative_to(self.root).as_posix()
        key = next(
            (
                key
                for key, row in self.files.items()
                if row["relative_path"] == relative
            ),
            uuid.uuid4().hex,
        )
        stat = path.stat()
        self.files[key] = {
            "file_id": key,
            "relative_path": relative,
            "name": path.name,
            "bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": digest(path),
            **source,
        }
        write_json(self.manifest_path, self.files)
        return self.public(key)

    def path(self, file_id):
        if file_id not in self.files:
            raise ValueError("未知文件标识，请先下载、创建或登记文件")
        row = self.files[file_id]
        if row.get("local_resource_id"):
            if self.local_resolver is None:
                raise ValueError("本地资料索引未连接")
            path = self.local_resolver(row["local_resource_id"])
        else:
            path = self.inside(row["relative_path"])
        if not path.is_file():
            raise ValueError("文件已移动或删除")
        return path

    def public(self, file_id):
        return {**self.files[file_id], "local_path": str(self.path(file_id))}

    def register_local(self, resource):
        resource_id = resource["resource_id"]
        path = self.local_resolver(resource_id)
        stat = path.stat()
        key = "local-" + resource_id
        from .documents import MAX_FILE

        self.files[key] = {
            "file_id": key,
            "relative_path": "@local/" + resource_id,
            "local_resource_id": resource_id,
            "name": resource["name"],
            "course_id": resource["course_id"],
            "origin": "local_course_material",
            "chapter": resource["chapter"],
            "mode": resource["mode"],
            "bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": digest(path) if stat.st_size <= MAX_FILE else None,
        }
        write_json(self.manifest_path, self.files)
        return self.public(key)

    def document(self, file_id):
        path = self.path(file_id)
        from .documents import MAX_FILE

        if path.stat().st_size > MAX_FILE:
            raise ValueError(
                "文件超过64 MiB，已保留引用；请使用客户端专用工具按页读取，不自动全文解析"
            )
        row = self.files[file_id]
        stat = path.stat()
        cache = self.state / f"text-{file_id}.json"
        if stat.st_size != row["bytes"] or stat.st_mtime_ns != row["mtime_ns"]:
            row.update(
                bytes=stat.st_size, mtime_ns=stat.st_mtime_ns, sha256=digest(path)
            )
            write_json(self.manifest_path, self.files)
        if cache.exists():
            value = json.loads(cache.read_text(encoding="utf-8"))
            if value.get("sha256") == row["sha256"]:
                return value
        value = {**extract_document(path), "sha256": row["sha256"]}
        write_json(cache, value)
        return value

    def read(self, file_id, unit=1, offset=0, limit=12000):
        path = self.path(file_id)
        from .documents import MAX_FILE, read_large_pdf

        if path.stat().st_size > MAX_FILE and path.suffix.lower() == ".pdf":
            return {
                "file_id": file_id,
                "name": self.files[file_id]["name"],
                **read_large_pdf(path, unit, offset, limit),
            }
        value = self.document(file_id)
        units = value["units"]
        if not 1 <= unit <= len(units):
            return {
                "file": self.public(file_id),
                "units": len(units),
                "note": value["note"],
                "text": "",
            }
        row = units[unit - 1]
        text = row["text"]
        offset = max(0, offset)
        limit = min(24000, max(1, limit))
        return {
            "file_id": file_id,
            "name": self.files[file_id]["name"],
            "unit": unit,
            "units": len(units),
            "locator": row["locator"],
            "offset": offset,
            "text": text[offset : offset + limit],
            "next_offset": offset + limit if offset + limit < len(text) else None,
            "note": value["note"],
        }

    def search(self, query, course_id="", limit=12):
        if not query.strip():
            raise ValueError("请输入检索关键词")
        terms = query.casefold().split()[:12]
        hits, indexed, unindexed = [], 0, 0
        for key, row in list(self.files.items()):
            if course_id and str(row.get("course_id", "")) != course_id:
                continue
            cache = self.state / f"text-{key}.json"
            if not cache.exists():
                unindexed += 1
                continue
            if indexed >= 100:
                unindexed += 1
                continue
            try:
                value = self.document(key)
            except (ValueError, OSError):
                unindexed += 1
                continue
            indexed += 1
            for number, unit in enumerate(value["units"], 1):
                lowered = unit["text"].casefold()
                positions = [lowered.find(term) for term in terms]
                found = [p for p in positions if p >= 0]
                if not found:
                    continue
                start = max(0, min(found) - 160)
                hits.append(
                    {
                        "file_id": key,
                        "name": row["name"],
                        "course_id": row.get("course_id", ""),
                        "locator": unit["locator"],
                        "unit": number,
                        "offset": start,
                        "excerpt": unit["text"][start : start + 900],
                        "matched_terms": len(found),
                    }
                )
        hits.sort(key=lambda row: -row["matched_terms"])
        return {
            "hits": hits[: min(30, max(1, limit))],
            "indexed_files_searched": indexed,
            "unindexed_files": unindexed,
            "scope": "只搜索当前账号已下载并索引的文件；不表示已覆盖全部课程资料",
        }
