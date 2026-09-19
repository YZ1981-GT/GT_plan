#!/usr/bin/env python
"""附注存货章节结构对齐源模版（幂等修订）。

**目标**：把附注模板中存货章节被压平的两级表头恢复为源模版结构。

历史问题：源模版表格是两行表头（如「期末余额」跨 3 列，第二行为「账面余额 /
跌价准备 / 账面价值」），但 seed 只保留了第一行 ``headers``，第二行被降级成
``row_type: header_label`` 的数据行 → 前端渲染出「项目」「组合」这类假数据行，
且「按组合计提」4 张表只剩 2 个表头（应 7 列）。

**修订内容**（列结构以源模版为准，行集合不动）：

- 上市 §五、9：9 张表补 ``headers`` / ``columns`` / ``_column_groups``；
  重名「续：」改为可区分名；删 ``header_label`` 行；开发成本表头
  「期末余额/上年年末余额」→「期末数/上年年末数」（对齐源 xlsx 与同步 columns）
- 国企 §八、10：2 张表补列结构；``text_sections`` 追加源模版数据资源提示段

**权威源**：
- ``基础数据/附注模版/上市报表附注.md`` §存货
- ``基础数据/附注模版/国企报表附注.md`` §存货
- 列数校验口径：``backend/data/note_check_preset_formulas.json`` F9-1~F9-13a

**行集原则（Sprint 7 修订）**：seed 行以**运行时权威源 xlsx** 为准（见
``LISTED_CATEGORY_LABELS`` / ``SOE_CATEGORY_ROWS``），含第一轮遗漏的「委托加工物资」
「发出商品」。第一轮的「行不动原则」（以 ``基础数据/附注模版/*.md`` 为裁决者）已推翻：
该目录在本仓库不存在，无法核对；而底稿披露表常量已与 xlsx 一致，附注 seed 少行会让
未同步项目看到与源模板不符的骨架。seed 行只是骨架，用户数据一律经同步的
``sub_table_data`` 整表覆盖，故重建行集无数据丢失风险。

Usage::

    python backend/scripts/fix/fix_note_inventory_structure.py --dry-run
    python backend/scripts/fix/fix_note_inventory_structure.py
    python backend/scripts/fix/fix_note_inventory_structure.py --check

spec: .kiro/specs/f2-inventory-disclosure-template-alignment/ R4
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"

ALIGNED_BY = "f2-inventory-disclosure-template-alignment"

LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

LISTED_SECTION = "五、9"
SOE_SECTION = "八、10"


# ─────────────────────────── 行构造 ───────────────────────────

def _data_row(label: str = "") -> dict[str, Any]:
    return {"label": label, "row_type": "data"}


def _total_row(label: str = "合计") -> dict[str, Any]:
    return {"label": label, "is_total": True, "row_type": "total"}


def _strip_header_labels(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """删除 ``header_label`` 行：其语义已由 ``_column_groups`` 承载。"""
    return [r for r in rows if str(r.get("row_type", "")) != "header_label"]


# ── 分类行集（Sprint 7 / R18）：逐字逐序取自运行时权威源 xlsx ──────────────
#
# 源：backend/wp_templates/F/F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx
#   「附注披露信息（上市公司）」 r10~r19
#   「附注披露信息（国企）」     r9~r22
#
# 🔴 推翻第一轮的「行不动原则」：当时以 `基础数据/附注模版/*.md` 为附注侧行集裁决者，
# 但该目录在本仓库**不存在**（无法核对），而 xlsx 是运行时权威（`wp_template_init_service`
# 据此生成底稿）。底稿 `F2_LISTED_DISCLOSURE_CATEGORIES` / `F2_SOE_DISCLOSURE_CATEGORIES`
# 已与 xlsx 一致，只有附注 seed 骨架少行 → 未同步项目看到的骨架与源模板不符。
#
# 与前端常量的对应关系（同步载荷 `label` 必须逐字一致，否则 seed 骨架与同步结果异构）：
#   前端 useF2DisclosureListed.ts / useF2DisclosureSoe.ts
# 🔴 Sprint 8：补「开发成本」「开发产品」两个种类行。
# 源 xlsx 上市 r20 注：「根据企业具体情况分类，**房地产开发企业应增加"开发成本"
# "开发产品"等种类**」。原 9 类的取数键并集漏掉 1408/1409 → 房企存货审定数在上市
# 披露表没有落点。行位对齐国企语义归属：开发成本属在建/在产（紧随在产品）、
# 开发产品属产成品（紧随库存商品）。
LISTED_CATEGORY_LABELS: list[str] = [
    "原材料",
    "在产品",
    "开发成本",
    "委托加工物资",
    "库存商品",
    "开发产品",
    "发出商品",
    "周转材料",
    "合同履约成本",
    "消耗性生物资产",
    "数据资源",
]

# (label, is_detail)：`其中：` 行为上一行的子集，不计入合计（防双计）
SOE_CATEGORY_ROWS: list[tuple[str, bool]] = [
    ("原材料", False),
    ("自制半成品及在产品", False),
    ("其中：开发成本", True),
    ("委托加工物资", False),
    ("库存商品（产成品）", False),
    ("其中：开发产品", True),
    ("周转材料（包装物、低值易耗品等）", False),
    ("发出商品", False),
    ("消耗性生物资产", False),
    ("合同履约成本", False),
    ("数据资源", False),
    ("其他", False),
    # 源 xlsx 为半角开括号 `(由房地产开发企业填列）`（排版笔误）→ 归一为全角，
    # 与前端 `F2_SOE_DISCLOSURE_CATEGORIES` 推送的 label 逐字一致。
    ("其中：尚未开发的土地储备（由房地产开发企业填列）", True),
]


# ─────────────────────────── 列结构（逐字取自源模版） ───────────────────────────

_IMP_LABEL = "跌价准备/合同履约成本减值准备"


def _classification(end_group: str, prior_group: str, label_header: str) -> dict[str, Any]:
    """存货分类表：标签列 + {账面余额, 跌价准备, 账面价值} × 期末/期初两组。

    ``label_header`` 取自源 xlsx 的 A 列表头：上市 A8「存货种类」/ 国企 A7「项  目」
    （归一为「项目」）。
    """
    return {
        "headers": [
            label_header,
            "账面余额", _IMP_LABEL, "账面价值",
            "账面余额", _IMP_LABEL, "账面价值",
        ],
        "columns": [
            {"key": "label", "label": label_header, "is_label": True},
            {"key": "end_gross", "label": "账面余额", "group": end_group, "format": "amount"},
            {"key": "end_impairment", "label": _IMP_LABEL, "group": end_group, "format": "amount"},
            {"key": "end_net", "label": "账面价值", "group": end_group, "format": "amount"},
            {"key": "prior_gross", "label": "账面余额", "group": prior_group, "format": "amount"},
            {"key": "prior_impairment", "label": _IMP_LABEL, "group": prior_group, "format": "amount"},
            {"key": "prior_net", "label": "账面价值", "group": prior_group, "format": "amount"},
        ],
        "_column_groups": [
            {"group": end_group, "start": 1, "span": 3},
            {"group": prior_group, "start": 4, "span": 3},
        ],
    }


# 上市标签列头（源 xlsx A8/A22/A35 均为「存货种类」；旧值「项目」为第一轮误写）
LISTED_LABEL_HEADER = "存货种类"
# 国企存货分类标签列头（源 xlsx A7「项  目」→ 归一）
SOE_LABEL_HEADER = "项目"

# 上市跌价变动：本期减少为「转回或转销」单列（源模版上市版）
LISTED_MOVEMENT = {
    "headers": [LISTED_LABEL_HEADER, "期初余额", "计提", "其他", "转回或转销", "其他", "期末余额"],
    "columns": [
        {"key": "label", "label": LISTED_LABEL_HEADER, "is_label": True},
        {"key": "opening", "label": "期初余额", "format": "amount"},
        {"key": "increase_provision", "label": "计提", "group": "本期增加", "format": "amount"},
        {"key": "increase_other", "label": "其他", "group": "本期增加", "format": "amount"},
        {"key": "decrease_reversal", "label": "转回或转销", "group": "本期减少", "format": "amount"},
        {"key": "decrease_other", "label": "其他", "group": "本期减少", "format": "amount"},
        {"key": "ending", "label": "期末余额", "format": "amount"},
    ],
    "_column_groups": [
        {"group": "本期增加", "start": 2, "span": 2},
        {"group": "本期减少", "start": 4, "span": 2},
    ],
}

# 国企跌价变动：本期减少拆「转回 / 转销 / 其他」三列（源模版国企版）
SOE_MOVEMENT = {
    "headers": ["存货种类", "期初数", "计提", "其他", "转回", "转销", "其他", "期末数"],
    "columns": [
        {"key": "label", "label": "存货种类", "is_label": True},
        {"key": "opening", "label": "期初数", "format": "amount"},
        {"key": "increase_provision", "label": "计提", "group": "本期增加", "format": "amount"},
        {"key": "increase_other", "label": "其他", "group": "本期增加", "format": "amount"},
        {"key": "decrease_reversal", "label": "转回", "group": "本期减少", "format": "amount"},
        {"key": "decrease_writeoff", "label": "转销", "group": "本期减少", "format": "amount"},
        {"key": "decrease_other", "label": "其他", "group": "本期减少", "format": "amount"},
        {"key": "ending", "label": "期末数", "format": "amount"},
    ],
    "_column_groups": [
        {"group": "本期增加", "start": 2, "span": 2},
        {"group": "本期减少", "start": 4, "span": 3},
    ],
}

# 按组合计提：组合 + 账面余额{金额,比例} + 存货跌价准备{金额,计提标准,比例} + 账面价值
PORTFOLIO = {
    "headers": ["组合", "金额", "比例(%)", "金额", "计提标准", "比例(%)", "账面价值"],
    "columns": [
        {"key": "group_name", "label": "组合", "is_label": True},
        {"key": "balance", "label": "金额", "group": "账面余额", "format": "amount"},
        {"key": "balance_pct", "label": "比例(%)", "group": "账面余额", "format": "percent"},
        {"key": "impairment", "label": "金额", "group": "存货跌价准备", "format": "amount"},
        {"key": "provision_standard", "label": "计提标准", "group": "存货跌价准备"},
        {"key": "impairment_pct", "label": "比例(%)", "group": "存货跌价准备", "format": "percent"},
        {"key": "net_value", "label": "账面价值", "format": "amount"},
    ],
    "_column_groups": [
        {"group": "账面余额", "start": 1, "span": 2},
        {"group": "存货跌价准备", "start": 3, "span": 3},
    ],
}

# 确认为存货的数据资源：单级表头，5 列（F9-7~F9-13a 口径）
#
# 🔴 `flat: True` 标在标签列即对整表生效（`_extract_column_groups` 的三态之一）。
# 单级表头的表**必须**显式标 flat，否则 `_column_groups` 为 None → seed 路径回退
# `_infer_groups_from_headers` 前缀推断，会凭空造出父表头。实测（无 flat 时）：
#   开发产品 → {本期,span2} + {期末,span2}；周转房 → {本期,span2}；
#   开发成本 → {预计,span2}（把「预计竣工时间」与「预计总投资」凑成一组）
# 只给同步载荷加 flat 不够 —— 模板 JSON 的 columns 是 seed 路径的唯一来源。
DATA_RESOURCE_COLUMNS = [
    {"key": "label", "label": "项目", "is_label": True, "flat": True},
    {"key": "purchased", "label": "外购的数据资源存货", "format": "amount"},
    {"key": "self_processed", "label": "自行加工的数据资源存货", "format": "amount"},
    {"key": "other", "label": "其他方式取得的数据资源存货", "format": "amount"},
    {"key": "total", "label": "合计", "format": "amount"},
]


# ─────────────────────────── 编制提示（guidance）───────────────────────────
# `tables[].guidance` = 附注模块 TAB 页签的编制提示。
# 🔴 内容只许取：源 xlsx 红字括注 / 附注模版 md 的【】提示与（）括注 / 15 号文条款，
# 以「勾稽：」前缀标注工具侧校验口径。禁止按"常识"自造披露要求。
_G_CLASSIFICATION = (
    "按企业具体情况分类；房地产开发企业应增加「开发成本」「开发产品」等种类"
    "（源模版注）。勾稽：合计行 = 各分类行之和；账面价值 = 账面余额 − 跌价准备。"
)
_G_MOVEMENT = (
    "按存货种类披露跌价准备（含合同履约成本减值准备）的期初、本期增加（计提/其他）、"
    "本期减少（转回或转销/其他）与期末余额。证监会《2024年上市公司年报会计监管报告》："
    "已交付客户的发出商品应以合同约定价格减去预计将发生的成本、销售费用和相关税费为基础"
    "计提减值；超过预计时间未完成验收的定制化产品应分析原因充分计提，"
    "不应简单机械采用库龄法。勾稽：期末 = 期初 + 计提 + 其他增加 − 转回或转销 − 其他减少。"
)
_G_MOVEMENT_CONT = (
    "披露确定可变现净值的具体依据，及本期转回或转销存货跌价准备的原因（源模版【】提示）。"
    "本表为文字表，行集合与上表一致。"
)
_G_PORTFOLIO = (
    "15 号文第十九条（六）：按组合计提存货跌价准备的，应分类披露不同组合存货的期初余额、"
    "期末余额，对应跌价准备的期初余额、期末余额、计提标准和比例。"
    "⚠️ 本表与「按库龄组合计提存货跌价准备」在源模版中是「或」的关系（二选一），"
    "按实际计提方式只填其中一组，未采用的一组不填。"
    "勾稽：比例(%) = 跌价准备 ÷ 账面余额；账面价值 = 账面余额 − 跌价准备。"
)
_G_PORTFOLIO_AGING = (
    "适用于按库龄组合计提的情形（源模版：对于在同一地区生产和销售且具有相同或类似最终用途的"
    "存货合并计提，其中按库龄、保管状态、历史销售折扣及预计未来销售情况等因素计提）。"
    "15 号文第十六条（十二）：基于库龄确认可变现净值的，应披露各库龄组合可变现净值的"
    "计算方法和确定依据。⚠️ 与「按组合计提存货跌价准备」是「或」的关系（二选一）。"
    "行标签为库龄段（1年以内 / 1至2年 / …）。"
)
_G_DATA_RESOURCE = (
    "《企业数据资源相关会计处理暂行规定》：应披露确定发出数据资源存货成本所采用的方法；"
    "数据资源存货可变现净值的确定依据、跌价准备计提方法、当期计提与转回金额及有关情况；"
    "单独披露对财务报表具有重要影响的单项数据资源存货。"
    "《关于严格执行企业会计准则 切实做好企业2025年年报工作的通知》：不得将不符合资产定义和"
    "确认条件的数据资源确认为资产，不得将前期已费用化的数据资源重新资本化。"
    "勾稽（F9-7~F9-13a）：各段 期末 = 期初 + 本期增加 − 本期减少；"
    "账面价值 = 账面原值 − 跌价准备；合计列 = 外购 + 自行加工 + 其他方式；"
    "「其中」子项之和 ≤ 父项（仅告警）。"
)
_G_REAL_ESTATE = (
    "房地产开发企业按此格式披露（源模版注）。开发中项目列示跌价准备时可以合并列示；"
    "对「停工」「烂尾」「空置」项目应予关注。非房地产开发企业本表填「无」或不填。"
)


# ─────────────────────────── 修订计划 ───────────────────────────
# 按 section.tables 顺序逐条匹配（游标只前进），因此重名的「续：」由位置区分。

def _listed_plan() -> list[dict[str, Any]]:
    return [
        {
            "aliases": ["存货分类"],
            "patch": {
                **_classification("期末余额", "上年年末余额", LISTED_LABEL_HEADER),
                "guidance": _G_CLASSIFICATION,
            },
            "rows": "listed_categories",
        },
        {
            "aliases": ["存货跌价准备及合同履约成本减值准备"],
            "patch": {**LISTED_MOVEMENT, "guidance": _G_MOVEMENT},
            "rows": "listed_categories",
        },
        {
            "aliases": ["存货跌价准备及合同履约成本减值准备（续）"],
            "patch": {
                # headers 为纯文本：附注模版 md 里的 `<br/>` 只是 md 表格的排版换行，
                # 源 xlsx（B35/C35）无此标记。前端 `el-table-column :label` 是纯文本
                # 渲染 → 留着会把 `<br/>` 当字面量显示；Word 导出同理。
                "headers": [
                    LISTED_LABEL_HEADER,
                    "确定可变现净值/剩余对价与将要发生的成本的具体依据",
                    "本期转回或转销存货跌价准备/合同履约成本减值准备的原因",
                ],
                "columns": [
                    {"key": "label", "label": LISTED_LABEL_HEADER,
                     "is_label": True, "flat": True},
                    {"key": "nrv_basis",
                     "label": "确定可变现净值/剩余对价与将要发生的成本的具体依据"},
                    {"key": "reversal_reason",
                     "label": "本期转回或转销存货跌价准备/合同履约成本减值准备的原因"},
                ],
                "guidance": _G_MOVEMENT_CONT,
            },
            "rows": "listed_categories_qual",
        },
        {
            "aliases": ["按组合计提存货跌价准备"],
            "patch": {**PORTFOLIO, "guidance": _G_PORTFOLIO},
            "rows": "portfolio_blank",
        },
        {
            "aliases": ["续：", "按组合计提存货跌价准备（续）"],
            "new_name": "按组合计提存货跌价准备（续）",
            "patch": {**PORTFOLIO, "guidance": _G_PORTFOLIO + " 本表为上年年末余额（续表）。"},
            "rows": "portfolio_blank",
        },
        {
            # 源模版此表标题是一整段说明文字（已在 text_sections 中保留），
            # 表名收敛为可区分短名，避免 TAB 页签显示整段文字。
            "aliases": ["按库龄组合计提存货跌价准备"],
            "alias_prefixes": ["本公司对于在同一地区生产和销售"],
            "new_name": "按库龄组合计提存货跌价准备",
            "patch": {**PORTFOLIO, "guidance": _G_PORTFOLIO_AGING},
            "rows": "portfolio_aging",
        },
        {
            "aliases": ["续：", "按库龄组合计提存货跌价准备（续）"],
            "new_name": "按库龄组合计提存货跌价准备（续）",
            "patch": {
                **PORTFOLIO,
                "guidance": _G_PORTFOLIO_AGING + " 本表为上年年末余额（续表）。",
            },
            "rows": "portfolio_aging",
        },
        {
            "aliases": ["确认为存货的数据资源"],
            "patch": {"columns": DATA_RESOURCE_COLUMNS, "guidance": _G_DATA_RESOURCE},
            "rows": "keep",
        },
        {
            "aliases": ["开发成本"],
            "patch": {
                # 对齐源 xlsx 与同步 columns：期末数 / 上年年末数；headers 去 `<br/>`
                # （源 xlsx D67 为「预计总投资」，md 的 `<br/>` 是表格排版残留）
                "headers": [
                    "项目名称", "开工时间", "预计竣工时间", "预计总投资",
                    "期末数", "上年年末数", "期末跌价准备",
                ],
                "columns": [
                    # flat：源模版为单行表头；不标会被推断出凭空的「预计」父表头
                    {"key": "project_name", "label": "项目名称", "is_label": True, "flat": True},
                    {"key": "start_date", "label": "开工时间"},
                    {"key": "expected_complete_date", "label": "预计竣工时间"},
                    {"key": "estimated_investment", "label": "预计总投资", "format": "amount"},
                    {"key": "end_balance", "label": "期末数", "format": "amount"},
                    {"key": "prior_balance", "label": "上年年末数", "format": "amount"},
                    {"key": "end_impairment", "label": "期末跌价准备", "format": "amount"},
                ],
                "guidance": _G_REAL_ESTATE,
            },
            "rows": "keep",
        },
        {
            "aliases": ["开发产品"],
            "patch": {
                "columns": [
                    # flat：不标会被推断出凭空的「本期」+「期末」父表头
                    {"key": "project_name", "label": "项目名称", "is_label": True, "flat": True},
                    {"key": "complete_date", "label": "竣工时间"},
                    {"key": "opening", "label": "期初余额", "format": "amount"},
                    {"key": "increase", "label": "本期增加", "format": "amount"},
                    {"key": "decrease", "label": "本期减少", "format": "amount"},
                    {"key": "ending", "label": "期末余额", "format": "amount"},
                    {"key": "end_impairment", "label": "期末跌价准备", "format": "amount"},
                ],
                "guidance": _G_REAL_ESTATE + " 勾稽：期末余额 = 期初 + 本期增加 − 本期减少。",
            },
            "rows": "keep",
        },
        {
            "aliases": ["周转房"],
            "patch": {
                "columns": [
                    # flat：不标会被推断出凭空的「本期」父表头
                    {"key": "project_name", "label": "项目名称", "is_label": True, "flat": True},
                    {"key": "opening", "label": "期初余额", "format": "amount"},
                    {"key": "increase", "label": "本期增加", "format": "amount"},
                    {"key": "decrease", "label": "本期减少", "format": "amount"},
                    {"key": "ending", "label": "期末余额", "format": "amount"},
                ],
                "guidance": _G_REAL_ESTATE + " 勾稽：期末余额 = 期初 + 本期增加 − 本期减少。",
            },
            "rows": "keep",
        },
    ]


def _soe_plan() -> list[dict[str, Any]]:
    return [
        {
            "aliases": ["存货分类"],
            "patch": {
                **_classification("期末数", "期初数", SOE_LABEL_HEADER),
                "guidance": (
                    _G_CLASSIFICATION
                    + " 国企版「其他」项应说明房地产企业土地储备情况，包括土地储备面积、"
                    "本期增加及土地储备年末余额（源模版注）。"
                    "「其中：」行为上一行的子集，不计入合计（防双计）。"
                ),
            },
            "rows": "soe_categories",
        },
        {
            "aliases": ["存货跌价准备及合同履约成本减值准备"],
            "patch": {
                **SOE_MOVEMENT,
                "guidance": (
                    "按存货种类披露跌价准备的期初数、本期增加（计提/其他）、"
                    "本期减少（转回/转销/其他）与期末数。国企版本期减少细分为三列"
                    "（转回 / 转销 / 其他），与上市版两列不同。"
                    "「其中：」行为上一行的子集，不计入合计。"
                    "勾稽：期末 = 期初 + 计提 + 其他增加 − 转回 − 转销 − 其他减少。"
                ),
            },
            "rows": "soe_categories",
        },
        {
            "aliases": ["确认为存货的数据资源"],
            "patch": {"columns": DATA_RESOURCE_COLUMNS, "guidance": _G_DATA_RESOURCE},
            "rows": "keep",
        },
    ]


# 国企版源模版在数据资源表后有两段暂行规定说明 + 一段提示，seed 缺失 → 追加。
SOE_TEXT_ADDITIONS = [
    (
        "（《企业数据资源相关会计处理暂行规定》：（2）企业应当披露确定发出数据资源存货成本所采用的方法。"
        "（3）企业应当披露数据资源存货可变现净值的确定依据、存货跌价准备的计提方法、当期计提的存货跌价准备的金额、"
        "当期转回的存货跌价准备的金额，以及计提和转回的有关情况。"
        "（4）企业应当单独披露对企业财务报表具有重要影响的单项数据资源存货的内容、账面价值和可变现净值。"
        "（5）企业应当披露所有权或使用权受到限制的数据资源存货，以及用于担保的数据资源存货的账面价值等情况。"
    ),
    (
        "企业对数据资源进行评估且评估结果对企业财务报表具有重要影响的，应当披露评估依据的信息来源，"
        "评估结论成立的假设前提和限制条件，评估方法的选择，各重要参数的来源、分析、比较与测算过程等信息。）"
    ),
    "【提示：上述信息，若已在会计政策、其他项目附注中披露，可索引至相关内容。】",
]
SOE_TEXT_ANCHOR = "### 确认为存货的数据资源"
# 兼容旧锚点（retitle 之前落库的模板）
SOE_TEXT_ANCHOR_LEGACY = "确认为存货的数据资源"

# R22：国企侧小节标题原为裸字符串 → 被 `_is_table_title_paragraph` 判为正文，
# 在附注里渲染成一行没有内容的「存货分类」段落。上市侧本就是 `### xxx`，此处对齐。
SOE_TEXT_RETITLE: list[str] = [
    "存货分类",
    "存货跌价准备及合同履约成本减值准备",
    "确认为存货的数据资源",
    "借款费用资本化",
    "合同履约成本本期摊销金额的说明",
]


# ─────────────────────────── 应用 ───────────────────────────

def _rows_for(mode: str, existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if mode == "strip":
        return _strip_header_labels(existing)
    if mode == "portfolio_blank":
        return [_data_row(), _data_row(), _data_row(), _total_row()]
    if mode == "portfolio_aging":
        return [_data_row("1年以内"), _data_row("1至2年"), _data_row(), _total_row()]
    # ── R18：分类行集重建（seed 行是骨架，用户数据一律经 sub_table_data 整表覆盖）──
    if mode == "listed_categories":
        return [_data_row(x) for x in LISTED_CATEGORY_LABELS] + [_total_row()]
    if mode == "listed_categories_qual":
        # 续表为文字表，源 xlsx r45 合计行两列均为「--」→ 仍保留合计行占位
        return [_data_row(x) for x in LISTED_CATEGORY_LABELS] + [_total_row()]
    if mode == "soe_categories":
        rows: list[dict[str, Any]] = []
        for label, is_detail in SOE_CATEGORY_ROWS:
            row = _data_row(label)
            if is_detail:
                # 「其中：」子集行标记，供渲染缩进与合计防双计
                row["is_detail"] = True
            rows.append(row)
        return rows + [_total_row()]
    return existing


def _matches(table_name: str, rule: dict[str, Any]) -> bool:
    if table_name in rule["aliases"]:
        return True
    for pre in rule.get("alias_prefixes", []):
        if table_name.startswith(pre):
            return True
    return False


def _find_section(doc: dict[str, Any], section_number: str) -> dict[str, Any] | None:
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")) == section_number:
            return sec
    return None


def apply_plan(
    section: dict[str, Any],
    plan: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    """按计划就地修订 section.tables。

    Returns:
        (changes, warnings)
    """
    tables: list[dict[str, Any]] = section.get("tables") or []
    changes: list[str] = []
    warnings: list[str] = []
    cursor = 0

    for rule in plan:
        idx = next(
            (i for i in range(cursor, len(tables)) if _matches(str(tables[i].get("name", "")), rule)),
            None,
        )
        if idx is None:
            warnings.append(f"未找到表：{rule['aliases'][0]}（游标 {cursor}）→ 跳过")
            continue

        tbl = tables[idx]
        old_name = str(tbl.get("name", ""))
        new_name = rule.get("new_name")

        if new_name and old_name != new_name:
            # 新名已在别处存在 → 跳过迁移，避免造成重名歧义
            dup = next(
                (j for j, t in enumerate(tables) if j != idx and str(t.get("name", "")) == new_name),
                None,
            )
            if dup is not None:
                warnings.append(
                    f"表名迁移跳过：「{old_name}」→「{new_name}」，索引 {dup} 已占用该名（请人工确认）"
                )
            else:
                tbl["name"] = new_name
                changes.append(f"[{idx}] 表名：「{old_name}」→「{new_name}」")

        patch = rule["patch"]
        for key in ("headers", "columns", "_column_groups"):
            if key not in patch:
                continue
            if tbl.get(key) != patch[key]:
                old_len = len(tbl.get(key) or [])
                tbl[key] = json.loads(json.dumps(patch[key], ensure_ascii=False))
                changes.append(
                    f"[{idx}] {tbl.get('name')}.{key}：{old_len} → {len(patch[key])} 项"
                )

        # guidance = TAB 页签编制提示（字符串，非列表 → 单独处理）
        if "guidance" in patch and tbl.get("guidance") != patch["guidance"]:
            had = bool(tbl.get("guidance"))
            tbl["guidance"] = patch["guidance"]
            changes.append(
                f"[{idx}] {tbl.get('name')}.guidance：{'更新' if had else '新增'}"
                f"（{len(patch['guidance'])} 字）"
            )

        rows_mode = rule.get("rows", "keep")
        if rows_mode != "keep":
            old_rows = tbl.get("rows") or []
            new_rows = _rows_for(rows_mode, old_rows)
            if new_rows != old_rows:
                tbl["rows"] = new_rows
                changes.append(
                    f"[{idx}] {tbl.get('name')}.rows：{len(old_rows)} → {len(new_rows)} 行"
                    f"（{rows_mode}）"
                )

        cursor = idx + 1

    return changes, warnings


def retitle_text_sections(section: dict[str, Any], plain_titles: list[str]) -> list[str]:
    """把裸标题段升级为 ``### 标题``（幂等：已有 `###` 版本则不动）。"""
    texts: list[str] = section.setdefault("text_sections", [])
    changes: list[str] = []
    for plain in plain_titles:
        marked = f"### {plain}"
        if marked in texts:
            continue
        if plain not in texts:
            continue
        texts[texts.index(plain)] = marked
        changes.append(f"text_sections 标题标记：「{plain}」→「{marked}」")
    return changes


