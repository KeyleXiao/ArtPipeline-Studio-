#!/usr/bin/env python3
"""云生图 API 凭证轻量连通性验证（不发起真实生图）。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from cloud.base import CloudProviderError
from cloud.http_util import http_json
from cloud.tencent_sign import tencent_request


def _http_status(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict | None = None,
    timeout: float = 20.0,
) -> tuple[int, str]:
    hdrs = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, raw[:400]
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        return exc.code, err_body[:400]
    except urllib.error.URLError as exc:
        raise CloudProviderError(f"网络错误: {exc}") from exc


def verify_stability(key: str) -> tuple[bool, str]:
    if not key:
        return False, "请填写 API Key"
    try:
        data = http_json(
            "https://api.stability.ai/v1/user/account",
            headers={"Authorization": f"Bearer {key}"},
            timeout=20.0,
        )
    except CloudProviderError as exc:
        msg = str(exc)
        if "401" in msg or "403" in msg:
            return False, "API Key 无效或已过期"
        return False, msg.replace("HTTP ", "")[:160]
    label = data.get("email") or data.get("id") or "OK"
    return True, f"已连接 · {label}"


def verify_dashscope(key: str) -> tuple[bool, str]:
    if not key:
        return False, "请填写 API Key"
    code, body = _http_status(
        "https://dashscope.aliyuncs.com/compatible-mode/v1/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    if code in (401, 403):
        return False, "API Key 无效或无权访问"
    if code >= 400:
        return False, f"验证失败 (HTTP {code})"
    return True, "已连接 · DashScope 可用"


def verify_tencent(secret_id: str, secret_key: str) -> tuple[bool, str]:
    if not secret_id or not secret_key:
        return False, "请填写 SecretId 与 SecretKey"
    try:
        tencent_request(
            secret_id=secret_id,
            secret_key=secret_key,
            action="QueryTextToImageJob",
            payload={"JobId": "artpipeline-verify-probe"},
        )
        return True, "已连接 · 混元 API 可用"
    except CloudProviderError as exc:
        msg = str(exc)
        upper = msg.upper()
        if "AUTHFAILURE" in upper or "UNAUTHORIZED" in upper or "SIGNATURE" in upper:
            return False, "SecretId / SecretKey 无效"
        if any(k in upper for k in ("INVALID", "NOTFOUND", "RESOURCE", "JOB")):
            return True, "已连接 · 混元 API 可用"
        return False, msg[:160]


def verify_volcengine(key: str, endpoint: str) -> tuple[bool, str]:
    if not key:
        return False, "请填写 API Key"
    if not endpoint.strip():
        return False, "请填写 Seedream 模型 ID"
    code, body = _http_status(
        "https://ark.cn-beijing.volces.com/api/v3/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    if code in (401, 403):
        return False, "API Key 无效或无权访问"
    if code >= 400:
        return False, f"验证失败 (HTTP {code})"
    return True, f"已连接 · 模型 {endpoint.strip()}"


def verify_cloud_provider(provider_id: str, keys: dict[str, str]) -> dict[str, Any]:
    pid = str(provider_id or "").strip().lower()
    k = keys or {}
    try:
        if pid == "stability":
            ok, message = verify_stability(str(k.get("stability") or "").strip())
        elif pid == "dashscope":
            ok, message = verify_dashscope(str(k.get("dashscope") or "").strip())
        elif pid == "tencent":
            ok, message = verify_tencent(
                str(k.get("tencent_secret_id") or "").strip(),
                str(k.get("tencent_secret_key") or "").strip(),
            )
        elif pid == "volcengine":
            ok, message = verify_volcengine(
                str(k.get("volcengine") or "").strip(),
                str(k.get("volcengine_endpoint") or "").strip(),
            )
        else:
            return {"ok": False, "message": f"未知 provider: {provider_id}"}
    except CloudProviderError as exc:
        return {"ok": False, "message": str(exc)[:160]}
    return {"ok": ok, "message": message, "provider": pid}
