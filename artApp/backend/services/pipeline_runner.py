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
            self.state.progress = info

    def run_async(self, kind: str, fn: Callable[[], None]) -> None:
        if self.is_busy():
            raise RuntimeError("已有任务进行中")
        self._set_busy(True, kind)

        def worker() -> None:
            try:
                fn()
            finally:
                self._set_busy(False)

        threading.Thread(target=worker, daemon=True, name=f"artapp-{kind}").start()

    def generate_batch(self, asset_ids: list[str], *, export_after: bool = False) -> None:
        from config_manager import Asset
        from pipeline_core import PipelineCore

        config = get_config_manager()
        pipeline = PipelineCore(config)

        def task() -> None:
            assets = [a for aid in asset_ids if (a := config.asset_by_id(aid))]
            enabled = [a for a in assets if a.enabled]
            if not enabled:
                log_bus.log("没有可生成的资源（可能已禁用）", kind="生成")
                return
            total = len(enabled)
            log_bus.log(f"── 开始 {'生成并导出' if export_after else '生成'} {total} 张 ──", kind="生成")

            def progress_cb(info: dict) -> None:
                self._set_progress(info)

            for i, asset in enumerate(enabled, start=1):
                if pipeline.cancel_event.is_set():
                    log_bus.log("── 已取消 ──", kind="生成")
                    break
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

        self.run_async("generate", task)

    def export_batch(self, asset_ids: list[str]) -> None:
        from pipeline_core import PipelineCore

        config = get_config_manager()
        pipeline = PipelineCore(config)

        def task() -> None:
            assets = [a for aid in asset_ids if (a := config.asset_by_id(aid))]
            if not assets:
                return
            ok, fail = pipeline.export_many(assets, log=lambda m: log_bus.log(m, kind="生成"))
            log_bus.log(f"导出完成: 成功 {ok}，失败 {fail}", kind="生成")

        self.run_async("export", task)


pipeline_runner = PipelineRunner()
