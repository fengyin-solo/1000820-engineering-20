#!/usr/bin/env python3
"""箱区样板数据生成器。

以前箱区样板靠口口相传，新人造的数据对不上接口口径。这里把约定固化下来：
生成结果是一份确定性的箱区清单（每次同样参数产物相同），写出前会逐条做
规则校验，任何一条不过就属于「数据问题」，不写产物、以退出码 2 结束。

用法：
    python3 ci/gen_yard_data.py [--count N] [--output 路径]

默认产物：.ci-work/data/yard.json（字段与 /api/yard 列表口径一致）。
只依赖标准库，不需要虚拟环境。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

# ---- 箱区样板口径（改规则只改这里）-------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / ".ci-work" / "data" / "yard.json"

CODE_PREFIX = "YARD"
YARDS = ["一期堆场", "二期堆场"]
KEEPERS = ["周振邦", "钱卫东", "蒋丽萍"]
# 单贝位数：一排 6 列，按层数堆高
BAYS = 20
COLUMNS = 6
# 箱区状态枚举，顺序必须与后端 services/yard.py 的 STATUS_ORDER 一致
STATUS_ENUM = ["待启用", "正常堆放", "接近满载", "已封闭"]
NEAR_FULL_RATIO = 0.85
# 前 4 个箱区固定覆盖全部状态；后续按「状态 + 与之匹配的利用率」循环铺开
FORCED_PROFILE: list[tuple[str, float]] = [
    ("待启用", 0.0),
    ("正常堆放", 0.35),
    ("接近满载", 0.90),
    ("已封闭", 1.0),
]
TAIL_PROFILE: list[tuple[str, float]] = [
    ("正常堆放", 0.35),
    ("正常堆放", 0.60),
    ("接近满载", 0.92),
    ("已封闭", 0.75),
]
MIN_COUNT = 4  # 少于 4 个箱区无法覆盖全部 4 种状态
MAX_COUNT = 200
ID_RE = re.compile(r"^YARD-\d{4}$")

REQUIRED_FIELDS = [
    "id", "status", "pending", "abnormal",
    "箱区编号", "箱区名称", "堆放层数", "可用箱位", "已用箱位",
    "所属堆场", "责任人", "箱区状态",
]


class DataError(Exception):
    """样板数据本身的问题（区别于脚本/环境问题）。"""


def generate(count: int) -> list[dict[str, Any]]:
    """按固定口径生成 count 个箱区，结果确定性、可复现。"""
    rows: list[dict[str, Any]] = []
    for index in range(count):
        code = f"{CODE_PREFIX}-{index + 1:04d}"
        layers = 3 + index % 4                   # 3~6 层循环
        capacity = BAYS * COLUMNS * layers
        if index < len(FORCED_PROFILE):
            status, ratio = FORCED_PROFILE[index]
        else:
            status, ratio = TAIL_PROFILE[(index - len(FORCED_PROFILE)) % len(TAIL_PROFILE)]
        used = round(capacity * ratio)
        available = capacity - used
        rows.append({
            "id": index + 1,
            "status": status,
            "pending": status != "已封闭",
            "abnormal": False,
            "箱区编号": code,
            "箱区名称": f"{YARDS[index % len(YARDS)]}{index // len(YARDS) + 1:02d}号箱区",
            "堆放层数": layers,
            "可用箱位": available,
            "已用箱位": used,
            "所属堆场": YARDS[index % len(YARDS)],
            "责任人": KEEPERS[index % len(KEEPERS)],
            "箱区状态": status,
        })
    return rows


def validate(rows: list[dict[str, Any]]) -> None:
    """逐条核对箱区口径；收集到的全部问题一次性报出。"""
    problems: list[str] = []
    seen_codes: set[str] = set()
    seen_ids: set[int] = set()

    if len(rows) < MIN_COUNT:
        problems.append(f"箱区数量 {len(rows)} 少于最少要求 {MIN_COUNT}（需覆盖全部状态）")

    for pos, row in enumerate(rows, start=1):
        where = f"第{pos}行"
        missing = [name for name in REQUIRED_FIELDS if name not in row]
        if missing:
            problems.append(f"{where} 缺字段：{'、'.join(missing)}")
            continue

        code = str(row["箱区编号"])
        if not ID_RE.match(code):
            problems.append(f"{where} 箱区编号 {code!r} 不符合 {ID_RE.pattern} 格式")
        if code in seen_codes:
            problems.append(f"{where} 箱区编号 {code} 重复")
        seen_codes.add(code)

        entry_id = row["id"]
        if not isinstance(entry_id, int) or entry_id <= 0:
            problems.append(f"{where} id 必须是正整数，实际为 {entry_id!r}")
        if entry_id in seen_ids:
            problems.append(f"{where} id {entry_id} 重复")
        seen_ids.add(entry_id)

        status = row["status"]
        if status not in STATUS_ENUM:
            problems.append(f"{where} 状态 {status!r} 不在 {STATUS_ENUM} 内")
        if row.get("箱区状态") != status:
            problems.append(f"{where} 箱区状态字段与 status 不一致")
        if not isinstance(row.get("pending"), bool):
            problems.append(f"{where} pending 必须是布尔值")
        elif row["pending"] != (status != "已封闭"):
            problems.append(f"{where} pending 与状态 {status} 不匹配（已封闭应为 false）")
        if not isinstance(row.get("abnormal"), bool):
            problems.append(f"{where} abnormal 必须是布尔值")

        layers = row["堆放层数"]
        available = row["可用箱位"]
        used = row["已用箱位"]
        for name, value in (("堆放层数", layers), ("可用箱位", available), ("已用箱位", used)):
            if not isinstance(value, int) or value < 0:
                problems.append(f"{where} {name} 必须是非负整数，实际为 {value!r}")
        if isinstance(layers, int) and layers > 0 and isinstance(available, int) and isinstance(used, int):
            capacity = BAYS * COLUMNS * layers
            total = available + used
            if total != capacity:
                problems.append(f"{where} 可用箱位+已用箱位={total}，与容量 {capacity}（{BAYS}贝×{COLUMNS}列×{layers}层）不符")
            if status == "接近满载" and used / capacity < NEAR_FULL_RATIO:
                problems.append(f"{where} 标为接近满载但利用率 {used / capacity:.0%} 低于 {NEAR_FULL_RATIO:.0%}")
            if status == "待启用" and used != 0:
                problems.append(f"{where} 待启用箱区不应有已用箱位，实际 {used}")

    for status in STATUS_ENUM:
        if not any(row.get("status") == status for row in rows):
            problems.append(f"整批数据缺少「{status}」状态的箱区，样板覆盖不全")

    if problems:
        raise DataError("；".join(problems))


def write_atomic(rows: list[dict[str, Any]], output: Path) -> None:
    """先写临时文件再原子替换，失败时不留下半截产物。"""
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "module": "yard",
        "generated_by": "ci/gen_yard_data.py",
        "count": len(rows),
        "rows": rows,
    }
    fd, tmp_name = tempfile.mkstemp(prefix=".yard-", suffix=".json", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_name, output)
    except BaseException:
        os.unlink(tmp_name)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成箱区样板数据")
    parser.add_argument("--count", type=int, default=12, help=f"箱区数量（{MIN_COUNT}~{MAX_COUNT}）")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="产物 JSON 路径")
    args = parser.parse_args(argv)

    if not MIN_COUNT <= args.count <= MAX_COUNT:
        print(f"[数据] 箱区数量 {args.count} 超出允许范围 {MIN_COUNT}~{MAX_COUNT}", file=sys.stderr)
        # 与校验失败一致：数据有问题时不留上一次的产物
        if args.output.exists():
            args.output.unlink()
        return 2

    try:
        rows = generate(args.count)
        validate(rows)
    except DataError as exc:
        print(f"[数据] 箱区样板数据校验失败：{exc}", file=sys.stderr)
        # 数据问题：不留上一次的产物，避免旧数据被当成新结果
        if args.output.exists():
            args.output.unlink()
        return 2

    write_atomic(rows, args.output)
    statuses = {status: sum(1 for row in rows if row["status"] == status) for status in STATUS_ENUM}
    summary = "、".join(f"{name}{num}个" for name, num in statuses.items())
    print(f"[数据] 已生成 {len(rows)} 个箱区（{summary}） -> {args.output.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
