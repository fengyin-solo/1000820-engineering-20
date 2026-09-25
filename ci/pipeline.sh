#!/usr/bin/env bash
# 提交前一键流水线：箱区样板数据 -> 后端接口自检 -> 前端构建。
#
# 用法：
#   ci/pipeline.sh              顺序跑三步，给出「本次能不能提交」的结论
#   ci/pipeline.sh data         只重跑箱区样板数据（先清旧数据）
#   ci/pipeline.sh backend      只重跑后端自检
#   ci/pipeline.sh frontend     只重跑前端构建
#   ci/pipeline.sh clean        清理全部流水线中间产物
#
# 各步骤退出码约定（每步脚本自己也遵守）：
#   0 成功   2 数据问题   3 构建问题   4 环境问题
# 全部步骤只在 .ci-work 与 frontend/dist 留产物，手工启动方式不受影响。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$ROOT/.ci-work"

STEP_DATA_NAME="箱区样板数据生成"
STEP_BACKEND_NAME="后端接口自检"
STEP_FRONTEND_NAME="前端构建"

step_data() {
    echo "── [1/3] $STEP_DATA_NAME ──"
    rm -f "$WORK/data/yard.json"
    python3 "$ROOT/ci/gen_yard_data.py"
}

step_backend() {
    echo "── [2/3] $STEP_BACKEND_NAME ──"
    : > "$WORK/reports/backend-selfcheck.log"
    python3 "$ROOT/ci/check_backend.py"
}

step_frontend() {
    echo "── [3/3] $STEP_FRONTEND_NAME ──"
    bash "$ROOT/ci/build_frontend.sh"
}

classify() {
    case "$1" in
        2) echo "数据问题" ;;
        3) echo "构建问题" ;;
        4) echo "环境问题" ;;
        *) echo "未知问题（退出码 $1）" ;;
    esac
}

run_one() {
    local key="$1" name="$2"; shift 2
    local start end elapsed
    start=$(date +%s)
    "$@"
    local code=$?
    end=$(date +%s)
    elapsed=$((end - start))
    if [ "$code" -ne 0 ]; then
        echo
        echo "✗ ${name} 失败：$(classify "$code")（耗时 ${elapsed}s）"
        echo "  可只重跑这一步：make verify-${key}"
        return "$code"
    fi
    echo "✓ ${name} 通过（耗时 ${elapsed}s）"
    return 0
}

clean_all() {
    echo "清理流水线中间产物：.ci-work/ 与 frontend/dist/"
    rm -rf "$WORK"
    rm -rf "$ROOT/frontend/dist"
}

usage() {
    # 打印文件头部注释里的用法说明（「用法：」到「中间产物」那段）
    awk '/^# 用法：/{flag=1} flag{line=$0; sub(/^# ?/, "", line); print line; if (line ~ /手工启动方式不受影响。$/) exit}' "$0"
}

mkdir -p "$WORK/data" "$WORK/reports"

case "${1:-all}" in
    all)
        echo "================ 提交前流水线开始 ================"
        run_one data "$STEP_DATA_NAME" step_data || { code=$?; echo; echo "结论：✗ 本次不能提交 —— $(classify "$code")，修复后可执行 make verify-data 只重跑这一步。"; exit "$code"; }
        echo
        run_one backend "$STEP_BACKEND_NAME" step_backend || { code=$?; echo; echo "结论：✗ 本次不能提交 —— $(classify "$code")，修复后可执行 make verify-backend 只重跑这一步。"; exit "$code"; }
        echo
        run_one frontend "$STEP_FRONTEND_NAME" step_frontend || { code=$?; echo; echo "结论：✗ 本次不能提交 —— $(classify "$code")，修复后可执行 make verify-frontend 只重跑这一步。"; exit "$code"; }
        echo
        echo "=================================================="
        echo "结论：✓ 三步全部通过（箱区样板数据、后端自检、前端构建），本次可以提交。"
        echo "=================================================="
        ;;
    data)
        run_one data "$STEP_DATA_NAME" step_data
        ;;
    backend)
        run_one backend "$STEP_BACKEND_NAME" step_backend
        ;;
    frontend)
        run_one frontend "$STEP_FRONTEND_NAME" step_frontend
        ;;
    clean)
        clean_all
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        echo "未知参数：$1" >&2
        usage >&2
        exit 64
        ;;
esac
