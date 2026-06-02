#!/usr/bin/env python3
"""
ArtPipeline Studio · Web 版（开发入口）

用法:
  cd ArtPipeline/artApp
  pip install -r requirements.txt
  python run_dev.py

浏览器自动打开 http://127.0.0.1:8765

旧版 Tk 回退:
  python ../tools/artTool_ui.py
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

ARTAPP_ROOT = Path(__file__).resolve().parent
if str(ARTAPP_ROOT) not in sys.path:
    sys.path.insert(0, str(ARTAPP_ROOT))


def _pick_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])


def main() -> None:
    parser = argparse.ArgumentParser(description="ArtPipeline Studio Web (dev)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    port = _pick_port(args.port)
    url = f"http://{args.host}:{port}"

    if not args.no_browser:
        def open_browser() -> None:
            time.sleep(0.6)
            webbrowser.open(url)

        threading.Thread(target=open_browser, daemon=True).start()

    import uvicorn

    uvicorn.run(
        "backend.main:create_app",
        factory=True,
        host=args.host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
