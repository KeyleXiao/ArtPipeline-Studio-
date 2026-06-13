#!/usr/bin/env python3
"""阿里云百炼 · 万相。"""

from __future__ import annotations

import base64
from typing import Any

from cloud.base import CloudGenerateRequest, CloudGenerateResult, CloudProvider, CloudProviderError
from cloud.http_util import download_bytes, http_json, image_to_data_url, poll_until
from cloud.registry import CLOUD_GEN_MODE_EDIT, CLOUD_GEN_MODE_I2I, CLOUD_GEN_MODE_TEXT

_BASE = "https://dashscope.aliyuncs.com/api/v1"


def _extract_image_from_output(out: dict[str, Any]) -> tuple[str | None, bytes | None]:
    """从任务 output 提取图片。wan2.6 用 choices；wan2.5 及更早用 results。"""
    for choice in out.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        msg = choice.get("message") or {}
        for item in msg.get("content") or []:
            if not isinstance(item, dict):
                continue
            img = item.get("image")
            if not img:
                continue
            img_s = str(img)
            if img_s.startswith(("http://", "https://")):
                return img_s, None
            if img_s.startswith("data:"):
                raw = img_s.split(",", 1)[-1]
                return None, base64.b64decode(raw)
            try:
                return None, base64.b64decode(img_s)
            except Exception:
                continue

    for row in out.get("results") or []:
        if not isinstance(row, dict):
            continue
        if row.get("b64_image"):
            return None, base64.b64decode(str(row["b64_image"]))
        url = row.get("url")
        if url:
            return str(url), None
    return None, None


class DashScopeProvider(CloudProvider):
    provider_id = "dashscope"

    def generate(
        self,
        req: CloudGenerateRequest,
        *,
        progress_cb=None,
        cancel_event=None,
    ) -> CloudGenerateResult:
        key = req.api_keys.get("dashscope", "")
        if not key:
            return CloudGenerateResult(False, "未配置 DashScope API Key")

        if req.mode == CLOUD_GEN_MODE_TEXT:
            return self._text_to_image(req, key, progress_cb, cancel_event)
        if req.mode == CLOUD_GEN_MODE_I2I:
            return self._image_to_image(req, key, progress_cb, cancel_event)
        if req.mode == CLOUD_GEN_MODE_EDIT:
            return self._image_edit(req, key, progress_cb, cancel_event)
        return CloudGenerateResult(False, f"不支持的模式: {req.mode}")

    def _headers(self, key: str, *, async_mode: bool = True) -> dict[str, str]:
        h = {"Authorization": f"Bearer {key}"}
        if async_mode:
            h["X-DashScope-Async"] = "enable"
        return h

    def _size(self, w: int, h: int) -> str:
        return f"{w}*{h}"

    def _submit_async(self, path: str, body: dict, key: str) -> str:
        data = http_json(f"{_BASE}/{path}", method="POST", headers=self._headers(key), body=body)
        out = data.get("output") or {}
        task_id = out.get("task_id") or data.get("task_id")
        if not task_id:
            raise CloudProviderError(f"万相未返回 task_id: {data}")
        return str(task_id)

    def _poll_task(self, task_id: str, key: str, progress_cb, cancel_event) -> bytes:
        def check():
            data = http_json(
                f"{_BASE}/tasks/{task_id}",
                headers={"Authorization": f"Bearer {key}"},
            )
            out = data.get("output") or {}
            st = str(out.get("task_status") or "")
            if progress_cb:
                pct = 15
                if st == "RUNNING":
                    pct = 55
                elif st == "PENDING":
                    pct = 15
                elif st == "SUCCEEDED":
                    pct = 95
                progress_cb(
                    {
                        "kind": "cloud_task",
                        "status": st or "PENDING",
                        "pct": pct,
                        "message": f"万相 · {st or '排队中'}",
                    }
                )
            if st in ("FAILED", "CANCELED", "UNKNOWN"):
                msg = out.get("message") or out.get("code") or st
                raise CloudProviderError(f"万相任务失败: {msg}")
            if st != "SUCCEEDED":
                return None
            url, raw = _extract_image_from_output(out)
            if raw:
                return raw
            if url:
                if progress_cb:
                    progress_cb({"kind": "cloud_task", "status": "DOWNLOADING", "pct": 95, "message": "万相 · 下载中"})
                return download_bytes(url)
            keys = ", ".join(sorted(out.keys()))
            raise CloudProviderError(f"万相任务无输出（响应字段: {keys or 'empty'}）")

        return poll_until(check, cancel_event=cancel_event)

    def _text_to_image(self, req, key, progress_cb, cancel_event) -> CloudGenerateResult:
        model = str(req.model.get("api_model") or "wan2.6-t2i")
        body = {
            "model": model,
            "input": {
                "messages": [
                    {"role": "user", "content": [{"text": req.prompt}]},
                ]
            },
            "parameters": {
                "size": self._size(req.width, req.height),
                "n": 1,
                "negative_prompt": req.negative or "",
                "watermark": False,
            },
        }
        if progress_cb:
            progress_cb({"kind": "cloud_task", "status": "SUBMITTING", "pct": 10, "message": "万相 · 文生图 · 提交中"})
        task_id = self._submit_async("services/aigc/image-generation/generation", body, key)
        png = self._poll_task(task_id, key, progress_cb, cancel_event)
        return CloudGenerateResult(True, "ok", png_bytes=png)

    def _image_to_image(self, req, key, progress_cb, cancel_event) -> CloudGenerateResult:
        if not req.ref_image_path or not req.ref_image_path.is_file():
            return CloudGenerateResult(False, "图生图：参考图不存在")
        model = str(req.model.get("api_model") or "wan2.6-t2i")
        ref_url = image_to_data_url(req.ref_image_path)
        body = {
            "model": model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"image": ref_url},
                            {"text": req.prompt},
                        ],
                    }
                ]
            },
            "parameters": {
                "size": self._size(req.width, req.height),
                "n": 1,
                "negative_prompt": req.negative or "",
                "watermark": False,
            },
        }
        if progress_cb:
            progress_cb({"kind": "cloud_task", "status": "SUBMITTING", "pct": 10, "message": "万相 · 图生图 · 提交中"})
        task_id = self._submit_async("services/aigc/multimodal-generation/generation", body, key)
        png = self._poll_task(task_id, key, progress_cb, cancel_event)
        return CloudGenerateResult(True, "ok", png_bytes=png)

    def _image_edit(self, req, key, progress_cb, cancel_event) -> CloudGenerateResult:
        base = req.base_image_path or req.ref_image_path
        if not base or not base.is_file():
            return CloudGenerateResult(False, "图像编辑：底图不存在")
        edit_model = str((req.model.get("modes") or {}).get("image_edit", {}).get("api_model") or "wanx2.1-imageedit")
        body = {
            "model": edit_model,
            "input": {
                "function": "description_edit",
                "prompt": req.prompt,
                "base_image_url": image_to_data_url(base),
            },
            "parameters": {"n": 1},
        }
        if progress_cb:
            progress_cb({"kind": "cloud_task", "status": "SUBMITTING", "pct": 10, "message": "万相 · 图像编辑 · 提交中"})
        task_id = self._submit_async("services/aigc/image2image/image-synthesis", body, key)
        png = self._poll_task(task_id, key, progress_cb, cancel_event)
        return CloudGenerateResult(True, "ok", png_bytes=png)
