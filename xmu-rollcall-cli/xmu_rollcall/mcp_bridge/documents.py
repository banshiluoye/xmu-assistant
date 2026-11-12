"""Bounded, passive document extraction; no macros or archive members execute."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
import zipfile

MAX_FILE = 64 * 1024 * 1024
MAX_TEXT = 2_000_000
MAX_MEMBER = 16 * 1024 * 1024


def _xml(archive, name):
    info = archive.getinfo(name)
    if info.file_size > MAX_MEMBER:
        raise ValueError("文档内部成员过大，请用专用工具读取")
    data = archive.read(info)
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("不支持包含实体声明的 XML")
    return ET.fromstring(data)


def _text(element):
    return " ".join(
        node.text or ""
        for node in element.iter()
        if node.tag.rsplit("}", 1)[-1] in {"t", "v"}
    )


def _decode(data):
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            value = data.decode(encoding)
            if "\x00" not in value:
                return value
        except UnicodeError:
            pass
    raise ValueError("文本编码无法识别，请转为 UTF-8")


def extract_document(path: Path) -> dict:
    if path.stat().st_size > MAX_FILE:
        raise ValueError("自动解析上限为 64 MiB，原文件仍可用专用工具读取")
    suffix = path.suffix.lower()
    units = []
    note = ""
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("PDF 已加密，需要先解密")
        size = 0
        for index, page in enumerate(reader.pages[:500], 1):
            value = (page.extract_text() or "")[:100_000]
            units.append({"locator": f"第 {index} 页", "text": value})
            size += len(value)
            if size >= MAX_TEXT:
                note = "解析达到文本上限，后续页未索引"
                break
        if len(reader.pages) > 500:
            note += "；仅解析前 500 页"
        if not any(row["text"].strip() for row in units):
            note = "未提取到文字，可能是扫描件；需要视觉识别/OCR，不代表文件为空"
    elif suffix in {".docx", ".pptx", ".xlsx"}:
        with zipfile.ZipFile(path) as archive:
            if suffix == ".docx":
                root = _xml(archive, "word/document.xml")
                paragraphs = [
                    _text(node) for node in root.iter() if node.tag.endswith("}p")
                ]
                units = [
                    {
                        "locator": "正文段落（无固定页码）",
                        "text": "\n".join(paragraphs)[:MAX_TEXT],
                    }
                ]
            elif suffix == ".pptx":
                names = [
                    n
                    for n in archive.namelist()
                    if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)
                ]
                for name in sorted(
                    names, key=lambda n: int(re.search(r"slide(\d+)", n)[1])
                )[:500]:
                    number = re.search(r"slide(\d+)", name)[1]
                    units.append(
                        {
                            "locator": f"第 {number} 张幻灯片",
                            "text": _text(_xml(archive, name))[:100_000],
                        }
                    )
            else:
                shared = []
                if "xl/sharedStrings.xml" in archive.namelist():
                    shared = [
                        _text(node)
                        for node in _xml(archive, "xl/sharedStrings.xml")
                        if node.tag.endswith("}si")
                    ]
                for name in sorted(
                    n
                    for n in archive.namelist()
                    if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)
                )[:100]:
                    lines = []
                    for row in _xml(archive, name).iter():
                        if not row.tag.endswith("}row"):
                            continue
                        cells = []
                        for cell in row:
                            value = _text(cell)
                            if (
                                cell.get("t") == "s"
                                and value.isdigit()
                                and int(value) < len(shared)
                            ):
                                value = shared[int(value)]
                            cells.append(f"{cell.get('r', '?')}={value}")
                        lines.append(" | ".join(cells))
                    units.append({"locator": name, "text": "\n".join(lines)[:MAX_TEXT]})
    elif suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            units = [
                {
                    "locator": "压缩包目录",
                    "text": "\n".join(
                        f"{i.filename} ({i.file_size} bytes)"
                        for i in archive.infolist()[:2000]
                    ),
                }
            ]
        note = "仅列出成员；可用 read_archive_member 按名称读取，不自动执行或解压代码"
    elif suffix in {
        ".txt",
        ".md",
        ".csv",
        ".json",
        ".html",
        ".htm",
        ".py",
        ".java",
        ".c",
        ".cpp",
        ".h",
        ".sql",
        ".xml",
        ".tex",
        ".ipynb",
        ".js",
        ".ts",
        ".yml",
        ".yaml",
        ".r",
        ".log",
    }:
        value = _decode(path.read_bytes())
        if suffix in {".html", ".htm"}:
            from html import unescape

            value = unescape(
                re.sub(
                    r"<[^>]*>",
                    " ",
                    re.sub(r"(?is)<(script|style)\b.*?</\1>", "", value),
                )
            )
        units = [{"locator": "文本行", "text": value[:MAX_TEXT]}]
    else:
        note = "此格式未内置文本解析；图片可用 read_image，旧版 .doc/.ppt 或音视频请用客户端专用工具处理"
    total = 0
    bounded = []
    for row in units:
        if total >= MAX_TEXT:
            note += "；其余文本未索引"
            break
        row["text"] = row["text"][: MAX_TEXT - total]
        total += len(row["text"])
        bounded.append(row)
    return {"units": bounded, "note": note, "characters": total}


def read_large_pdf(path, unit=1, offset=0, limit=12000):
    """Read just the requested textbook page; no full-file hash or text index."""
    from pypdf import PdfReader
    with path.open("rb") as stream:
        if stream.read(5) != b"%PDF-" or path.stat().st_size > 1024 * 1024 * 1024:
            raise ValueError("超过64 MiB的文件仅支持有效PDF按页读取（最大1 GiB）")
        stream.seek(0)
        reader = PdfReader(stream)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("PDF已加密，需要先解密")
        count = len(reader.pages)
        if not 1 <= unit <= count:
            raise ValueError(f"页码应在1到{count}之间")
        text = (reader.pages[unit - 1].extract_text() or "")[:100_000]
    offset, limit = max(0, offset), min(24000, max(1, limit))
    return {"unit": unit, "units": count, "locator": f"第 {unit} 页", "offset": offset,
            "text": text[offset:offset + limit], "next_offset": offset + limit if offset + limit < len(text) else None,
            "note": "大PDF按当前页读取，未全文索引" + ("；本页可能需视觉/OCR识别" if not text.strip() else "")}


def grade_statistics(path: Path, score_column="score", credit_column="credits"):
    """Statistics of the supplied sample, never assumed to be a class roster."""
    import math

    text = _decode(path.read_bytes())
    rows = (
        json.loads(text)
        if path.suffix.lower() == ".json"
        else list(csv.DictReader(io.StringIO(text)))
    )
    if not isinstance(rows, list):
        raise ValueError("成绩 JSON 需要为记录数组，或使用有表头的 CSV")
    bins = {"<60": 0, "60-69": 0, "70-79": 0, "80-89": 0, "90-100": 0}
    scores, weighted, weights, weighted_count = [], 0.0, 0.0, 0
    excluded = 0
    for row in rows:
        try:
            score = float(row[score_column])
            if not math.isfinite(score) or not 0 <= score <= 100:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            excluded += 1
            continue
        scores.append(score)
        bins[
            "<60"
            if score < 60
            else "60-69"
            if score < 70
            else "70-79"
            if score < 80
            else "80-89"
            if score < 90
            else "90-100"
        ] += 1
        try:
            weight = float(row.get(credit_column, 0))
            if math.isfinite(weight) and weight > 0:
                weighted += score * weight
                weights += weight
                weighted_count += 1
        except (TypeError, ValueError):
            pass
    return {
        "scope": "仅所提供文件内的有效百分制记录；不推定为班级分布",
        "count": len(scores),
        "excluded": excluded,
        "bins": bins,
        "mean": sum(scores) / len(scores) if scores else None,
        "credit_weighted_mean": weighted / weights if weights else None,
        "weighted_record_count": weighted_count,
        "total_credits_used": weights,
        "gpa": None,
        "note": "未指定学校绩点规则，不换算 GPA；课程考核占比应检索课程介绍/教学大纲",
    }
