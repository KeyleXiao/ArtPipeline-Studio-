#!/usr/bin/env python3
"""系统字体枚举与 PIL 字体解析（Web 安全：不依赖 Tkinter）。"""

from __future__ import annotations

import platform
import re
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

FALLBACK_FAMILIES = (
    "PingFang SC",
    "Heiti SC",
    "STHeiti",
    "Arial Unicode MS",
    "Arial",
    "Helvetica",
)

FONT_DIRS = (
    Path("/System/Library/Fonts"),
    Path("/System/Library/Fonts/Supplemental"),
    Path("/Library/Fonts"),
    Path.home() / "Library/Fonts",
)

_FONT_EXTS = {".ttf", ".ttc", ".otf", ".otc"}
_font_list_cache: list[str] | None = None

# macOS 常见字体族（无 Tk 时的补充）
_MACOS_COMMON = (
    "PingFang SC",
    "PingFang TC",
    "Heiti SC",
    "Heiti TC",
    "STHeiti",
    "Songti SC",
    "Kaiti SC",
    "Arial",
    "Arial Unicode MS",
    "Helvetica",
    "Helvetica Neue",
    "Times New Roman",
    "Menlo",
    "Monaco",
    "Courier New",
)


def _stem_to_family(stem: str) -> str:
    name = stem.replace("_", " ").replace("-", " ")
    name = re.sub(r"\s+(Regular|Bold|Italic|Medium|Light|Semibold|Heavy|Black)$", "", name, flags=re.I)
    return name.strip()


def _families_from_font_dirs() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for base in FONT_DIRS:
        if not base.is_dir():
            continue
        try:
            paths = list(base.rglob("*"))
        except OSError:
            continue
        for path in paths:
            if path.suffix.lower() not in _FONT_EXTS:
                continue
            family = _stem_to_family(path.stem)
            if not family or family.startswith("."):
                continue
            key = family.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(family)
    return sorted(out, key=str.lower)


def _families_from_system_profiler() -> list[str]:
    if platform.system() != "Darwin":
        return []
    try:
        proc = subprocess.run(
            ["system_profiler", "SPFontsDataType"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if not (lower.startswith("family:") or lower.startswith("fullname:")):
            continue
        _, _, val = stripped.partition(":")
        val = val.strip()
        if not val or val.startswith("."):
            continue
        key = val.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(val)
    return names


def list_system_fonts() -> list[str]:
    """返回可用字体族名（不创建 Tk 窗口，可在 FastAPI 工作线程调用）。"""
    global _font_list_cache
    if _font_list_cache is not None:
        return _font_list_cache

    preferred: list[str] = []
    rest: list[str] = []
    seen: set[str] = set()
    preferred_keys = {f.lower() for f in FALLBACK_FAMILIES}

    def add(name: str, *, force_preferred: bool = False) -> None:
        name = name.strip()
        if not name:
            return
        key = name.lower()
        if key in seen:
            return
        seen.add(key)
        if force_preferred or key in preferred_keys or any(
            p in name for p in ("PingFang", "Heiti", "Songti", "YaHei", "Arial")
        ):
            preferred.append(name)
        else:
            rest.append(name)

    for name in FALLBACK_FAMILIES:
        add(name, force_preferred=True)
    if platform.system() == "Darwin":
        for name in _MACOS_COMMON:
            add(name, force_preferred=True)
    for name in _families_from_system_profiler():
        add(name)
    for name in _families_from_font_dirs():
        add(name)

    _font_list_cache = preferred + rest or list(FALLBACK_FAMILIES)
    return _font_list_cache


def _scan_font_dirs(family: str) -> Path | None:
    family_lower = family.lower().replace(" ", "")
    candidates: list[Path] = []
    for base in FONT_DIRS:
        if not base.is_dir():
            continue
        try:
            paths = list(base.rglob("*"))
        except OSError:
            continue
        for path in paths:
            if path.suffix.lower() not in _FONT_EXTS:
                continue
            stem = path.stem.lower().replace(" ", "").replace("-", "")
            if family_lower in stem or stem in family_lower:
                candidates.append(path)
    if candidates:
        return sorted(candidates, key=lambda p: len(p.name))[0]
    return None


@lru_cache(maxsize=256)
def resolve_font_path(family: str) -> Path | None:
    family = family.strip()
    if not family:
        return None

    path = _scan_font_dirs(family)
    if path:
        return path

    if platform.system() == "Darwin":
        path = _macos_font_path_via_system_profiler(family)
        if path:
            return path

    for fallback in FALLBACK_FAMILIES:
        if fallback == family:
            continue
        path = _scan_font_dirs(fallback)
        if path:
            return path
    return None


def _macos_font_path_via_system_profiler(family: str) -> Path | None:
    try:
        out = subprocess.run(
            ["system_profiler", "SPFontsDataType"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    text = out.stdout
    family_lower = family.lower()
    current_path: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.endswith(":") and "path:" not in stripped.lower():
            current_path = None
            continue
        lower = stripped.lower()
        if "path:" in lower:
            _, _, path_part = stripped.partition(":")
            current_path = path_part.strip()
            continue
        if "fullname:" in lower or "family:" in lower:
            _, _, val = stripped.partition(":")
            if family_lower in val.strip().lower() and current_path:
                p = Path(current_path)
                if p.is_file():
                    return p
    return None


def load_pil_font(family: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    size = max(8, int(size))
    path = resolve_font_path(family)
    if path:
        try:
            return ImageFont.truetype(str(path), size=size)
        except OSError:
            pass
    try:
        return ImageFont.truetype("Arial.ttf", size=size)
    except OSError:
        return ImageFont.load_default()
