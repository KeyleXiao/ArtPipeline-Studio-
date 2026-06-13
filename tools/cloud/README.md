# 云生图模块（规划 / 注册表）

与 **ComfyUI 本地生图** 并行：ComfyUI 相关代码（`pipeline_core.py`、`comfyui_client.py`）保持不变；云任务走 `cloud/generator.py` + `cloud/runner.py`。

## 注册表

`registry.json` 定义：

- **providers**：Stability（国外）、万相 / 混元 / 即梦（国内）
- **models**：Checkpoint 下拉中的 `cloud:provider/model` 项
- **gen_modes**：三种统一模式 — **文生图 / 图生图 / 图像编辑**

## Checkpoint 约定

| 类型 | 示例 | 说明 |
|------|------|------|
| 本地 ComfyUI | `animagineXL_v3.safetensors` | 来自 ComfyUI `/models/checkpoints` |
| 云端 | `cloud:dashscope/wan2.6-t2i` | 以 `cloud:` 前缀识别，走云 API |

判断：

```python
def is_cloud_checkpoint(value: str) -> bool:
    return value.strip().startswith("cloud:")
```

## 三种生成模式（统一命名）

| 对内枚举 | UI 中文 | ComfyUI `gen_mode` | 说明 |
|----------|---------|-------------------|------|
| `text_to_image` | 文生图 | `txt2img` | 纯文字出图 |
| `image_to_image` | 图生图 | `img2img` | 参考图 + 强度 |
| `image_edit` | 图像编辑 | `redraw` | 以 source 为底编辑（ComfyUI 仍用 redraw 实现） |

云资源使用 asset 字段 `cloud_gen_mode`；ComfyUI 资源仍用 `gen_mode` + 四段 prompt + workflow。

## 资源 JSON 示例（云）

```json
{
  "id": "icon_example",
  "filename": "icon_example.png",
  "checkpoint": "cloud:volcengine/seedream-4",
  "cloud_gen_mode": "text_to_image",
  "cloud_prompt": "game item icon, single object, centered",
  "cloud_negative": "watermark, text",
  "cloud_strength": 0.65
}
```

## 全局配置（规划，`defaults` 扩展）

```json
{
  "cloud_api_keys": {
    "stability": "",
    "dashscope": "",
    "tencent": "",
    "volcengine": ""
  },
  "cloud_max_concurrent": 3
}
```

## 任务调度

- **ComfyUI**：现有 `PipelineRunner` 单 worker 串行队列，不变。
- **云**：`cloud/runner.py` 内 `ThreadPoolExecutor`，并发上限 `min(cloud_max_concurrent, provider.default_max_parallel)`。
- 混合批量：`pipeline_runner._run_generate` 按 checkpoint 分流；进度通过 `/api/jobs/status` 的 `cloud_tasks[]` 上报。

.tools/cloud/README.md
