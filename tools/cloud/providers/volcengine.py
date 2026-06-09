#!/usr/bin/env python3
"""火山方舟 · Seedream / 即梦。"""

from __future__ import annotations

import base64
import json
import math

from cloud.base import CloudGenerateRequest, CloudGenerateResult, CloudProvider, CloudProviderError
from cloud.http_util import http_json, image_to_data_url, run_with_progress_heartbeat
from cloud.registry import CLOUD_GEN_MODE_EDIT, CLOUD_GEN_MODE_I2I, CLOUD_GEN_MODE_TEXT

_DEFAULT_BASE = "https://ark.cn-beijing.volces.com/api/v3"
_MIN_PIXELS = 3_686_400  # Seedream 4 下限（约 1920×1920）


def _api_size(width: int, height: int) -> tuple[int, int]:
    w = max(1, int(width))
    h = max(1, int(height))
    if w * h >= _MIN_PIXELS:
        return w, h
    scale = math.sqrt(_MIN_PIXELS / (w * h)) * 1.02
    return max(w, int(math.ceil(w * scale))), max(h, int(math.ceil(h * scale)))


class VolcengineProvider(CloudProvider):
    provider_id = "volcengine"

    def generate(self, req: CloudGenerateRequest, *, progress_cb=None, cancel_event=None) -> CloudGenerateResult:
        key = req.api_keys.get("volcengine", "")
        if not key:
            return CloudGenerateResult(False, "未配置火山方舟 API Key")
        model = req.api_keys.get("volcengine_endpoint") or str(req.model.get("api_model") or "doubao-seedream-4-0")
        if not model:
            return CloudGenerateResult(False, "未配置 Seedream 模型 ID（volcengine_endpoint）")

        api_w, api_h = _api_size(req.width, req.height)
        body: dict = {
            "model": model,
            "prompt": req.prompt,
            "size": f"{api_w}x{api_h}",
            "response_format": "b64_json",
            "watermark": False,
        }
        if req.negative:
            body["negative_prompt"] = req.negative

        if req.mode in (CLOUD_GEN_MODE_I2I, CLOUD_GEN_MODE_EDIT):
            base = req.ref_image_path if req.mode == CLOUD_GEN_MODE_I2I else (req.base_image_path or req.ref_image_path)
            if not base or not base.is_file():
                return CloudGenerateResult(False, "图生图/图像编辑：参考图或底图不存在")
            body["image"] = image_to_data_url(base)
            if req.mode == CLOUD_GEN_MODE_EDIT:
                body["prompt"] = f"Edit the image: {req.prompt}"

        label = {
            CLOUD_GEN_MODE_TEXT: "文生图",
            CLOUD_GEN_MODE_I2I: "图生图",
            CLOUD_GEN_MODE_EDIT: "图像编辑",
        }.get(req.mode, req.mode)
        if progress_cb:
            progress_cb(
                {
                    "kind": "cloud_task",
                    "status": "SUBMITTING",
                    "pct": 10,
                    "message": f"即梦 · {label} · 提交中",
                }
            )

        def _request() -> dict:
            return http_json(
                f"{_DEFAULT_BASE}/images/generations",
                method="POST",
                headers={"Authorization": f"Bearer {key}"},
                body=body,
                timeout=300.0,
            )

        data = run_with_progress_heartbeat(
            _request,
            progress_cb=progress_cb,
            cancel_event=cancel_event,
            message=f"即梦 · {label} · 生成中",
            start_pct=18,
            max_pct=90,
        )
        items = data.get("data") or []
        if not items:
            err = data.get("error") or data
            raise CloudProviderError(f"即梦无输出: {json.dumps(err, ensure_ascii=False)[:200]}")
        b64 = items[0].get("b64_json") or items[0].get("b64_image")
        if not b64:
            url = items[0].get("url")
            if url:
                from cloud.http_util import download_bytes

                png = download_bytes(url)
                return CloudGenerateResult(True, "ok", png_bytes=png)
            raise CloudProviderError("即梦结果无图像数据")
        png = base64.b64decode(b64)
        if progress_cb:
            progress_cb({"kind": "cloud_task", "status": "SUCCEEDED", "pct": 100, "message": "即梦 · 完成"})
        return CloudGenerateResult(True, "ok", png_bytes=png)
