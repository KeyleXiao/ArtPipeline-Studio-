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
import traceback
import urllib.error
import urllib.request
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


def _startup_log_path() -> Path:
    from backend.runtime_paths import setup_paths, user_data_dir

    setup_paths()
    path = user_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path / "startup.log"


def _log_startup(message: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    try:
        with _startup_log_path().open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def _run_server(host: str, port: int, error_box: list[str]) -> None:
    try:
        import uvicorn

        from backend.main import WEB_DIR, create_app

        if not WEB_DIR.is_dir() or not (WEB_DIR / "index.html").is_file():
            raise RuntimeError(f"Web 资源目录无效: {WEB_DIR}")
        _log_startup(f"WEB_DIR={WEB_DIR}")
        uvicorn.run(create_app(), host=host, port=port, log_level="warning")
    except Exception as exc:
        tb = traceback.format_exc()
        error_box.append(str(exc))
        _log_startup(f"SERVER ERROR: {exc}\n{tb}")


def _http_ok(url: str, timeout: float = 0.6) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return int(getattr(resp, "status", 200)) == 200
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def _wait_for_http(url: str, *, timeout_sec: float = 12.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if _http_ok(url):
            return True
        time.sleep(0.06)
    return False


def _show_fatal(message: str) -> None:
    _log_startup(f"FATAL: {message}")
    if sys.platform == "darwin":
        import subprocess

        esc = message.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display alert "ArtPipeline Studio 启动失败" message "{esc}" as critical',
            ],
            check=False,
        )
    else:
        print(message, file=sys.stderr)


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

    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False

    _log_startup("--- launch ---")
    port = _free_port(args.port)
    url = f"http://{args.host}:{port}"
    _log_startup(f"url={url}")

    server_error: list[str] = []
    server = threading.Thread(
        target=_run_server,
        args=(args.host, port, server_error),
        daemon=True,
        name="artapp-api",
    )
    server.start()

    if not _wait_for_http(f"{url}/api/health"):
        log_path = _startup_log_path()
        detail = server_error[0] if server_error else "本地 API 未响应"
        _show_fatal(
            f"{detail}\n\n请查看启动日志：\n{log_path}\n\n"
            "若从 zip 解压，请用「归档实用工具」解压以保留符号链接。"
        )
        raise SystemExit(1)

    if not _wait_for_http(url, timeout_sec=3.0):
        _show_fatal(f"界面资源加载失败：{url}")
        raise SystemExit(1)

    webview.create_window(
        APP_TITLE,
        url,
        width=1280,
        height=990,
        min_size=(720, 520),
        background_color="#06080d",
    )
    webview.start()


if __name__ == "__main__":
    main()
