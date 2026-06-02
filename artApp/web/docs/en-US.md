# ArtPipeline Studio User Guide

> Online docs: <https://art.vrast.cn> (when deployed)

## Introduction

ArtPipeline Studio is a web-based art pipeline for game assets. It connects **ComfyUI generation → source originals → inbox editing → game engine export**. Features include batch generation, layer post-processing, AI prompt assistant, and configuration management.

## Work Environment

### Requirements

| Component | Description |
|-----------|-------------|
| **ComfyUI** | Local or LAN Stable Diffusion service; the tool submits workflows via HTTP |
| **ArtPipeline folder** | Holds source/inbox, workflow JSON, post-process overlays, and config |
| **Game engine project** | Usually Unity; export target is set under **Settings** |

### Recommended layout

```
ArtPipeline/
├── source/          # ComfyUI output (read-only for post-process)
├── inbox/           # Working copies and composited output
├── workflows/       # Per-asset workflow JSON
└── postprocess/     # Frames, backgrounds, overlays

YourGame/
└── Assets/...       # Final paths inside the engine project
```

### Starting the web app

```bash
cd ArtPipeline/artApp
python run_dev.py
```

Open the URL shown in the terminal (default `http://127.0.0.1:8765`).

## Features

### Asset pipeline

1. **Generate**: ComfyUI writes to **source**
2. **Post-process** (optional): Layers, crop, text on **inbox**; **source is never modified**
3. **Export to engine**: Copy inbox files into the engine project

**S·in·U** status chips:

- **S (source)**: green = exists, gray = not generated
- **in (inbox)**: green = matches source, yellow = post-processed, red = missing
- **U (engine)**: green = matches inbox, red = missing or needs re-export

### Main UI actions

| Action | Description |
|--------|-------------|
| Generate Selected / Category | Run ComfyUI for selected or all enabled assets in category |
| Generate & Export | Generate then export to engine |
| Export to Engine | Copy inbox → engine only (no regeneration) |
| Export Category | Export all assets in current category |
| Post-process… | Open layer editor on inbox |

Preview shows **post-process composite** when configured; otherwise the inbox/source image. Switch source / inbox / engine to inspect each stage.

### AI assistant

Modes: write prompts, refine, workflow, free chat. Configure DeepSeek API Key in **Settings**. AI uses asset category, size, and existing prompts; some modes write back to config.

### Checkpoint configuration

Models are configured at **category → asset** level. **Settings** only needs **ComfyUI URL** to list checkpoints:

| Location | Purpose | When empty |
|----------|---------|------------|
| **Category** | Default checkpoint for assets in category | Not set — generation will prompt you |
| **Basic info** | Per-asset override | Inherit from category |
| **Settings** | ComfyUI URL, sampler params, etc. | — |

When creating a category, pick a checkpoint. If ComfyUI is offline, type a known model filename.

### Post-process editor

- Subject layer `$asset` binds to **inbox** only
- **Restore from source**: overwrite inbox and reset layers
- **Apply to inbox**: composite and save
- **Export to engine**: save, export, return to main UI

## Best Practices

### 1. Keep source pristine

source is the AI “master”. Post-process only on **inbox**. Use **Restore from source** to start over.

### 2. Organize by category

Each category has its own paths, checkpoint, and shared prompt prefixes. Use separate categories for items, skills, avatars, etc. Override checkpoint per asset under **Basic info** when needed.

### 3. Pre-flight checks

- ComfyUI pill shows **online**
- **Category or asset has a checkpoint configured**
- Assets enabled and workflow JSON valid
- Prompts and dimensions match category rules

### 4. Suggested batch workflow

1. Set category prompts + per-asset subject
2. **Generate Category** → verify S / in status
3. **Post-process** assets that need polish
4. **Export Category** or **Generate & Export**
5. Refresh assets in the engine project

### 5. Version control & teamwork

- Use **Save Config** regularly
- Prefer paths relative to project root
- Backup ArtPipeline config and inbox before large changes

### 6. Troubleshooting

| Issue | Fix |
|-------|-----|
| Empty preview | Ensure source/inbox exists; refresh status |
| Engine out of date (red U) | Re-export after inbox/post-process changes |
| ComfyUI offline | Check URL, firewall, ComfyUI process |
| No checkpoint configured | Set model under **Category**, or per asset under **Basic info** |
| Export 405 | Restart `run_dev.py` |

---

See project maintenance docs and team wiki for updates.
