"""Campus integration invariants using synthetic accounts and no school writes."""

import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock
import zipfile

import pytest

from xmu_rollcall.mcp_bridge.documents import extract_document, grade_statistics
from xmu_rollcall.mcp_bridge.storage import FileStore, workspace_lock
from xmu_rollcall.mcp_bridge import service as bridge


@pytest.fixture
def campus(tmp_path, monkeypatch):
    current = {"id": 1, "username": "synthetic", "name": "测试账号"}
    cookie = tmp_path / "session.json"
    cookie.write_text("synthetic-cookie", encoding="utf-8")
    monkeypatch.setattr(bridge, "load_config", lambda: {"account": current})
    monkeypatch.setattr(bridge, "get_current_account", lambda config: config["account"])
    monkeypatch.setattr(bridge, "get_cookies_path", lambda owner: str(cookie))
    monkeypatch.setattr(bridge, "load_session", lambda session, path: True)
    service = bridge.CampusService(tmp_path / "workspace")
    record = {
        "detail": {
            "title": "实验报告",
            "course_id": "c1",
            "type": "homework",
            "uploads": [{"id": 8, "name": "题目.pdf"}],
        },
        "submission": {"id": None, "comment": "", "is_draft": False, "uploads": []},
        "group": False,
        "history": [],
    }
    api = SimpleNamespace(
        homework=Mock(side_effect=lambda task: json.loads(json.dumps(record))),
        upload_file=Mock(return_value={"id": 99, "name": "报告.md"}),
        submit=Mock(return_value={"submission": {"id": 123, "is_draft": True}}),
    )
    monkeypatch.setattr(bridge, "LearningApi", lambda *args: api)
    return service, current, cookie, record, api


def test_course_order_and_pagination(campus, monkeypatch):
    service, *_ = campus
    from xmu_rollcall.courseware import CourseSummary

    monkeypatch.setattr(
        bridge,
        "fetch_courses",
        lambda session: ([CourseSummary("b", "编译"), CourseSummary("a", "算法")], ""),
    )
    result = service.courses(limit=1)
    assert result["items"][0]["course_id"] == "b"
    assert result["next_offset"] == 1


def test_default_todo_filter_and_history_option(campus):
    service, _, _, _, api = campus
    from xmu_rollcall.learning import LearningTask

    tasks = [
        LearningTask("a", "c1", "课程", "过期", "homework", "2000-01-01"),
        LearningTask("b", "c1", "课程", "无截止", "homework"),
    ]
    api.todos = lambda: tasks
    api.homework_list = lambda *args: tasks
    assert [r["title"] for r in service.tasks()["items"]] == ["无截止"]
    assert service.tasks(course_id="c1", include_overdue=True)["total"] == 2


def test_assignment_output_is_narrow_and_has_snapshot(campus):
    service, _, _, record, _ = campus
    record["detail"].update(secret="never-expose", student_list=[{"name": "other"}])
    record["submission"]["token"] = "private"
    result = service.assignment("c1", "h1")
    assert result["attachments"] == [{"id": 8, "name": "题目.pdf"}]
    assert "never-expose" not in json.dumps(result)
    assert "private" not in json.dumps(result)
    assert len(result["platform_snapshot"]) == 64


def test_assignment_includes_real_nested_platform_description(campus):
    service, _, _, record, _ = campus
    record["detail"]["data"] = {"description": "<p>请分析社会分层。</p>", "private": "do-not-expose"}
    value = service.assignment("c1", "h1")
    assert "社会分层" in value["requirements"]["description"]
    assert "do-not-expose" not in json.dumps(value)


