#!/usr/bin/env python3
"""Stability AI · Stable Image v2beta。"""

from __future__ import annotations

from cloud.base import CloudGenerateRequest, CloudGenerateResult, CloudProvider
from cloud.http_util import http_multipart
from cloud.registry import CLOUD_GEN_MODE_EDIT, CLOUD_GEN_MODE_I2I, CLOUD_GEN_MODE_TEXT

_BASE = "https://api.stability.ai"


class StabilityProvider(CloudProvider):
    provider_id = "stability"

    def generate(self, req: CloudGenerateRequest, *, progress_cb=None, cancel_event=None) -> CloudGenerateResult:
        key = req.api_keys.get("stability", "")
        if not key:
            return CloudGenerateResult(False, "未配置 Stability API Key")

        modes = req.model.get("modes") or {}
        if req.mode == CLOUD_GEN_MODE_TEXT:
            ep = str((modes.get("text_to_image") or {}).get("endpoint") or "v2beta/stable-image/generate/core")
        elif req.mode == CLOUD_GEN_MODE_I2I:
            ep = str((modes.get("image_to_image") or {}).get("endpoint") or "v2beta/stable-image/control/structure")
        elif req.mode == CLOUD_GEN_MODE_EDIT:
            ep = str((modes.get("image_edit") or {}).get("endpoint") or "v2beta/stable-image/control/structure")
        else:
            return CloudGenerateResult(False, f"不支持的模式: {req.mode}")

        fields: dict[str, str] = {
            "prompt": req.prompt,
            "output_format": "png",
            "aspect_ratio": self._aspect_ratio(req.width, req.height),
        }
        if req.negative:
            fields["negative_prompt"] = req.negative
        if req.seed is not None:
            fields["seed"] = str(req.seed)

        files = None
        img_path = None
        if req.mode in (CLOUD_GEN_MODE_I2I, CLOUD_GEN_MODE_EDIT):
            img_path = req.ref_image_path if req.mode == CLOUD_GEN_MODE_I2I else (req.base_image_path or req.ref_image_path)
            if not img_path or not img_path.is_file():
                return CloudGenerateResult(False, "图生图/图像编辑：参考图或底图不存在")
            img_bytes = img_path.read_bytes()
            mime = "image/png"
            if img_path.suffix.lower() in (".jpg", ".jpeg"):
                mime = "image/jpeg"
            files = {"image": (img_path.name, img_bytes, mime)}
            strength = max(0.05, min(0.95, req.strength))
            if req.mode == CLOUD_GEN_MODE_EDIT:
                strength = max(strength, 0.55)
            fields["control_strength"] = f"{strength:.2f}"

        label = {"text_to_image": "文生图", "image_to_image": "图生图", "image_edit": "图像编辑"}.get(req.mode, req.mode)
        if progress_cb:
            progress_cb(
                {
                    "kind": "cloud_task",
                    "status": "RUNNING",
                    "pct": 40,
                    "message": f"Stability · {label} · 生成中",
                }
            )

        raw = http_multipart(
            f"{_BASE}/{ep.lstrip('/')}",
            fields=fields,
            files=files,
            headers={"Authorization": f"Bearer {key}", "Accept": "image/*"},
        )
        if not raw:
            return CloudGenerateResult(False, "Stability 无输出")
        if progress_cb:
            progress_cb({"kind": "cloud_task", "status": "SUCCEEDED", "pct": 100, "message": "Stability · 完成"})
        return CloudGenerateResult(True, "ok", png_bytes=raw)

    @staticmethod
    def _aspect_ratio(w: int, h: int) -> str:
        if w == h:
            return "1:1"
        if w > h:
            return "16:9" if w / h > 1.4 else "4:3"
        return "9:16" if h / w > 1.4 else "3:4"
