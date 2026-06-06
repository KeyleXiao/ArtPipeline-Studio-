#!/usr/bin/env python3
"""云任务并发执行与进度聚合。"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from cloud.generator import generate_one_cloud
from cloud.registry import is_cloud_checkpoint, max_parallel_for_provider, provider_for_checkpoint
from config_manager import Asset, ConfigManager

LogFn = Callable[[str], None]
ProgressFn = Callable[[dict[str, Any]], None]


class CloudTaskTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.tasks: dict[str, dict[str, Any]] = {}

    def upsert(self, asset_id: str, **fields: Any) -> None:
        with self._lock:
            cur = dict(self.tasks.get(asset_id) or {})
            cur.update(fields)
            self.tasks[asset_id] = cur

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(v) for v in self.tasks.values()]

    def overall_pct(self) -> int:
        items = self.snapshot()
        if not items:
            return 0
        total = sum(int(t.get("pct") or 0) for t in items)
        return min(100, total // len(items))


def _max_workers(config: ConfigManager, assets: list[Asset]) -> int:
    global_max = int(config.defaults.get("cloud_max_concurrent") or 3)
    providers = {provider_for_checkpoint(config.checkpoint_for_asset(a)) for a in assets}
    caps = [max_parallel_for_provider(p, global_max) for p in providers if p]
    cap = min(caps) if caps else global_max
    return max(1, min(global_max, cap, len(assets) or 1))


def run_cloud_batch(
    config: ConfigManager,
    assets: list[Asset],
    *,
    to_inbox: bool = True,
    export_after: bool = False,
    log: LogFn | None = None,
    progress_cb: ProgressFn | None = None,
    cancel_event: threading.Event | None = None,
    tracker: CloudTaskTracker | None = None,
) -> list[Any]:
    from pipeline_core import GenerateResult, PipelineCore

    if not assets:
        return []
    tracker = tracker or CloudTaskTracker()
    workers = _max_workers(config, assets)
    results: list[Any] = []
    pipeline = PipelineCore(config)

    def work(asset: Asset) -> Any:
        if cancel_event and cancel_event.is_set():
            return GenerateResult(asset.id, False, "已取消")
        tracker.upsert(
            asset.id,
            asset_id=asset.id,
            filename=asset.filename,
            status="PENDING",
            pct=5,
            message="排队中",
        )
        if progress_cb:
            progress_cb({"kind": "cloud_batch", "cloud_tasks": tracker.snapshot()})

        def inner_progress(info: dict[str, Any]) -> None:
            tracker.upsert(
                asset.id,
                asset_id=asset.id,
                filename=asset.filename,
                status=str(info.get("status") or "RUNNING"),
                pct=int(info.get("pct") or 0),
                message=str(info.get("message") or ""),
            )
            if progress_cb:
                progress_cb(
                    {
                        "kind": "cloud_batch",
                        "cloud_tasks": tracker.snapshot(),
                        "overall_pct": tracker.overall_pct(),
                        "filename": asset.filename,
                    }
                )

        result = generate_one_cloud(
            config,
            asset,
            to_inbox=to_inbox,
            log=log,
            progress_cb=inner_progress,
            cancel_event=cancel_event,
        )
        tracker.upsert(
            asset.id,
            status="SUCCEEDED" if result.ok else "FAILED",
            pct=100 if result.ok else 0,
            message="完成" if result.ok else result.message,
        )
        if result.ok and export_after:
            pipeline.export_one(asset, log=log)
        if progress_cb:
            progress_cb({"kind": "cloud_batch", "cloud_tasks": tracker.snapshot(), "overall_pct": tracker.overall_pct()})
        return result

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="cloud-gen") as pool:
        futures = {pool.submit(work, asset): asset for asset in assets}
        for fut in as_completed(futures):
            if cancel_event and cancel_event.is_set():
                break
            try:
                results.append(fut.result())
            except Exception as exc:
                asset = futures[fut]
                results.append(GenerateResult(asset.id, False, str(exc)))
    return results


def partition_assets_by_backend(
    config: ConfigManager, asset_ids: list[str]
) -> tuple[list[Asset], list[Asset]]:
    cloud: list[Asset] = []
    comfy: list[Asset] = []
    for aid in asset_ids:
        asset = config.asset_by_id(aid)
        if not asset:
            continue
        ckpt = config.checkpoint_for_asset(asset)
        if is_cloud_checkpoint(ckpt):
            cloud.append(asset)
        else:
            comfy.append(asset)
    return cloud, comfy
