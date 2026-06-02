#!/usr/bin/env python3
"""后处理模板：分类默认层栈。"""

from __future__ import annotations

from typing import Any

from postprocess.models import (
    ASSET_SUBJECT_SOURCE,
    Layer,
    LayerStack,
    default_stack_for_canvas,
    stack_from_dict,
    stack_to_dict,
)

BUILTIN_TEMPLATES: dict[str, str] = {
    "minimal": "仅主体",
    "icon_3layer": "背景 + 主体 + 边框",
}


def builtin_template(name: str, width: int, height: int) -> LayerStack:
    if name == "icon_3layer":
        return LayerStack(
            canvas_width=width,
            canvas_height=height,
            layers=[
                Layer.new_image("背景", source="overlays/icon_bg.png"),
                Layer.new_image("主体", source=ASSET_SUBJECT_SOURCE, is_subject=True),
                Layer.new_image("边框", source="overlays/icon_frame.png"),
            ],
        )
    return default_stack_for_canvas(width, height)


def resolve_template(
    config_data: dict[str, Any],
    *,
    template_id: str | None,
    category_id: str | None,
    width: int,
    height: int,
) -> LayerStack:
    tid = template_id
    if not tid and category_id:
        for cat in config_data.get("categories", []):
            if cat.get("id") == category_id:
                tid = cat.get("postprocess_template")
                break
    if tid:
        templates = config_data.get("postprocess_templates", {})
        raw = templates.get(tid)
        if raw:
            stack = stack_from_dict(raw)
            if stack:
                stack.canvas_width = width
                stack.canvas_height = height
                stack.ensure_subject_layer()
                return stack
        if tid in BUILTIN_TEMPLATES:
            return builtin_template(tid, width, height)
    return default_stack_for_canvas(width, height)


def save_template(config_data: dict[str, Any], template_id: str, stack: LayerStack) -> None:
    config_data.setdefault("postprocess_templates", {})[template_id] = stack_to_dict(stack)
