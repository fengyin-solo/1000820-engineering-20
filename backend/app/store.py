"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

import json
import os
from typing import Any

from app.seed import SEED_ROWS


def _load_seed_rows() -> dict[str, list[dict[str, Any]]]:
    """装配启动数据。

    默认直接用内置 SEED_ROWS；设置 YARD_SEED_FILE（流水线自检时用）后，
    箱区表换成该文件里生成的样板，其余模块不变。文件读不出来直接抛错，
    让启动失败暴露问题，而不是静默回退到旧数据。
    """
    tables: dict[str, list[dict[str, Any]]] = {
        name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
    }
    seed_file = os.environ.get("YARD_SEED_FILE")
    if seed_file:
        with open(seed_file, encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload.get("module") != "yard" or not isinstance(payload.get("rows"), list):
            raise ValueError(f"{seed_file} 不是合法的箱区样板文件（缺少 module=yard 或 rows 列表）")
        tables["yard"] = [dict(row) for row in payload["rows"]]
    return tables


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = _load_seed_rows()

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
