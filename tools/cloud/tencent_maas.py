#!/usr/bin/env python3
"""腾讯混元 · TokenHub OpenAI 兼容 API（Bearer sk-...）。"""

from __future__ import annotations

from typing import Any

from cloud.base import CloudProviderError
from cloud.http_util import http_json

TOKENHUB_BASE = "https://tokenhub.tencentmaas.com/v1"
MODEL_IMAGE_V3 = "hy-image-v3.0"
MODEL_VERIFY = "hy3-preview"


def resolve_tencent_api_key(keys: dict[str, Any] | None) -> str:
    """读取 TokenHub API Key；兼容旧版 tencent_secret_* 字段。"""
    raw = keys if isinstance(keys, dict) else {}
    direct = str(raw.get("tencent") or "").strip()
    if direct:
        return direct
    for name in ("tencent_secret_key", "tencent_secret_id"):
        value = str(raw.get(name) or "").strip()
        if value.startswith("sk-"):
            return value
    return str(raw.get("tencent_secret_key") or "").strip()


def maas_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def maas_post(api_key: str, path: str, body: dict[str, Any], *, timeout: float = 120.0) -> dict[str, Any]:
    if not api_key:
        raise CloudProviderError("未配置 TokenHub API Key")
    url = f"{TOKENHUB_BASE}/{path.lstrip('/')}"
    data = http_json(url, method="POST", headers=maas_headers(api_key), body=body, timeout=timeout)
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            msg = err.get("message") or err.get("code") or err
            raise CloudProviderError(f"混元 API 错误: {msg}")
        if isinstance(err, str) and err:
            raise CloudProviderError(f"混元 API 错误: {err}")
    if not isinstance(data, dict):
        raise CloudProviderError(f"混元 API 响应异常: {data!r}")
    return data
