from dataclasses import replace
from datetime import timedelta
import io
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
import requests

from xmu_rollcall.learning import (LearningApi, LearningStore, LearningTask, MultipartFile,
    ProgressFile, SubmissionUncertain, platform_time)
from xmu_rollcall.learning_html import clean_html
from xmu_rollcall.learning_paths import courseware_directory, directory_name, existing_directory, resolve_courseware_directory


TASK = LearningTask("123", "456", "示例课程", "示例作业", "homework")


def test_datetime_and_type_specific_links():
    assert platform_time("2026-11-05T00:00:00Z").hour == 8
    assert platform_time("2026-11-05 08:00:00").utcoffset() == timedelta(hours=8)
    assert platform_time("bad") is None
    assert replace(TASK, kind="exam").url.endswith("#/exam/123")
    assert TASK.url.endswith("#/123")


def test_platform_activity_order_wins_over_creation_id():
    from xmu_rollcall.courseware import _activity_order_key
    activities = [{"id": 1, "module_id": 5, "sort": 20}, {"id": 2, "module_id": 5, "sort": 10}]
    ordered = sorted(enumerate(activities), key=lambda pair: _activity_order_key(pair[1], {("5", ""): (0, 0)}, pair[0]))
    assert [value["id"] for _, value in ordered] == [2, 1]


def test_malformed_todos_are_not_an_empty_success():
    api = LearningApi(None)
    api.request = mock.Mock(return_value={"message": "different schema"})
    with pytest.raises(ValueError):
        api.todos()


def test_homework_history_reads_every_page_and_submission_state():
    api = LearningApi(None)
    api.request = mock.Mock(side_effect=[
        {"pages": 2, "homework_activities": [{"id": 1, "submitted": True}]},
        {"pages": 2, "homework_activities": [{"id": 2, "submitted": False}]},
    ])
    tasks = api.homework_list("456", "课程")
    assert [task.status for task in tasks] == ["已提交", "未完成"]
    assert api.request.call_args_list[1].kwargs["params"]["page"] == 2


def test_windows_courseware_directory_is_flat_and_reuses_legacy_names(tmp_path):
    item = SimpleNamespace(module_name="第一章", syllabus_name="1.1 概述", activity_title="CON", activity_id="99", chapter_index=1, activity_index=2)
    path = courseware_directory(item)
    assert len(path.parts) == 1
    assert path.name == "第一章 - 1.1 概述"
    assert not path.is_absolute()
    legacy = tmp_path / ("01 " + path.name)
    legacy.mkdir()
    assert existing_directory(tmp_path, path.name) == legacy
    module_legacy = tmp_path / "legacy"
    module_legacy.mkdir()
    (module_legacy / "01 第一章").mkdir()
    assert resolve_courseware_directory(module_legacy, item) == module_legacy / "01 第一章"
    spaced = tmp_path / "社会学与生活  [2026-2027]"
    spaced.mkdir()
    assert existing_directory(tmp_path, "社会学与生活 [2026-2027]") == spaced
    assert directory_name("COM1.txt") == "_COM1.txt"
    assert len(directory_name("长" * 100)) <= 55


def test_streaming_multipart_body_has_exact_length_and_does_not_buffer_entire_file():
    stream = io.BytesIO(b"abc" * 50000)
    progress = []
    body = MultipartFile(ProgressFile(stream, 150000, lambda sent, size: progress.append((sent, size)), lambda: None), 'a"b.txt', "text/plain")
    chunks = []
    while value := body.read(8192):
        assert len(value) <= 8192
        chunks.append(value)
    result = b"".join(chunks)
    assert len(result) == len(body)
    assert b'filename="a_b.txt"' in result
    assert b"abc" * 50000 in result
    assert progress[-1] == (150000, 150000)


def test_upload_to_storage_does_not_forward_school_session(tmp_path):
    path = tmp_path / "answer.txt"
    path.write_text("answer", encoding="utf-8")
    school, storage = mock.Mock(), mock.Mock()
    response = mock.Mock(is_redirect=False)
    storage.put.return_value = response
    api = LearningApi(school)
    api.request = mock.Mock(return_value={"id": 8, "upload_url": "https://storage.example/upload", "storage_type": "LOCAL"})
    with mock.patch("xmu_rollcall.learning.requests.Session", return_value=storage):
        uploaded = api.upload_file(path)
    assert uploaded["id"] == 8
    school.put.assert_not_called()
    assert "Cookie" not in storage.put.call_args.kwargs["headers"]
    assert storage.put.call_args.kwargs["allow_redirects"] is False
    storage.close.assert_called_once()


