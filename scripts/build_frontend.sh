#!/usr/bin/env bash
# 前端构建打包：先清掉上一次的 dist，再跑类型检查 + 打包。
# 失败一律视为「前端构建问题」（含依赖没装），退出码非 0。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$ROOT/frontend"

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "[frontend] 未找到 node_modules，请先执行 make install" >&2
  exit 2
fi

echo "[frontend] 清理上次构建产物 $FRONTEND_DIR/dist"
rm -rf "$FRONTEND_DIR/dist"

echo "[frontend] 类型检查 + 打包（npm run build）"
cd "$FRONTEND_DIR"
npm run build

if [ ! -d "$FRONTEND_DIR/dist" ] || [ -z "$(ls -A "$FRONTEND_DIR/dist" 2>/dev/null)" ]; then
  echo "[frontend] 构建命令返回成功，但 dist 为空，按构建失败处理" >&2
  exit 1
fi

echo "[frontend] 构建产物已生成在 $FRONTEND_DIR/dist"
