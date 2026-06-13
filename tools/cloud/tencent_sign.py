#!/usr/bin/env python3
"""腾讯云 API 3.0 TC3 签名（aiart 混元生图）。"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

from cloud.base import CloudProviderError
from cloud.http_util import http_json


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def tencent_request(
    *,
    secret_id: str,
    secret_key: str,
    action: str,
    payload: dict[str, Any],
    version: str = "2022-12-29",
    region: str = "ap-guangzhou",
    service: str = "aiart",
    host: str = "aiart.tencentcloudapi.com",
) -> dict[str, Any]:
    if not secret_id or not secret_key:
        raise CloudProviderError("未配置腾讯混元 SecretId / SecretKey")

    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    now = datetime.now(timezone.utc)
    date = now.strftime("%Y-%m-%d")
    timestamp = str(int(now.timestamp()))

    canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{host}\n"
    signed_headers = "content-type;host"
    canonical_request = "\n".join(
        [
            "POST",
            "/",
            "",
            canonical_headers,
            signed_headers,
            _sha256_hex(body),
        ]
    )
    credential_scope = f"{date}/{service}/tc3_request"
    string_to_sign = "\n".join(
        ["TC3-HMAC-SHA256", timestamp, credential_scope, _sha256_hex(canonical_request)]
    )
    secret_date = _hmac_sha256(f"TC3{secret_key}".encode(), date)
    secret_service = _hmac_sha256(secret_date, service)
    secret_signing = _hmac_sha256(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    auth = (
        f"TC3-HMAC-SHA256 Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    headers = {
        "Authorization": auth,
        "Content-Type": "application/json; charset=utf-8",
        "Host": host,
        "X-TC-Action": action,
        "X-TC-Version": version,
        "X-TC-Timestamp": timestamp,
        "X-TC-Region": region,
    }
    # 必须与签名时的 body 字节完全一致（不能用默认 json.dumps 的空格格式）
    data = http_json(f"https://{host}", method="POST", headers=headers, body_text=body)
    resp = data.get("Response") or data
    if resp.get("Error"):
        err = resp["Error"]
        raise CloudProviderError(f"混元 API 错误: {err.get('Code')}: {err.get('Message')}")
    return resp
