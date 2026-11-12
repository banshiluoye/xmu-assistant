import math
import re
import uuid

import requests

from .number_code import complete_number_code, find_number_code  # re-export legacy helper
from .request_probe import classify_status
from .utils import (
    API_TIMEOUT,
    SessionExpiredError,
    base_url,
    response_session_expired,
    retry_request,
)


def _raise_if_session_expired(response):
    """会话过期判定：302 落身份域/登录页（最终 200 HTML）也必须识别为过期。

    requests 对 302 的 PUT 重放会降级为 GET，最终停在 200 登录页——仅凭
    status_code==200 会假成功（界面记「已签到」实际未签成）。send_* 的
    SessionExpiredError 透传契约（见各 docstring 与 send_radar 网络层注释）
    由上游 answer_failure_detail 分流，此处让契约在过期页场景真正生效。
    """
    # 401 是确定失效；403 的资源权限语义仍由调用方按原有 bool 契约处理。
    if response.status_code == 401:
        raise classify_status(response.status_code, "签到应答")
    if response_session_expired(response):
        raise SessionExpiredError("登录已过期，请重新登录")


# 数字签到沿用平台应答接口。
def send_code(in_session, rollcall_id, number_code="", *, course_id="", rollcall_time="", course_title=""):
    """提交数字签到码。返回 True/False；网络层/SessionExpired 异常按契约处理。

    仅用于兼容层：PySide6 桌面端直接组装提交，这里保留统一 bool 契约。
    """
    code_url = f"{base_url}/api/rollcall/{rollcall_id}/student_rollcalls"
    answer_url = f"{base_url}/api/rollcall/{rollcall_id}/answer_number_rollcall"
    request_headers = in_session.headers
    number_code = str(number_code or "").strip()
    if not number_code:
        code_data = None
        try:
            code_response = retry_request(
                lambda: in_session.get(code_url, headers=request_headers, timeout=API_TIMEOUT),
                max_attempts=3,
                delay=2,
                label="get_number_code",
            )
            _raise_if_session_expired(code_response)
            if code_response.status_code == 200:
                code_data = code_response.json()
        except requests.RequestException:
            pass
        except ValueError:
            pass
        number_code = complete_number_code(
            in_session, rollcall_id, code_data, course_id=course_id,
            rollcall_time=rollcall_time, course_title=course_title,
        )
    if not number_code:
        return False

    payload = {"deviceId": str(uuid.uuid4()), "numberCode": number_code}
    try:
        response = retry_request(
            lambda: in_session.put(answer_url, json=payload, headers=request_headers, timeout=API_TIMEOUT),
            # 写请求不盲重试：超时可能只是回执丢失，重复 PUT 会造成重复签到。
            max_attempts=1,
            delay=2,
            label="answer_number",
        )
        _raise_if_session_expired(response)
        return response.status_code == 200
    except requests.RequestException:
        return False


def radar_response_detail(code, data):
    """保留可诊断的拒绝原因，不记录请求凭据、坐标或整个响应体。"""
    reason = ""
    if isinstance(data, dict):
        for key in ("message", "msg", "error", "detail", "code"):
            value = data.get(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                reason = str(value).strip()
                if reason:
                    break
    reason = re.sub(r"(?i)bearer\s+\S+", "Bearer [redacted]", reason)
    reason = re.sub(
        r"(?i)(password|token|cookie|authorization)\s*[:=]\s*[^\s;,]+",
        r"\1=[redacted]", reason,
    )
    reason = " ".join(reason.split())[:200]
    return f"HTTP {code}" + (f"，{reason}" if reason else "")


def send_radar(in_session, rollcall_id, *, on_failure=None):
    """A radar event without a selected location is handled in the official client."""
    if on_failure is not None:
        on_failure("未配置课程地点，请在畅课完成雷达签到")
    return False


def send_radar_at(in_session, rollcall_id, latitude, longitude, *, on_failure=None):
    """按已配置的课程坐标提交一次，不发送任何探测坐标。

    与 Android 端 answerRadarAt 同语义：未配置坐标的课程不会被提交，避免先写入
    记录再回头修正。坐标必须是有限数值，调用方负责取课程首选地点。
    """
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        latitude = longitude = float("nan")
    if (
        not (math.isfinite(latitude) and math.isfinite(longitude))
        or not -90.0 <= latitude <= 90.0
        or not -180.0 <= longitude <= 180.0
    ):
        if on_failure is not None:
            on_failure("雷达签到失败：课程坐标无效")
        return False

    url = f"{base_url}/api/rollcall/{rollcall_id}/answer"
    body = {
        "accuracy": 35, "altitude": 0, "altitudeAccuracy": None,
        "deviceId": str(uuid.uuid4()), "heading": None,
        "latitude": latitude, "longitude": longitude, "speed": None,
    }

    def fail(detail):
        if on_failure is not None:
            on_failure(f"雷达签到失败：{detail}")
        return False

    try:
        response = retry_request(
            lambda: in_session.put(
                url, json=body, headers=in_session.headers,
                timeout=API_TIMEOUT, allow_redirects=False,
            ),
            # 写请求不盲重试：超时可能只是回执丢失，重复 PUT 会造成重复签到。
            max_attempts=1, delay=2, label="radar",
        )
        _raise_if_session_expired(response)
    except requests.RequestException:
        return fail("网络回执未收到，提交结果未知；请核实本人记录")

    try:
        data = response.json()
    except ValueError:
        data = None
    detail = radar_response_detail(response.status_code, data)
    text = (getattr(response, "text", "") or "").strip()
    content_type = str(getattr(response, "headers", {}).get("Content-Type", "")).lower()
    html = data is None and (text.startswith("<") or (text and "text/html" in content_type))
    if response.status_code == 200 and not html:
        return True
    return fail(detail)
