#!/usr/bin/env python3
"""云模型注册表加载与 checkpoint 识别。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

REGISTRY_FILE = Path(__file__).resolve().parent / "registry.json"

CLOUD_GEN_MODE_TEXT = "text_to_image"
CLOUD_GEN_MODE_I2I = "image_to_image"
CLOUD_GEN_MODE_EDIT = "image_edit"
CLOUD_GEN_MODES = frozenset({CLOUD_GEN_MODE_TEXT, CLOUD_GEN_MODE_I2I, CLOUD_GEN_MODE_EDIT})

DEFAULT_CLOUD_STRENGTH = 0.65


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    return data


def is_cloud_checkpoint(value: str) -> bool:
    return str(value or "").strip().startswith("cloud:")


def list_cloud_models() -> list[dict[str, Any]]:
    reg = load_registry()
    providers = reg.get("providers") or {}
    out: list[dict[str, Any]] = []
    for m in reg.get("models") or []:
        pid = str(m.get("provider", ""))
        prov = providers.get(pid) or {}
        out.append(
            {
                "id": m["id"],
                "label_zh": m.get("label_zh", m["id"]),
                "label_en": m.get("label_en", m["id"]),
                "summary_zh": m.get("summary_zh", ""),
                "summary_en": m.get("summary_en", ""),
                "provider": pid,
                "provider_label_zh": prov.get("label_zh", pid),
                "provider_label_en": prov.get("label_en", pid),
                "region": prov.get("region", ""),
                "modes": list((m.get("modes") or {}).keys()),
            }
        )
    return out


def cloud_gen_modes() -> dict[str, Any]:
    return dict(load_registry().get("gen_modes") or {})


def get_model(checkpoint: str) -> dict[str, Any] | None:
    ck = str(checkpoint or "").strip()
    for m in load_registry().get("models") or []:
        if m.get("id") == ck:
            return m
    return None


def provider_for_checkpoint(checkpoint: str) -> str:
    m = get_model(checkpoint)
    return str(m.get("provider", "")) if m else ""


def provider_meta(provider_id: str) -> dict[str, Any]:
    return dict((load_registry().get("providers") or {}).get(provider_id) or {})


def max_parallel_for_provider(provider_id: str, global_max: int) -> int:
    prov = provider_meta(provider_id)
    cap = int(prov.get("default_max_parallel") or global_max or 3)
    return max(1, min(global_max or cap, cap))


def effective_cloud_gen_mode(asset: Any) -> str:
    mode = str(getattr(asset, "cloud_gen_mode", "") or CLOUD_GEN_MODE_TEXT).strip()
    return mode if mode in CLOUD_GEN_MODES else CLOUD_GEN_MODE_TEXT


def parse_cloud_gen_mode(raw: str | None) -> str:
    mode = str(raw or CLOUD_GEN_MODE_TEXT).strip()
    return mode if mode in CLOUD_GEN_MODES else CLOUD_GEN_MODE_TEXT
