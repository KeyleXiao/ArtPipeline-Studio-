#!/usr/bin/env python3
"""
打包 ArtPipeline Studio · Windows 发布包

用法（在 Windows 上）:
  cd ArtPipeline\\artApp
  python build_release_win.py

产物:
  release/ArtPipeline Studio/ArtPipeline Studio.exe
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from release_build import (
    BUILD_VENV,
    ensure_build_venv,
    build_portable_win,
    build_pyinstaller,
    venv_python_path,
)


def _require_windows() -> None:
    if sys.platform != "win32":
        raise SystemExit(
            "build_release_win.py 仅支持在 Windows 上运行。\n"
            "macOS 请使用: python3 build_release_mac.py"
        )


def main() -> None:
    _require_windows()

    parser = argparse.ArgumentParser(description="Build ArtPipeline Studio for Windows")
    parser.add_argument("--no-clean", action="store_true", help="保留上次 build/dist")
    parser.add_argument(
        "--setup-venv",
        action="store_true",
        help="创建/更新 .build-venv 后退出",
    )
    parser.add_argument(
        "--portable",
        action="store_true",
        help="构建便携目录（不跑 PyInstaller，需本机 Python）",
    )
    args = parser.parse_args()

    if args.setup_venv:
        ensure_build_venv(recreate=False)
        print(f"\n✓ 构建环境就绪: {BUILD_VENV}")
        return

    if args.portable:
        artifact = build_portable_win()
        print(f"\n✓ Windows 便携版: {artifact}")
        return

    py = venv_python_path()
    if not py.is_file():
        ensure_build_venv()

    try:
        artifact = build_pyinstaller(
            clean=not args.no_clean,
            python=str(py),
            target="win",
        )
        print(f"\n✓ Windows 独立版: {artifact}")
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"PyInstaller 打包失败: {exc}") from exc


if __name__ == "__main__":
    main()
