#!/usr/bin/env python3
"""FastAPI 应用工厂。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from backend.runtime_paths import bundle_root
from backend.routes import router

WEB_DIR = bundle_root() / "web"


class StaticFilesSkipApiWrite(StaticFiles):
    """避免 /api 的 POST/PUT 等落入静态文件层返回 405。"""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith("/api"):
            method = scope.get("method", "GET")
            if method not in ("GET", "HEAD", "OPTIONS"):
                resp = JSONResponse({"detail": "Not Found"}, status_code=404)
                await resp(scope, receive, send)
                return
        await super().__call__(scope, receive, send)


def create_app() -> FastAPI:
    app = FastAPI(title="ArtPipeline Studio", version="2.0.0", docs_url="/api/docs", redoc_url=None)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.on_event("startup")
    async def _startup() -> None:
        import asyncio

        from backend.services.log_bus import log_bus

        log_bus.bind_loop(asyncio.get_running_loop())
        from backend.deps import get_config_manager, sync_log_bus_from_config

        sync_log_bus_from_config()
        cfg = get_config_manager()
        log_bus.log(
            f"ArtPipeline Web 已启动 · {len(cfg.categories())} 分类 · {len(cfg.assets())} 资源",
            kind="系统",
        )
        log_file = log_bus.log_file_path()
        if log_file:
            log_bus.log(f"运行日志文件: {log_file}", kind="系统")

    if WEB_DIR.is_dir():
        app.mount("/", StaticFilesSkipApiWrite(directory=str(WEB_DIR), html=True), name="web")

    return app
