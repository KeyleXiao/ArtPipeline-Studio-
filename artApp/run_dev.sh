#!/usr/bin/env bash
# ArtPipeline Studio Web · 开发启动
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
python3 -m pip install -r requirements.txt -q
exec python3 run_dev.py "$@"
