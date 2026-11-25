"""A Windows confirmation owned by the MCP process, independent of the AI client."""
import ctypes


def _label(value, limit=120):
    text = " ".join(str(value).replace("\0", "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def confirm_on_windows(plan):
    course = _label(plan.get("course_name") or plan["course_id"])
    title = _label(plan.get("title") or plan["activity_id"])
    lines = [
        f"课程：{course}",
        f"作业：{title}（{_label(plan['activity_id'])}）",
        f"计划：{plan['plan_id'][:8]}",
        "已有正式提交，将更新平台记录。" if plan.get("previously_submitted")
        else "确认后向教学平台正式交付。",
        "正文：有正文" if plan["content_html"] else "正文：空",
    ]
    for label, files in (
        ("新增附件", plan["files"]),
        ("保留附件", plan["existing"]),
        ("移除附件", plan.get("removed_existing_files", [])),
    ):
        lines.append(f"{label}：{len(files)} 项")
        lines.extend(f"  {_label(item['name'], 72)}" for item in files[:4])
        if len(files) > 4:
            lines.append("  其余文件见 AI 展示的提交预览。")
    lines.append("\n请与 AI 展示的完整预览核对，点「确定」正式提交。")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    message_box = user32.MessageBoxW
    message_box.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint)
    message_box.restype = ctypes.c_int
    ok_cancel = 0x1
    warning_icon = 0x30
    default_cancel = 0x100
    foreground = 0x10000
    topmost = 0x40000
    return message_box(
        None, "\n".join(lines), "厦大助手 · 确认正式提交",
        ok_cancel | warning_icon | default_cancel | foreground | topmost,
    ) == 1