def test_download_own_submission_attachment_but_not_other_uploads(campus, monkeypatch):
    service, _, _, record, _ = campus
    record["submission"]["uploads"] = [{"id": 98, "name": "期中作业.md"}, {"id": 99, "name": "Text content.pdf", "source": "auto-generated-pdf"}]
    def download(session, url, directory, filename, **kwargs):
        assert url.endswith("/98/blob")
        assert directory.is_dir(), "download destination must be created by the service"
        path = directory / filename
        path.write_text("本人提交的作业", encoding="utf-8")
        return path
    monkeypatch.setattr("xmu_rollcall.courseware._download_url", download)
    value = service.download_assignment_file("c1", "h1", "98")
    assert value["file"]["origin"] == "own_submission_attachment"
    assert service.read_document(value["file"]["file_id"])["text"] == "本人提交的作业"
    for invalid in ("99", "other-student"):
        with pytest.raises(ValueError, match="附件不属于"):
            service.download_assignment_file("c1", "h1", invalid)


def test_account_and_cookie_changes_stop_active_operation(campus):
    service, account, cookie, *_ = campus
    with pytest.raises(bridge.SessionExpiredError):
        with service.context() as (_, _, _, ensure):
            account["id"] = 2
            ensure()
    with pytest.raises(bridge.SessionExpiredError):
        with service.context(network=True) as (_, _, _, ensure):
            cookie.unlink()
            ensure()


def test_local_work_survives_a_desktop_cookie_rotation(campus):
    service, _, cookie, *_ = campus
    with service.context() as (_, _, _, ensure):
        cookie.write_text("new-synthetic-cookie", encoding="utf-8")
        ensure()


def test_network_reads_tolerate_cookie_rotation_but_writes_stop(campus):
    service, _, cookie, *_ = campus
    with service.context(network=True) as (_, _, _, ensure):
        cookie.write_text("updated-synthetic-cookie", encoding="utf-8")
        ensure()
    with pytest.raises(bridge.SessionExpiredError, match="已更新"):
        with service.context(network=True, protect_write=True) as (_, _, _, ensure):
            cookie.write_text("newer-cookie", encoding="utf-8")
            ensure()


def test_status_only_probes_when_explicitly_requested(campus, monkeypatch):
    service, *_ = campus
    probe = Mock(return_value="valid")
    monkeypatch.setattr(service, "_verify_saved_session", probe)
    unchecked = service.status()
    assert unchecked["session_state"] == "unchecked"
    assert unchecked["session_verified"] is None
    assert "desktop_version" not in unchecked
    probe.assert_not_called()
    assert service.status(verify=True)["session_verified"] is True
    probe.return_value = "expired"
    assert service.status(verify=True)["session_verified"] is False
    probe.return_value = "unknown"
    assert service.status(verify=True)["session_verified"] is None


def test_account_workspaces_do_not_share_files(campus):
    service, account, *_ = campus
    file = service.create_artifact("answer.md", "alpha", "c1", "h1")
    assert service.read_document(file["file_id"])["text"] == "alpha"
    account["id"] = 2
    assert service.files()["total"] == 0
    with pytest.raises(ValueError):
        service.read_document(file["file_id"])


@pytest.mark.parametrize(
    "path",
    [
        "../escape",
        "C:/secret",
        "sub/../../secret",
        ".bridge/files.json",
        "sub/name:stream",
    ],
)
def test_paths_cannot_escape_workspace(tmp_path, path):
    with pytest.raises(ValueError):
        FileStore(tmp_path).inside(path)


def test_workspace_lock_excludes_other_clients(tmp_path):
    with workspace_lock(tmp_path):
        with pytest.raises(ValueError, match="另一个"):
            with workspace_lock(tmp_path):
                pass


def test_artifact_does_not_overwrite(campus):
    service, *_ = campus
    service.create_artifact("answer.md", "original")
    with pytest.raises(FileExistsError):
        service.create_artifact("answer.md", "changed")
    assert service.files()["total"] == 1


