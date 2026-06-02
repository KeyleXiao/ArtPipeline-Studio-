#!/usr/bin/env python3
"""
ArtPipeline Studio · 桌面壳（发布 / .app 打包入口）

用法:
  python run_app.py

基于 pywebview 加载本地 FastAPI，无浏览器地址栏。
打包 .app 示例（需 pyinstaller）见 README.md

开发调试请用 run_dev.py。
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
from pathlib import Path

ARTAPP_ROOT = Path(__file__).resolve().parent
if str(ARTAPP_ROOT) not in sys.path:
    sys.path.insert(0, str(ARTAPP_ROOT))

APP_TITLE = "ArtPipeline Studio"
DEFAULT_PORT = 8765


def _free_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])


def _run_server(host: str, port: int) -> None:
    import uvicorn
    from backend.main import create_app

    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


def main() -> None:
    parser = argparse.ArgumentParser(description="ArtPipeline Studio desktop shell")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    try:
        import webview
    except ImportError as exc:
        print("缺少 pywebview，请: pip install pywebview", file=sys.stderr)
        raise SystemExit(1) from exc

    port = _free_port(args.port)
    url = f"http://{args.host}:{port}"

    server = threading.Thread(
        target=_run_server,
        args=(args.host, port),
        daemon=True,
        name="artapp-api",
    )
    server.start()

    for _ in range(80):
        try:
            with socket.create_connection((args.host, port), timeout=0.08):
                break
        except OSError:
            time.sleep(0.05)
    else:
        print("API 启动超时", file=sys.stderr)
        raise SystemExit(1)

    webview.create_window(APP_TITLE, url, width=1280, height=840, min_size=(720, 520))
    webview.start()


if __name__ == "__main__":
    main()
