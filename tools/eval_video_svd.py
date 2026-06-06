#!/usr/bin/env python3
"""
SVD 图生视频 idle 微动评估。

流程:
  1. txt2img 生成 idle 定稿图 source_idle.png
  2. Stable Video Diffusion 图生短视频（低 motion_bucket，适合 UI 微动）
  3. 输出到 ArtPipeline/video_eval/

用法:
  python eval_video_svd.py
  python eval_video_svd.py --skip-source   # 已有 source_idle.png 时
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
ART_ROOT = TOOLS_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from comfyui_client import ComfyUiClient, ComfyUiError, check_connection
from workflow_engine import build_workflow, load_workflow_template

OUT_DIR = ART_ROOT / "video_eval"
SVD_CKPT = "svd.safetensors"
COMFY_OUTPUT = Path.home() / "comflowy/ComfyUI/output"

NEGATIVE = (
    "lowres, bad anatomy, bad hands, blurry, watermark, text, logo, "
    "deformed, ugly, gun, weapon, violence"
)

SOURCE_POSITIVE = (
    "masterpiece, best quality, very aesthetic, absurdres, "
    "1girl, solo, beautiful woman, mature female, upper body portrait, "
    "gentle smile, relaxed idle pose, looking at viewer, "
    "soft cinematic lighting, dark simple background, "
    "subtle hair movement, breathing, film still, highly detailed face"
)


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


def build_svd_workflow(
    *,
    init_image: str,
    width: int,
    height: int,
    frames: int,
    motion_bucket: int,
    fps: int,
    seed: int,
    steps: int,
) -> dict:
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": init_image}},
        "2": {
            "class_type": "ImageOnlyCheckpointLoader",
            "inputs": {"ckpt_name": SVD_CKPT},
        },
        "3": {
            "class_type": "SVD_img2vid_Conditioning",
            "inputs": {
                "clip_vision": ["2", 1],
                "init_image": ["1", 0],
                "vae": ["2", 2],
                "width": width,
                "height": height,
                "video_frames": frames,
                "motion_bucket_id": motion_bucket,
                "fps": fps,
                "augmentation_level": 0.02,
            },
        },
        "4": {
            "class_type": "VideoLinearCFGGuidance",
            "inputs": {"model": ["2", 0], "min_cfg": 1.0},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": 2.5,
                "sampler_name": "euler",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["3", 0],
                "negative": ["3", 1],
                "latent_image": ["3", 2],
            },
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["5", 0], "vae": ["2", 2]},
        },
        "7": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["6", 0],
                "frame_rate": float(fps),
                "loop_count": 0,
                "filename_prefix": "svd_idle_eval",
                "format": "image/webp",
                "pingpong": True,
                "save_output": True,
            },
        },
    }


def save_one_image(client: ComfyUiClient, history: dict, out_path: Path) -> bool:
    images = client.collect_output_images(history)
    if not images:
        return False
    meta = images[-1]
    data = client.download_image(
        meta["filename"],
        meta.get("subfolder") or "",
        meta.get("type") or "output",
    )
    out_path.write_bytes(data)
    return True


def collect_vhs_outputs(history: dict, out_dir: Path) -> list[Path]:
    """从 history 与 ComfyUI output 目录取 VHS 产物。"""
    saved: list[Path] = []
    outputs = history.get("outputs") or {}
    for node_out in outputs.values():
        for vid in node_out.get("gifs") or []:
            fn = vid.get("filename")
            sub = vid.get("subfolder") or ""
            typ = vid.get("type") or "output"
            if not fn:
                continue
            q = urllib.parse.urlencode({"filename": fn, "subfolder": sub, "type": typ})
            data = urllib.request.urlopen(f"http://127.0.0.1:8188/view?{q}").read()
            dest = out_dir / Path(fn).name
            dest.write_bytes(data)
            saved.append(dest)
        for img in node_out.get("images") or []:
            fn = img.get("filename")
            if not fn:
                continue
            src = COMFY_OUTPUT / fn
            if src.is_file():
                dest = out_dir / fn
                shutil.copy2(src, dest)
                saved.append(dest)
    # 兜底：按前缀搜 output 目录最新文件
    if not saved and COMFY_OUTPUT.is_dir():
        for p in sorted(COMFY_OUTPUT.glob("svd_idle_eval*"), key=lambda x: x.stat().st_mtime, reverse=True):
            dest = out_dir / p.name
            shutil.copy2(p, dest)
            saved.append(dest)
            if len(saved) >= 3:
                break
    return saved


def ensure_svd_model() -> Path:
    ckpt = Path.home() / "comflowy/ComfyUI/models/checkpoints" / SVD_CKPT
    if not ckpt.is_file() or ckpt.stat().st_size < 8_000_000_000:
        raise ComfyUiError(
            f"缺少 SVD 模型 {SVD_CKPT}（约 9GB）。"
            f"下载: hf-mirror.com/stabilityai/stable-video-diffusion-img2vid → checkpoints/"
        )
    return ckpt


def run(
    *,
    url: str,
    checkpoint: str,
    source_w: int,
    source_h: int,
    svd_w: int,
    svd_h: int,
    frames: int,
    motion_bucket: int,
    fps: int,
    steps_source: int,
    steps_svd: int,
    seed: int,
    skip_source: bool,
) -> int:
    out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    ok, msg = check_connection(url)
    if not ok:
        print(f"ComfyUI 不可用: {msg}", file=sys.stderr)
        return 1

    client = ComfyUiClient(url)
    info = client._get_json("/object_info")
    if "SVD_img2vid_Conditioning" not in info:
        print("ComfyUI 缺少 SVD 节点", file=sys.stderr)
        return 1
    if "VHS_VideoCombine" not in info:
        print("缺少 VideoHelperSuite，请确认 custom_nodes 已安装并重启 ComfyUI", file=sys.stderr)
        return 1

    report: list[str] = [
        f"SVD idle 微动评估 — {datetime.now().isoformat(timespec='seconds')}",
        f"输出: {out_dir}",
        "",
    ]

    source_path = out_dir / "source_idle.png"

    if not skip_source or not source_path.is_file():
        print("[1/2] 生成 idle 定稿图…")
        wf = txt2img_workflow(
            checkpoint=checkpoint,
            positive=SOURCE_POSITIVE,
            width=source_w,
            height=source_h,
            seed=seed,
            steps=steps_source,
            prefix="video_eval_source",
        )
        pid = client.queue_prompt(wf)
        hist = client.wait_prompt(pid, steps_hint=steps_source, timeout_s=900.0)
        if not save_one_image(client, hist, source_path):
            print("定稿图生成失败", file=sys.stderr)
            return 1
        print(f"  → {source_path}")
        report.append(f"source_idle.png OK ({source_w}x{source_h})")
    else:
        report.append("复用已有 source_idle.png")

    print("[2/2] SVD 图生视频（idle 微动）…")
    ensure_svd_model()
    ref_name = client.upload_image(source_path)
    wf = build_svd_workflow(
        init_image=ref_name,
        width=svd_w,
        height=svd_h,
        frames=frames,
        motion_bucket=motion_bucket,
        fps=fps,
        seed=seed + 1,
        steps=steps_svd,
    )
    t0 = time.time()
    try:
        pid = client.queue_prompt(wf)
        hist = client.wait_prompt(pid, steps_hint=steps_svd, timeout_s=3600.0)
    except ComfyUiError as exc:
        report.append(f"SVD FAIL: {exc}")
        (out_dir / "eval_report.txt").write_text("\n".join(report), encoding="utf-8")
        print(exc, file=sys.stderr)
        return 1

    entry = hist if "outputs" in hist else {}
    outputs = collect_vhs_outputs(entry, out_dir)

    # 另存逐帧 PNG 便于对比
    frame_dir = out_dir / "frames"
    frame_dir.mkdir(exist_ok=True)
    images = client.collect_output_images(entry)
    for i, meta in enumerate(sorted(images, key=lambda m: m.get("filename", ""))):
        data = client.download_image(
            meta["filename"],
            meta.get("subfolder") or "",
            meta.get("type") or "output",
        )
        fp = frame_dir / f"frame_{i:02d}.png"
        fp.write_bytes(data)
        outputs.append(fp)

    elapsed = time.time() - t0
    report.extend(
        [
            f"SVD: {svd_w}x{svd_h}, frames={frames}, motion_bucket={motion_bucket}, fps={fps}",
            f"耗时 {elapsed:.0f}s",
            "",
            "输出文件:",
            *[f"  - {p.name}" for p in outputs],
            "",
            "说明: motion_bucket 越低越接近静态；pingpong webp 适合 UI 循环预览。",
            "Unity 可用 VideoPlayer 播 webp/mp4，或继续用 frames/ 内 PNG。",
        ]
    )
    (out_dir / "eval_report.txt").write_text("\n".join(report), encoding="utf-8")
    meta = {
        "mode": "svd_idle",
        "motion_bucket": motion_bucket,
        "frames": frames,
        "fps": fps,
        "elapsed_s": round(elapsed, 1),
        "files": [p.name for p in outputs],
    }
    (out_dir / "eval_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n".join(report[-6:]))
    return 0 if outputs else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="SVD idle 微动视频评估")
    ap.add_argument("--url", default="http://127.0.0.1:8188")
    ap.add_argument("--checkpoint", default="animagineXL_v3.safetensors")
    ap.add_argument("--source-width", type=int, default=512)
    ap.add_argument("--source-height", type=int, default=768)
    ap.add_argument("--svd-width", type=int, default=576)
    ap.add_argument("--svd-height", type=int, default=1024)
    ap.add_argument("--frames", type=int, default=14)
    ap.add_argument("--motion-bucket", type=int, default=55, help="越低越微动，建议 40-80")
    ap.add_argument("--fps", type=int, default=8)
    ap.add_argument("--steps-source", type=int, default=28)
    ap.add_argument("--steps-svd", type=int, default=20)
    ap.add_argument("--seed", type=int, default=515151)
    ap.add_argument("--skip-source", action="store_true")
    args = ap.parse_args()
    return run(
        url=args.url,
        checkpoint=args.checkpoint,
        source_w=args.source_width,
        source_h=args.source_height,
        svd_w=args.svd_width,
        svd_h=args.svd_height,
        frames=max(4, min(args.frames, 25)),
        motion_bucket=max(1, min(args.motion_bucket, 255)),
        fps=args.fps,
        steps_source=args.steps_source,
        steps_svd=args.steps_svd,
        seed=args.seed,
        skip_source=args.skip_source,
    )


if __name__ == "__main__":
    raise SystemExit(main())
