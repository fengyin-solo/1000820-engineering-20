"""箱区样板数据生成规格（声明式）。

以前样板数据是谁造谁清楚：改字段、改状态全靠人手编辑 app/seed.py。
现在把「每个模块的样板行长什么样」收敛到这份规格里，由 scripts/generate_seed.py
结合各模块的 service（状态序列、必填字段）与 router（列表字段）确定性地生成
backend/app/seed.py。想调整样板内容只改这里，不要手改 seed.py。

字段取值规则见 VALUE_RULES，模块级补充信息见 MODULES。
"""
from __future__ import annotations

# 每个模块：业务中文名 + 主键编码字段使用的前缀（生成形如 YARD-0001 的编号）。
# 中文名用于生成 "<中文名>样例1/2/3" 这类占位文本。
MODULES: dict[str, dict[str, str]] = {
    "berth": {"label": "泊位计划", "prefix": "BERT"},
    "vessel": {"label": "船舶档案", "prefix": "VESS"},
    "voyage": {"label": "航次管理", "prefix": "VOYA"},
    "crane": {"label": "岸桥作业", "prefix": "CRAN"},
    "loading": {"label": "装卸任务", "prefix": "LOAD"},
    "yard": {"label": "堆场管理", "prefix": "YARD"},
    "container": {"label": "集装箱档案", "prefix": "CONT"},
    "yardstore": {"label": "堆存记录", "prefix": "YARD"},
    "gate": {"label": "闸口通行", "prefix": "GATE"},
    "truck": {"label": "集卡调度", "prefix": "TRUC"},
    "tally": {"label": "理货作业", "prefix": "TALL"},
    "damage": {"label": "残损登记", "prefix": "DAMA"},
    "manifest": {"label": "单证处理", "prefix": "MANI"},
    "storage": {"label": "堆存计费", "prefix": "STOR"},
    "pilot": {"label": "引航拖轮", "prefix": "PILO"},
    "safety": {"label": "安全监督", "prefix": "SAFE"},
    "customer": {"label": "货主档案", "prefix": "CUST"},
    "settle": {"label": "作业结算", "prefix": "SETT"},
}

# 个别模块历史上没有编号字段（container 的箱号只是占位文本），
# 在这里列出后，其必填首字段按普通占位文本生成，不取 "<前缀>-000n"。
NO_PRIMARY_CODE = {"container"}

# 除主键编码字段外，还有哪些字段也是编号类（值取 "<前缀>-000n"）。
# key 为模块名，value 为这些字段名；前缀沿用 MODULES[module]["prefix"]。
EXTRA_CODE_FIELDS: dict[str, list[str]] = {
    "berth": ["泊位编号"],
    "yardstore": ["箱区编号"],
    "gate": ["道口编号"],
}

# 日期字段：第 n 行（n=1,2,3）取值 2026-09-0n。
DATE_FIELDS = {
    "计划靠泊时间", "计划离泊时间", "开始时间", "通行时间", "派车时间", "返回时间",
    "完成时间", "发现时间", "提交时间", "计划时间", "实际时间", "检查日期",
}

# 金额字段：第 n 行取 12.5 * n（float，与历史样板保持一致）。
MONEY_FIELDS = {"应收金额", "已收金额"}

# 电话字段：第 n 行取 1380000000n。
PHONE_FIELDS = {"联系电话"}

# 每个模块生成几条样板行；三行覆盖「初始态 / 中间态 / 终态」三种状态。
ROWS_PER_MODULE = 3
