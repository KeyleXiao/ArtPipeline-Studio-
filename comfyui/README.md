# ComfyUI 工作流

1. 在 ComfyUI 中搭好工作流（checkpoint：**animagineXL_v3.safetensors**）。
2. 菜单 **Save (API Format)** → 保存到 `workflows/`。
3. 工作流需支持变量（后续脚本会替换）：
   - 正向 / 负向 prompt
   - `width`, `height`（与 manifest 中 `size` 一致）
   - `seed`（可选）

## 建议文件名

| 文件 | 用途 |
|------|------|
| `workflows/role_icon_api.json` | 角色 512² + 抠图 |
| `workflows/item_icon_api.json` | 道具 256² + 框图 |
| `workflows/ui_icon_api.json` | UI 小标 128² |

## 环境

```bash
export COMFYUI_URL=http://127.0.0.1:8188
export COMFYUI_CHECKPOINT=animagineXL_v3.safetensors
```

将 API JSON 放入 `workflows/` 后，使用批处理脚本（已内置 SDXL 工作流，无需手填 JSON）：

```bash
# 查看 checkpoint 与清单
python3 Assets/Scripts/Tools/generate_icons_comfyui.py --list

# 生成全部角色 → source/roles/（需 ComfyUI 运行 + animagineXL_v3.safetensors）
python3 Assets/Scripts/Tools/generate_icons_comfyui.py --kind role --to-inbox

# 单张
python3 Assets/Scripts/Tools/generate_icons_comfyui.py --file role_warrior.png --to-inbox --deploy

# 全部生成并入库 Unity
python3 Assets/Scripts/Tools/generate_icons_comfyui.py --all --to-inbox --deploy
```

若列表里没有该文件，请将 `animagineXL_v3.safetensors` 放入 ComfyUI 的 `models/checkpoints/` 后重启或刷新。