def test_text_read_pagination_cache_invalidation_and_search(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("Redis 持久化\n" + "x" * 20000, encoding="utf-8")
    store = FileStore(tmp_path)
    key = store.register(path, course_id="c1")["file_id"]
    result = store.read(key, limit=20)
    assert result["next_offset"] == 20
    assert store.search("Redis", "c1")["hits"][0]["file_id"] == key
    path.write_text("事务隔离级别", encoding="utf-8")
    assert not store.search("Redis", "c1")["hits"]
    assert store.search("隔离", "c1")["hits"]
    assert not store.search("隔离", "c2")["hits"]


@pytest.mark.parametrize(
    "suffix,member,xml,expected",
    [
        (
            ".docx",
            "word/document.xml",
            '<w:document xmlns:w="w"><w:p><w:r><w:t>成绩构成：期末60%</w:t></w:r></w:p></w:document>',
            "期末60%",
        ),
        (
            ".pptx",
            "ppt/slides/slide2.xml",
            '<p:sld xmlns:p="p" xmlns:a="a"><a:t>Redis 主从复制</a:t></p:sld>',
            "主从复制",
        ),
        (
            ".xlsx",
            "xl/worksheets/sheet1.xml",
            '<sheet xmlns="x"><row><c r="A1" t="inlineStr"><is><t>score</t></is></c><c r="B1"><v>90</v></c></row></sheet>',
            "B1=90",
        ),
    ],
)
def test_office_extraction_has_source_locations(
    tmp_path, suffix, member, xml, expected
):
    path = tmp_path / ("course" + suffix)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(member, xml)
    result = extract_document(path)
    assert expected in result["units"][0]["text"]
    assert result["units"][0]["locator"]


def test_pptx_numeric_slide_order(tmp_path):
    path = tmp_path / "deck.pptx"
    with zipfile.ZipFile(path, "w") as z:
        for n in [10, 2, 1]:
            z.writestr(f"ppt/slides/slide{n}.xml", f'<s xmlns:a="a"><a:t>{n}</a:t></s>')
    assert [u["text"] for u in extract_document(path)["units"]] == ["1", "2", "10"]


def test_empty_pdf_requires_visual_read_not_empty_document_claim(tmp_path):
    from pypdf import PdfWriter

    path = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(path)
    assert "不代表文件为空" in extract_document(path)["note"]


def test_xml_entities_are_rejected(tmp_path):
    path = tmp_path / "bad.docx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "word/document.xml", '<!DOCTYPE d [<!ENTITY test "bad">]><d>&test;</d>'
        )
    with pytest.raises(ValueError):
        extract_document(path)


def test_archive_member_ignores_malicious_member_path(campus):
    service, *_ = campus
    with service.context() as (_, store, _, _):
        path = store.inside("input.zip")
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("../../escape.txt", "data, never execute")
        key = store.register(path)["file_id"]
    value = service.archive_member(key, "../../escape.txt")
    assert "archive-members" in value["file"]["local_path"]
    assert (
        service.read_document(value["file"]["file_id"])["text"] == "data, never execute"
    )


def test_grade_sample_scope_invalid_scores_and_weight_coverage(tmp_path):
    path = tmp_path / "grades.csv"
    path.write_text(
        "成绩,学分\n95,2\n75,1\n59,\nNaN,1\n120,1\n优秀,1\n", encoding="utf-8-sig"
    )
    value = grade_statistics(path, "成绩", "学分")
    assert value["count"] == 3 and value["excluded"] == 3
    assert value["bins"]["<60"] == 1
    assert value["credit_weighted_mean"] == pytest.approx(265 / 3)
    assert value["weighted_record_count"] == 2 and value["gpa"] is None
    assert "不推定为班级" in value["scope"]


def make_plan(campus):
    service = campus[0]
    file = service.create_artifact("report.md", "# 真实本地成果", "c1", "h1")
    return file, service.prepare_submission("c1", "h1", file_ids=[file["file_id"]])


def test_prepare_has_no_upload_and_commit_draft_verifies_once(campus):
    service, _, _, _, api = campus
    _, plan = make_plan(campus)
    assert not plan["platform_written"]
    api.upload_file.assert_not_called()
    result = service.commit_submission(plan["plan_id"])
    assert result["state"] == "confirmed" and result["receipt"]["is_draft"] is True
    assert api.submit.call_args.kwargs["is_draft"] is True
    assert api.submit.call_args.args[1] == ""
    again = service.commit_submission(plan["plan_id"])
    assert again["reused_receipt"]
    api.upload_file.assert_called_once()
    api.submit.assert_called_once()


