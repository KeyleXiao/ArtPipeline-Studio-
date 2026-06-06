#!/usr/bin/env python3
"""预览图生成（后台线程安全，纯 PIL）。"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Literal

from config_manager import Asset, ConfigManager

PreviewSource = Literal["inbox", "source", "unity"]

PREVIEW_MAX = 440


def resolve_path_for_source(
    config: ConfigManager,
    asset: Asset,
    source: PreviewSource,
) -> Path | None:
    src, inbox, unity = config.resolve_paths(asset)
    return {"source": src, "inbox": inbox, "unity": unity}.get(source)


def resolve_preview_file(
    config: ConfigManager,
    asset: Asset,
    source: PreviewSource,
) -> Path:
    """按预览来源解析文件；source/unity 不存在时不回退到其他路径。"""
    src, inbox, unity = config.resolve_paths(asset)
    primary = resolve_path_for_source(config, asset, source)
    if primary is not None:
        try:
            if primary.is_file():
                return primary
        except OSError:
            pass
    if source == "inbox":
        fallback = first_existing_path(inbox, src, unity)
        if fallback is not None:
            return fallback
    raise FileNotFoundError(f"无 {source} 文件")


def first_existing_path(*candidates: Path | None) -> Path | None:
    for path in candidates:
        if path is None:
            continue
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def category_remove_bg_default(config: ConfigManager, cat_id: str) -> bool:
    cat = config.category_by_id(cat_id)
    if not cat:
        return True
    return cat.alpha_matte.strip().lower() != "none"


def should_remove_bg(config: ConfigManager, asset: Asset) -> bool:
    from config_manager import REMOVE_BG_INHERIT, REMOVE_BG_KEEP, REMOVE_BG_REMOVE

    mode = asset.remove_bg_mode
    if mode == REMOVE_BG_REMOVE:
        return True
    if mode == REMOVE_BG_KEEP:
        return False
    return category_remove_bg_default(config, asset.category)


def build_preview_rgba(
    config: ConfigManager,
    asset: Asset,
    *,
    source: PreviewSource = "inbox",
    max_size: int = PREVIEW_MAX,
) -> Any:
    from PIL import Image

    path = resolve_preview_file(config, asset, source)

    # 主页预览与「打开文件」一致：直接读 inbox / source / unity 原图。
    # 后处理合成预览请在后处理编辑器内查看，避免对 inbox 二次套用 stack 导致缩小/偏移。
    with Image.open(path) as raw:
        raw.load()
        im = raw.convert("RGBA")

    w, h = im.size
    cap = max(64, min(int(max_size), 2048))
    if max(w, h) > cap:
        scale = cap / max(w, h)
        im = im.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            Image.Resampling.LANCZOS,
        )

    if should_remove_bg(config, asset):
        try:
            from alpha_matte import border_matte_to_alpha

            im = border_matte_to_alpha(im)
        except ImportError:
            pass

    return im


def preview_png_bytes(
    config: ConfigManager,
    asset: Asset,
    *,
    source: PreviewSource = "inbox",
    max_size: int = PREVIEW_MAX,
) -> bytes:
    im = build_preview_rgba(config, asset, source=source, max_size=max_size)
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
