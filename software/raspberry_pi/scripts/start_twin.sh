#!/usr/bin/env bash
# 一键启动数字孪生双端（小车端 8000 / 家长端 8001），可选同时拉起干杯助手桥接（8010）。
#
# 用法：
#   scripts/start_twin.sh                 # 只起数字孪生双端
#   scripts/start_twin.sh --with-assistant  # 同时起 xiaozhi_bridge（需要 py-xiaozhi 环境）
#   OPENKIDCAR_PASSWORD=你的密码 scripts/start_twin.sh   # 真车部署必须设密码
#
# 说明：这是 Linux / macOS / 树莓派上的等价脚本，对位 Windows 的 start_xiaozhi.bat。
set -euo pipefail

cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"; fi

WITH_ASSISTANT=0
for arg in "$@"; do
  case "$arg" in
    --with-assistant) WITH_ASSISTANT=1 ;;
    --dev-allow-no-password) DEV_FLAG="--dev-allow-no-password" ;;
    *) echo "未知参数: $arg"; exit 2 ;;
  esac
done
DEV_FLAG="${DEV_FLAG:-}"

if [ "$WITH_ASSISTANT" -eq 1 ]; then
  echo "[1/2] 启动干杯助手桥接 (8010)..."
  if [ -x "py-xiaozhi/.venv/bin/python" ]; then
    py-xiaozhi/.venv/bin/python digital_twin/backend/xiaozhi_bridge.py 8010 &
  else
    echo "  ⚠ 未找到 py-xiaozhi/.venv，跳过桥接（数字孪生仍可用，只是没有语音助手）"
  fi
  sleep 2
  echo "[2/2] 启动数字孪生 (8000/8001)..."
else
  echo "启动数字孪生 (8000/8001)..."
fi

if [ -z "${OPENKIDCAR_PASSWORD:-}" ] && [ -z "$DEV_FLAG" ]; then
  echo "提示：未设置 OPENKIDCAR_PASSWORD，本机开发用 --dev-allow-no-password 放行"
  DEV_FLAG="--dev-allow-no-password"
fi

echo "小车端 http://localhost:8000   家长端 http://localhost:8001"
exec "$PY" digital_twin/backend/twin_server.py 8000 8001 $DEV_FLAG
