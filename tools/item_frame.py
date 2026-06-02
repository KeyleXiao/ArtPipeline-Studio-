#!/usr/bin/env python3
"""道具 icon 统一金框（程序化绘制，AI 只负责内景物件）。"""

from __future__ import annotations

import math
from functools import lru_cache
from io import BytesIO

try:
    from PIL import Image, ImageDraw
except ImportError:
    raise SystemExit("需要 Pillow: pip install Pillow")


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * max(0.0, min(1.0, t))


def _gold(t: float, alpha: int = 255) -> tuple[int, int, int, int]:
    return (
        int(_lerp(255, 130, t)),
        int(_lerp(232, 100, t)),
        int(_lerp(155, 50, t)),
        alpha,
    )


def render_inner_panel(size: int) -> Image.Image:
    """暗紫灰径向内底（物件绘制区域）。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    cx = cy = (size - 1) / 2.0
    max_r = size * 0.72
    for y in range(size):
        for x in range(size):
            dx = (x - cx) / max_r
            dy = (y - cy) / max_r
            dist = math.sqrt(dx * dx + dy * dy)
            edge = min(1.0, dist)
            r = int(_lerp(42, 58, edge))
            g = int(_lerp(34, 48, edge))
            b = int(_lerp(58, 72, edge))
            px[x, y] = (r, g, b, 255)
    return img


def render_frame_overlay(size: int) -> Image.Image:
    """透明中心 + 四边金框与角饰（叠在 AI 物件图之上）。"""
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    border = max(3, size // 32)
    inner = border + max(1, size // 64)

    for i in range(border):
        t = i / max(1, border - 1)
        c = _gold(t * 0.35 + 0.55)
        d.rectangle([i, i, size - 1 - i, size - 1 - i], outline=c, width=1)

    d.rectangle([inner, inner, size - 1 - inner, size - 1 - inner], outline=_gold(0.2, 180), width=1)

    corner = max(8, size // 8)

    def corner_ornament(ox: int, oy: int, flip_x: bool, flip_y: bool) -> None:
        local = Image.new("RGBA", (corner, corner), (0, 0, 0, 0))
        ld = ImageDraw.Draw(local)
        ld.arc([0, 0, corner - 1, corner - 1], start=200, end=305, fill=_gold(0.15, 200), width=max(1, size // 128))
        ld.line([(2, corner // 2), (corner // 2, 2)], fill=_gold(0.55, 220), width=max(1, size // 128))
        if flip_x:
            local = local.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if flip_y:
            local = local.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        overlay.paste(local, (ox, oy), local)

    pad = inner
    corner_ornament(pad, pad, False, False)
    corner_ornament(size - pad - corner, pad, True, False)
    corner_ornament(pad, size - pad - corner, False, True)
    corner_ornament(size - pad - corner, size - pad - corner, True, True)
    return overlay


@lru_cache(maxsize=8)
def _cached_frame_bytes(size: int) -> bytes:
    buf = BytesIO()
    inner = render_inner_panel(size)
    inner.save(buf, format="PNG")
    return buf.getvalue()


@lru_cache(maxsize=8)
def _cached_overlay_bytes(size: int) -> bytes:
    buf = BytesIO()
    render_frame_overlay(size).save(buf, format="PNG")
    return buf.getvalue()


def composite_item_icon(ai_png: bytes, *, size: int) -> bytes:
    """AI 物件图 + 程序化紫底 + 金框叠加 → 最终道具 icon。"""
    obj = Image.open(BytesIO(ai_png)).convert("RGBA")
    # 裁切中心区域，去掉 AI 在边缘生成的杂散背景（如窗帘/面板）
    cw = int(obj.width * 0.72)
    ch = int(obj.height * 0.72)
    obj = obj.crop(
        (
            (obj.width - cw) // 2,
            (obj.height - ch) // 2,
            (obj.width + cw) // 2,
            (obj.height + ch) // 2,
        )
    )
    obj = obj.resize((size, size), Image.Resampling.LANCZOS)
    panel = render_inner_panel(size)
    frame = render_frame_overlay(size)

    # 物件居中缩放到内面板约 62%
    inner_margin = max(12, size // 5)
    inner_w = size - inner_margin * 2
    inner_h = size - inner_margin * 2
    scale = min(inner_w / obj.width, inner_h / obj.height) * 0.92
    nw = max(1, int(obj.width * scale))
    nh = max(1, int(obj.height * scale))
    obj_scaled = obj.resize((nw, nh), Image.Resampling.LANCZOS)

    result = panel.copy()
    x = (size - nw) // 2
    y = (size - nh) // 2
    result.alpha_composite(obj_scaled, (x, y))
    result.alpha_composite(frame)
    buf = BytesIO()
    result.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
