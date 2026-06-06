#!/usr/bin/env python3
"""ComfyUI 工作流预设目录（API JSON，仅标准节点）。"""

from __future__ import annotations

from typing import Any

# 参考实践：SDXL 双 CLIP 分段（ComfyUI 官方 SDXL 文档）、场景+主体两阶段 img2img（refiner 思路简化版）
# 分层合成节点（LayerStyle 等）需额外安装插件，此处不纳入默认预设。

WORKFLOW_PRESETS: list[dict[str, Any]] = [
    {
        "id": "sdxl_standard",
        "name": "SDXL 标准（单次）",
        "mode": "single_pass",
        "file": "workflows/_default_sdxl_api.json",
        "description": "一次文生图，G/L 同文。适合角色、UI 边框、按钮。",
        "how_it_works": "EmptyLatent → 一次 KSampler → 出图。正向 G/L 注入相同文本，结构最简单、速度最快。",
        "categories": ["roles", "ui_frames", "ui_buttons", "ui_combat", "ui_status", "*"],
        "gen_modes": ["txt2img"],
        "tags": ["single-pass", "default"],
        "recommended_for": "角色头像、九宫格边框、战斗贴图",
    },
    {
        "id": "sdxl_split_gl",
        "name": "SDXL 分段 G/L",
        "mode": "dual_clip",
        "file": "workflows/_sdxl_split_g_l_api.json",
        "description": "G=画质+主体+场景，L=主体+场景+光影。配合四段 prompt 效果更好。",
        "how_it_works": "仍是一次采样，但 SDXL 的 G/L 双通道分别接收不同 prompt 段，构图与氛围可分开微调（非多图层渲染）。",
        "categories": ["backgrounds", "roles", "*"],
        "gen_modes": ["txt2img"],
        "tags": ["segment", "sdxl-dual"],
        "recommended_for": "竖屏海报、需要单独调场景/光影的资源",
    },
    {
        "id": "sdxl_layered",
        "name": "分层：场景 → 主体",
        "mode": "two_pass",
        "file": "workflows/_sdxl_layered_scene_subject_api.json",
        "description": "Pass1 生成场景+光影，Pass2 以 img2img 叠加主体（denoise 可调）。适合复杂海报。",
        "how_it_works": "Pass1 用「前缀+场景+光影」生成背景；Pass2 对 Pass1 结果 img2img，用「前缀+主体」叠加前景。Pass2 强度跟 img2img denoise。",
        "categories": ["backgrounds", "*"],
        "gen_modes": ["txt2img"],
        "tags": ["layered", "two-pass"],
        "recommended_for": "startup_poster 类竖屏海报、主体与背景需分开控 prompt",
    },
    {
        "id": "sdxl_img2img",
        "name": "图生图 / 重绘",
        "mode": "img2img",
        "file": "workflows/_default_sdxl_img2img_api.json",
        "description": "上传参考图 + denoise 重绘。重绘图、图生图模式使用。",
        "how_it_works": "LoadImage → VAEEncode → KSampler 按 denoise 重绘。不改变构图大结构，适合微调或重绘图写入 inbox。",
        "categories": ["*"],
        "gen_modes": ["img2img", "redraw"],
        "tags": ["img2img", "default"],
        "recommended_for": "重绘图、参考图微调",
    },
    {
        "id": "sdxl_img2img_split",
        "name": "图生图分段 G/L",
        "mode": "img2img_dual",
        "file": "workflows/_sdxl_img2img_split_g_l_api.json",
        "description": "图生图 + SDXL G/L 分段，重绘时四段 prompt 分工更细。",
        "how_it_works": "与「图生图/重绘」相同，但正向走 G/L 双通道，四段 prompt 在重绘时分工更细。",
        "categories": ["*"],
        "gen_modes": ["img2img", "redraw"],
        "tags": ["img2img", "segment"],
        "recommended_for": "重绘海报、需分通道控 prompt",
    },
    {
        "id": "item_gii",
        "name": "道具 Icon · GII V4",
        "mode": "icon_gii",
        "file": "workflows/_item_icon_gii_api.json",
        "description": "Game Icon Institute XL + gmic_(3dicon)，G/L 双通道。",
        "how_it_works": "GII 专用 checkpoint + gmic_(3dicon) 触发词，G/L 双通道，单次采样出透明底 icon。",
        "categories": ["items", "skills"],
        "gen_modes": ["txt2img"],
        "tags": ["icon", "lora"],
        "recommended_for": "道具、技能 icon",
    },
    {
        "id": "item_sdxl_lora",
        "name": "道具 Icon · SDXL LoRA",
        "mode": "icon_lora",
        "file": "workflows/_item_icon_sdxl_api.json",
        "description": "SDXL + RPG Item Icons LoRA，weic 触发词。",
        "how_it_works": "SDXL + Item Icons LoRA，G/L 双通道，单次采样；GII 不可用时的备用 icon 流程。",
        "categories": ["items", "skills"],
        "gen_modes": ["txt2img"],
        "tags": ["icon", "lora"],
        "recommended_for": "备用道具工作流",
    },
]


def _match_list(patterns: list[str], value: str) -> bool:
    if not patterns or "*" in patterns:
        return True
    return value in patterns


def list_presets(
    *,
    category: str = "",
    gen_mode: str = "txt2img",
) -> list[dict[str, Any]]:
    """按分类与生成模式筛选可用预设。"""
    cat = (category or "").strip()
    mode = (gen_mode or "txt2img").strip().lower()
    out: list[dict[str, Any]] = []
    for p in WORKFLOW_PRESETS:
        if not _match_list(list(p.get("gen_modes") or []), mode):
            continue
        if cat and not _match_list(list(p.get("categories") or []), cat):
            continue
        out.append(
            {
                "id": p["id"],
                "name": p["name"],
                "mode": p.get("mode", ""),
                "description": p.get("description", ""),
                "how_it_works": p.get("how_it_works", ""),
                "file": p["file"],
                "tags": list(p.get("tags") or []),
                "recommended_for": p.get("recommended_for", ""),
            }
        )
    return out


def preset_by_id(preset_id: str) -> dict[str, Any] | None:
    key = (preset_id or "").strip()
    for p in WORKFLOW_PRESETS:
        if p["id"] == key:
            return p
    return None


def suggest_preset_id(*, category: str, gen_mode: str) -> str:
    """为资源推荐默认预设 id。"""
    mode = (gen_mode or "txt2img").strip().lower()
    cat = (category or "").strip()
    if mode in ("img2img", "redraw"):
        return "sdxl_img2img"
    if cat in ("items", "skills"):
        return "item_gii"
    if cat == "backgrounds":
        return "sdxl_split_gl"
    return "sdxl_standard"
