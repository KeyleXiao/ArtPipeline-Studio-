#!/usr/bin/env python3
"""DeepSeek AI 助手：生成提示词与工作流 JSON。"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"
SUPPORTED_MODELS = ("deepseek-v4-flash", "deepseek-v4-pro")
_LEGACY_MODEL_MAP = {
    "deepseek-chat": "deepseek-v4-flash",
    "deepseek-reasoner": "deepseek-v4-pro",
}


def resolve_model(name: str | None) -> str:
    m = (name or "").strip()
    if not m:
        return DEFAULT_MODEL
    return _LEGACY_MODEL_MAP.get(m, m)


def verify_deepseek(api_key: str, model: str = "") -> tuple[bool, str]:
    """轻量连通性验证（max_tokens=1，不写入对话历史）。"""
    key = api_key.strip()
    if not key:
        return False, "请填写 API Key"
    resolved = resolve_model(model or DEFAULT_MODEL)
    if resolved not in SUPPORTED_MODELS:
        supported = " / ".join(SUPPORTED_MODELS)
        return False, f"不支持的模型「{resolved}」，请使用: {supported}"

    payload = {
        "model": resolved,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "temperature": 0,
    }
    req = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, "API Key 无效或已过期"
        return False, f"验证失败 (HTTP {exc.code})"
    except urllib.error.URLError as exc:
        return False, f"无法连接 DeepSeek: {exc}"

    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        return False, str(msg)[:160]

    return True, f"已连接 · {resolved}"


SYSTEM_PROMPT = """你是 ArtPipeline 美术流水线的 AI 助手，为 Unity 卡牌游戏生成 ComfyUI 提示词，必要时返回工作流 JSON。

## 正向提示词四段结构（核心 · 所有分类优先使用）

生成/修改提示词时，**必须**按以下四段分别写入 updates（英文逗号分隔 tag，勿用中文进 prompt 正文）：

1. **positive_prefix（画质前缀）**：masterpiece, best quality, ultra detailed, photorealistic, cinematic lighting, 8k, RAW photo, very aesthetic, absurdres 等质量与风格基线
2. **positive_subject（主核心主体）**：画面主角/核心物件，材质、形状、状态、构图主体（左轮、角色、边框、按钮等）
3. **positive_scene（环境场景道具）**：背景、桌面道具、轮盘、塔罗牌、硬币、UI 九宫格边框构图词等
4. **positive_light（光影色彩氛围）**：low-key lighting, chiaroscuro, color palette, bokeh, mood, 材质质感词

**negative** 单独一段负向 prompt。

**合并规则**（pipeline 自动完成，你只需填四段 + negative）：
- 完整正向 positive = prefix + subject + scene + light
- SDXL-G = prefix + subject + scene（构图/全局）
- SDXL-L = subject + scene + light（细节/氛围）
- 分类 positive_common 会在生成时**前置**到正向，四段内勿重复透明底/分类通用词

**微调技巧**：用户说「去掉轮盘」只改 positive_scene 置 null 或删 roulette 相关词；其它段 null 表示保留。

### items / skills 道具技能 icon 补充
- positive_prefix 含 gmic_(3dicon) 触发词（GII V4_XL）
- positive_subject = 常见生活物体（real），人人可辨认
- positive_scene 含 game item icon, single object, centered, fills canvas 等
- positive_light = 特效 effects（紫光、绿雾、金边等），勿纯抽象符号
- checkpoint: game_icon_institute_v4_xl.safetensors；工作流 workflows/_item_icon_gii_api.json

### roles 角色头像
- prefix 含 masterpiece, best quality, very aesthetic, absurdres
- subject 含角色外貌与 cowboy shot / upper body 等构图
- scene 可 minimal 或 dark fantasy 氛围词
- light 含 painterly, detailed shading, engraved gold trim 等

### backgrounds 海报（如 startup_poster 512×896）
- subject 聚焦左轮/核心物件与近景丝绒
- scene 含 roulette wheel, tarot cards, coins, candlesticks 等
- light 含 low-key chiaroscuro, maroon purple palette, volumetric lighting

### ui_frames / ui_buttons / ui_combat
- scene 强调 border frame only, hollow transparent center, nine-slice

