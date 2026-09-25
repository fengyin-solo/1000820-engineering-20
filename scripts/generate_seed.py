#!/usr/bin/env python3
"""生成箱区样板数据 backend/app/seed.py。

数据来源分两层：
- scripts/seed_spec.py：人维护的声明式规格（模块前缀、字段取值规则等）；
- backend/app/services、backend/app/routers：状态序列、必填字段、列表字段，
  生成结果自动与代码里的接口定义对齐，字段一改生成期就能发现对不上。

产物先写到临时文件并通过结构自校验，再原子替换 seed.py；任何一步不通过都
不会留下半截文件。退出码非 0 即视为「数据问题」。
"""
from __future__ import annotations

import importlib
import os
import pprint
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))

import seed_spec  # noqa: E402

SEED_PATH = ROOT / "backend" / "app" / "seed.py"


def _load(module_path: str) -> Any:
    return importlib.import_module(module_path)


def build_rows() -> dict[str, list[dict[str, Any]]]:
    """按规格 + service/router 元数据生成全部样板行。"""
    tables: dict[str, list[dict[str, Any]]] = {}
    for module, meta in seed_spec.MODULES.items():
        service = _load(f"app.services.{module}")
        router = _load(f"app.routers.{module}")

        status_order: list[str] = service.STATUS_ORDER
        required: list[str] = service.REQUIRED_FIELDS
        list_fields: list[str] = router.LIST_FIELDS

        # 与接口定义对齐：必填字段必须出现在列表字段里，否则前端列表拿不到。
        missing = [f for f in required if f not in list_fields]
        if missing:
            raise ValueError(
                f"[{module}] service 必填字段 {missing} 不在 router.LIST_FIELDS 中"
            )
        if seed_spec.ROWS_PER_MODULE > len(status_order):
            raise ValueError(
                f"[{module}] 状态序列只有 {len(status_order)} 个，"
                f"无法生成 {seed_spec.ROWS_PER_MODULE} 行不同状态的样板"
            )

        prefix = meta["prefix"]
        label = meta["label"]
        primary_code_field = None if module in seed_spec.NO_PRIMARY_CODE else required[0]
        extra_code_fields = set(seed_spec.EXTRA_CODE_FIELDS.get(module, []))

        rows: list[dict[str, Any]] = []
        for index in range(1, seed_spec.ROWS_PER_MODULE + 1):
            row: dict[str, Any] = {
                "id": index,
                "status": status_order[index - 1],
                # 除终态外都算「待处理」；第 2 行带异常标记，供看板异常量展示。
                "pending": index != seed_spec.ROWS_PER_MODULE,
                "abnormal": index == 2,
            }
            for field in list_fields:
                if field == primary_code_field or field in extra_code_fields:
                    value: Any = f"{prefix}-{index:04d}"
                elif field in seed_spec.DATE_FIELDS:
                    value = f"2026-09-0{index}"
                elif field in seed_spec.MONEY_FIELDS:
                    value = round(12.5 * index, 2)
                elif field in seed_spec.PHONE_FIELDS:
                    value = f"1380000000{index}"
                else:
                    value = f"{label}样例{index}"
                row[field] = value
            rows.append(row)
        tables[module] = rows
    return tables


def validate(tables: dict[str, list[dict[str, Any]]]) -> list[str]:
    """结构自校验：返回问题清单，空列表表示通过。"""
    problems: list[str] = []
    expected_modules = set(seed_spec.MODULES)
    if set(tables) != expected_modules:
        missing = sorted(expected_modules - set(tables))
        extra = sorted(set(tables) - expected_modules)
        if missing:
            problems.append(f"缺少模块: {missing}")
        if extra:
            problems.append(f"多出模块: {extra}")

    for module, rows in tables.items():
        service = _load(f"app.services.{module}")
        router = _load(f"app.routers.{module}")
        status_order: list[str] = service.STATUS_ORDER
        required: list[str] = service.REQUIRED_FIELDS
        list_fields: list[str] = router.LIST_FIELDS

        if len(rows) != seed_spec.ROWS_PER_MODULE:
            problems.append(f"[{module}] 行数 {len(rows)} 不是 {seed_spec.ROWS_PER_MODULE}")
        ids = [row.get("id") for row in rows]
        if ids != list(range(1, len(rows) + 1)):
            problems.append(f"[{module}] id 不连续: {ids}")

        seen_status: set[str] = set()
        for row in rows:
            rid = row.get("id")
            status = row.get("status")
            if status not in status_order:
                problems.append(f"[{module}#{rid}] 状态 {status!r} 不在 {status_order}")
            seen_status.add(str(status))
            if not isinstance(row.get("pending"), bool):
                problems.append(f"[{module}#{rid}] pending 不是布尔值")
            if not isinstance(row.get("abnormal"), bool):
                problems.append(f"[{module}#{rid}] abnormal 不是布尔值")
            for field in list_fields:
                if field not in row:
                    problems.append(f"[{module}#{rid}] 缺字段 {field}")
            for field in required:
                if not str(row.get(field) or "").strip():
                    problems.append(f"[{module}#{rid}] 必填字段 {field} 为空")
        # 前三个状态必须各覆盖一行，保证起服务就能看到初始/中间/终态。
        expected_status = set(status_order[: seed_spec.ROWS_PER_MODULE])
        if seen_status != expected_status:
            problems.append(
                f"[{module}] 状态覆盖 {sorted(seen_status)}，预期 {sorted(expected_status)}"
            )
    return problems


def render(tables: dict[str, list[dict[str, Any]]]) -> str:
    body = pprint.pformat(tables, width=80, sort_dicts=False)
    return (
        '"""示例数据：由 scripts/generate_seed.py 生成，请勿手工编辑。\n\n'
        "需要调整样板内容时改 scripts/seed_spec.py（或对应 service/router 的字段定义），\n"
        '然后运行 `make check-seed`（或 python3 scripts/generate_seed.py）重新生成。\n"""\n'
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n"
        f"SEED_ROWS: dict[str, list[dict[str, Any]]] = {body}\n"
    )


def main() -> int:
    try:
        tables = build_rows()
        problems = validate(tables)
    except Exception as exc:  # 规格 / 元数据本身对不上，归为数据问题
        print(f"[seed] 样板数据生成失败（数据问题）：{exc}", file=sys.stderr)
        return 1

    if problems:
        print("[seed] 样板数据自校验未通过（数据问题）：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    content = render(tables)

    # 先写同目录临时文件再原子替换，失败不会动到旧的 seed.py。
    os.makedirs(SEED_PATH.parent, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".seed.", suffix=".py.tmp", dir=str(SEED_PATH.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, SEED_PATH)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise

    total = sum(len(rows) for rows in tables.values())
    print(f"[seed] 已生成 {SEED_PATH.relative_to(ROOT)}：{len(tables)} 个模块、{total} 行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
