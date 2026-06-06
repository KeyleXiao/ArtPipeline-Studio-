# 云生图说明

ArtPipeline Studio 支持 **ComfyUI 本地生图**（基本盘）与 **云端 API 生图**（补充）。二者共用 source / inbox / 导出流程，生图后端不同。

> 实现状态：云 API 调用、并发调度与 Web UI 已接入；ComfyUI 路径未改动。各平台需配置对应 API Key。

## 模型选择

在 **基本信息** 或 **分类设置** 的 **Checkpoint** 下拉中：

```
── 本地 ComfyUI ──
  game_icon_institute_v4_xl.safetensors
  animagineXL_v3.safetensors
── 云端 · 国外 ──
  Stability · Core
  Stability · SD3
── 云端 · 国内 ──
  万相 · wan2.6
  混元 · 3.0
  即梦 · Seedream 4
```

- 选 **本地 checkpoint** → 使用「提示词与工作流」页（四段 prompt + ComfyUI 工作流）。
- 选 **`cloud:` 开头模型** → 使用「云提示词」页（单段 prompt，无工作流 JSON）。

完整列表见 `tools/cloud/registry.json`。

## 三种生成模式（统一命名）

ComfyUI 与云端在界面上使用 **相同名称**：

| 模式 | 说明 |
|------|------|
| **文生图** | 仅根据文字描述生成，无需参考图 |
| **图生图** | 指定参考图，按描述与 **参考强度** 重绘 |
| **图像编辑** | 以 **source 原图** 为底（ComfyUI 称 redraw），按描述修改；结果写入 inbox，不覆盖 source |

云 API 侧分别映射为各平台的 Text-to-Image / Image-to-Image / Image Editing 接口（见注册表 `modes` 字段）。

## 全局设置 · API Key

| 平台 | 配置项 | 用途 |
|------|--------|------|
| ComfyUI | ComfyUI URL | 本地 checkpoint 与生图（不变） |
| Stability AI | `cloud_api_keys.stability` | 国外 · Stable Image |
| 阿里云万相 | `cloud_api_keys.dashscope` | 国内 · 可与视觉 API 共用 Key |
| 腾讯混元 | SecretId + SecretKey | 国内 · 混元生图 |
| 火山即梦 | `cloud_api_keys.volcengine` | 国内 · 方舟 Seedream |

**云任务并发数**（`cloud_max_concurrent`）：默认可同时跑多个云任务；混元账户通常并发更低，按 provider 上限自动裁剪。

## 进度与队列

- **ComfyUI**：串行队列，逐步采样进度（WebSocket）。
- **云**：异步任务轮询（排队 → 生成中 → 下载），浮动进度条显示 **总进度** 与 **各资源子状态**；多个云任务可并行。

日志格式示例：

```
[万相] 文生图 · icon_sword.png · 生成中 62%
[混元] 图像编辑 · icon_shield.png · 排队中
```

## 与 ComfyUI 的差异

| 能力 | ComfyUI | 云端 |
|------|---------|------|
| 工作流 JSON | ✅ 完整节点链 | ❌ 不适用 |
| 四段 SDXL prompt | ✅ | ❌ 单段 `cloud_prompt` |
| 自定义节点 / LoRA | ✅ | ❌ |
| 无需本地 GPU | ❌ | ✅ |
| 多任务并行 | 串行 | 可配置并发 |

复杂道具工作流（GII、双通道、两阶段）仍建议 **ComfyUI**；快速试稿或没有本地 GPU 时可用 **云端**。

## 相关文件

- 模型注册表：`ArtPipeline/tools/cloud/registry.json`
- 开发说明：`ArtPipeline/tools/cloud/README.md`
- Web 使用文档：`artApp/web/docs/zh-CN.md`