## 项目风格（animagineXL / SDXL）
- 默认 SDXL 链；道具工作流用 {{POSITIVE_G}} {{POSITIVE_L}}；也可用 {{POSITIVE_PREFIX}} 等分段占位符
- **透明底分类**：勿在 scene/light 写 solid backdrop / white background 等与抠底冲突的词

## 工作流规范
- ComfyUI API Format，节点 ID 为字符串数字
- **内置预设**（提示词页可选）：sdxl_standard / sdxl_split_gl / sdxl_layered（场景→主体两 pass）/ sdxl_img2img / item_gii
- sdxl_layered：Pass1=prefix+scene+light，Pass2 img2img 叠 prefix+subject；denoise 跟随 img2img_denoise
- 占位符含 {{POSITIVE_G}} {{POSITIVE_L}} {{POSITIVE_SCENE_BG}} {{POSITIVE_SUBJECT_FG}} {{DENOISE_SUBJECT}}
- 用户未明确要求改节点结构时 workflow 设为 null，引导其选用预设模板

## 回复要求
1. 只输出一个 JSON 对象，不要用 markdown 代码块包裹，不要输出其它文字
2. 写/改提示词时优先返回四段 positive_prefix / positive_subject / positive_scene / positive_light 与 negative；未改段设为 null
3. 可额外返回 positive（合并预览）或 positive_g/positive_l（一般留 null，由 pipeline 从四段推导）
4. 根据用户描述与当前资源上下文修改，保留未提及部分的合理内容
5. 用户要求填写「基本信息」时，在 updates 中返回 filename / category / width / height / seed / enabled / remove_bg_mode / subject / checkpoint；未改动的字段设为 null
6. 用户要求填写「分类设置」时，在 updates.category_settings 中返回 source/inbox/unity/checkpoint/alpha_matte/positive_common/negative_common
7. 用户要求改生成模式时，在 updates 中返回 gen_mode / ref_image / img2img_denoise

