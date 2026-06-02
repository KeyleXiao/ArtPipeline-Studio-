#!/usr/bin/env python3
"""后处理编辑器 · 图层抠图（写回 PNG）。"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from alpha_matte import border_matte_to_alpha, seed_matte_to_alpha
from postprocess.models import ASSET_SUBJECT_SOURCE, Layer, layer_image_source


def resolve_layer_image_path(
    *,
    art_root: Path,
    layer: Layer,
    inbox_path: Path,
) -> Path | None:
    """返回可写的图层 PNG 路径。"""
    key = layer_image_source(layer)
    if not key:
        return None
    if key == ASSET_SUBJECT_SOURCE:
        return inbox_path if inbox_path.is_file() else None
    path = Path(key)
    if not path.is_absolute():
        path = art_root / key
    return path if path.is_file() else None


def apply_layer_matte(
    path: Path,
    *,
    mode: str,
    seed_x: int | None = None,
    seed_y: int | None = None,
    color_tol: float = 34.0,
    step_tol: float = 16.0,
    feather: int = 0,
) -> dict[str, Any]:
    from PIL import Image

    with Image.open(path) as im:
        im.load()
        rgba = im.convert("RGBA")
    if mode == "border":
        out = border_matte_to_alpha(
            rgba,
            color_tol=color_tol,
            step_tol=step_tol,
            feather=max(0, int(feather)),
        )
    elif mode == "seed":
        if seed_x is None or seed_y is None:
            raise ValueError("seed 模式需要 seed_x / seed_y")
        out = seed_matte_to_alpha(
            rgba,
            int(seed_x),
            int(seed_y),
            color_tol=color_tol,
            step_tol=step_tol,
        )
    else:
        raise ValueError(f"未知抠图模式: {mode}")

    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    path.write_bytes(buf.getvalue())
    return {"width": out.width, "height": out.height, "path": str(path)}
