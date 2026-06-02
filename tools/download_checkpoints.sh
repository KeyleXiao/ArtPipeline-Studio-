#!/usr/bin/env bash
# 下载 ArtPipeline 推荐 checkpoint
# 用法: ./download_checkpoints.sh [illustrious|gameicon|civitai-v4|gameicon-v3-hf|all]
#
# V4_XL 说明:
#   - 官方仅 Civitai 提供完整 6.46GB SDXL checkpoint
#   - civitai.com 在国内通常无法直连 (DNS 有解析但 TCP 超时)
#   - 无 hf-mirror 上的 V4_XL 单文件镜像
#   - 国内替代: 哩布 LiblibAI (官方合作) 网页下载，或 VPN 后 civitai-v4

set -euo pipefail
CKPT="${COMFYUI_CKPT_DIR:-$HOME/comflowy/ComfyUI/models/checkpoints}"
LORA="${COMFYUI_LORA_DIR:-$HOME/comflowy/ComfyUI/models/loras}"
VAE="${COMFYUI_VAE_DIR:-$HOME/comflowy/ComfyUI/models/vae}"
mkdir -p "$CKPT" "$LORA" "$VAE"

# 国内建议 hf-mirror
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"

# Civitai 需代理 + API Token（作者要求登录下载）
# Token: https://civitai.com/user/account → API Keys
# 可 export CIVITAI_TOKEN=... 或写入 ~/.civitai_token
PROXY="${http_proxy:-${HTTP_PROXY:-http://127.0.0.1:7890}}"
export http_proxy="${http_proxy:-$PROXY}"
export https_proxy="${https_proxy:-$PROXY}"
CIVITAI_TOKEN="${CIVITAI_TOKEN:-${CIVITAI_API_KEY:-}}"
if [[ -z "$CIVITAI_TOKEN" && -f "$HOME/.civitai_token" ]]; then
  CIVITAI_TOKEN="$(tr -d '[:space:]' < "$HOME/.civitai_token")"
fi

download_illustrious() {
  echo "==> Illustrious XL v2.0-stable (~6.9 GB) via hf-mirror"
  huggingface-cli download ashllay/Illustrious-XL-Backups \
    Illustrious-XL-v2.0-stable.safetensors \
    --local-dir "$CKPT"
  echo "完成: $CKPT/Illustrious-XL-v2.0-stable.safetensors"
}

download_gameicon_hf() {
  echo "==> game_icon_v1.0 (~2.8 GB, HF 镜像, SD 系) via hf-mirror"
  huggingface-cli download Alptekinege/loras \
    game_icon_v1.0.safetensors \
    --local-dir "$CKPT"
  echo "完成: $CKPT/game_icon_v1.0.safetensors"
  echo "==> 3d-icon-SDXL-LoRA (SDXL LoRA, 可叠 animagineXL)"
  huggingface-cli download ellemac/3d-icon-SDXL-LoRA \
    3d-icon-SDXL-LoRA.safetensors \
    --local-dir "$LORA"
  echo "完成: $LORA/3d-icon-SDXL-LoRA.safetensors"
}

download_civitai_v4() {
  echo "==> Game Icon Institute V4_XL (~6.46 GB) from Civitai"
  echo "    代理: $https_proxy"
  OUT="$CKPT/game_icon_institute_v4_xl.safetensors"
  if [[ -z "$CIVITAI_TOKEN" ]]; then
    echo "[!] 该模型作者要求登录下载，需要 Civitai API Token"
    echo "    获取: https://civitai.com/user/account → API Keys"
    echo "    然后: export CIVITAI_TOKEN='你的token'"
    echo "    或:   echo '你的token' > ~/.civitai_token"
    exit 1
  fi
  curl -L --fail --retry 5 --continue-at - \
    -H "Authorization: Bearer $CIVITAI_TOKEN" \
    "https://civitai.com/api/download/models/505488?type=Model&format=SafeTensor" \
    -o "$OUT"
  echo "完成: $OUT"
  echo "可选 VAE: https://civitai.com/models/47800 → 下载配套 VAE 到 $VAE"
}

download_rpg_item_icons_lora() {
  echo "==> SDXL RPG Item Icons LoRA (~177 MB) from Civitai"
  echo "    触发词: weic | 推荐 weight 0.85 CFG 4-6.5"
  OUT="$LORA/sdxl_rpg_item_icons.safetensors"
  AUTH=()
  if [[ -n "$CIVITAI_TOKEN" ]]; then
    AUTH=(-H "Authorization: Bearer $CIVITAI_TOKEN")
  fi
  curl -L --fail --retry 5 --continue-at - "${AUTH[@]}" \
    "https://civitai.com/api/download/models/2818920?type=Model&format=SafeTensor" \
    -o "$OUT"
  echo "完成: $OUT"
}

print_v4_mirror_help() {
  cat <<'EOF'
[!] V4_XL 无法从 Civitai 直连时的替代方案:

  1. 配置 Token 后重试:
     export CIVITAI_TOKEN='你的token'   # https://civitai.com/user/account
     ./download_checkpoints.sh civitai-v4

  2. 哩布 LiblibAI（国内可访问，游戏图标研究所官方合作方）:
     https://www.liblib.art
     搜索「游戏图标研究所」或「gameIconInstitute」
     在模型页点击下载 → 放入 ComfyUI/models/checkpoints/
     注意: 哩布上常见为 v3.0，V4_XL 可能需搜「V4」或等作者上传

  3. HuggingFace 镜像（无 V4_XL，仅有旧版 v3.0 SD1.5 系 ~4GB）:
     ./download_checkpoints.sh gameicon-v3-hf

  4. 已下载的 game_icon_v1.0 (2.6GB) 是 SD1.5，不能替代 V4_XL SDXL 工作流

  5. 暂用 animagineXL + 3d-icon-SDXL-LoRA 生成道具（需工作流加 LoRA 节点）
EOF
}

download_gameicon_v3_hf() {
  echo "==> gameIconInstitute_v30 (~4.0 GB, HF 镜像, SD1.5 非 V4_XL) via hf-mirror"
  huggingface-cli download aceevanss/GameIconInstitute_mode \
    gameIconInstitute_v30.safetensors \
    --local-dir "$CKPT"
  echo "完成: $CKPT/gameIconInstitute_v30.safetensors"
  echo "注意: 这是 v3.0 (SD1.5)，不是 Civitai 上的 V4_XL (SDXL 6.46GB)"
}

TARGET="${1:-all}"
case "$TARGET" in
  illustrious) download_illustrious ;;
  gameicon) download_gameicon_hf ;;
  rpg-item-lora) download_rpg_item_icons_lora ;;
  civitai-v4) download_civitai_v4 ;;
  gameicon-v3-hf) download_gameicon_v3_hf ;;
  all)
    download_illustrious
    download_gameicon_hf
    if curl -sI --max-time 10 https://civitai.com >/dev/null 2>&1; then
      download_rpg_item_icons_lora
      if [[ -n "$CIVITAI_TOKEN" ]]; then
        download_civitai_v4
      else
        echo "跳过 Civitai V4_XL（未设置 CIVITAI_TOKEN，作者要求登录下载）"
        print_v4_mirror_help
      fi
    else
      echo "跳过 Civitai V4_XL（当前网络无法访问 civitai.com）"
      print_v4_mirror_help
    fi
    ;;
  *) echo "用法: $0 [illustrious|gameicon|rpg-item-lora|civitai-v4|gameicon-v3-hf|all]"; exit 1 ;;
esac

echo "全部完成。重启 ComfyUI 后在 ArtPipeline 全局设置刷新 checkpoint 列表。"