def append_text_sections(
    section: dict[str, Any],
    additions: list[str],
    anchor: str | None,
    anchor_legacy: str | None = None,
) -> list[str]:
    """在 anchor 之后插入缺失文本段（精确串查重 → 幂等）。"""
    texts: list[str] = section.setdefault("text_sections", [])
    missing = [t for t in additions if t not in texts]
    if not missing:
        return []

    pos = len(texts)
    for cand in (anchor, anchor_legacy):
        if cand and cand in texts:
            pos = texts.index(cand) + 1
            break
    texts[pos:pos] = missing
    return [f"text_sections 追加 {len(missing)} 段（位置 {pos}）"]


def _stamp(section: dict[str, Any]) -> None:
    section["_aligned_by"] = ALIGNED_BY
    section["_aligned_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────── 校验 ───────────────────────────

def validate_section(section: dict[str, Any]) -> list[str]:
    """结构自洽校验（Property 6 / 7 + 无 header_label + 表名唯一）。"""
    errs: list[str] = []
    tables = section.get("tables") or []
    seen: dict[str, int] = {}

    for i, tbl in enumerate(tables):
        name = str(tbl.get("name", ""))
        if name in seen:
            errs.append(f"[{i}] 表名重复：「{name}」（首现于 {seen[name]}）")
        seen[name] = i

        headers = tbl.get("headers") or []
        n_val = max(len(headers) - 1, 0)

        for j, row in enumerate(tbl.get("rows") or []):
            if str(row.get("row_type", "")) == "header_label":
                errs.append(f"[{i}] {name} 第 {j} 行仍为 header_label")
            vals = row.get("values")
            if isinstance(vals, list) and len(vals) != n_val:
                errs.append(
                    f"[{i}] {name} 第 {j} 行 values={len(vals)} ≠ headers-1={n_val}"
                )

        groups = tbl.get("_column_groups")
        if groups:
            occupied: set[int] = set()
            for g in groups:
                start, span = int(g.get("start", 0)), int(g.get("span", 0))
                if start < 1:
                    errs.append(f"[{i}] {name} 分组「{g.get('group')}」start={start} < 1")
                if start + span > len(headers):
                    errs.append(
                        f"[{i}] {name} 分组「{g.get('group')}」越界："
                        f"{start}+{span} > {len(headers)}"
                    )
                rng = set(range(start, start + span))
                if rng & occupied:
                    errs.append(f"[{i}] {name} 分组「{g.get('group')}」区间重叠")
                occupied |= rng

        cols = tbl.get("columns")
        if cols and len(cols) != len(headers):
            errs.append(f"[{i}] {name} columns={len(cols)} ≠ headers={len(headers)}")

        # ── seed 路径守卫（Sprint 7）──────────────────────────────
        # 每张表必须在 `_column_groups` 与 `columns[].flat` 之间明确表态，否则
        # seed 渲染回退 `_infer_groups_from_headers` 前缀推断 → 凭空父表头。
        if cols:
            has_flat = any(isinstance(c, dict) and c.get("flat") for c in cols)
            has_group = any(isinstance(c, dict) and c.get("group") for c in cols)
            if not has_flat and not has_group:
                errs.append(
                    f"[{i}] {name} 既无 columns[].group 也无 columns[].flat "
                    f"→ seed 路径会被前缀推断塞凭空父表头，请显式标 flat"
                )
            if has_flat and has_group:
                errs.append(f"[{i}] {name} 同时声明 flat 与 group（语义冲突）")

        # guidance = TAB 编制提示，全表必备（K1 已启用的平台范式）
        if not str(tbl.get("guidance") or "").strip():
            errs.append(f"[{i}] {name} 缺 guidance（附注 TAB 编制提示）")

        # headers 必须是纯文本：`el-table-column :label` 与 Word 导出都不解析 HTML，
        # 留着 md 搬来的 `<br/>` 会当字面量显示。
        for h in headers:
            if "<" in str(h) and ">" in str(h):
                errs.append(f"[{i}] {name} headers 含 HTML 标记：{h!r}（应为纯文本）")

        # headers 与 columns[].label 必须逐位一致（否则表头与列定义两套说法）
        if cols and len(cols) == len(headers):
            for k, (h, c) in enumerate(zip(headers, cols)):
                if not isinstance(c, dict):
                    continue
                if str(c.get("label") or "") != str(h):
                    errs.append(
                        f"[{i}] {name} 第 {k} 列 headers={h!r} ≠ columns.label={c.get('label')!r}"
                    )

    return errs


# ─────────────────────────── 入口 ───────────────────────────

def _process(
    path: Path,
    section_number: str,
    plan: list[dict[str, Any]],
    text_additions: list[str],
    text_anchor: str | None,
    text_retitle: list[str] | None = None,
    *,
    dry_run: bool,
    check_only: bool,
) -> tuple[bool, list[str]]:
    raw = path.read_text(encoding="utf-8")
    doc = json.loads(raw)
    section = _find_section(doc, section_number)
    if section is None:
        return False, [f"[FATAL] {path.name} 未找到 section_number={section_number}"]

    log: list[str] = [f"=== {path.name} §{section_number} {section.get('section_title')} ==="]

    if check_only:
        errs = validate_section(section)
        aligned = section.get("_aligned_by") == ALIGNED_BY
        log.append(f"_aligned_by={section.get('_aligned_by')!r}")
        if not aligned:
            errs.append("尚未对齐（缺 _aligned_by 标记）")
        log.extend(errs or ["结构校验通过"])
        return not errs, log

    changes, warnings = apply_plan(section, plan)
    if text_retitle:
        changes += retitle_text_sections(section, text_retitle)
    if text_additions:
        changes += append_text_sections(
            section, text_additions, text_anchor, SOE_TEXT_ANCHOR_LEGACY,
        )

    log.extend(changes or ["无需修改（已对齐）"])
    log.extend(f"[WARN] {w}" for w in warnings)

    errs = validate_section(section)
    if errs:
        log.append("[FATAL] 修订后结构校验失败，未写入：")
        log.extend(f"  {e}" for e in errs)
        return False, log

    log.append(f"结构校验通过（{len(section.get('tables') or [])} 张表）")

    if dry_run:
        log.append("[dry-run] 未写文件")
        return True, log

    # 无实际变更且已打标 → 不重写（避免空跑刷新 _aligned_at 产生无谓 diff）
    if not changes and section.get("_aligned_by") == ALIGNED_BY:
        log.append("已对齐且无变更，跳过写入")
        return True, log

    _stamp(section)
    # 保留各文件原有尾换行约定，避免整文件级 diff
    trailing = "\n" if raw.endswith("\n") else ""
    path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + trailing,
        encoding="utf-8",
    )
    log.append(f"已写入 {path}")
    return True, log


def main() -> int:
    ap = argparse.ArgumentParser(description="附注存货章节结构对齐源模版（幂等）")
    ap.add_argument("--dry-run", action="store_true", help="只打印 diff 摘要，不写文件")
    ap.add_argument("--check", action="store_true", help="仅校验对齐状态（供 CI）")
    args = ap.parse_args()

    targets = [
        (LISTED_PATH, LISTED_SECTION, _listed_plan(), [], None, None),
        (
            SOE_PATH, SOE_SECTION, _soe_plan(),
            SOE_TEXT_ADDITIONS, SOE_TEXT_ANCHOR, SOE_TEXT_RETITLE,
        ),
    ]

    ok_all = True
    for path, section_number, plan, texts, anchor, retitle in targets:
        ok, log = _process(
            path, section_number, plan, texts, anchor, retitle,
            dry_run=args.dry_run, check_only=args.check,
        )
        print("\n".join(log))
        print()
        ok_all = ok_all and ok

    if not ok_all:
        print("[FAIL] 存在未通过项")
        return 1
    print("[OK] 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
