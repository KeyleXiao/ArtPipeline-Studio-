#!/usr/bin/env python3
"""开发 / 打包发布时的路径解析。"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def bundle_root() -> Path:
    if is_frozen():
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def resolve_web_dir() -> Path:
    """定位 web 静态资源（开发 / PyInstaller .app 内 Resources 或 Frameworks  symlink）。"""
    candidates: list[Path] = [bundle_root() / "web"]
    if is_frozen():
        exe = Path(sys.executable).resolve()
        contents = exe.parent.parent
        candidates.extend(
            [
                contents / "Resources" / "web",
                contents / "Frameworks" / "web",
                exe.parent / "web",
            ]
        )
    else:
        candidates.append(Path(__file__).resolve().parent.parent / "web")
    seen: set[str] = set()
    for cand in candidates:
        key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        try:
            resolved = cand.resolve()
        except OSError:
            resolved = cand
        if (resolved / "index.html").is_file():
            return resolved
    return candidates[0]


def _resolve_bundled_tools() -> Path:
    """PyInstaller .app 内 tools 目录（Frameworks 或 Resources）。"""
    roots: list[Path] = []
    if is_frozen():
        roots.append(Path(sys._MEIPASS))
        exe = Path(sys.executable).resolve()
        # macOS: .../Contents/MacOS/exe → Contents/{Frameworks,Resources}
        contents = exe.parent.parent
        roots.extend([contents / "Frameworks", contents / "Resources", exe.parent])
    for root in roots:
        cand = root / "tools"
        if (cand / "config_manager.py").is_file():
            return cand
    return roots[0] / "tools" if roots else Path("tools")


def user_data_dir() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "ArtPipeline Studio"
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return Path(base) if base else home / "ArtPipeline Studio"
    return home / ".artpipeline-studio"


def _bootstrap_user_data(bundled_tools: Path) -> None:
    """打包版：配置与工作流写入用户目录，避免 .app 内只读。"""
    import paths as tp

    user = user_data_dir()
    user.mkdir(parents=True, exist_ok=True)

    config_dest = user / "pipeline_config.json"
    src_config = bundled_tools / "pipeline_config.json"
    if not config_dest.is_file() and src_config.is_file():
        shutil.copy2(src_config, config_dest)

    wf_dest = user / "workflows"
    wf_src = bundled_tools / "workflows"
    if wf_src.is_dir() and not wf_dest.is_dir():
        shutil.copytree(wf_src, wf_dest)

    tp.CONFIG_FILE = config_dest
    tp.WORKFLOWS_DIR = wf_dest


def setup_paths() -> tuple[Path, Path, Path]:
    """
    配置 sys.path 与 tools.paths 常量。
    返回 (ARTAPP_ROOT, ART_PIPELINE_ROOT, TOOLS_DIR)。
    """
    bundle_env = os.environ.get("ARTPIPELINE_BUNDLE_ROOT")
    if bundle_env:
        bundle = Path(bundle_env).resolve()
        artapp_root = bundle / "artApp"
        tools_dir = bundle / "tools"
        if str(artapp_root) not in sys.path:
            sys.path.insert(0, str(artapp_root))
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        return artapp_root, bundle, tools_dir

    if is_frozen():
        artapp_root = bundle_root()
        tools_dir = _resolve_bundled_tools()
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        _bootstrap_user_data(tools_dir)
        return artapp_root, artapp_root, tools_dir

    artapp_root = Path(__file__).resolve().parent.parent
    art_pipeline_root = artapp_root.parent
    tools_dir = art_pipeline_root / "tools"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    return artapp_root, art_pipeline_root, tools_dir