def test_formal_submission_is_disabled_by_default(campus):
    service, _, _, _, api = campus
    _, plan = make_plan(campus)
    with pytest.raises(ValueError, match="未启用"):
        service.commit_submission(plan["plan_id"], "submit")
    api.upload_file.assert_not_called()


def test_explicit_enabled_submission_mode(campus):
    service, _, _, _, api = campus
    service.allow_submit = True
    _, plan = make_plan(campus)
    service.commit_submission(plan["plan_id"], "submit")
    assert api.submit.call_args.kwargs["is_draft"] is False


@pytest.mark.parametrize("change", ["file", "platform", "closed", "group"])
def test_stale_or_forbidden_submission_never_uploads(campus, change):
    service, _, _, record, api = campus
    file, plan = make_plan(campus)
    if change == "file":
        Path(file["local_path"]).write_text("changed", encoding="utf-8")
    elif change == "platform":
        record["submission"]["comment"] = "browser edit"
    elif change == "closed":
        record["detail"]["is_closed"] = True
    else:
        record["group"] = True
    with pytest.raises(ValueError):
        service.commit_submission(plan["plan_id"])
    api.upload_file.assert_not_called()


def test_uncertain_write_is_persisted_and_not_retried(campus):
    service, _, _, _, api = campus
    _, plan = make_plan(campus)
    api.submit.side_effect = TimeoutError("secret storage URL")
    with pytest.raises(bridge.SubmissionUncertain):
        service.commit_submission(plan["plan_id"])
    with pytest.raises(ValueError, match="禁止直接重试"):
        service.commit_submission(plan["plan_id"])
    api.submit.assert_called_once()


def test_existing_attachments_preserved_and_teacher_files_not_submitted(campus):
    service, _, _, record, _ = campus
    record["submission"]["uploads"] = [
        {"id": 1, "name": "existing.pdf"},
        {"id": 2, "source": "auto-generated-pdf"},
    ]
    plan = service.prepare_submission("c1", "h1")
    assert plan["kept_existing_files"] == [{"id": 1, "name": "existing.pdf"}]
    with service.context() as (_, store, _, _):
        p = store.inside("teacher.txt")
        p.write_text("teacher attachment", encoding="utf-8")
        file = store.register(p, origin="assignment_attachment")
    with pytest.raises(ValueError, match="教师附件"):
        service.prepare_submission("c1", "h1", file_ids=[file["file_id"]])


def test_mcp_schema_and_annotations_match_operations(campus):
    from xmu_rollcall.mcp_bridge.server import build_server

    tools = {t.name: t for t in asyncio.run(build_server(campus[0]).list_tools())}
    assert len(tools) == 20
    assert tools["get_monitor_logs"].annotations.readOnlyHint
    assert not tools["get_monitor_logs"].annotations.openWorldHint
    assert tools["get_assignment"].annotations.readOnlyHint
    assert not tools["commit_submission"].annotations.readOnlyHint
    assert tools["commit_submission"].annotations.destructiveHint
    assert (
        tools["list_tasks"].inputSchema["properties"]["include_overdue"]["type"]
        == "boolean"
    )
    assert tools["list_tasks"].inputSchema["properties"]["limit"]["type"] == "integer"


