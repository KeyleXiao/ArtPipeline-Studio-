#!/usr/bin/env python3
"""Provider 工厂。"""

from __future__ import annotations

from cloud.base import CloudProvider
from cloud.providers.dashscope import DashScopeProvider
from cloud.providers.stability import StabilityProvider
from cloud.providers.tencent import TencentProvider
from cloud.providers.volcengine import VolcengineProvider

_PROVIDERS: dict[str, CloudProvider] = {
    "dashscope": DashScopeProvider(),
    "stability": StabilityProvider(),
    "tencent": TencentProvider(),
    "volcengine": VolcengineProvider(),
}


def get_cloud_provider(provider_id: str) -> CloudProvider:
    p = _PROVIDERS.get(provider_id)
    if not p:
        raise ValueError(f"未知云 provider: {provider_id}")
    return p
