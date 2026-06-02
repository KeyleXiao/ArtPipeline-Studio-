#!/usr/bin/env python3
"""将 AI 图外侧纯色/灰底转为透明（不依赖 rembg）。"""

from __future__ import annotations

import io
from collections import deque

import numpy as np
from PIL import Image


def _color_dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.max(np.abs(a.astype(np.float32) - b.astype(np.float32))))


def _pixel_saturation(rgb: np.ndarray) -> float:
    return float(np.max(rgb) - np.min(rgb))


def _estimate_border_bg_color(rgb: np.ndarray, *, border_band: int) -> np.ndarray:
    """从四边采样估计背景色（中位数，抗角落主体干扰）。"""
    h, w = rgb.shape[:2]
    band = max(1, min(border_band, h // 4, w // 4))
    samples: list[np.ndarray] = []
    for x in range(w):
        for y in range(band):
            samples.append(rgb[y, x])
        for y in range(h - band, h):
            samples.append(rgb[y, x])
    for y in range(band, h - band):
        for x in range(band):
            samples.append(rgb[y, x])
        for x in range(w - band, w):
            samples.append(rgb[y, x])
    if not samples:
        return np.array([127.0, 127.0, 127.0], dtype=np.float32)
    return np.median(np.stack(samples, axis=0), axis=0).astype(np.float32)


def _is_background_like(
    px: np.ndarray,
    bg: np.ndarray,
    *,
    color_tol: float,
    bg_sat: float,
) -> bool:
    """仅判断像素是否像背景色，主体彩色/高饱和区域不会被标记。"""
    if _color_dist(px, bg) > color_tol:
        return False
    px_sat = _pixel_saturation(px)
    # 背景多为低饱和；主体上的彩色细节即使亮度接近也不泛洪
    if px_sat > max(28.0, bg_sat + 20.0):
        return False
    return True


def border_matte_to_alpha(
    im: Image.Image,
    *,
    color_tol: float = 34.0,
    step_tol: float = 16.0,
    border_band: int = 4,
    feather: int = 0,
) -> Image.Image:
    """从四边泛洪：仅剔除与边框背景色相近的外侧区域，保留主体颜色。"""
    arr = np.array(im.convert("RGBA"))
    h, w = arr.shape[:2]
    rgb = arr[:, :, :3].astype(np.float32)
    bg = _estimate_border_bg_color(rgb, border_band=border_band)
    bg_sat = _pixel_saturation(bg)

    outside = np.zeros((h, w), dtype=bool)
    q: deque[tuple[int, int]] = deque()

    def seed(y: int, x: int) -> None:
        if outside[y, x]:
            return
        if _is_background_like(rgb[y, x], bg, color_tol=color_tol, bg_sat=bg_sat):
            outside[y, x] = True
            q.append((y, x))

    for x in range(w):
        seed(0, x)
        seed(h - 1, x)
    for y in range(h):
        seed(y, 0)
        seed(y, w - 1)

    while q:
        y, x = q.popleft()
        cur = rgb[y, x]
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if not (0 <= ny < h and 0 <= nx < w) or outside[ny, nx]:
                continue
            npx = rgb[ny, nx]
            if not _is_background_like(npx, bg, color_tol=color_tol + 6.0, bg_sat=bg_sat):
                continue
            if _color_dist(npx, cur) > step_tol:
                continue
            outside[ny, nx] = True
            q.append((ny, nx))

    if not outside.any():
        return im.convert("RGBA")

    out = arr.copy()
    out[outside, 3] = 0

    if feather > 0:
        alpha = out[:, :, 3].astype(np.float32)
        bg_mask = outside
        for _ in range(feather):
            neighbor_bg = np.zeros_like(bg_mask)
            neighbor_bg[1:, :] |= bg_mask[:-1, :]
            neighbor_bg[:-1, :] |= bg_mask[1:, :]
            neighbor_bg[:, 1:] |= bg_mask[:, :-1]
            neighbor_bg[:, :-1] |= bg_mask[:, 1:]
            rim = neighbor_bg & ~bg_mask & (alpha > 0)
            alpha[rim] = np.minimum(alpha[rim], 180.0)
            bg_mask |= rim
        out[:, :, 3] = alpha.astype(np.uint8)

    return Image.fromarray(out, mode="RGBA")


def seed_matte_to_alpha(
    im: Image.Image,
    seed_x: int,
    seed_y: int,
    *,
    color_tol: float = 34.0,
    step_tol: float = 16.0,
) -> Image.Image:
    """从指定像素泛洪：剔除与点击处颜色相近的相连区域。"""
    arr = np.array(im.convert("RGBA"))
    h, w = arr.shape[:2]
    if h == 0 or w == 0:
        return im.convert("RGBA")
    sx = int(np.clip(seed_x, 0, w - 1))
    sy = int(np.clip(seed_y, 0, h - 1))
    if arr[sy, sx, 3] == 0:
        return im.convert("RGBA")

    rgb = arr[:, :, :3].astype(np.float32)
    bg = rgb[sy, sx].copy()
    bg_sat = _pixel_saturation(bg)

    outside = np.zeros((h, w), dtype=bool)
    q: deque[tuple[int, int]] = deque()
    outside[sy, sx] = True
    q.append((sy, sx))

    while q:
        y, x = q.popleft()
        cur = rgb[y, x]
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if not (0 <= ny < h and 0 <= nx < w) or outside[ny, nx]:
                continue
            if arr[ny, nx, 3] == 0:
                continue
            npx = rgb[ny, nx]
            if not _is_background_like(npx, bg, color_tol=color_tol, bg_sat=bg_sat):
                continue
            if _color_dist(npx, cur) > step_tol:
                continue
            outside[ny, nx] = True
            q.append((ny, nx))

    if not outside.any():
        return im.convert("RGBA")

    out = arr.copy()
    out[outside, 3] = 0
    return Image.fromarray(out, mode="RGBA")


def apply_alpha_matte_png(data: bytes, *, mode: str = "border") -> bytes:
    if mode == "none":
        return data
    im = Image.open(io.BytesIO(data))
    if mode == "border":
        im = border_matte_to_alpha(im)
    else:
        im = im.convert("RGBA")
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
