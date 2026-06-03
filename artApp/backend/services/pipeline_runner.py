#!/usr/bin/env python3
"""后台生成 / 导出任务。"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.deps import get_config_manager
from backend.services.log_bus import log_bus


@dataclass
class JobState:
    busy: bool = False
    kind: str = ""
    run_id: int = 0
    progress: dict[str, Any] = field(default_factory=dict)
    cancel_requested: bool = False


class PipelineRunner:
    def __init__(self) -> None:
        self.state = JobState()
        self._lock = threading.Lock()

    def is_busy(self) -> bool:
        with self._lock:
            return self.state.busy

    def progress_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "busy": self.state.busy,
                "kind": self.state.kind,
                "run_id": self.state.run_id,
                "progress": dict(self.state.progress),
            }

    def cancel(self) -> None:
        from pipeline_core import PipelineCore

        with self._lock:
            self.state.cancel_requested = True
        try:
            PipelineCore(get_config_manager()).request_cancel()
        except Exception:
            pass
        log_bus.log("已请求取消（ComfyUI interrupt）", kind="操作")

    def _set_busy(self, busy: bool, kind: str = "") -> None:
        with self._lock:
            self.state.busy = busy
            self.state.kind = kind if busy else ""
            if not busy:
                self.state.progress = {}
                self.state.cancel_requested = False

    def _set_progress(self, info: dict[str, Any]) -> None:
        with self._lock:
            if info.get("kind") == "batch":
                self.state.progress = dict(info)
                return
            prev = dict(self.state.progress)
            merged = dict(info)
            for key in ("index", "total", "filename"):
                if key in prev and key not in merged:
                    merged[key] = prev[key]
            self.state.progress = merged

    def run_async(self, kind: str, fn: Callable[[], None]) -> int:
        if self.is_busy():
            raise RuntimeError("已有任务进行中")
        with self._lock:
            self.state.run_id += 1
            run_id = self.state.run_id
        self._set_busy(True, kind)
        self._set_progress({"kind": "status", "message": "任务启动中…"})

        def worker() -> None:
            try:
                fn()
            finally:
                self._set_busy(False)

        threading.Thread(target=worker, daemon=True, name=f"artapp-{kind}").start()
        return run_id

    def generate_batch(self, asset_ids: list[str], *, export_after: bool = False) -> int:
        from config_manager import Asset
        from pipeline_core import PipelineCore

        config = get_config_manager()

        def task() -> None:
            from backend.deps import reload_config_manager

            nonlocal config
            config = reload_config_manager()
            pipeline = PipelineCore(config)
            ok, comfy_msg = pipeline.test_comfyui()
            if not ok:
                log_bus.log(f"ComfyUI 不可用，已取消生成: {comfy_msg}", kind="生成")
                self._set_progress({"kind": "status", "message": comfy_msg})
                return
            assets = [a for aid in asset_ids if (a := config.asset_by_id(aid))]
            if not assets:
                missing = [aid for aid in asset_ids if not config.asset_by_id(aid)]
                if missing:
                    log_bus.log(f"未找到资源: {', '.join(missing)}", kind="生成")
                else:
                    log_bus.log("没有可生成的资源", kind="生成")
                return
            disabled = [a for a in assets if not a.enabled]
            if disabled:
                log_bus.log(
                    f"以下资源未勾选「启用」，仍按指定生成: "
                    f"{', '.join(a.filename for a in disabled)}",
                    kind="生成",
                )
            total = len(asset_ids)
            log_bus.log(f"── 开始 {'生成并导出' if export_after else '生成'} {total} 张 ──", kind="生成")

            def progress_cb(info: dict) -> None:
                self._set_progress(info)

            for i, asset_id in enumerate(asset_ids, start=1):
                if pipeline.cancel_event.is_set():
                    log_bus.log("── 已取消 ──", kind="生成")
                    break
                asset = config.asset_by_id(asset_id)
                if not asset:
                    log_bus.log(f"SKIP 资源不存在: {asset_id}", kind="生成")
                    continue
                self._set_progress(
                    {"kind": "batch", "index": i, "total": total, "filename": asset.filename}
                )
                try:
                    result = pipeline.generate_one(
                        asset,
                        to_inbox=True,
                        log=lambda m: log_bus.log(m, kind="生成"),
                        progress_cb=progress_cb,
                    )
                    if export_after and result.ok:
                        pipeline.export_one(asset, log=lambda m: log_bus.log(m, kind="生成"))
                    if not result.ok:
                        log_bus.log(f"FAIL {asset.filename}: {result.message}", kind="生成")
                except Exception as exc:
                    if pipeline.cancel_event.is_set():
                        log_bus.log("── 已取消 ──", kind="生成")
                        break
                    log_bus.log(f"FAIL {asset.filename}: {exc}", kind="生成")
            log_bus.log("── 任务结束 ──", kind="生成")

        return self.run_async("generate", task)

    def export_batch(self, asset_ids: list[str]) -> int:
        from pipeline_core import PipelineCore

        config = get_config_manager()

        def task() -> None:
            pipeline = PipelineCore(config)
            assets = [a for aid in asset_ids if (a := config.asset_by_id(aid))]
            if not assets:
                log_bus.log("未找到指定资源", kind="生成")
                return
            ok, fail = pipeline.export_many(assets, log=lambda m: log_bus.log(m, kind="生成"))
            log_bus.log(f"导出完成: 成功 {ok}，失败 {fail}", kind="生成")

        return self.run_async("export", task)


pipeline_runner = PipelineRunner()
