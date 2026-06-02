#!/usr/bin/env python3
"""
打包 ArtPipeline Studio · macOS 发布包

用法:
  cd ArtPipeline/artApp
  python3 build_release_mac.py

产物:
  release/ArtPipeline Studio.app
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from release_build import (
    BUILD_VENV,
    ensure_build_venv,
    build_portable_mac,
    build_portable_win,
    build_pyinstaller,
    venv_python_path,
)


def _require_macos() -> None:
    if sys.platform != "darwin":
        raise SystemExit(
            "build_release_mac.py 仅支持在 macOS 上运行。\n"
            "Windows 请使用: python build_release_win.py"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ArtPipeline Studio for macOS")
    parser.add_argument("--no-clean", action="store_true", help="保留上次 build/dist")
    parser.add_argument(
        "--setup-venv",
        action="store_true",
        help="创建/更新 .build-venv 后退出",
    )
    parser.add_argument(
        "--portable",
        action="store_true",
        help="构建便携 .app（不跑 PyInstaller，需本机 Python）",
    )
    parser.add_argument(
        "--portable-win",
        action="store_true",
        help="在 Mac 上组装 Windows 便携目录（仅复制源码+bat，不含 .exe；目标机需 Python）",
    )
    args = parser.parse_args()

    if args.setup_venv:
        ensure_build_venv(recreate=False)
        print(f"\n✓ 构建环境就绪: {BUILD_VENV}")
        return

    _require_macos()
    if args.portable and args.portable_win:
        raise SystemExit("--portable 与 --portable-win 不能同时使用")

    if args.portable_win:
        artifact = build_portable_win()
        print(f"\n✓ Windows 便携目录（在 Mac 上组装）: {artifact}")
        print("  将整个文件夹拷到 Windows，先 pip install -r bundle\\artApp\\requirements.txt")
        print("  再双击 ArtPipeline Studio.bat 启动。")
        print("  若要独立 .exe，请在 Windows 上运行 build_release_win.py，或使用 CI（见 README）。")
        return

    if args.portable:
        artifact = build_portable_mac()
        print(f"\n✓ macOS 便携版: {artifact}")
        return

    py = venv_python_path()
    if not py.is_file():
        ensure_build_venv()

    try:
        artifact = build_pyinstaller(
            clean=not args.no_clean,
            python=str(py),
            target="mac",
        )
        print(f"\n✓ macOS 独立版: {artifact}")
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"PyInstaller 打包失败: {exc}") from exc


if __name__ == "__main__":
    main()