def snapshot(comment="", *, record_id=None, draft=False, uploads=()):
    return {"detail": {"is_closed": False}, "group": False, "history": [],
            "submission": {"id": record_id, "is_draft": draft, "comment": comment, "uploads": list(uploads)}}


def test_submission_timeout_is_verified_without_second_post():
    api = LearningApi(None)
    api.homework = mock.Mock(side_effect=[snapshot(), snapshot("<p>答案</p>", record_id=9, uploads=[{"id": 8}])])
    api.request = mock.Mock(side_effect=requests.ReadTimeout())
    result = api.submit(TASK, "<p>答案</p>", [{"id": 8}])
    assert result["submission"]["id"] == 9
    assert api.request.call_count == 1
    assert api.request.call_args.kwargs["json"] == {"comment": "<p>答案</p>", "uploads": [8], "slides": [], "is_draft": False}


def test_unconfirmed_submission_is_never_reported_success_or_retried():
    api = LearningApi(None)
    api.homework = mock.Mock(return_value=snapshot())
    api.request = mock.Mock(return_value={})
    with pytest.raises(SubmissionUncertain):
        api.submit(TASK, "new answer", [])
    assert api.request.call_count == 1


def test_same_confirmed_submission_does_not_create_duplicate():
    api = LearningApi(None)
    api.homework = mock.Mock(return_value=snapshot("same", record_id=1))
    api.request = mock.Mock()
    api.submit(TASK, "same", [])
    api.request.assert_not_called()


def test_group_submission_is_not_sent_to_personal_endpoint():
    api = LearningApi(None)
    api.homework = mock.Mock(return_value={**snapshot(), "group": True})
    api.request = mock.Mock()
    with pytest.raises(ValueError, match="分组"):
        api.submit(TASK, "answer", [])
    api.request.assert_not_called()


def test_store_is_account_scoped_and_atomic(tmp_path):
    first, second = LearningStore("account-a", tmp_path), LearningStore("account-b", tmp_path)
    first.save_tasks([TASK], last_sync="now")
    assert second.read("tasks") is None
    assert first.read("tasks")["tasks"][0]["activity_id"] == "123"
    assert len(list(first.directory.iterdir())) == 1


def test_rich_html_removes_active_content_and_local_files():
    result = clean_html('<script>alert(1)</script><p onclick="x()">答案 <b>bold</b><img src="file:///secret"><a href="javascript:alert(1)">link</a></p>')
    assert "script" not in result and "file:" not in result and "onclick" not in result and "javascript:" not in result
    assert "<b>bold</b>" in result


def test_expired_or_missing_cookie_uses_saved_credentials_once():
    from xmu_rollcall.desktop_qt import app
    old, fresh = mock.Mock(), mock.Mock()
    host = SimpleNamespace(_emit=mock.Mock())
    account = {"id": 1, "username": "fixture", "password": "fixture password"}
    with mock.patch.object(app, "load_config", return_value={}), mock.patch.object(app, "get_current_account", return_value=account), \
         mock.patch.object(app.requests, "Session", return_value=old), mock.patch.object(app, "load_session", return_value=False), \
         mock.patch.object(app, "xmulogin", return_value=fresh) as login, mock.patch.object(app, "verify_session", return_value={"name": "Fixture"}):
        app.DashboardWindow._restore_worker(host, True, 4)
    login.assert_called_once_with(type=3, username="fixture", password="fixture password")
    event = host._emit.call_args.args[0]
    assert event[:4] == ("login_success", fresh, None, 4)
    old.close.assert_called_once()
    fresh.close.assert_not_called()


def test_offline_startup_does_not_attempt_password_login():
    from xmu_rollcall.desktop_qt import app
    host = SimpleNamespace(_emit=mock.Mock())
    with mock.patch.object(app, "load_config", return_value={}), \
         mock.patch.object(app, "get_current_account", return_value={"id": 1, "password": "fixture"}), \
         mock.patch.object(app, "load_session", return_value=True), mock.patch.object(app, "verify_session", return_value=None), \
         mock.patch.object(app, "xmulogin") as login:
        app.DashboardWindow._restore_worker(host, True, 4)
    login.assert_not_called()
    assert host._emit.call_args.args[0][-1] == "network"