def test_real_stdio_roundtrip_without_live_account(tmp_path):
    """The official client discovers/calls the server through an actual subprocess."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    source = Path(__file__).resolve().parents[1] / "xmu-rollcall-cli"
    env = {
        **os.environ,
        "PYTHONPATH": str(source),
        "PYTHONUTF8": "1",
        "XMU_ROLLCALL_CONFIG_DIR": str(tmp_path / "empty-config"),
    }

    async def run():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "xmu_rollcall.mcp_bridge"], env=env
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                assert len((await session.list_tools()).tools) == 20
                value = await session.call_tool("get_status", {})
                assert (
                    not value.isError
                    and value.structuredContent["account_selected"] is False
                )
                logs = await session.call_tool("get_monitor_logs", {})
                assert not logs.isError and logs.structuredContent["lines"] == []
                error = await session.call_tool(
                    "get_assignment", {"course_id": "c1", "activity_id": "h1"}
                )
                assert error.isError
                assert (await session.read_resource("xmu://guide")).contents
                assert (
                    await session.get_prompt(
                        "study_assistant", {"request": "讲解第二章"}
                    )
                ).messages

    asyncio.run(run())


def test_stdio_study_workflow_with_synthetic_local_files(tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    source = Path(__file__).resolve().parents[1] / "xmu-rollcall-cli"
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.json").write_text(json.dumps({"accounts": [{"id": 1, "username": "synthetic", "password": "", "name": "Offline"}], "current_account_id": 1}), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(source), "PYTHONUTF8": "1", "XMU_ROLLCALL_CONFIG_DIR": str(config)}
    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "xmu_rollcall.mcp_bridge", "--workspace", str(tmp_path / "workspace")], env=env)
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                result = await session.call_tool("create_artifact", {"relative_path": "课程介绍.md", "text": "考核：期末60%，实验40%。Redis使用AOF。", "course_id": "c1"})
                assert not result.isError
                file_id = result.structuredContent["file_id"]
                read = await session.call_tool("read_document", {"file_id": file_id})
                assert "期末60%" in read.structuredContent["text"]
                search = await session.call_tool("search_documents", {"query": "考核", "course_id": "c1"})
                assert search.structuredContent["hits"][0]["file_id"] == file_id
                grades = await session.call_tool("create_artifact", {"relative_path": "成绩.csv", "text": "score,credits\n90,2\n80,1\n"})
                stats = await session.call_tool("analyze_grades", {"file_id": grades.structuredContent["file_id"]})
                assert stats.structuredContent["count"] == 2
                assert stats.structuredContent["credit_weighted_mean"] == pytest.approx(260 / 3)
                error = await session.call_tool("create_artifact", {"relative_path": "../../escape.md", "text": "escape"})
                assert error.isError
    asyncio.run(run())


def test_qiniu_large_file_is_split_and_streams_exact_block_ranges(tmp_path, monkeypatch):
    from xmu_rollcall.learning import LearningApi
    from xmu_rollcall import learning
    block_size = 4 * 1024 * 1024
    path = tmp_path / "large.pdf"
    path.write_bytes(b"a" * block_size + b"b" * 70001)
    requests = []
    class Storage:
        trust_env = True
        def post(self, url, data, headers, **kwargs):
            if "/mkblk/" in url:
                pieces = []
                while chunk := data.read(17003):
                    pieces.append(chunk)
                body = b"".join(pieces)
                requests.append((url, body, headers))
            else:
                requests.append((url, data, headers))
            return SimpleNamespace(raise_for_status=lambda: None, is_redirect=False, json=lambda: {"ctx": str(len(requests))})
        def close(self):
            pass
    monkeypatch.setattr(learning.requests, "Session", Storage)
    api = LearningApi(SimpleNamespace(cookies="SCHOOL_SECRET"))
    api.request = Mock(side_effect=[{"id": 9, "upload_url": "https://storage.example", "storage_type": "QINIU"}, {"uptoken": "storage-token"}])
    progress = []
    api.upload_file(path, lambda sent, size: progress.append(sent))
    assert requests[0][1] == b"a" * block_size
    assert requests[1][1] == b"b" * 70001
    assert requests[2][1] == "1,2"
    assert requests[0][0].endswith(f"/mkblk/{block_size}")
    assert requests[1][0].endswith("/mkblk/70001")
    assert all("SCHOOL_SECRET" not in str(headers) for _, _, headers in requests)
    assert progress == sorted(progress)
