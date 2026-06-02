# ArtPipeline · tools

美术工作流 **可视化工具 + CLI**，配置集中在 `pipeline_config.json`。

## 快速启动

```bash
# 图形界面（推荐）
python3 ArtPipeline/tools/artTool_ui.py
# 或
./ArtPipeline/tools/run_art_tool.sh

# 命令行
python3 ArtPipeline/tools/cli.py --list
python3 ArtPipeline/tools/cli.py --category roles --to-inbox --deploy
```

## 目录结构

```
ArtPipeline/tools/
├── README.md                 # 本文件
├── 维护指南.md               # 日常维护说明
├── artTool_ui.py             # 可视化入口
├── cli.py                    # 命令行入口
├── pipeline_config.json      # 主配置（分类、资源、路径、提示词、工作流）
├── config_manager.py         # 配置读写
├── pipeline_core.py          # 生成 / 导出 / ComfyUI 调度
├── workflow_engine.py        # 工作流 JSON 占位符替换
├── comfyui_client.py         # ComfyUI HTTP 客户端
├── bootstrap_config.py       # 首次默认配置
├── paths.py
└── workflows/
    ├── _default_sdxl_api.json    # SDXL 默认模板（含 {{占位符}}）
    └── assets/                   # 每张图独立工作流（可编辑）
        ├── role_warrior.json
        └── ...
```

## 配置说明（pipeline_config.json）

| 区块 | 作用 |
|------|------|
| `defaults` | ComfyUI URL、采样参数（steps/cfg/sampler）；`checkpoint` 仅作新建分类时的预选，不参与生图兜底 |
| `categories[]` | 分类 ↔ `source/` / `inbox/` / Unity 路径映射；**checkpoint** 为分类默认模型 |
| `assets[]` | 每张图的文件名、尺寸、正负 prompt、工作流路径；可选 **checkpoint** 覆盖分类 |

**新增分类** = 新增 `source/<id>/`、`inbox/<id>/` 文件夹 + 配置项。  
**新增资源** = 在 UI 或 JSON 中添加 asset，并创建 `workflows/assets/<id>.json`。

## 工作流 JSON

从 ComfyUI 导出 **API Format**，粘贴到 UI「工作流 JSON」页签。  
字符串中使用占位符，生成时自动替换：

`{{POSITIVE}}` `{{NEGATIVE}}` `{{WIDTH}}` `{{HEIGHT}}` `{{SEED}}`  
`{{CHECKPOINT}}` `{{FILENAME_PREFIX}}` `{{STEPS}}` `{{CFG}}` `{{SAMPLER}}` `{{SCHEDULER}}`

## 兼容旧脚本

`Assets/Scripts/Tools/generate_icons_comfyui.py` 与 `art_paths.py` 仍可用，内部转发到本目录。

## 依赖

```bash
pip install -r ArtPipeline/tools/requirements.txt
```

- Python 3.10+
- **ttkbootstrap** — 现代深色主题与统一样式（未安装时回退原生 tkinter）
- **Pillow** — 正方形预览缩略图与 PNG 缩放
- **websocket-client**（可选）— ComfyUI 实时采样进度
- tkinter（macOS 自带）
- ComfyUI 本地运行（默认 `http://127.0.0.1:8188`）

## 图形界面功能

| 功能 | 说明 |
|------|------|
| 主题 | ttkbootstrap `darkly` 主题，顶部菜单为统一样式下拉按钮 |
| 正方形预览 | 288×288 缩略图，inbox/source/Unity 切换，**点击打开原图** |
| 右键菜单 | 资源列表右键：生成 / 导出 / 打开文件 / 打开文件夹 / 复制 / 删除 |
| 实时进度 | 右下角 label 显示 `生成 45%` 或 `生成 2/7 · 45%` |
| 取消生成 | 生成进行中时，资源列表 **右键 → 取消生成** |
| 复制 prompt | 正向 / 负向一键复制到剪贴板 |
| 复制资源 | 基于当前资源快速 duplicate（含工作流 JSON） |
| Checkpoint 下拉 | 全局 + 分类级，可扫描 ComfyUI 模型列表 |

