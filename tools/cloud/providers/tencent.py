#!/usr/bin/env python3
"""腾讯混元生图 · TokenHub API。"""

from __future__ import annotations

from cloud.base import CloudGenerateRequest, CloudGenerateResult, CloudProvider, CloudProviderError
from cloud.http_util import download_bytes, image_to_data_url, poll_until
from cloud.registry import CLOUD_GEN_MODE_EDIT, CLOUD_GEN_MODE_I2I, CLOUD_GEN_MODE_TEXT
from cloud.tencent_maas import MODEL_IMAGE_V3, maas_post, resolve_tencent_api_key


class TencentProvider(CloudProvider):
    provider_id = "tencent"

    def generate(self, req: CloudGenerateRequest, *, progress_cb=None, cancel_event=None) -> CloudGenerateResult:
        api_key = resolve_tencent_api_key(req.api_keys)
        if not api_key:
            return CloudGenerateResult(False, "未配置 TokenHub API Key（sk-...）")

        if req.mode == CLOUD_GEN_MODE_I2I:
            return self._submit_job(req, api_key, progress_cb, cancel_event, ref=req.ref_image_path, label="图生图")
        if req.mode == CLOUD_GEN_MODE_EDIT:
            base = req.base_image_path or req.ref_image_path
            return self._submit_job(req, api_key, progress_cb, cancel_event, ref=base, label="图像编辑")
        return self._submit_job(req, api_key, progress_cb, cancel_event, label="文生图")

    def _resolution(self, w: int, h: int) -> str:
        return f"{w}:{h}"

    def _submit_job(
        self,
        req: CloudGenerateRequest,
        api_key: str,
        progress_cb,
        cancel_event,
        *,
        ref=None,
        label: str,
    ) -> CloudGenerateResult:
        payload: dict = {
            "model": MODEL_IMAGE_V3,
            "prompt": req.prompt,
            "resolution": self._resolution(req.width, req.height),
            "rsp_img_type": "url",
        }
        if ref is not None:
            if not ref.is_file():
                return CloudGenerateResult(False, f"{label}：参考图不存在")
            payload["images"] = [image_to_data_url(ref)]
            if req.mode == CLOUD_GEN_MODE_I2I:
                payload["strength"] = max(0.01, min(1.0, req.strength))

        if progress_cb:
            progress_cb(
                {"kind": "cloud_task", "status": "SUBMITTING", "pct": 10, "message": f"混元 · {label} · 提交中"}
            )

        resp = maas_post(api_key, "api/image/submit", payload)
        job_id = resp.get("id")
        if not job_id:
            raise CloudProviderError(f"混元未返回任务 id: {resp}")

        def check():
            q = maas_post(
                api_key,
                "api/image/query",
                {"model": MODEL_IMAGE_V3, "id": str(job_id)},
                timeout=60.0,
            )
            status = str(q.get("status") or "").lower()
            if progress_cb:
                pct = 20
                if status in ("running", "processing"):
                    pct = 55
                elif status == "queued":
                    pct = 20
                progress_cb(
                    {
                        "kind": "cloud_task",
                        "status": status or "queued",
                        "pct": pct,
                        "message": f"混元 · {status or '排队中'}",
                    }
                )
            if status in ("failed", "error"):
                detail = q.get("message") or q.get("error") or status
                raise CloudProviderError(f"混元任务失败: {detail}")
            if status != "completed":
                return None
            rows = q.get("data") or []
            if not rows:
                raise CloudProviderError("混元任务无输出图")
            url = rows[0].get("url") if isinstance(rows[0], dict) else rows[0]
            if not url:
                raise CloudProviderError("混元任务无输出 URL")
            if progress_cb:
                progress_cb({"kind": "cloud_task", "status": "DOWNLOADING", "pct": 92, "message": "混元 · 下载中"})
            return download_bytes(str(url))

        png = poll_until(check, cancel_event=cancel_event, interval_s=3.0)
        return CloudGenerateResult(True, "ok", png_bytes=png)
