#!/usr/bin/env bash
# 前端构建步骤：确认依赖 -> 清掉上一次产物 -> 类型检查 + 打包。
#
# 退出码：
#   0 通过
#   3 构建问题（依赖装不上、typecheck 或 vite build 失败）
# 产物：frontend/dist（失败时删除，不留下半截 dist）
# 日志：.ci-work/reports/frontend-build.log
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND="$ROOT/frontend"
REPORT_DIR="$ROOT/.ci-work/reports"
REPORT="$REPORT_DIR/frontend-build.log"
mkdir -p "$REPORT_DIR"

log() { printf '%s\n' "$*"; }

fail_build() {
    log "[失败][构建问题] $1"
    log "结论：前端构建未通过（构建问题），本次不能提交。"
    rm -rf "$FRONTEND/dist"
    exit 3
}

: > "$REPORT"
exec > >(tee -a "$REPORT") 2>&1

log "==== 前端构建 ===="

command -v node >/dev/null 2>&1 || { log "[失败][构建问题] 找不到 node，请先安装 Node.js。"; exit 4; }
command -v npm >/dev/null 2>&1 || { log "[失败][构建问题] 找不到 npm，请先安装 Node.js（自带 npm）。"; exit 4; }

# 依赖是否可用：node_modules 缺失、vite 解析不到，或换了平台导致原生二进制
# （esbuild、@rollup/rollup-*）对不上，都重装修复
need_install=0
[ -d "$FRONTEND/node_modules" ] || need_install=1
[ -f "$FRONTEND/node_modules/vite/bin/vite.js" ] || need_install=1
# require('rollup') 时会加载平台原生二进制，换平台装错包在这一步就会抛错
(cd "$FRONTEND" && node -e "require('rollup')" >/dev/null 2>&1) || need_install=1
(cd "$FRONTEND" && node -e "require('child_process').execFileSync(require('path').join('node_modules/esbuild/bin/esbuild'), ['--version'])" >/dev/null 2>&1) || need_install=1
if [ "$need_install" -ne 0 ]; then
    log "[构建] node_modules 缺失或与当前平台不匹配，执行 npm install……"
    if ! (cd "$FRONTEND" && npm install); then
        fail_build "npm install 失败，依赖没有装齐。"
    fi
fi

# 不带上一次的中间产物：每次构建都是干净产物
log "[构建] 清理旧的 frontend/dist……"
rm -rf "$FRONTEND/dist"

log "[构建] 类型检查 + 打包（npm run build）……"
if ! (cd "$FRONTEND" && npm run build); then
    fail_build "npm run build 失败（vue-tsc 类型检查或 vite 打包报错，见上方日志）。"
fi

if [ ! -f "$FRONTEND/dist/index.html" ]; then
    fail_build "构建命令退出码为 0，但 dist/index.html 不存在，产物不完整。"
fi

ASSET_COUNT=$(find "$FRONTEND/dist/assets" -type f 2>/dev/null | wc -l | tr -d ' ')
log "结论：前端构建通过（dist/index.html + ${ASSET_COUNT} 个资源文件）。"
