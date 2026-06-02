#!/usr/bin/env python3
"""共享依赖：接入 ArtPipeline/tools 现有模块。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from backend.runtime_paths import setup_paths

ARTAPP_ROOT, ART_PIPELINE_ROOT, TOOLS_DIR = setup_paths()

from config_manager import ConfigManager  # noqa: E402


@lru_cache(maxsize=1)
def get_config_manager() -> ConfigManager:
    return ConfigManager()


def reload_config_manager() -> ConfigManager:
    get_config_manager.cache_clear()
    return get_config_manager()


def sync_log_bus_from_config() -> None:
    from backend.services.log_bus import log_bus

    log_bus.configure(get_config_manager().log_dir())