JSON 格式:
{
  "message": "给用户的简短中文说明（1-3句）",
  "updates": {
    "filename": "资源文件名 xxx.png 或 null",
    "category": "分类 id 或 null",
    "width": 128,
    "height": 128,
    "seed": "留空字符串表示清除 seed，或 null 表示不改",
    "enabled": true,
    "remove_bg_mode": "inherit|remove|keep 或 null",
    "subject": "短中文说明或 null",
    "checkpoint": "模型文件名或空字符串表示跟随分类，或 null 表示不改",
    "category_settings": {
      "source": "Icons/Items/source 或 null",
      "inbox": "Icons/Items/inbox 或 null",
      "unity": "Icons/Items 或 null",
      "checkpoint": "game_icon_institute_v4_xl.safetensors 或空字符串或 null",
      "alpha_matte": "border|none 或 null",
      "positive_common": "分类通用正向或 null",
      "negative_common": "分类通用负向或 null"
    },
    "gen_mode": "txt2img|img2img|redraw 或 null",
    "ref_image": "参考图相对路径或 null",
    "img2img_denoise": 0.65,
    "positive_prefix": "画质前缀英文 tags 或 null",
    "positive_subject": "主核心主体或 null",
    "positive_scene": "环境场景道具或 null",
    "positive_light": "光影色彩氛围或 null",
    "positive_g": "一般 null，由四段推导",
    "positive_l": "一般 null，由四段推导",
    "positive": "合并正向或 null",
    "negative": "完整负向 prompt 或 null",
    "workflow": null
  }
}
"""


class AiAssistantError(RuntimeError):
    pass


def _ai_update_present(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, bool):
        return True
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return True
    s = str(val).strip().lower()
    return s not in ("", "null", "none")


def _ai_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    raise AiAssistantError(f"无法解析 enabled 布尔值: {val!r}")


def build_context_message(
    *,
    asset_id: str,
    filename: str,
    category: str,
    category_label: str,
    width: int,
    height: int,
    subject: str,
    positive: str,
    negative: str,
    workflow_summary: str,
    positive_prefix: str = "",
    positive_subject: str = "",
    positive_scene: str = "",
    positive_light: str = "",
    positive_g: str = "",
    positive_l: str = "",
    seed: str = "",
    enabled: bool = True,
    remove_bg_mode: str = "inherit",
    category_options: str = "",
    category_source: str = "",
    category_inbox: str = "",
    category_unity: str = "",
    category_checkpoint: str = "",
    category_alpha_matte: str = "",
    category_positive_common: str = "",
    category_negative_common: str = "",
    asset_checkpoint: str = "",
    effective_checkpoint: str = "",
    gen_mode: str = "txt2img",
    ref_image: str = "",
    img2img_denoise: float = 0.65,
) -> str:
    if any(
        str(x or "").strip()
        for x in (positive_prefix, positive_subject, positive_scene, positive_light)
    ):
        prompt_block = (
            f"【画质前缀 positive_prefix】\n{positive_prefix or '（空）'}\n\n"
            f"【主核心主体 positive_subject】\n{positive_subject or '（空）'}\n\n"
            f"【环境场景 positive_scene】\n{positive_scene or '（空）'}\n\n"
            f"【光影氛围 positive_light】\n{positive_light or '（空）'}\n\n"
            f"【合并 positive】\n{positive or '（空）'}"
        )
    elif category in ("items", "skills") and (positive_g or positive_l):
        prompt_block = (
            f"SDXL-G 边框:\n{positive_g or '（空）'}\n\n"
            f"SDXL-L 物件:\n{positive_l or '（空）'}"
        )
    else:
        prompt_block = positive or "（空）"
    return (
        f"当前资源上下文:\n"
        f"- id: {asset_id}\n"
        f"- 文件名: {filename}\n"
        f"- 分类: {category} ({category_label})\n"
        f"- 尺寸: {width}×{height}\n"
        f"- 说明(subject): {subject or '（空）'}\n"
        f"- seed: {seed or '（留空=全局）'}\n"
        f"- 启用: {'是' if enabled else '否'}\n"
        f"- 剔除背景: {remove_bg_mode or 'inherit'}\n"
        f"- 资源 checkpoint: {asset_checkpoint or '（跟随分类）'}\n"
        f"- 实际生效 checkpoint: {effective_checkpoint or '（未配置）'}\n"
        f"- 可用分类 id: {category_options or category}\n"
        f"- 当前分类设置 (category_settings):\n"
        f"  · source: {category_source or '（空）'}\n"
        f"  · inbox: {category_inbox or '（空）'}\n"
        f"  · unity: {category_unity or '（空）'}\n"
        f"  · checkpoint: {category_checkpoint or '（未设置）'}\n"
        f"  · alpha_matte: {category_alpha_matte or 'border'}\n"
        f"  · positive_common: {category_positive_common or '（空）'}\n"
        f"  · negative_common: {category_negative_common or '（空）'}\n"
        f"- 生成模式: gen_mode={gen_mode or 'txt2img'}"
        f"{f', ref_image={ref_image}' if ref_image else ''}"
        f"{f', img2img_denoise={img2img_denoise}' if gen_mode in ('img2img', 'redraw') else ''}\n"
        f"- 正向 prompt:\n{prompt_block}\n"
        f"- 负向 prompt:\n{negative or '（空）'}\n"
        f"- 工作流: {workflow_summary}\n"
    )


def chat(
    messages: list[dict[str, str]],
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    timeout_s: float = 120.0,
) -> str:
    if not api_key.strip():
        raise AiAssistantError("请先在「全局设置」中填写 DeepSeek API Key")

    model = resolve_model(model)
    if model not in SUPPORTED_MODELS:
        supported = " / ".join(SUPPORTED_MODELS)
        raise AiAssistantError(f"不支持的模型「{model}」，请使用: {supported}")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key.strip()}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AiAssistantError(f"DeepSeek HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise AiAssistantError(f"无法连接 DeepSeek: {exc}") from exc

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AiAssistantError(f"DeepSeek 响应格式异常: {data}") from exc


_JSON_BLOCK = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def parse_ai_response(text: str) -> tuple[str, dict[str, Any]]:
    """解析 AI 回复，返回 (message, updates)。"""
    raw = text.strip()
    block = _JSON_BLOCK.search(raw)
    if block:
        raw = block.group(1).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AiAssistantError(f"AI 返回的不是有效 JSON:\n{raw[:500]}") from exc

    if not isinstance(data, dict):
        raise AiAssistantError("AI 返回的根节点必须是 JSON 对象")

    message = str(data.get("message") or "已更新")
    updates = data.get("updates") or {}
    if not isinstance(updates, dict):
        updates = {}
    return message, updates
