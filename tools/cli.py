#!/usr/bin/env python3
"""ArtPipeline 命令行入口（无 GUI）。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from comfyui_client import check_connection  # noqa: E402
from config_manager import ConfigManager  # noqa: E402
from pipeline_core import PipelineCore  # noqa: E402

_KIND_MAP = {
    "role": "roles",
    "item": "items",
    "skill": "skills",
    "hp": "ui_status",
    "frame": "ui_frames",
    "button": "ui_buttons",
    "combat": "ui_combat",
    "bg": "backgrounds",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="ArtPipeline CLI · ComfyUI 批量生成/导出")
    parser.add_argument("--list", action="store_true", help="列出分类、资源与 ComfyUI 状态")
    parser.add_argument("--category", "-c", help="分类 ID（roles/items/skills/ui_status/ui_frames/…，见 --list）")
    parser.add_argument("--kind", choices=list(_KIND_MAP.keys()), help="旧参数别名")
    parser.add_argument("--file", help="单个文件名，如 role_warrior.png")
    parser.add_argument("--all", action="store_true", help="全部 enabled 资源")
    parser.add_argument("--generate", action="store_true", help="生成到 source（默认仅 --list 时不生成）")
    parser.add_argument("--to-inbox", action="store_true", help="生成后复制到 inbox")
    parser.add_argument("--deploy", action="store_true", help="从 inbox 导出到 Unity")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    mgr = ConfigManager()
    core = PipelineCore(mgr)

    if args.list:
        ok, msg = check_connection(mgr.defaults.get("comfyui_url", ""))
        print("ComfyUI:", "OK" if ok else "FAIL", msg)
        print(f"项目根: {mgr.project_root()}")
        print(f"ArtPipeline 根: {mgr.art_root()}")
        print("\n分类:")
        for cat in mgr.categories():
            print(f"  [{cat.id}] {cat.label}")
            print(f"    source → {cat.source}")
            print(f"    inbox  → {cat.inbox}")
            print(f"    unity  → {cat.unity}")
        print("\n资源:")
        for a in mgr.assets():
            print(f"  [{a.category}] {a.filename} {a.size_label()}px {'✓' if a.enabled else '(disabled)'}")
        return 0

    assets = mgr.assets(enabled_only=True)
    if args.file:
        a = mgr.asset_by_filename(args.file)
        assets = [a] if a else []
        if not assets:
            print(f"未找到: {args.file}", file=sys.stderr)
            return 1
    elif args.category:
        assets = mgr.assets(category=args.category, enabled_only=True)
    elif args.kind:
        assets = mgr.assets(category=_KIND_MAP.get(args.kind, args.kind), enabled_only=True)
    elif not args.all: 
        parser.print_help()
        return 1

    if args.generate or args.to_inbox or args.deploy:
        if args.generate or args.to_inbox:
            for a in assets:
                core.generate_one(a, seed=args.seed, to_inbox=True)

        if args.deploy:
            core.export_many(assets)
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
