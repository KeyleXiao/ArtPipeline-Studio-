#!/usr/bin/env python3
"""应用版本与发行说明（写入 pipeline_config.json，供欢迎弹窗展示）。"""

from __future__ import annotations

APP_VERSION = "1.0"

DEFAULT_RELEASE_NOTES: dict[str, str] = {
    "zh-CN": (
        "首发版本：ComfyUI 本地 SDXL 生图、多云 API 批量生图、DeepSeek AI 助手、"
        "后处理工作台与 Unity 一键导出。"
    ),
    "en-US": (
        "Initial release: ComfyUI local SDXL, multi-cloud batch generation, "
        "DeepSeek AI assistant, post-process workspace, and Unity export."
    ),
}
