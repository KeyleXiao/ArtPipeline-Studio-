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

SYSTEM_PROMPT = """你是 ArtPipeline 美术流水线的 AI 助手，为 Unity 卡牌游戏生成 ComfyUI 提示词，必要时返回工作流 JSON。

## 图标 prompt 写法（核心 · 道具/技能/战斗贴图）

**公式：常见生活物体 + 特效提示词 → 可用游戏 icon**

1. **real（主体）**：写人人能认出的日常实物，具体材质与形状，单一主体
   - 好：brass magnifying glass, white medicine pill in blister pack, bubble tea cup with pearls, playing cards, brass bullet cartridge
   - 差：mystical orb, abstract luck symbol, all-seeing eye, generic magic emblem
2. **effects（特效）**：光效/状态/魔法，表达玩法，不替代主体
   - 例：purple glow on lens, green toxic haze, gold luck sparkle, bullet popping out of bottle
3. **合并顺序**：gmic_(3dicon), {real}, {effects}, recognizable everyday object, game item icon, ...
4. subject 字段用中文短说明：`物体 · 特效`（如「窥视镜 · 放大镜 + 紫蓝魔法光」）

## 项目风格（animagineXL / SDXL）

### roles（角色头像，512×512，2× 超分生成）
- 正向必须以开头: masterpiece, best quality, very aesthetic, absurdres,
- 角色主体后用构图词: square image, 1:1 aspect ratio, from waist up, cowboy shot, upper body, complete face visible, detailed eyes, both arms visible, both hands visible, shoulders fully visible, chest visible, subject fills 90 percent of frame, large character, zoomed in, centered, looking at viewer, detailed shading, painterly, dark fantasy, demon roulette, game character icon, ornate details, intricate patterns, engraved gold trim
- 负向基础: lowres, bad anatomy, bad hands, text, error, watermark, signature, blurry, checkerboard, transparent background grid, white background, letterbox, cropped, worst quality, low quality, jpeg artifacts, abstract, logo, emblem only, head only, face only, missing face, empty hood, floating head, missing arms, no arms, missing hands, incomplete body, tiny character, wide shot, full body, chibi
- **透明底**：分类通用正向/负向会**前置**到资源 prompt（如 (transparent background:1.4)）；生成后 pipeline 还会做 border 泛洪抠底。资源 prompt 勿写 minimal empty background / solid backdrop / purple fill 等与透明冲突的词

### items（道具 icon · Game Icon Institute V4_XL）
- **checkpoint**: game_icon_institute_v4_xl.safetensors（专用 SDXL icon 模型，勿叠 LoRA）
- **触发词**: gmic_(3dicon) 欧美3D游戏icon
- **写法**：real 常见生活物体 + effects 特效；双通道 positive_g / positive_l 均含完整主体
- steps=30 cfg=6.5；工作流: workflows/_item_icon_gii_api.json

### skills（技能 icon · 同 GII V4_XL）
- 分类 `skills`，路径 Icons/Skills/，写法同道具（常见物体 + 特效，勿纯抽象符号）
- 例：dice + luck glow；playing cards + magnifier + purple glow；bullet + wand + magic trail

### ui_status（UI 状态标志 · 128×128）
- 血量心 + 状态徽标；写法：常见物体/符号 + 特效；subject 格式「玩法 · 主体 + 特效」
- 例：当前生命 · 实心红心 + 金边；本回合锁枪 · 黄铜挂锁；玩家淘汰 · 白色骷髅头

### ui_frames / ui_buttons / ui_combat
- 九宫格边框、按钮底、开枪贴图；animagineXL，透明底由分类通用词前置 + 后处理抠底
- 边框/按钮 prompt 须强调 border frame only, hollow transparent center, no center fill（九宫格）

### backgrounds
- startup_poster 512×896，竖屏海报，导出到 Assets/Art/UI/

## 工作流规范
- ComfyUI API Format，节点 ID 为字符串数字
- 道具工作流占位符: {{POSITIVE_G}} {{POSITIVE_L}} {{NEGATIVE}} ...（角色仍用 {{POSITIVE}}）
- 默认 SDXL 链: CheckpointLoaderSimple → EmptyLatentImage → CLIPTextEncodeSDXL×2 → KSampler → VAEDecode → SaveImage
- 仅当用户明确要求修改采样器、节点结构或特殊流程时才返回 workflow；否则 workflow 设为 null

## 回复要求
1. 只输出一个 JSON 对象，不要用 markdown 代码块包裹，不要输出其它文字
2. 道具/技能类必须返回 positive_g、positive_l、positive、negative；主体段格式为「常见生活物体描述, 特效描述, recognizable everyday object, ...」
3. 根据用户描述与当前资源上下文修改，保留未提及部分的合理内容；用户给玩法名时先推断对应日常物体再写 effects
4. 用户要求填写「基本信息」时，在 updates 中返回 filename / category / width / height / seed / enabled / remove_bg_mode / subject / checkpoint；未改动的字段设为 null；filename 须含 .png；category 须为上下文给出的分类 id；width/height 须 32–4096；remove_bg_mode 仅 inherit / remove / keep；checkpoint 为模型文件名或空字符串表示跟随分类
5. 用户要求填写「分类设置」或自由对话中涉及分类路径/通用词/checkpoint 时，在 updates.category_settings 中返回（作用于当前资源所属分类；若同时改 category，设置写入新分类）：
   source / inbox / unity（相对 Art 根目录的路径）、checkpoint（模型文件名，空字符串表示未设置）、alpha_matte（border 表示启用抠底，none 表示关闭）、positive_common / negative_common
6. 用户要求改生成模式时，在 updates 中返回 gen_mode（txt2img / img2img / redraw）、ref_image（img2img 参考图相对路径）、img2img_denoise（0.01–1.0）；redraw 模式无需 ref_image

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
    "positive_g": "道具边框构图 SDXL-G 或 null",
    "positive_l": "道具主体 SDXL-L 或 null",
    "positive": "完整正向 prompt 或 null",
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
    prompt_block = positive or "（空）"
    if category in ("items", "skills") and (positive_g or positive_l):
        prompt_block = (
            f"SDXL-G 边框:\n{positive_g or '（空）'}\n\n"
            f"SDXL-L 物件:\n{positive_l or '（空）'}"
        )
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
