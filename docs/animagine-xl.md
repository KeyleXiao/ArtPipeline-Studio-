# animagineXL v3 · 本项目生图约定

推荐用 **animagineXL_v3.safetensors** 作为角色与道具的主 checkpoint（ComfyUI `CheckpointLoaderSimple`）。

## 通用正向标签（可前缀）

```
masterpiece, best quality, very aesthetic, absurdres
```

## 通用负向

```
lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry, artist name, checkerboard, transparent background grid, white background, letterbox, border frame
```

> 负向里显式写 `checkerboard` / `transparent background grid`，减少 AI 画假透明棋盘格。

## 角色（`source/roles` → `inbox/roles`）

- **导出**：1024×1024 生成后缩至 512×512（脚本内自动）
- **构图**：正方画布、男/女上半身撑满、黑底
- **Prompt**：各资源独立标签见 `ArtPipeline/tools/pipeline_config.json` 或 GUI「提示词」页签
- **禁止**：`round frame`, `card border`, `chibi`, 画面内文字
- **背景**：黑底生成；可选 rembg（`--no-rembg` 关闭）

各职业要点：

| 角色 | 道具/特效关键词 |
|------|----------------|
| 庄家 | 筹码、扑克牌、轮盘纹、预知金光 |
| 魔术师 | 礼帽、魔杖、子弹反转、紫色魔法粒子 |
| 赌徒 | 骰子、窥视镜、幸运金光、扑克花色 |
| 战士 | 重甲、护身符、金色护盾光晕 |
| 佣兵 | 眼罩、弹药、狂暴剂红光、火星 |
| 医生 | 注射器、药瓶、毒雾、炼金符号 |
| 背叛者 | 无面、兜帽、紫黑斗篷、腐蚀粒子 |

## 道具（`source/items` → `inbox/items`）

- **导出**：256×256
- **构图**：物件居中，**整张图带统一暗金道具框**，边到边，无白边
- 八道具画面要点见 `Assets/Scripts/表现优化文档.md` §8.4

示例（护身符）：

```
masterpiece, best quality, game icon, amulet pendant, gold ornament, dark ruby, thin ornate gold border, purple-gray inner panel, square icon, centered, demon roulette item
```

## UI 小标（`source/ui` → `inbox/ui`）

- 血量心：128×128，**无边框**，单符号居中
- 可用同一 checkpoint 或更简模型；优先轮廓清晰

## ComfyUI 工作流建议节点

1. CheckpointLoaderSimple → **animagineXL_v3.safetensors**
2. CLIP Text Encode（正 / 负）
3. Empty Latent Image（**固定 width = height**）
4. KSampler
5. VAE Decode
6. **背景移除**（BiRefNet / Rembg 等）→ 真 PNG Alpha
7. Save Image（或 API 回传）

导出 API JSON 后放到 `ArtPipeline/comfyui/workflows/`。
