#!/usr/bin/env bash
# 提交前自检流水线：样板数据生成 -> 后端接口自检 -> 前端构建打包。
#
# 用法：
#   scripts/pipeline.sh all      依次跑三步（默认）
#   scripts/pipeline.sh seed     只重跑样板数据生成
#   scripts/pipeline.sh backend  只重跑后端接口自检
#   scripts/pipeline.sh frontend 只重跑前端构建
#
# 每一步开跑前都会清掉自己上一次的中间产物，不与历史结果混在一起；
# 哪一步失败，结论里会写明是「数据问题」还是「构建问题」，以及只重跑该步的命令。
# 各步的完整输出落在 .pipeline/<步骤>.log。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK_DIR="$ROOT/.pipeline"
PYTHON="$ROOT/backend/.venv/bin/python"

STEPS=(seed backend frontend)

step_label() {
  case "$1" in
    seed) echo "① 箱区样板数据生成" ;;
    backend) echo "② 后端接口自检" ;;
    frontend) echo "③ 前端构建打包" ;;
  esac
}

# 把失败归类为数据问题或构建问题，方便直接判断从哪里修。
step_kind() {
  case "$1" in
    seed) echo "数据问题" ;;
    backend|frontend) echo "构建问题" ;;
  esac
}

# 每步自己的中间产物：开跑前清干净，避免沿用上一次的结果。
prepare_step() {
  case "$1" in
    seed)
      find "$ROOT/backend/app" -maxdepth 1 -name '.seed.*.tmp' -delete 2>/dev/null || true
      ;;
    backend)
      # 自检不落地文件，只需保证没有残留服务；进程在脚本 finally 里保证清理。
      ;;
    frontend)
      rm -rf "$ROOT/frontend/dist"
      ;;
  esac
  rm -f "$WORK_DIR/$1.log"
}

run_step() {
  local step="$1"
  local label
  label="$(step_label "$step")"
  echo "-------------------------------------------"
  echo "$label"
  prepare_step "$step"

  local status=0
  case "$step" in
    seed)
      "$PYTHON" "$ROOT/scripts/generate_seed.py" 2>&1 | tee "$WORK_DIR/$step.log"
      status=${PIPESTATUS[0]}
      ;;
    backend)
      "$PYTHON" "$ROOT/scripts/check_backend.py" 2>&1 | tee "$WORK_DIR/$step.log"
      status=${PIPESTATUS[0]}
      ;;
    frontend)
      bash "$ROOT/scripts/build_frontend.sh" 2>&1 | tee "$WORK_DIR/$step.log"
      status=${PIPESTATUS[0]}
      ;;
  esac

  if [ "$status" -ne 0 ]; then
    # 环境缺失（exit code 2）单独提示，避免误报成代码/数据错误。
    local hint=""
    if [ "$status" -eq 2 ]; then
      hint="运行环境未就绪，请先执行 make install 后再重跑。"
    fi
    echo
    echo "==========================================="
    echo "结论：本次不能提交"
    echo "失败步骤：$label —— 属于$(step_kind "$step")"
    [ -n "$hint" ] && echo "$hint"
    echo "详细日志：.pipeline/$step.log"
    echo "修好后只重跑这一步：make check-$step"
    echo "==========================================="
    exit 1
  fi
}

main() {
  local target="${1:-all}"
  local chosen=()
  case "$target" in
    all) chosen=("${STEPS[@]}") ;;
    seed|backend|frontend) chosen=("$target") ;;
    *)
      echo "未知步骤：$target（可选：all / seed / backend / frontend）" >&2
      exit 64
      ;;
  esac

  if [ ! -x "$PYTHON" ]; then
    echo "找不到后端虚拟环境 $PYTHON，请先执行 make install" >&2
    exit 2
  fi

  rm -rf "$WORK_DIR"
  mkdir -p "$WORK_DIR"

  echo "提交前自检流水线（步骤：${chosen[*]}）"
  echo "工作目录：$WORK_DIR（每次运行整体重建，不保留上次中间产物）"
  for step in "${chosen[@]}"; do
    run_step "$step"
  done

  echo
  echo "==========================================="
  echo "结论：本次可以提交"
  if [ "$target" = "all" ]; then
    echo "样板数据、后端接口自检、前端构建全部通过。"
  else
    echo "$(step_label "$target") 通过；如需完整结论请再跑一次 make check。"
  fi
  # 全部通过后清掉中间产物，只留下最终结论；失败时保留日志用于定位。
  rm -rf "$WORK_DIR"
  echo "==========================================="
}

main "$@"
