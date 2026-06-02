#!/usr/bin/env python3
"""图层合成、命中测试与边界计算。"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageDraw

from postprocess.fonts import load_pil_font
from postprocess.models import (
    ASSET_SUBJECT_SOURCE,
    CropRect,
    Layer,
    LayerStack,
    LayerTransform,
    TextStyle,
    layer_image_source,
)


class ImageResolver(Protocol):
    def resolve(self, source: str) -> Image.Image | None: ...


@dataclass
class Bounds:
    x: int
    y: int
    w: int
    h: int

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px < self.x2 and self.y <= py < self.y2


@dataclass
class AssetImageResolver:
    """从 ArtPipeline / Unity 路径解析图片。"""

    art_root: Path
    asset_source: Path | None
    asset_inbox: Path | None
    asset_unity: Path | None = None
    subject_path: Path | None = None

    def resolve(self, source: str) -> Image.Image | None:
        if not source:
            return None
        if source == ASSET_SUBJECT_SOURCE:
            path = self._subject_file_path()
            if not path:
                return None
            return _load_rgba(path)
        path = Path(source)
        if not path.is_absolute():
            path = self.art_root / source
        if not path.is_file():
            return None
        return _load_rgba(path)

    def _subject_file_path(self) -> Path | None:
        """主体层 $asset 仅读 inbox（后处理不碰 source）。"""
        if self.subject_path and self.subject_path.is_file():
            return self.subject_path
        if self.asset_inbox and self.asset_inbox.is_file():
            return self.asset_inbox
        return None


def _load_rgba(path: Path) -> Image.Image:
    with Image.open(path) as im:
        im.load()
        return im.convert("RGBA")


def _parse_hex_color(value: str, default: tuple[int, int, int, int] = (255, 255, 255, 255)) -> tuple[int, int, int, int]:
    value = (value or "").strip()
    if not value:
        return default
    if value.startswith("#"):
        value = value[1:]
    if len(value) == 6:
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
        return r, g, b, 255
    if len(value) == 8:
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
        a = int(value[6:8], 16)
        return r, g, b, a
    return default


def _anchor_point(transform: LayerTransform, canvas_w: int, canvas_h: int) -> tuple[float, float]:
    if transform.anchor == "top_left":
        return transform.offset_x, transform.offset_y
    return canvas_w / 2.0 + transform.offset_x, canvas_h / 2.0 + transform.offset_y


def _scaled_size(img_w: int, img_h: int, scale: float) -> tuple[int, int]:
    scale = max(0.01, scale)
    return max(1, int(round(img_w * scale))), max(1, int(round(img_h * scale)))


def _paste_box(anchor_x: float, anchor_y: float, w: int, h: int, anchor: str) -> tuple[int, int]:
    if anchor == "top_left":
        return int(round(anchor_x)), int(round(anchor_y))
    return int(round(anchor_x - w / 2)), int(round(anchor_y - h / 2))


def _apply_crop(im: Image.Image, crop: CropRect | None) -> Image.Image:
    if not crop:
        return im
    c = crop.clamp_to(im.width, im.height)
    return im.crop((c.x, c.y, c.x + c.w, c.y + c.h))


def _prepare_image_layer(
    layer: Layer,
    resolver: ImageResolver,
    canvas_w: int,
    canvas_h: int,
) -> tuple[Image.Image | None, Bounds | None]:
    src_key = layer_image_source(layer)
    raw = resolver.resolve(src_key)
    if raw is None:
        return None, None
    im = _apply_crop(raw, layer.crop)
    sw, sh = _scaled_size(im.width, im.height, layer.transform.scale)
    if (sw, sh) != im.size:
        im = im.resize((sw, sh), Image.Resampling.LANCZOS)
    ax, ay = _anchor_point(layer.transform, canvas_w, canvas_h)
    px, py = _paste_box(ax, ay, sw, sh, layer.transform.anchor)
    return im, Bounds(px, py, sw, sh)


def _effective_font_size(text: TextStyle, transform: LayerTransform) -> int:
    return max(8, int(round(text.font_size * max(0.01, transform.scale))))


def _text_bbox_and_origin(
    text: TextStyle,
    transform: LayerTransform,
    canvas_w: int,
    canvas_h: int,
    *,
    draw: ImageDraw.ImageDraw,
) -> tuple[Bounds | None, tuple[int, int]]:
    if not text.content.strip():
        return None, (0, 0)
    font_size = _effective_font_size(text, transform)
    font = load_pil_font(text.font_family, font_size)
    stroke_w = max(0, text.stroke_width)
    bbox = draw.textbbox(
        (0, 0),
        text.content,
        font=font,
        stroke_width=stroke_w if text.stroke_color else 0,
    )
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    ax, ay = _anchor_point(transform, canvas_w, canvas_h)
    if text.align == "center":
        px = int(round(ax - tw / 2))
    elif text.align == "right":
        px = int(round(ax - tw))
    else:
        px = int(round(ax))
    py = int(round(ay - th / 2))
    draw_x = px - bbox[0]
    draw_y = py - bbox[1]
    return Bounds(px, py, tw, th), (draw_x, draw_y)


def _text_bounds_on_canvas(
    layer: Layer,
    canvas_w: int,
    canvas_h: int,
    *,
    draw: ImageDraw.ImageDraw | None = None,
    scratch: Image.Image | None = None,
) -> Bounds | None:
    if not layer.text or not layer.text.content.strip():
        return None
    if draw is None or scratch is None:
        scratch = Image.new("RGBA", (max(canvas_w, 4), max(canvas_h, 4)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(scratch)
    bounds, _origin = _text_bbox_and_origin(layer.text, layer.transform, canvas_w, canvas_h, draw=draw)
    return bounds


def layer_bounds(
    layer: Layer,
    stack: LayerStack,
    resolver: ImageResolver,
    *,
    scratch: Image.Image | None = None,
) -> Bounds | None:
    if not layer.visible:
        return None
    cw, ch = stack.canvas_width, stack.canvas_height
    if layer.type == "image":
        _, bounds = _prepare_image_layer(layer, resolver, cw, ch)
        return bounds
    if layer.type == "text":
        if scratch is None:
            scratch = Image.new("RGBA", (max(cw, 4), max(ch, 4)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(scratch)
        return _text_bounds_on_canvas(layer, cw, ch, draw=draw, scratch=scratch)
    return None


def hit_test(
    stack: LayerStack,
    resolver: ImageResolver,
    px: float,
    py: float,
    *,
    skip_locked: bool = True,
    skip_hidden: bool = True,
) -> Layer | None:
    scratch = Image.new(
        "RGBA",
        (max(stack.canvas_width, 4), max(stack.canvas_height, 4)),
        (0, 0, 0, 0),
    )
    for layer in reversed(stack.layers):
        if skip_hidden and not layer.visible:
            continue
        if skip_locked and layer.locked:
            continue
        bounds = layer_bounds(layer, stack, resolver, scratch=scratch)
        if bounds and bounds.contains(px, py):
            return layer
    return None


def render_stack(
    stack: LayerStack,
    resolver: ImageResolver,
    *,
    solo_layer_id: str | None = None,
) -> Image.Image:
    cw, ch = stack.canvas_width, stack.canvas_height
    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    scratch = Image.new("RGBA", (max(cw, 4), max(ch, 4)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(scratch)

    for layer in stack.layers:
        if solo_layer_id and layer.id != solo_layer_id:
            continue
        if not layer.visible:
            continue
        opacity = max(0.0, min(1.0, layer.opacity))
        if layer.type == "image":
            im, bounds = _prepare_image_layer(layer, resolver, cw, ch)
            if im is None or bounds is None:
                continue
            if opacity < 0.999:
                im = _apply_opacity(im, opacity)
            canvas.alpha_composite(im, (bounds.x, bounds.y))
        elif layer.type == "text" and layer.text and layer.text.content.strip():
            _draw_text_layer(canvas, layer, cw, ch, draw=draw, scratch=scratch, opacity=opacity)
    return canvas


def _apply_opacity(im: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 0.999:
        return im
    out = im.copy()
    alpha = out.getchannel("A")
    alpha = alpha.point(lambda a: int(a * opacity))
    out.putalpha(alpha)
    return out


def _draw_text_layer(
    canvas: Image.Image,
    layer: Layer,
    canvas_w: int,
    canvas_h: int,
    *,
    draw: ImageDraw.ImageDraw,
    scratch: Image.Image,
    opacity: float,
) -> None:
    assert layer.text is not None
    text = layer.text
    font_size = _effective_font_size(text, layer.transform)
    font = load_pil_font(text.font_family, font_size)
    fill = _parse_hex_color(text.color)
    if opacity < 0.999:
        fill = (fill[0], fill[1], fill[2], int(fill[3] * opacity))
    stroke_fill = _parse_hex_color(text.stroke_color, (0, 0, 0, 0)) if text.stroke_color else None
    stroke_w = max(0, text.stroke_width)
    _bounds, origin = _text_bbox_and_origin(text, layer.transform, canvas_w, canvas_h, draw=draw)
    if _bounds is None:
        return
    text_draw = ImageDraw.Draw(canvas)
    text_draw.text(
        origin,
        text.content,
        font=font,
        fill=fill,
        stroke_width=stroke_w if stroke_fill else 0,
        stroke_fill=stroke_fill,
    )


def render_stack_to_png_bytes(stack: LayerStack, resolver: ImageResolver) -> bytes:
    im = render_stack(stack, resolver)
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def stack_checkerboard(width: int, height: int, *, cell: int = 8) -> Image.Image:
    light = (72, 72, 72, 255)
    dark = (48, 48, 48, 255)
    bg = Image.new("RGBA", (width, height), light)
    px = bg.load()
    for y in range(height):
        for x in range(width):
            if ((x // cell) + (y // cell)) % 2:
                px[x, y] = dark
    return bg
