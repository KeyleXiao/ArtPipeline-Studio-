#!/usr/bin/env python3
"""ArtPipeline 路径常量。"""

from __future__ import annotations

from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
INFERRED_ART_ROOT = TOOLS_DIR.parent
INFERRED_PROJECT_ROOT = INFERRED_ART_ROOT.parent

# 未配置 defaults 根路径时的回退（随 tools 脚本位置推断）
ART_ROOT = INFERRED_ART_ROOT
PROJECT_ROOT = INFERRED_PROJECT_ROOT

CONFIG_FILE = TOOLS_DIR / "pipeline_config.json"
WORKFLOWS_DIR = TOOLS_DIR / "workflows"

SOURCE_ROOT = ART_ROOT / "source"
INBOX_ROOT = ART_ROOT / "inbox"
ASSETS_ROOT = PROJECT_ROOT / "Assets"

DEFAULT_COMFYUI_URL = "http://127.0.0.1:8188"
DEFAULT_CHECKPOINT = "animagineXL_v3.safetensors"


def default_log_dir() -> Path:
    """各平台默认运行日志目录（用户可在全局配置中覆盖）。"""
    import os
    import sys

    home = Path.home()
    if sys.platform == "darwin":
        return (home / "Library" / "Logs" / "ArtPipeline Studio").resolve()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        root = Path(base) if base else home / "ArtPipeline Studio"
        return (root / "Logs").resolve()
    return (home / ".artpipeline-studio" / "logs").resolve()
