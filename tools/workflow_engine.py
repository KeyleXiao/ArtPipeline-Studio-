#!/usr/bin/env python3
"""ComfyUI 工作流 JSON 加载与占位符替换。"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from paths import WORKFLOWS_DIR

_PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def _coerce_numeric_strings(obj: Any) -> Any:
    """ComfyUI 部分节点需要 int/float，模板里可能是字符串。

    注意：节点连线格式为 [\"node_id\", slot]，node_id 必须保持字符串，不可转成 int。
    """
    if isinstance(obj, dict):
        return {k: _coerce_numeric_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        if len(obj) == 2 and isinstance(obj[0], str) and obj[0].isdigit():
            slot = obj[1]
            if isinstance(slot, str) and slot.isdigit():
                slot = int(slot)
            return [obj[0], slot]
        return [_coerce_numeric_strings(v) for v in obj]
    if isinstance(obj, str) and obj.isdigit():
        return int(obj)
    if isinstance(obj, str):
        try:
            if "." in obj:
                return float(obj)
        except ValueError:
            pass
    return obj


def _replace_in_obj(obj: Any, variables: dict[str, str]) -> Any:
    if isinstance(obj, dict):
        return {k: _replace_in_obj(v, variables) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_replace_in_obj(v, variables) for v in obj]
    if isinstance(obj, str):
        def repl(m: re.Match[str]) -> str:
            key = m.group(1)
            return variables.get(key, m.group(0))

        return _PLACEHOLDER.sub(repl, obj)
    return obj


def load_workflow_template(path: Path | str) -> dict:
    p = Path(path)
    if not p.is_absolute():
        p = WORKFLOWS_DIR / p
    if not p.is_file():
        raise FileNotFoundError(p)
    data = json.loads(p.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not str(k).startswith("_")}


def build_workflow(
    template: dict,
    *,
    positive: str,
    negative: str,
    width: int,
    height: int,
    seed: int,
    checkpoint: str,
    filename_prefix: str,
    steps: int = 35,
    cfg: float = 7.0,
    sampler: str = "euler_ancestral",
    scheduler: str = "normal",
    positive_g: str | None = None,
    positive_l: str | None = None,
    lora: str = "",
    lora_strength: float = 0.7,
    ref_image: str = "",
    denoise: float = 1.0,
) -> dict:
    pg = positive_g if positive_g is not None else positive
    pl = positive_l if positive_l is not None else positive
    variables = {
        "POSITIVE": positive,
        "POSITIVE_G": pg,
        "POSITIVE_L": pl,
        "NEGATIVE": negative,
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "SEED": str(seed),
        "CHECKPOINT": checkpoint,
        "LORA": lora,
        "LORA_STRENGTH": str(lora_strength),
        "FILENAME_PREFIX": filename_prefix,
        "STEPS": str(steps),
        "CFG": str(cfg),
        "SAMPLER": sampler,
        "SCHEDULER": scheduler,
        "REF_IMAGE": ref_image,
        "DENOISE": str(denoise),
    }
    wf = _replace_in_obj(copy.deepcopy(template), variables)
    return _coerce_numeric_strings(wf)


def validate_workflow_json(text: str) -> tuple[dict | None, str | None]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, "根节点必须是 JSON 对象"
    prompt_nodes = {k: v for k, v in data.items() if not str(k).startswith("_")}
    if not prompt_nodes:
        return None, "至少需要一个 ComfyUI 节点（键为节点 ID）"
    for node_id, node in prompt_nodes.items():
        if not isinstance(node, dict):
            return None, f"节点 {node_id} 必须是对象"
        if "class_type" not in node:
            return None, f"节点 {node_id} 缺少 class_type"
    return data, None
