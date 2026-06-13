#!/usr/bin/env python3
"""云 API 通用 HTTP 工具。"""

from __future__ import annotations

import base64
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, TypeVar

from cloud.base import CloudProviderError, ProgressCallback

T = TypeVar("T")


def download_bytes(url: str, *, timeout: float = 120.0) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.URLError as exc:
        raise CloudProviderError(f"下载失败 {url}: {exc}") from exc


def image_to_data_url(path: Path) -> str:
    data = path.read_bytes()
    suffix = path.suffix.lower()
    mime = "image/png"
    if suffix in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    elif suffix == ".webp":
        mime = "image/webp"
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict | None = None,
    body_text: str | None = None,
    timeout: float = 120.0,
) -> Any:
    hdrs = dict(headers or {})
    data = None
    if body_text is not None:
        data = body_text.encode("utf-8")
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise CloudProviderError(f"HTTP {exc.code}: {err_body}") from exc
    except urllib.error.URLError as exc:
        raise CloudProviderError(f"请求失败: {exc}") from exc


def http_multipart(
    url: str,
    *,
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 180.0,
) -> bytes:
    import uuid

    boundary = f"----ArtPipe{uuid.uuid4().hex}"
    lines: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        lines.append(f"--{boundary}\r\n".encode())
        lines.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        lines.append(value.encode("utf-8"))
        lines.append(b"\r\n")

    for k, v in fields.items():
        add_field(k, v)
    for name, (filename, content, mime) in (files or {}).items():
        lines.append(f"--{boundary}\r\n".encode())
        lines.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        )
        lines.append(f"Content-Type: {mime}\r\n\r\n".encode())
        lines.append(content)
        lines.append(b"\r\n")
    lines.append(f"--{boundary}--\r\n".encode())
    body = b"".join(lines)
    hdrs = dict(headers or {})
    hdrs["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise CloudProviderError(f"HTTP {exc.code}: {err_body}") from exc
    except urllib.error.URLError as exc:
        raise CloudProviderError(f"请求失败: {exc}") from exc


def poll_until(
    fn,
    *,
    timeout_s: float = 600.0,
    interval_s: float = 2.0,
    progress_cb: ProgressCallback | None = None,
    cancel_event: Any | None = None,
    on_tick: Any | None = None,
) -> Any:
    deadline = time.time() + timeout_s
    start = time.time()
    while time.time() < deadline:
        if cancel_event and cancel_event.is_set():
            raise CloudProviderError("用户取消生成")
        result = fn()
        if on_tick:
            on_tick(result, elapsed=time.time() - start)
        if result is not None:
            return result
        time.sleep(interval_s)
    raise CloudProviderError("云任务超时")


def run_with_progress_heartbeat(
    fn: Callable[[], T],
    *,
    progress_cb: ProgressCallback | None = None,
    cancel_event: Any | None = None,
    message: str = "生成中",
    start_pct: int = 12,
    max_pct: int = 92,
    interval_s: float = 2.0,
) -> T:
    """在阻塞请求期间定期上报进度（适用于无轮询接口的同步云 API）。"""
    result_box: dict[str, T] = {}
    error_box: dict[str, BaseException] = {}
    done = threading.Event()

    def worker() -> None:
        try:
            result_box["value"] = fn()
        except BaseException as exc:
            error_box["exc"] = exc
        finally:
            done.set()

    threading.Thread(target=worker, daemon=True, name="cloud-progress").start()
    pct = start_pct
    tick = 0
    while not done.wait(timeout=interval_s):
        if cancel_event and cancel_event.is_set():
            raise CloudProviderError("用户取消生成")
        tick += 1
        pct = min(max_pct, start_pct + tick * 4)
        if progress_cb:
            progress_cb(
                {
                    "kind": "cloud_task",
                    "status": "RUNNING",
                    "pct": pct,
                    "message": message,
                }
            )
    if "exc" in error_box:
        raise error_box["exc"]
    return result_box["value"]


def cloud_keys_from_defaults(defaults: dict[str, Any]) -> dict[str, str]:
    raw = defaults.get("cloud_api_keys") or {}
    if not isinstance(raw, dict):
        raw = {}
    from cloud.tencent_maas import resolve_tencent_api_key

    out = {
        "stability": str(raw.get("stability") or defaults.get("stability_api_key") or "").strip(),
        "dashscope": str(
            raw.get("dashscope") or defaults.get("vision_api_key") or defaults.get("dashscope_api_key") or ""
        ).strip(),
        "tencent": resolve_tencent_api_key(raw),
        "volcengine": str(raw.get("volcengine") or "").strip(),
        "volcengine_endpoint": str(raw.get("volcengine_endpoint") or "").strip(),
    }
    return out
