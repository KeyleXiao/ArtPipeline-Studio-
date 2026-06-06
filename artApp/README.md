# ArtPipeline Studio · Web 版 (`artApp`)

现代化 Web UI（FastAPI + 静态前端），与旧版 Tk 工具 **共用** `../tools/pipeline_config.json` 与 inbox/source 目录。

## 快速开始（开发）

```bash
cd ArtPipeline/artApp
pip install -r requirements.txt
python run_dev.py
```

浏览器自动打开 http://127.0.0.1:8765

## 打包发布（桌面独立应用）

**无需安装 Python / pip 依赖**，在对应平台上运行：

| 平台 | 命令 | 产物 |
|------|------|------|
| macOS | `python3 build_release_mac.py` | `release/ArtPipeline Studio.app` |
| Windows | `python build_release_win.py` | `release/ArtPipeline Studio/ArtPipeline Studio.exe` |

也可使用兼容入口（自动识别当前系统）:

```bash
python3 build_release.py
```

脚本会自动：
1. 创建 `.build-venv`（隔离打包依赖）
2. 用 PyInstaller 生成独立桌面应用

配置写入用户目录（macOS: `~/Library/Application Support/ArtPipeline Studio/`，Windows: `%LOCALAPPDATA%\ArtPipeline Studio\`）。

备用便携版（需本机 Python，不推荐）:

```bash
python3 build_release_mac.py --portable   # macOS
python build_release_win.py --portable    # Windows
python3 build_release_mac.py --portable-win  # 在 Mac 上仅组装 Win 便携目录（无 .exe）
```

### 在 Mac 上生成 Windows 版

PyInstaller **不能**从 macOS 交叉编译出 `.exe`，可选方案：

| 方案 | 产物 | 说明 |
|------|------|------|
| **`--portable-win`（Mac 可跑）** | 便携文件夹 + `.bat` | 拷到 Win 后安装 Python + pip 依赖即可运行，**无独立 exe** |
| **Windows 虚拟机 / 实体机** | 完整 `.exe` | Parallels / UTM / Boot Camp 等，在 Win 内执行 `build_release_win.py` |
| **GitHub Actions** | 完整 `.exe` | 用 `windows-latest` _runner 自动打包（见 `.github/workflows/build-windows.yml`） |
| **云 Windows** | 完整 `.exe` | Azure、AWS 等按需开 Win 实例，同上命令打包 |

Mac 上立即可用（便携版）:

```bash
python3 build_release_mac.py --portable-win
# → release/ArtPipeline Studio/  拷到 Windows 使用
```

## 旧版回退（Tk）

若 Web 版缺少某边缘功能，可回退：

```bash
python ../tools/artTool_ui.py
```

Web 内「Tk 回退」页也有说明。

## 功能对照（Tk → Web）

| 功能 | Web |
|------|-----|
| 分类 / 资源列表、筛选 | ✅ |
| inbox / source / Unity 预览、后处理预览 | ✅ |
| 扫描 in/Unity 状态 | ✅ |
| 基本信息 / 分类设置 / 提示词 / 工作流 | ✅ |
| 全局设置、ComfyUI 状态 | ✅ |
| 云生图（Stability / 万相 / 混元 / 即梦） | ✅ 基础实现（ComfyUI 路径不变） |
| 生成选中 / 本类 / 生成并导出 / 导出 / 导出全部 | ✅ |
| 运行日志 SSE | ✅ |
| AI 助手（DeepSeek） | ✅ |
| 后处理编辑器（图层、模板、应用到 inbox） | ✅ `/postprocess.html` |
| 后处理：Canvas 拖拽 / 裁切 / Solo / 图层管理 | ✅ |
| 新建 / 删除 / 复制资源、新建分类 | ✅ |
| **导入外部资源**（多选贴图批量创建） | ✅ |
| **运行日志目录**（全局设置 + studio.log） | ✅ |
| 打开文件 / 目录 | ✅ |

## 目录结构

```
artApp/
├── run_dev.py
├── run_app.py
├── release_build.py       # 打包公共逻辑
├── build_release.py       # 兼容入口（自动识别平台）
├── build_release_mac.py   # macOS 打包
├── build_release_win.py   # Windows 打包
├── release/               # 发布产物（构建后生成）
├── backend/           # FastAPI + 复用 ../tools 业务
└── web/               # 静态前端（无 npm 构建）
```

完整 API 文档：http://127.0.0.1:8765/api/docs

云生图说明：[docs/cloud-generation.md](../docs/cloud-generation.md) · 模型注册表：[tools/cloud/registry.json](../tools/cloud/registry.json)
