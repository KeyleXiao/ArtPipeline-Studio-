#!/usr/bin/env python3
"""腾讯混元生图。"""

from __future__ import annotations

import base64
import time

from cloud.base import CloudGenerateRequest, CloudGenerateResult, CloudProvider, CloudProviderError
from cloud.http_util import download_bytes, image_to_data_url, poll_until
from cloud.registry import CLOUD_GEN_MODE_EDIT, CLOUD_GEN_MODE_I2I, CLOUD_GEN_MODE_TEXT
from cloud.tencent_sign import tencent_request


class TencentProvider(CloudProvider):
    provider_id = "tencent"

    def generate(self, req: CloudGenerateRequest, *, progress_cb=None, cancel_event=None) -> CloudGenerateResult:
        sid = req.api_keys.get("tencent_secret_id", "")
        skey = req.api_keys.get("tencent_secret_key", "")
        if not sid or not skey:
            return CloudGenerateResult(False, "未配置腾讯混元 SecretId / SecretKey")

        if req.mode == CLOUD_GEN_MODE_I2I:
            return self._image_to_image(req, sid, skey, progress_cb, cancel_event)
        return self._text_job(req, sid, skey, progress_cb, cancel_event, with_images=req.mode == CLOUD_GEN_MODE_EDIT)

    def _resolution(self, w: int, h: int) -> str:
        return f"{w}:{h}"

    def _text_job(
        self,
        req: CloudGenerateRequest,
        sid: str,
        skey: str,
        progress_cb,
        cancel_event,
        *,
        with_images: bool,
    ) -> CloudGenerateResult:
        payload: dict = {
            "Prompt": req.prompt,
            "Resolution": self._resolution(req.width, req.height),
        }
        if with_images:
            base = req.base_image_path or req.ref_image_path
            if not base or not base.is_file():
                return CloudGenerateResult(False, "图像编辑：底图不存在")
            payload["Images"] = [image_to_data_url(base)]

        label = "图像编辑" if with_images else "文生图"
        if progress_cb:
            progress_cb({"kind": "cloud_task", "status": "SUBMITTING", "pct": 10, "message": f"混元 · {label} · 提交中"})

        resp = tencent_request(
            secret_id=sid,
            secret_key=skey,
            action="SubmitTextToImageJob",
            payload=payload,
        )
        job_id = resp.get("JobId") or resp.get("JobID")
        if not job_id:
            raise CloudProviderError(f"混元未返回 JobId: {resp}")

        def check():
            q = tencent_request(
                secret_id=sid,
                secret_key=skey,
                action="QueryTextToImageJob",
                payload={"JobId": job_id},
            )
            code = str(q.get("JobStatusCode") or "")
            msg = str(q.get("JobStatusMsg") or "")
            if progress_cb:
                pct = 20
                if code == "2":
                    pct = 55
                elif code == "1":
                    pct = 20
                progress_cb(
                    {
                        "kind": "cloud_task",
                        "status": msg or code,
                        "pct": pct,
                        "message": f"混元 · {msg or '处理中'}",
                    }
                )
            if code == "4":
                raise CloudProviderError(f"混元任务失败: {q.get('JobErrorMsg') or msg}")
            if code != "5":
                return None
            urls = q.get("ResultImage") or []
            if not urls:
                raise CloudProviderError("混元任务无输出图")
            if progress_cb:
                progress_cb({"kind": "cloud_task", "status": "DOWNLOADING", "pct": 92, "message": "混元 · 下载中"})
            return download_bytes(str(urls[0]))

        png = poll_until(check, cancel_event=cancel_event, interval_s=3.0)
        return CloudGenerateResult(True, "ok", png_bytes=png)

    def _image_to_image(
        self,
        req: CloudGenerateRequest,
        sid: str,
        skey: str,
        progress_cb,
        cancel_event,
    ) -> CloudGenerateResult:
        if not req.ref_image_path or not req.ref_image_path.is_file():
            return CloudGenerateResult(False, "图生图：参考图不存在")
        if progress_cb:
            progress_cb({"kind": "cloud_task", "status": "RUNNING", "pct": 40, "message": "混元 · 图生图 · 生成中"})
        resp = tencent_request(
            secret_id=sid,
            secret_key=skey,
            action="ImageToImage",
            payload={
                "InputImage": image_to_data_url(req.ref_image_path),
                "Prompt": req.prompt,
                "Strength": max(0.01, min(1.0, req.strength)),
            },
        )
        b64 = resp.get("ResultImage") or resp.get("ResultImageBase64")
        url = resp.get("ResultUrl")
        if isinstance(b64, str) and b64.startswith("http"):
            url = b64
            b64 = None
        if url:
            png = download_bytes(str(url))
        elif b64:
            raw = str(b64)
            if raw.startswith("data:"):
                raw = raw.split(",", 1)[-1]
            png = base64.b64decode(raw)
        else:
            images = resp.get("Images") or resp.get("ResultImages") or []
            if images:
                u = images[0] if isinstance(images[0], str) else images[0].get("Url")
                png = download_bytes(str(u))
            else:
                raise CloudProviderError(f"混元图生图无输出: {list(resp.keys())}")
        if progress_cb:
            progress_cb({"kind": "cloud_task", "status": "SUCCEEDED", "pct": 100, "message": "混元 · 完成"})
        return CloudGenerateResult(True, "ok", png_bytes=png)
