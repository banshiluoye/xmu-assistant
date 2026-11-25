"""Student learning API. Reads never mark activities complete or start exams."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import mimetypes
import os
from pathlib import Path
import tempfile
from urllib.parse import urljoin, urlsplit

import requests

from .config import get_config_dir
from .learning_html import submission_html
from .utils import API_TIMEOUT, DOWNLOAD_TIMEOUT, SessionExpiredError, base_url, headers, response_session_expired

LOCAL_TZ = timezone(timedelta(hours=8))
TASK_TYPES = {"homework": "作业", "exam": "测验", "questionnaire": "问卷", "discussion": "讨论", "material": "资料"}


def user_attachments(submission):
    return [item for item in submission.get("uploads") or [] if item.get("source") != "auto-generated-pdf"]


def generated_previews(submission):
    return [item for item in submission.get("uploads") or [] if item.get("source") == "auto-generated-pdf"]


def submission_file_counts(submission):
    return {
        "attachment_count": len(user_attachments(submission)),
        "platform_text_preview_count": len(generated_previews(submission)),
    }


def platform_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=LOCAL_TZ) if parsed.tzinfo is None else parsed.astimezone(LOCAL_TZ)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class LearningTask:
    activity_id: str
    course_id: str
    course_name: str
    title: str
    kind: str
    deadline: str = ""
    status: str = "未完成"
    locked: bool = False

    @property
    def key(self):
        return f"{self.course_id}:{self.kind}:{self.activity_id}"

    @property
    def url(self):
        suffix = f"exam/{self.activity_id}" if self.kind == "exam" else f"questionnaire/{self.activity_id}" if self.kind == "questionnaire" else self.activity_id
        return f"{base_url}/course/{self.course_id}/learning-activity#/{suffix}"

    @property
    def due(self):
        return platform_time(self.deadline)

    @classmethod
    def from_api(cls, value, *, course_id="", course_name=""):
        if not isinstance(value, dict) or not value.get("id") or not (value.get("course_id") or course_id):
            raise ValueError("待办记录缺少课程或活动标识")
        status = "未完成"
        if value.get("submitted") is True:
            status = "已提交"
        elif str(value.get("submitted_status", "")).lower() in {"draft", "is_draft"}:
            status = "草稿"
        return cls(str(value["id"]), str(value.get("course_id") or course_id),
                   str(value.get("course_name") or course_name), str(value.get("title") or "未命名活动"),
                   str(value.get("type") or "homework"), str(value.get("end_time") or value.get("deadline") or ""), status,
                   bool(value.get("is_locked", False)))


class LearningApi:
    def __init__(self, session, ensure_current=None):
        self.session = session
        self.ensure_current = ensure_current or (lambda: None)

    def request(self, method, endpoint, **kwargs):
        self.ensure_current()
        response = self.session.request(method, base_url + endpoint, headers=headers, timeout=kwargs.pop("timeout", API_TIMEOUT), **kwargs)
        if response.status_code == 401 or response_session_expired(response):
            raise SessionExpiredError("登录已过期，请重新登录")
        response.raise_for_status()
        if response.status_code == 204:
            return {}
        if "json" not in response.headers.get("Content-Type", ""):
            raise ValueError("平台返回了网页，无法确认操作结果")
        payload = response.json()
        if isinstance(payload, dict) and payload.get("errors"):
            raise ValueError("平台未接受此操作，请在原页面检查作业要求")
        return payload

    def todos(self):
        payload = self.request("GET", "/api/todos")
        values = payload.get("todo_list") if isinstance(payload, dict) else None
        if not isinstance(values, list):
            raise ValueError("平台待办格式已变化；保留上次结果")
        return [LearningTask.from_api(value) for value in values]

    def homework_list(self, course_id, course_name):
        result = []
        for page in range(1, 101):
            payload = self.request("GET", f"/api/courses/{course_id}/homework-activities", params={"page": page, "page_size": 100})
            values = payload.get("homework_activities")
            if not isinstance(values, list):
                raise ValueError("平台作业列表格式已变化")
            result.extend(LearningTask.from_api(value, course_id=course_id, course_name=course_name) for value in values)
            if page >= int(payload.get("pages", 1)) or not values:
                return result
        raise ValueError("作业列表分页超过上限，请缩小查询范围")

    def homework(self, task):
        detail = self.request("GET", f"/api/activities/{task.activity_id}")
        if str(detail.get("course_id")) != task.course_id or detail.get("type") != "homework":
            raise ValueError("活动类型或课程不匹配，请刷新待办")
        if detail.get("submit_by_group"):
            # A group write must not silently use the personal submission route.
            return {"detail": detail, "submission": {}, "history": [], "group": True}
        profile = self.request("GET", "/api/profile")
        user_id = profile["id"]
        submission = self.request("GET", f"/api/course/activities/{task.activity_id}/students/{user_id}/submission")
        history = self.request("GET", f"/api/activities/{task.activity_id}/students/{user_id}/submission_list")
        return {"detail": detail, "submission": submission, "history": history.get("list", []), "group": False}

    def upload_file(self, filename, progress=None):
        path = Path(filename)
        if not path.is_file():
            raise ValueError(f"文件不存在：{path.name}")
        size = path.stat().st_size
        metadata = self.request("POST", "/api/uploads", json={
            "name": path.name, "size": size, "parent_type": None, "parent_id": 0,
            "is_scorm": False, "is_wmpkg": False,
        })
        if not metadata.get("id") or not metadata.get("upload_url"):
            raise ValueError("平台没有返回有效的附件上传地址")
        url = urljoin(base_url, metadata["upload_url"])
        if urlsplit(url).scheme != "https" or urlsplit(url).username or urlsplit(url).password:
            raise ValueError("平台返回了不受支持的上传地址")
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.ensure_current()
        # Storage hosts receive the selected file, never the school's cookies.
        same_origin = urlsplit(url).netloc == urlsplit(base_url).netloc
        transport = self.session if same_origin else requests.Session()
        if not same_origin:
            transport.trust_env = False
        try:
            with path.open("rb") as raw:
                source = ProgressFile(raw, size, progress, self.ensure_current)
                storage = str(metadata.get("storage_type", "")).upper()
                if storage == "QINIU":
                    token = self.request("GET", "/api/uptoken", params={"id": metadata["id"]})["uptoken"]
                    contexts = []
                    offset = 0
                    if not size:
                        raise ValueError("不能上传空文件")
                    while offset < size:
                        block_size = min(4 * 1024 * 1024, size - offset)
                        def block_progress(sent, total, start=offset):
                            if progress:
                                progress(start + sent, size)
                        block = ProgressFile(raw, block_size, block_progress, self.ensure_current)
                        response = transport.post(url.rstrip("/") + f"/mkblk/{block_size}", data=block, headers={"Authorization": "UpToken " + token, "Content-Type": "application/octet-stream"}, timeout=DOWNLOAD_TIMEOUT, allow_redirects=False)
                        response.raise_for_status()
                        if response.is_redirect:
                            raise ValueError("上传地址发生跳转，请重新读取作业后重试")
                        contexts.append(response.json()["ctx"])
                        offset += block_size
                    self.ensure_current()
                    response = transport.post(url.rstrip("/") + f"/mkfile/{size}", data=",".join(contexts), headers={"Authorization": "UpToken " + token, "Content-Type": "text/plain;charset=UTF-8"}, timeout=DOWNLOAD_TIMEOUT, allow_redirects=False)
                elif storage == "S3" and metadata.get("transcoder") == "WRPC":
                    response = transport.put(url, data=source, headers={"Content-Type": mime}, timeout=DOWNLOAD_TIMEOUT, allow_redirects=False)
                else:
                    # requests' multipart encoder buffers files; use a streaming body.
                    body = MultipartFile(source, path.name, mime)
                    response = transport.put(url, data=body, headers={"Content-Type": body.content_type}, timeout=DOWNLOAD_TIMEOUT, allow_redirects=False)
                response.raise_for_status()
                if response.is_redirect:
                    raise ValueError("上传地址发生跳转，请重新读取作业后重试")
            if str(metadata.get("storage_type", "")).upper() == "S3":
                self.request("POST", f"/internal-api/upload/callback/{metadata['id']}", json={"file_key": metadata["id"]})
            if progress:
                progress(size, size)
            return {"id": metadata["id"], "name": path.name}
        finally:
            if transport is not self.session:
                transport.close()

    def submit(self, task, content, uploads, *, is_draft=False):
        content = submission_html(content)
        current = self.homework(task)
        detail = current["detail"]
        if current["group"]:
            raise ValueError("分组作业请在原平台提交")
        if detail.get("is_closed") or detail.get("is_started") is False:
            raise ValueError("作业当前不可提交，请检查开放时间")
        # A legacy draft may have kept only the attachment ID and lost source.
        previews = {str(item["id"]) for item in generated_previews(current["submission"]) if item.get("id") is not None}
        uploads = [
            item for item in user_attachments({"uploads": uploads})
            if str(item["id"]) not in previews
        ]
        if submission_matches(current["submission"], content, uploads, is_draft=is_draft):
            return current
        self.ensure_current()
        payload = {"comment": content, "uploads": [entry["id"] for entry in uploads], "slides": [], "is_draft": is_draft}
        try:
            self.request("POST", f"/api/course/activities/{task.activity_id}/submissions", json=payload, timeout=DOWNLOAD_TIMEOUT)
        except (requests.RequestException, ValueError):
            # A timeout can occur after the server commits. Never retry the write.
            pass
        checked = self.homework(task)
        submission = checked["submission"]
        if not submission_matches(submission, content, uploads, is_draft=is_draft):
            raise SubmissionUncertain("提交结果尚未确认，已保留本地草稿和上传附件；请刷新记录或打开原页面检查，避免直接重交。")
        return checked


def submission_matches(submission, content, uploads, *, is_draft):
    expected = {str(entry["id"]) for entry in uploads}
    return (
        submission.get("id") is not None
        and bool(submission.get("is_draft")) == is_draft
        and submission_html(submission.get("comment") or "") == content
        and expected == {str(entry.get("id")) for entry in user_attachments(submission)}
        and (bool(content) or not generated_previews(submission))
    )


class SubmissionUncertain(RuntimeError):
    pass


class ProgressFile:
    def __init__(self, stream, size, progress, check):
        self.stream, self.size, self.progress, self.check = stream, size, progress, check
        self.sent = 0

    def __len__(self):
        return self.size

    def read(self, size=-1):
        self.check()
        remaining = self.size - self.sent
        if remaining <= 0:
            return b""
        size = min(remaining, size) if size >= 0 else min(remaining, 65536)
        data = self.stream.read(size)
        self.sent += len(data)
        if self.progress:
            self.progress(self.sent, self.size)
        return data


class MultipartFile:
    def __init__(self, source, name, mime):
        boundary = "xmu-assistant-" + os.urandom(16).hex()
        name = name.replace('"', "_").replace("\r", "_").replace("\n", "_")
        self.prefix = f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: {mime}\r\n\r\n'.encode("utf-8")
        self.suffix = f"\r\n--{boundary}--\r\n".encode()
        self.source = source
        self.content_type = "multipart/form-data; boundary=" + boundary
        self.length = len(self.prefix) + len(source) + len(self.suffix)
        self.position = 0

    def __len__(self):
        return self.length

    def read(self, size=-1):
        size = 65536 if size < 0 else size
        if self.position < len(self.prefix):
            chunk = self.prefix[self.position:self.position + size]
        elif self.position < len(self.prefix) + len(self.source):
            chunk = self.source.read(size)
        else:
            offset = self.position - len(self.prefix) - len(self.source)
            chunk = self.suffix[offset:offset + size]
        self.position += len(chunk)
        return chunk


class LearningStore:
    def __init__(self, account_id, directory=None):
        import hashlib
        token = hashlib.sha256(str(account_id).encode()).hexdigest()[:20]
        self.directory = Path(directory or get_config_dir()) / "learning" / token

    def read(self, name, default=None):
        try:
            value = json.loads((self.directory / (name + ".json")).read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else default
        except (OSError, ValueError):
            return default

    def write(self, name, data):
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, ensure_ascii=False)
            os.replace(temporary, self.directory / (name + ".json"))
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def save_tasks(self, tasks, **metadata):
        self.write("tasks", {"tasks": [asdict(task) for task in tasks][-1000:], **metadata})

    def draft_name(self, task):
        import hashlib
        return "draft-" + hashlib.sha256(task.key.encode()).hexdigest()[:24]
