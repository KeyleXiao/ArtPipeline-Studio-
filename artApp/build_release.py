#!/usr/bin/env python3
"""
ArtPipeline Studio 打包入口（按当前系统自动选择平台脚本）

推荐直接使用平台专用脚本:
  macOS:   python3 build_release_mac.py
  Windows: python build_release_win.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build ArtPipeline Studio (auto-detect platform)",
        add_help=True,
    )
    parser.add_argument("--no-clean", action="store_true")
    parser.add_argument("--setup-venv", action="store_true")
    parser.add_argument("--portable", action="store_true")
    args, _unknown = parser.parse_known_args()

    if sys.platform == "darwin":
        script = "build_release_mac.py"
    elif sys.platform == "win32":
        script = "build_release_win.py"
    else:
        raise SystemExit(
            "当前系统未配置自动打包。\n"
            "请在 macOS 运行 build_release_mac.py，或在 Windows 运行 build_release_win.py。"
        )

    cmd = [sys.executable, script]
    if args.no_clean:
        cmd.append("--no-clean")
    if args.setup_venv:
        cmd.append("--setup-venv")
    if args.portable:
        cmd.append("--portable")

    print(f">>> 转发到 {script}")
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
