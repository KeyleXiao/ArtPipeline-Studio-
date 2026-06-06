#!/usr/bin/env python3
"""
ComfyUI 序列帧能力评估（本地一次性测试）。

当前环境若无 AnimateDiff，则用「首帧 txt2img + 链式 img2img」模拟短动作序列，
输出逐帧 PNG 与 eval_report.txt，便于人工判断能否用于 idle/微动。

用法（在 ArtPipeline/tools 下）:
  python eval_sequence_frames.py
  python eval_sequence_frames.py --frames 6 --width 512 --height 768
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
ART_ROOT = TOOLS_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from comfyui_client import ComfyUiClient, ComfyUiError, check_connection
from workflow_engine import build_workflow, load_workflow_template

DEFAULT_OUT = ART_ROOT / "seq_frame_eval"
DEFAULT_OUT_AD = ART_ROOT / "seq_frame_eval_ad"

NEGATIVE = (
    "lowres, bad anatomy, bad hands, extra fingers, missing fingers, "
    "blurry, watermark, text, logo, deformed, ugly, duplicate, "
    "multiple guns, broken gun"
)

BASE_POSITIVE = (
    "masterpiece, best quality, very aesthetic, absurdres, "
    "1girl, solo, beautiful woman, mature female, "
    "holding silver revolver with both hands, pointing revolver directly at viewer, "
    "break the fourth wall, intense eye contact, dramatic cinematic lighting, "
    "upper body, dark background, film still, highly detailed face and hands, "
    "realistic gun metal texture"
)

# 链式 img2img：每帧在上一帧基础上推进动作（非 AnimateDiff，仅评估连贯性上限）
FRAME_STAGES = [
    "aiming steady, finger near trigger, tense expression",
    "finger on trigger, slight squint, anticipation",
    "firing moment, bright muzzle flash at barrel, smoke puff, sharp recoil start",
    "strong recoil, arms pushed back, eyes widened, muzzle flash peak",
    "after shot, smoke from barrel, slight motion blur on gun, recovering posture",
    "gun lowering slightly, smoke dissipating, breathing out",
    "returning to aim, residual smoke, focused expression",
    "steady aim again, faint smoke trail, dramatic rim light",
]


def probe_capabilities(client: ComfyUiClient) -> dict:
    info = client._get_json("/object_info")
    keys = set(info.keys())
    ad_nodes = [k for k in keys if k.startswith("ADE_")]
    return {
        "animatediff_nodes": ad_nodes,
        "animatediff_ready": "ADE_LoadAnimateDiffModel" in keys and "ADE_UseEvolvedSampling" in keys,
        "save_animated_webp": "SaveAnimatedWEBP" in keys,
        "save_video": "SaveVideo" in keys,
        "svd_conditioning": "SVD_img2vid_Conditioning" in keys,
    }


def txt2img_workflow(
    *,
    checkpoint: str,
    positive: str,
    width: int,
    height: int,
    seed: int,
    steps: int,
    prefix: str,
) -> dict:
    tpl = load_workflow_template("_default_sdxl_api.json")
    return build_workflow(
        tpl,
        positive=positive,
        negative=NEGATIVE,
        width=width,
        height=height,
        seed=seed,
        checkpoint=checkpoint,
        filename_prefix=prefix,
        steps=steps,
        cfg=7.0,
        sampler="euler_ancestral",
        scheduler="normal",
    )


def img2img_workflow(
    *,
    checkpoint: str,
    positive: str,
    ref_name: str,
    width: int,
    height: int,
    seed: int,
    steps: int,
    denoise: float,
    prefix: str,
) -> dict:
    tpl = load_workflow_template("_default_sdxl_img2img_api.json")
    return build_workflow(
        tpl,
        positive=positive,
        negative=NEGATIVE,
        width=width,
        height=height,
        seed=seed,
        checkpoint=checkpoint,
        filename_prefix=prefix,
        steps=steps,
        cfg=7.0,
        sampler="euler_ancestral",
        scheduler="normal",
        ref_image=ref_name,
        denoise=denoise,
    )


def save_outputs(client: ComfyUiClient, history: dict, out_dir: Path, frame_tag: str) -> Path | None:
    images = client.collect_output_images(history)
    if not images:
        return None
    meta = images[-1]
    data = client.download_image(
        meta["filename"],
        meta.get("subfolder") or "",
        meta.get("type") or "output",
    )
    out_path = out_dir / f"{frame_tag}.png"
    out_path.write_bytes(data)
    return out_path


def build_animatediff_workflow(
    *,
    checkpoint: str,
    positive: str,
    width: int,
    height: int,
    seed: int,
    steps: int,
    frames: int,
    prefix: str,
    motion_model: str = "mm_sdxl_v10_beta.ckpt",
) -> dict:
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint},
        },
        "2": {
            "class_type": "ADE_LoadAnimateDiffModel",
            "inputs": {"model_name": motion_model},
        },
        "3": {
            "class_type": "ADE_ApplyAnimateDiffModelSimple",
            "inputs": {"motion_model": ["2", 0]},
        },
        "4": {
            "class_type": "ADE_UseEvolvedSampling",
            "inputs": {
                "model": ["1", 0],
                "beta_schedule": "linear (AnimateDiff-SDXL)",
                "m_models": ["3", 0],
            },
        },
        "5": {
            "class_type": "CLIPTextEncodeSDXL",
            "inputs": {
                "clip": ["1", 1],
                "width": width,
                "height": height,
                "crop_w": 0,
                "crop_h": 0,
                "target_width": width,
                "target_height": height,
                "text_g": positive,
                "text_l": positive,
            },
        },
        "6": {
            "class_type": "CLIPTextEncodeSDXL",
            "inputs": {
                "clip": ["1", 1],
                "width": width,
                "height": height,
                "crop_w": 0,
                "crop_h": 0,
                "target_width": width,
                "target_height": height,
                "text_g": NEGATIVE,
                "text_l": NEGATIVE,
            },
        },
        "7": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": frames},
        },
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": 7.0,
                "sampler_name": "euler_ancestral",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["5", 0],
                "negative": ["6", 0],
                "latent_image": ["7", 0],
            },
        },
        "9": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["8", 0], "vae": ["1", 2]},
        },
        "10": {
            "class_type": "SaveImage",
            "inputs": {"images": ["9", 0], "filename_prefix": prefix},
        },
    }


def save_all_frame_outputs(client: ComfyUiClient, history: dict, out_dir: Path) -> list[Path]:
    images = client.collect_output_images(history)
    if not images:
        return []
    images = sorted(images, key=lambda m: m.get("filename", ""))
    saved: list[Path] = []
    for i, meta in enumerate(images):
        data = client.download_image(
            meta["filename"],
            meta.get("subfolder") or "",
            meta.get("type") or "output",
        )
        out_path = out_dir / f"frame_{i:02d}.png"
        out_path.write_bytes(data)
        saved.append(out_path)
    return saved


def run_animatediff(
    *,
    out_dir: Path,
    checkpoint: str,
    width: int,
    height: int,
    frames: int,
    steps: int,
    seed: int,
    url: str,
) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_lines: list[str] = []
    report_lines.append(f"AnimateDiff 序列评估 — {datetime.now().isoformat(timespec='seconds')}")
    report_lines.append(f"输出目录: {out_dir}")

    ok, msg = check_connection(url)
    if not ok:
        print(f"ComfyUI 不可用: {msg}", file=sys.stderr)
        return 1
    report_lines.append(f"ComfyUI: {msg}")

    client = ComfyUiClient(url)
    caps = probe_capabilities(client)
    if not caps.get("animatediff_ready"):
        report_lines.append("FAIL: 未检测到 AnimateDiff 节点，请先安装 ComfyUI-AnimateDiff-Evolved 并重启 ComfyUI")
        (out_dir / "eval_report.txt").write_text("\n".join(report_lines), encoding="utf-8")
        print(report_lines[-1], file=sys.stderr)
        return 1

    positive = f"{BASE_POSITIVE}, firing revolver at viewer, muzzle flash, dynamic motion, cinematic action"
    report_lines.append(f"Motion: mm_sdxl_v10_beta.ckpt · beta=linear (AnimateDiff-SDXL)")
    report_lines.append(f"尺寸: {width}x{height}, 帧数={frames}, steps={steps}, seed={seed}")
    report_lines.append("")

    print(f"AnimateDiff 生成 {frames} 帧…（单次采样，约需数分钟）")
    t0 = time.time()
    wf = build_animatediff_workflow(
        checkpoint=checkpoint,
        positive=positive,
        width=width,
        height=height,
        seed=seed,
        steps=steps,
        frames=frames,
        prefix="seq_ad_eval",
    )
    try:
        pid = client.queue_prompt(wf)
        hist = client.wait_prompt(pid, steps_hint=steps, timeout_s=3600.0)
    except ComfyUiError as exc:
        report_lines.append(f"FAIL: {exc}")
        (out_dir / "eval_report.txt").write_text("\n".join(report_lines), encoding="utf-8")
        print(exc, file=sys.stderr)
        return 1

    saved = save_all_frame_outputs(client, hist, out_dir)
    elapsed = time.time() - t0
    for p in saved:
        report_lines.append(f"OK → {p.name}")
        print(f"  → {p}")

    report_lines.append("")
    report_lines.append(f"完成 {len(saved)}/{frames} 帧, 耗时 {elapsed:.0f}s")
    report_lines.append("")
    report_lines.append("=== AnimateDiff 评估 ===")
    report_lines.append("1. 帧间由 motion module 约束，通常比链式 img2img 更连贯。")
    report_lines.append("2. SDXL motion 仍为 beta；大动作（开枪）可能模糊或鬼影，idle 微动更合适。")
    report_lines.append("3. 查看 preview_loop.webp / contact_sheet.png 对比连贯性与画质。")

    meta = {
        "mode": "animatediff",
        "checkpoint": checkpoint,
        "motion_model": "mm_sdxl_v10_beta.ckpt",
        "width": width,
        "height": height,
        "frames": frames,
        "frames_saved": len(saved),
        "elapsed_s": round(elapsed, 1),
        "capabilities": caps,
        "files": [p.name for p in saved],
    }
    (out_dir / "eval_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "eval_report.txt").write_text("\n".join(report_lines), encoding="utf-8")

    if saved:
        try:
            from PIL import Image

            imgs = [Image.open(p).convert("RGBA") for p in saved]
            w, h = imgs[0].size
            sheet = Image.new("RGBA", (w * len(imgs), h), (0, 0, 0, 0))
            for i, im in enumerate(imgs):
                sheet.paste(im, (i * w, 0))
            sheet.save(out_dir / "contact_sheet.png")
            imgs[0].save(
                out_dir / "preview_loop.webp",
                save_all=True,
                append_images=imgs[1:],
                duration=100,
                loop=0,
            )
        except ImportError:
            pass

    print(f"\n报告: {out_dir / 'eval_report.txt'}")
    return 0 if len(saved) >= max(2, frames // 2) else 1


def run_eval(
    *,
    out_dir: Path,
    checkpoint: str,
    width: int,
    height: int,
    frames: int,
    steps: int,
    seed: int,
    denoise: float,
    url: str,
) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_lines: list[str] = []
    report_lines.append(f"ComfyUI 序列帧评估 — {datetime.now().isoformat(timespec='seconds')}")
    report_lines.append(f"输出目录: {out_dir}")
    report_lines.append("")

    ok, msg = check_connection(url)
    if not ok:
        print(f"ComfyUI 不可用: {msg}", file=sys.stderr)
        return 1
    report_lines.append(f"ComfyUI: {msg}")

    client = ComfyUiClient(url)
    caps = probe_capabilities(client)
    report_lines.append(f"AnimateDiff 节点数: {len(caps['animatediff_nodes'])}")
    report_lines.append(f"SaveAnimatedWEBP: {caps['save_animated_webp']}")
    report_lines.append(f"SVD_img2vid: {caps['svd_conditioning']}")
    report_lines.append("")

    ckpts = client.list_checkpoints()
    if checkpoint not in ckpts:
        report_lines.append(f"警告: checkpoint 不在列表中，仍尝试: {checkpoint}")
        if ckpts:
            report_lines.append(f"可用: {', '.join(ckpts[:8])}...")

    if caps["animatediff_nodes"]:
        report_lines.append("检测到 AnimateDiff，本脚本仍使用链式 img2img 作对照（可后续扩展 AD 分支）。")
    else:
        report_lines.append(
            "未安装 AnimateDiff — 本次为「首帧 txt2img + 链式 img2img」伪序列。"
            "结论仅供参考：真实序列帧动画需安装 ComfyUI-AnimateDiff-Evolved + motion 模型。"
        )
    report_lines.append("")
    report_lines.append(f"测试主题: 美女持左轮指向镜头开枪")
    report_lines.append(f"尺寸: {width}x{height}, steps={steps}, seed={seed}, img2img denoise={denoise}")
    report_lines.append(f"计划帧数: {frames}")
    report_lines.append("")

    stages = FRAME_STAGES[: max(0, frames - 1)]
    saved: list[Path] = []
    t0 = time.time()

    # Frame 0: txt2img
    print("[0] txt2img 首帧…")
    wf0 = txt2img_workflow(
        checkpoint=checkpoint,
        positive=f"{BASE_POSITIVE}, {FRAME_STAGES[0]}",
        width=width,
        height=height,
        seed=seed,
        steps=steps,
        prefix="seq_eval_00",
    )
    pid = client.queue_prompt(wf0)
    hist = client.wait_prompt(pid, steps_hint=steps, timeout_s=900.0)
    p0 = save_outputs(client, hist, out_dir, "frame_00")
    if not p0:
        report_lines.append("FAIL: 首帧无输出")
        (out_dir / "eval_report.txt").write_text("\n".join(report_lines), encoding="utf-8")
        print("首帧生成失败", file=sys.stderr)
        return 1
    saved.append(p0)
    report_lines.append(f"frame_00 OK → {p0.name}")
    print(f"  → {p0}")

    prev = p0
    for i, stage in enumerate(stages, start=1):
        tag = f"frame_{i:02d}"
        print(f"[{i}] img2img {stage[:40]}…")
        ref_name = client.upload_image(prev)
        positive = f"{BASE_POSITIVE}, {stage}"
        wf = img2img_workflow(
            checkpoint=checkpoint,
            positive=positive,
            ref_name=ref_name,
            width=width,
            height=height,
            seed=seed + i,
            steps=steps,
            denoise=denoise,
            prefix=f"seq_eval_{i:02d}",
        )
        pid = client.queue_prompt(wf)
        hist = client.wait_prompt(pid, steps_hint=steps, timeout_s=900.0)
        pi = save_outputs(client, hist, out_dir, tag)
        if not pi:
            report_lines.append(f"FAIL: {tag} 无输出")
            break
        saved.append(pi)
        prev = pi
        report_lines.append(f"{tag} OK → {pi.name} (denoise={denoise})")
        print(f"  → {pi}")

    elapsed = time.time() - t0
    report_lines.append("")
    report_lines.append(f"完成 {len(saved)}/{frames} 帧, 耗时 {elapsed:.0f}s")
    report_lines.append("")
    report_lines.append("=== 评估结论（请肉眼查看 PNG） ===")
    report_lines.append("1. 若无 AnimateDiff：帧间连贯性依赖 img2img 链，人物/枪型易漂移，难作游戏序列。")
    report_lines.append("2. 单帧画质取决于 checkpoint；animagineXL 偏二次元，majicmix 偏写实。")
    report_lines.append("3. 若要做 idle 微动：8 帧 AnimateDiff 循环通常优于链式 img2img。")
    report_lines.append("4. 开枪/大动作：ControlNet + 分 keyframe 比纯 AI 序列更可控。")

    meta = {
        "checkpoint": checkpoint,
        "width": width,
        "height": height,
        "frames_requested": frames,
        "frames_saved": len(saved),
        "elapsed_s": round(elapsed, 1),
        "capabilities": caps,
        "files": [p.name for p in saved],
    }
    (out_dir / "eval_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "eval_report.txt").write_text("\n".join(report_lines), encoding="utf-8")
    print("\n" + "\n".join(report_lines[-8:]))
    print(f"\n报告: {out_dir / 'eval_report.txt'}")
    return 0 if saved else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="ComfyUI 序列帧能力评估")
    ap.add_argument(
        "--mode",
        choices=("chain", "animatediff"),
        default="animatediff",
        help="chain=链式 img2img; animatediff=AnimateDiff 一次出序列",
    )
    ap.add_argument("--out", type=Path, default=None, help="输出目录")
    ap.add_argument("--url", default="http://127.0.0.1:8188")
    ap.add_argument("--checkpoint", default="animagineXL_v3.safetensors")
    ap.add_argument("--width", type=int, default=512)
    ap.add_argument("--height", type=int, default=768)
    ap.add_argument("--frames", type=int, default=16)
    ap.add_argument("--steps", type=int, default=28)
    ap.add_argument("--seed", type=int, default=424242)
    ap.add_argument("--denoise", type=float, default=0.58)
    args = ap.parse_args()
    out = args.out
    if out is None:
        out = DEFAULT_OUT_AD if args.mode == "animatediff" else DEFAULT_OUT
    out = out.resolve()
    frames = max(2, min(args.frames, 24))
    if args.mode == "animatediff":
        return run_animatediff(
            out_dir=out,
            checkpoint=args.checkpoint,
            width=args.width,
            height=args.height,
            frames=frames,
            steps=args.steps,
            seed=args.seed,
            url=args.url,
        )
    return run_eval(
        out_dir=args.out.resolve(),
        checkpoint=args.checkpoint,
        width=args.width,
        height=args.height,
        frames=max(2, min(args.frames, 12)),
        steps=args.steps,
        seed=args.seed,
        denoise=max(0.35, min(0.85, args.denoise)),
        url=args.url,
    )


if __name__ == "__main__":
    raise SystemExit(main())
