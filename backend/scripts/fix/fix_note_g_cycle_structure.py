#!/usr/bin/env python
"""附注 G 循环（金融工具）披露章节结构对齐源模版（幂等修订）。

**目标**：为 `disclosure-sync-path-buildout` 批 1 的 G 循环章节补齐同步链路所需的
模板前置条件 —— 表名可用、`columns` 明确表态、`guidance` 齐备、行骨架对齐源模版。

`diagnose_disclosure_sheet_vs_template.py --cycle G*` 跑出的 G 循环欠账（2026-07-30）：

- **66 张表全部 `columns` 未表态**（seed 路径会被 `_infer_groups_from_headers`
  按前缀反猜出凭空父表头）
- **66 张表全部无 `guidance`**（附注 TAB 页签无编制提示）
- 3 个章节（G4/G5/G6 上市）存在裸 `续：` 表名 + headers 被 md 重建脚本压扁
- G5 上市有 5 张重名 `组合计提项目：XXX`（按 name 建键会互相覆盖丢表）
- 多处表名是**表头首格**（`项  目` / `种  类`）→ 附注 TAB 页签显示列名而非表名

本脚本按 `--cycle` 分批修订，当前已覆盖 **G8 / G9 / G12**（结构干净、共 8 张表）。
G4/G5/G6 的压扁表头重建单独追加（表数多且需逐小节核对源 xlsx）。

**权威源**（冲突裁决见 `disclosure-sync-path-buildout` design）：

- 🔴 源 xlsx = ``backend/wp_templates/G/*.xlsx``（**运行时权威**：`wp_template_init_service`
  生成底稿时从这里复制，`wp_template_finder` 以 `_index.json` 索引）。
  ``基础数据/致同通用审计程序及底稿模板…`` 只是参考副本，**已实测落后**：G4/G5/G6 三个循环
  两处不一致（权威版增补「项目N（可改名）」占位行与「（预留，可填或在本区内插入行）」
  预留区、加了 6 条「编制说明」；G4 国企把三阶段用语统一为「减值准备」；
  G6/G4 上市阶段表只有「期末第一阶段」末列是「理由」；G5 删掉了
  「应收保证金 / 应收关联方款项」两行）。G8/G9/G10/G11/G12 两处字节一致。
  2026-07-30 曾因先读参考副本导致 G4/G5/G6 按旧版重建，已按权威版重做。
- ``附注模版/{上市,国企}报表附注_单体.md``（**附注侧列结构裁决者**：附注是交付物）
- ``backend/data/note_template_variant_matrix.json``（章节号）

裁决要点：

- **G9 国企行骨架取源 xlsx 的 4 个分类**（债务工具投资 / 权益工具投资 /
  指定为以公允价值计量且其变动计入当期损益的金融资产 / 其他）。附注模版 md 该表是
  3 个空行，但上市侧 md 与 xlsx **都**列了这 4 类，国企 xlsx 亦然 → 空行是 md 简写，
  按 xlsx 补齐分类骨架（同步时仍由底稿整表覆盖）。
- **G8 上市第 2 张表名取国企侧的「期末其他权益工具投资情况」**：上市源模版该表**无**
  小节标题（只有 15 号文括注），seed 因此拿表头首格 `项  目` 当表名。同一张表在国企
  源模版里有正式小节名（`（2）期末其他权益工具投资情况`）→ 借用同一套致同措辞，
  不自造。两个 variant 在不同文件里，不冲突。
- **列结构全部单级**（源模版均为一行表头）→ 每张表标 `flat`，并删除 seed 可能误留的
  `_column_groups`。

Usage::

    python backend/scripts/fix/fix_note_g_cycle_structure.py --dry-run
    python backend/scripts/fix/fix_note_g_cycle_structure.py --cycle G9
    python backend/scripts/fix/fix_note_g_cycle_structure.py
    python backend/scripts/fix/fix_note_g_cycle_structure.py --check

spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2
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

ALIGNED_BY = "disclosure-sync-path-buildout"

TEMPLATE_PATH = {
    "listed": DATA_DIR / "note_template_listed.json",
    "soe": DATA_DIR / "note_template_soe.json",
}

AMOUNT = "amount"


# ─────────────────────────── 行构造 ───────────────────────────

def _data(label: str = "") -> dict[str, Any]:
    return {"label": label, "row_type": "data"}


def _total(label: str = "合计") -> dict[str, Any]:
    return {"label": label, "is_total": True, "row_type": "total"}


def _subtotal(label: str = "小计") -> dict[str, Any]:
    return {"label": label, "is_total": True, "row_type": "subtotal"}


def _blanks_then_total(n: int) -> list[dict[str, Any]]:
    return [_data() for _ in range(n)] + [_total()]


def _labels_then_total(labels: list[str]) -> list[dict[str, Any]]:
    return [_data(x) for x in labels] + [_total()]


def _flat_columns(pairs: list[tuple[str, str, str | None]]) -> list[dict[str, Any]]:
    """单级表头列定义：`(key, label, format)`，首列自动标 `is_label` + `flat`。"""
    out: list[dict[str, Any]] = []
    for i, (key, label, fmt) in enumerate(pairs):
        col: dict[str, Any] = {"key": key, "label": label}
        if i == 0:
            col["is_label"] = True
            col["flat"] = True
        if fmt:
            col["format"] = fmt
        out.append(col)
    return out


def _grouped_columns(
    label: tuple[str, str],
    specs: list[tuple[str, str, str | None, str | None]],
) -> list[dict[str, Any]]:
    """两级表头列定义。

    Args:
        label: 标签列 `(key, label)`（对应源模版 rowspan=2 的首列）
        specs: `(key, label, format, group|None)`；``group=None`` 表示该列本身是
            rowspan=2 的独立列（如 G5 的「折现率区间」），不进任何父表头。

    🔴 平台只支持**两级**表头（`ColumnDef.group` → `_column_groups`）。源模版若是
    三级（G5「坏账准备计提情况」= 期末余额>账面余额>金额），按「父级取期间、
    子级用限定名（`账面余额-金额`）」投影，信息不丢且两个区分维度都保留 —— **不新建机制**。
    """
    out: list[dict[str, Any]] = [{"key": label[0], "label": label[1], "is_label": True}]
    for key, lbl, fmt, group in specs:
        col: dict[str, Any] = {"key": key, "label": lbl}
        if group:
            col["group"] = group
        if fmt:
            col["format"] = fmt
        out.append(col)
    return out


def _derive_column_groups(cols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从 columns 派生 `_column_groups`（`start` 为 headers 下标，标签列占 0）。

    与后端 `note_sub_table_projector._extract_column_groups` 同口径：相邻同名 group 合并。
    """
    groups: list[dict[str, Any]] = []
    idx = 1
    for col in cols[1:]:
        name = col.get("group")
        if not name:
            idx += 1
            continue
        last = groups[-1] if groups else None
        if last and last["group"] == name and last["start"] + last["span"] == idx:
            last["span"] += 1
        else:
            groups.append({"group": name, "start": idx, "span": 1})
        idx += 1
    return groups


def _headers_of(cols: list[dict[str, Any]]) -> list[str]:
    """headers = 各列 label（两级表头时是**叶子**列名，父表头由 `_column_groups` 承载）。"""
    return [str(c["label"]) for c in cols]


# ─────────────────────────── 表名常量 ───────────────────────────
# 🔴 每个值必须与前端 `g{n}DisclosureSyncPayload.ts` 的 sub_table_data 键逐字一致，
#    否则同步产出孤儿子表（附注 TAB 永空 + 底稿数据丢失）。

T_G12 = "净敞口套期收益"
T_G12_LISTED_OBSOLETE = "项  目"

T_G9 = "其他非流动金融资产"
T_G9_LISTED_OBSOLETE = "种  类"

T_G8_LISTED_MAIN = "其他权益工具投资"
T_G8_SOE_MAIN = "其他权益工具投资情况"
T_G8_DETAIL = "期末其他权益工具投资情况"
T_G8_LISTED_DETAIL_OBSOLETE = "项  目"

G9_CATEGORY_ROWS = [
    "债务工具投资",
    "权益工具投资",
    "指定为以公允价值计量且其变动计入当期损益的金融资产",
    "其他",
]

_G15_ART19_9 = (
    "（15号文第十九条（九）分项列示其他权益工具投资期初余额、期末余额、本期计入其他综合"
    "收益的利得和损失、本期末累计计入其他综合收益的利得和损失、本期确认的股利收入以及"
    "指定为以公允价值计量且其变动计入其他综合收益的原因。本期存在终止确认的，应分项披露"
    "终止确认的原因，以及因终止确认转入留存收益的累计利得和损失。）"
)

_G8_DESIGNATION_REASON = (
    "【披露企业将上述各项目指定为以公允价值计量且其变动计入其他综合收益的原因。】"
)


# ─────────────────────────── 修订计划 ───────────────────────────
# 每个 cycle → {variant: {"section": 章节号, "plan": [...], "expected": [表名]}}
# plan 条目：aliases（按 tables 顺序游标匹配）/ new_name / headers / columns / rows / guidance

SECTION_PLANS: dict[str, dict[str, dict[str, Any]]] = {
    "G12": {
        "listed": {
            "section": "五、70",
            "plan": [
                {
                    "aliases": [T_G12_LISTED_OBSOLETE, T_G12],
                    "new_name": T_G12,
                    "headers": ["项目", "本期发生额", "上期发生额"],
                    "columns": _flat_columns([
                        ("label", "项目", None),
                        ("current_amount", "本期发生额", AMOUNT),
                        ("prior_amount", "上期发生额", AMOUNT),
                    ]),
                    "rows": _blanks_then_total(3),
                    "guidance": (
                        "按上市公司口径列示净敞口套期收益（6103）本期 / 上期发生额。"
                        "勾稽：各明细行之和 = 合计行（本期 / 上期各独立校验）；"
                        "合计行本期发生额 = G12-1 审定表审定数（6103）；"
                        "分项来源应与 G12-2 套期明细表一致。"
                    ),
                },
            ],
        },
        "soe": {
            "section": "八、71",
            "plan": [
                {
                    "aliases": [T_G12],
                    "headers": ["产生净敞口套期收益的来源", "本期发生额", "上期发生额"],
                    "columns": _flat_columns([
                        ("label", "产生净敞口套期收益的来源", None),
                        ("current_amount", "本期发生额", AMOUNT),
                        ("prior_amount", "上期发生额", AMOUNT),
                    ]),
                    "rows": _labels_then_total([
                        "净敞口套期下被套期项目累计公允价值变动转入当期损益的金额",
                        "净敞口套期下现金流量套期储备转入当期损益的金额",
                    ]),
                    "guidance": (
                        "按国企口径分两项来源列示（被套期项目累计公允价值变动转入损益、"
                        "现金流量套期储备转入损益）。"
                        "勾稽：两项来源之和 = 合计行；合计行本期发生额 = G12-1 审定数（6103）；"
                        "来源金额应与 G12-2 套期明细表的有效 / 无效部分拆分一致。"
                    ),
                },
            ],
        },
    },
    "G9": {
        "listed": {
            "section": "五、20",
            "plan": [
                {
                    "aliases": [T_G9_LISTED_OBSOLETE, T_G9],
                    "new_name": T_G9,
                    "headers": ["种类", "期末余额", "上年年末余额"],
                    "columns": _flat_columns([
                        ("label", "种类", None),
                        ("end_balance", "期末余额", AMOUNT),
                        ("prior_balance", "上年年末余额", AMOUNT),
                    ]),
                    "rows": _labels_then_total(G9_CATEGORY_ROWS),
                    "guidance": (
                        "按种类列示其他非流动金融资产期末 / 上年年末余额。"
                        "勾稽：各种类行之和 = 合计行（期末 / 上年年末各独立校验）；"
                        "合计行期末余额 = 资产负债表「其他非流动金融资产」期末数"
                        " = G9-1 审定表审定数；分类口径应与 G9 估值层级表一致。"
                    ),
                },
            ],
        },
        "soe": {
            "section": "八、20",
            "plan": [
                {
                    "aliases": [T_G9],
                    "headers": ["项目", "期末公允价值", "期初公允价值"],
                    "columns": _flat_columns([
                        ("label", "项目", None),
                        ("end_fair_value", "期末公允价值", AMOUNT),
                        ("opening_fair_value", "期初公允价值", AMOUNT),
                    ]),
                    "rows": _labels_then_total(G9_CATEGORY_ROWS),
                    "guidance": (
                        "按国企口径列示其他非流动金融资产期末 / 期初公允价值。"
                        "勾稽：各项目行之和 = 合计行（期末 / 期初各独立校验）；"
                        "合计行期末公允价值 = 资产负债表「其他非流动金融资产」期末数"
                        " = G9-1 审定表审定数；公允价值应与 G9 估值层级表（L1/L2/L3）合计一致。"
                    ),
                },
            ],
        },
    },
    "G8": {
        "listed": {
            "section": "五、19",
            "plan": [
                {
                    "aliases": [T_G8_LISTED_MAIN],
                    "headers": ["项目", "期末余额", "上年年末余额"],
                    "columns": _flat_columns([
                        ("label", "项目", None),
                        ("end_balance", "期末余额", AMOUNT),
                        ("prior_balance", "上年年末余额", AMOUNT),
                    ]),
                    "rows": _blanks_then_total(3),
                    "guidance": (
                        _G15_ART19_9
                        + _G8_DESIGNATION_REASON
                        + "勾稽：各明细行之和 = 合计行（期末 / 上年年末各独立校验）；"
                        "合计行期末余额 = 资产负债表「其他权益工具投资」期末数"
                        " = G8-1 审定表审定数。"
                    ),
                },
                {
                    "aliases": [T_G8_LISTED_DETAIL_OBSOLETE, T_G8_DETAIL],
                    "new_name": T_G8_DETAIL,
                    "headers": [
                        "项目",
                        "本期计入其他综合收益的利得和损失",
                        "本期末累计计入其他综合收益的利得和损失",
                        "本期确认的股利收入",
                        "因终止确认转入留存收益的累计利得和损失",
                        "终止确认的原因",
                    ],
                    "columns": _flat_columns([
                        ("label", "项目", None),
                        ("oci_current", "本期计入其他综合收益的利得和损失", AMOUNT),
                        ("oci_cumulative", "本期末累计计入其他综合收益的利得和损失", AMOUNT),
                        ("dividend_income", "本期确认的股利收入", AMOUNT),
                        ("derecognition_to_re", "因终止确认转入留存收益的累计利得和损失", AMOUNT),
                        ("derecognition_reason", "终止确认的原因", None),
                    ]),
                    "rows": [_data() for _ in range(3)],
                    "guidance": (
                        _G15_ART19_9
                        + "本表逐项目列示，项目集合须与上表「其他权益工具投资」一致。"
                        "勾稽：本期计入其他综合收益的利得和损失合计 = 所有者权益变动表"
                        "「其他综合收益」中其他权益工具公允价值变动部分；"
                        "存在终止确认时，「因终止确认转入留存收益的累计利得和损失」与"
                        "「终止确认的原因」不得为空。"
                    ),
                },
            ],
        },
        "soe": {
            "section": "八、19",
            "plan": [
                {
                    "aliases": [T_G8_SOE_MAIN],
                    "headers": ["项目", "期末余额", "期初余额"],
                    "columns": _flat_columns([
                        ("label", "项目", None),
                        ("end_balance", "期末余额", AMOUNT),
                        ("opening_balance", "期初余额", AMOUNT),
                    ]),
                    "rows": _blanks_then_total(3),
                    "guidance": (
                        _G8_DESIGNATION_REASON
                        + "勾稽：各明细行之和 = 合计行（期末 / 期初各独立校验）；"
                        "合计行期末余额 = 资产负债表「其他权益工具投资」期末数"
                        " = G8-1 审定表审定数。"
                    ),
                },
                {
                    "aliases": [T_G8_DETAIL],
                    "headers": [
                        "项目名称",
                        "本期确认的股利收入",
                        "本期计入其他综合收益的利得或损失",
                        "截至期末累计计入其他综合收益的利得或损失",
                        "其他综合收益转入留存收益的金额",
                        "其他综合收益转入留存收益的原因",
                    ],
                    "columns": _flat_columns([
                        ("label", "项目名称", None),
                        ("dividend_income", "本期确认的股利收入", AMOUNT),
                        ("oci_current", "本期计入其他综合收益的利得或损失", AMOUNT),
                        ("oci_cumulative", "截至期末累计计入其他综合收益的利得或损失", AMOUNT),
                        ("oci_to_re", "其他综合收益转入留存收益的金额", AMOUNT),
                        ("oci_to_re_reason", "其他综合收益转入留存收益的原因", None),
                    ]),
                    "rows": _blanks_then_total(4),
                    "guidance": (
                        "本表逐项目列示，项目集合须与上表「其他权益工具投资情况」一致。"
                        "勾稽：各明细行之和 = 合计行（每个金额列独立校验）；"
                        "「本期计入其他综合收益的利得或损失」合计 = 所有者权益变动表"
                        "「其他综合收益」中其他权益工具公允价值变动部分；"
                        "「其他综合收益转入留存收益的金额」非零时，转入原因不得为空。"
                    ),
                },
            ],
        },
    },
}


# ═══════════════════════ G4 / G5 / G6（压扁表头重建） ═══════════════════════
#
# 这三个循环的上市章节被 `rebuild_note_from_md.py` 压扁得最重：两级表头只留了第一行，
# 第二行降级成 `row_type: header_label` 的**假数据行**；`续：` 成了裸表名；
# G5 上市还有 5 张同名 `组合计提项目：XXX`（按 name 建键会互相覆盖丢表）。
#
# 权威：源 xlsx 逐 sheet 精读（含合并单元格）+ `附注模版/{上市,国企}报表附注_单体.md`。
# 冲突裁决（列结构随**附注模版**，底稿可多留审计列）：
#   - 上市三阶段表末列 = `划分依据`（md），国企 = `理由`（md + xlsx 一致）；
#     上市 xlsx 第一阶段写「理由」属底稿笔误，不采纳。
#   - G5 国企 §八、17 的「坏账准备计提情况」**附注模版无表**（只有「参考附注八、5 /
#     八、8」的交叉引用），故国企侧**不加**坏账准备系列表（宁缺勿造）；那些表留在底稿侧。
#   - G6 国企「减值准备计提情况」同理：附注模版只写「参照附注八、15 债权投资」→ 不加表。

_ECL_STAGE_ROWS_LISTED = [
    _data("按单项计提减值准备"), _data("其中："), _data(), _data(),
    _data("按组合计提减值准备"), _data("其中："), _data(), _data(),
    _total(),
]
# 🔴 G4 国企：权威模板 R93 明确「三阶段用语统一为『减值准备』」（旧参考副本写「坏账准备」）。
#    G6 国企仍用「坏账准备」（其权威副本 R24/R28 如此）→ 两者不可互相套用。
_ECL_STAGE_ROWS_SOE = [
    _data("按单项计提减值准备"), _data("其中："), _data(), _data(),
    _data("按组合计提减值准备"), _data("其中："), _data(), _data(),
    _total(),
]

# 三阶段迁移表（本期计提、收回或转回）——两级表头：第N阶段 > 具体损失口径
_STAGE_MOVE_SPECS = [
    ("stage1", "未来12个月预期信用损失", AMOUNT, "第一阶段"),
    ("stage2", "整个存续期预期信用损失（未发生信用减值）", AMOUNT, "第二阶段"),
    ("stage3", "整个存续期预期信用损失（已发生信用减值）", AMOUNT, "第三阶段"),
    ("total", "合计", AMOUNT, None),
]
_STAGE_MOVE_ROW_LABELS = [
    "期初余额", "期初余额在本期",
    "--转入第二阶段", "--转入第三阶段", "--转回第二阶段", "--转回第一阶段",
    "本期计提", "本期转回", "本期转销", "本期核销", "其他变动", "期末余额",
]
_STAGE_MOVE_ROW_LABELS_SOE = [
    "期初余额", "期初余额在本期",
    "—转入第二阶段", "—转入第三阶段", "—转回第二阶段", "—转回第一阶段",
    "本期计提", "本期转回", "本期转销", "本期核销", "其他变动", "期末余额",
]

_ECL_INPUT_GUIDANCE = (
    "【15号文第十九条（十一）】披露减值输入值、假设及信用风险是否显著增加的判断依据。"
)

# 权威模板「编制说明」第 3 条（G4 R170 / G6 R177）
_STAGE_JUDGEMENT_NOTE = (
    "按 CAS 22 三阶段披露：一阶段用未来12个月 ECL，二 / 三阶段用整个存续期 ECL；"
    "「划分依据」须说明信用风险是否显著增加 / 已发生信用减值的判断。"
    "「其中：」为可扩展区（默认 1 行明细 + 预留行），只在「按单项 / 按组合」与下一父行之间"
    "填写或插入行，勿改父行 SUM 起止边界。"
)


def _LISTED_STAGE_SPECS(account: str) -> list[tuple[str, str, str]]:
    """上市侧 6 张阶段表：`(表名, 损失率列名, 末列名)`。

    🔴 末列**只有「期末第一阶段」是「理由」**，其余 5 张是「划分依据」
    （权威模板 G4 R39 vs R56/R73/R92/R109/R126；G6 R46 vs R63/R80/R99/R116/R133）。
    旧参考副本此处不一致，曾被统一写成「划分依据」。
    """
    m12 = "未来12个月内预期信用损失率(%)"
    life = "整个存续期预期信用损失率(%)"
    return [
        (f"期末处于第一阶段的{account}的减值准备", m12, "理由"),
        (f"期末处于第二阶段的{account}的减值准备", life, "划分依据"),
        (f"期末处于第三阶段的{account}的减值准备", life, "划分依据"),
        (f"上年年末处于第一阶段的{account}的减值准备", m12, "划分依据"),
        (f"上年年末处于第二阶段的{account}的减值准备", life, "划分依据"),
        (f"上年年末处于第三阶段的{account}的减值准备", life, "划分依据"),
    ]
_WRITEOFF_GUIDANCE = (
    "【15号文第十九条（八）2.列示本期实际核销的债权投资、其他债权投资金额。对于其中重要的"
    "款项，应逐项披露款项性质、核销原因、履行的核销程序及核销金额。实际核销的款项由关联"
    "交易产生的，应单独披露。】"
)


def _three_col_book_value(end_group: str, prior_group: str, provision_label: str) -> list[dict[str, Any]]:
    """账面余额 / 减值(坏账)准备 / 账面价值 × 期末·期初 两组（7 列两级表头）。"""
    return _grouped_columns(
        ("label", "项目"),
        [
            ("end_gross", "账面余额", AMOUNT, end_group),
            ("end_provision", provision_label, AMOUNT, end_group),
            ("end_net", "账面价值", AMOUNT, end_group),
            ("prior_gross", "账面余额", AMOUNT, prior_group),
            ("prior_provision", provision_label, AMOUNT, prior_group),
            ("prior_net", "账面价值", AMOUNT, prior_group),
        ],
    )


def _important_bond_cols(group: str, prefix: str) -> list[dict[str, Any]]:
    """期末重要的（其他）债权投资：面值/票面利率/实际利率/到期日/逾期本金（5 列 + 标签）。"""
    return _grouped_columns(
        ("label", "项目"),
        [
            (f"{prefix}_face_value", "面值", AMOUNT, group),
            (f"{prefix}_coupon_rate", "票面利率", None, group),
            (f"{prefix}_effective_rate", "实际利率", None, group),
            (f"{prefix}_maturity_date", "到期日", None, group),
            (f"{prefix}_overdue_principal", "逾期本金", AMOUNT, group),
        ],
    )


def _ecl_stage_cols(rate_label: str, reason_label: str) -> list[dict[str, Any]]:
    return _flat_columns([
        ("label", "类别", None),
        ("gross", "账面余额", AMOUNT),
        ("loss_rate", rate_label, "percent"),
        ("provision", "减值准备", AMOUNT),
        ("net", "账面价值", AMOUNT),
        ("reason", reason_label, None),
    ])


def _writeoff_detail_cols(nature_label: str) -> list[dict[str, Any]]:
    return _flat_columns([
        ("label", "项目", None),
        ("nature", nature_label, None),
        ("amount", "核销金额", AMOUNT),
        ("reason", "核销原因", None),
        ("procedure", "履行的核销程序", None),
        ("related_party", "是否由关联交易产生", None),
    ])


def _stage_move_plan(aliases: list[str], new_name: str | None, soe: bool) -> dict[str, Any]:
    cols = _grouped_columns(("label", "减值准备"), _STAGE_MOVE_SPECS)
    labels = _STAGE_MOVE_ROW_LABELS_SOE if soe else _STAGE_MOVE_ROW_LABELS
    rule: dict[str, Any] = {
        "aliases": aliases,
        "headers": _headers_of(cols),
        "columns": cols,
        "rows": [_data(x) for x in labels],
        "guidance": (
            "三阶段迁移表：两级表头「第一/二/三阶段」下分别是未来12个月预期信用损失、"
            "整个存续期预期信用损失（未发生 / 已发生信用减值）。"
            "阶段间转移行有符号约束（转入下一阶段：转出方为负、转入方为正；转回则相反）。"
            "勾稽：期末余额 = 期初余额 + 阶段间转移合计 + 本期计提 − 本期转回 − 本期转销 "
            "− 本期核销 + 其他变动（逐列独立校验）；合计列 = 三个阶段之和；"
            "期末余额合计 = 各阶段减值准备表的合计行减值准备之和。"
        ),
    }
    if new_name:
        rule["new_name"] = new_name
    return rule


def _g4_plans() -> dict[str, dict[str, Any]]:
    listed_main = _three_col_book_value("期末余额", "上年年末余额", "减值准备")
    soe_main = _three_col_book_value("期末数", "期初数", "减值准备")
    end_important = _important_bond_cols("期末余额", "end")
    prior_important = _important_bond_cols("上年年末余额", "prior")
    return {
        "listed": {
            "section": "五、14",
            "plan": [
                {
                    "aliases": ["债权投资"],
                    "headers": _headers_of(listed_main),
                    "columns": listed_main,
                    "rows": [_data(), _data(), _data(), _data(),
                             _subtotal(), _data("减：一年内到期的债权投资"), _total()],
                    "guidance": (
                        "两级表头：期末余额 / 上年年末余额 各含账面余额、减值准备、账面价值。"
                        "勾稽：账面价值 = 账面余额 − 减值准备（逐行）；各明细行之和 = 小计行；"
                        "合计行 = 小计行 − 减：一年内到期的债权投资行；"
                        "合计行期末账面价值 = 资产负债表「债权投资」期末数 = G4-1 审定表审定数。"
                    ),
                },
                {
                    "aliases": ["债权投资减值准备本期变动情况"],
                    "columns": _flat_columns([
                        ("label", "项目", None),
                        ("opening", "期初余额", AMOUNT),
                        ("increase", "本期增加", AMOUNT),
                        ("decrease", "本期减少", AMOUNT),
                        ("closing", "期末余额", AMOUNT),
                    ]),
                    "headers": ["项目", "期初余额", "本期增加", "本期减少", "期末余额"],
                    "rows": _blanks_then_total(3),
                    "guidance": (
                        "勾稽：期末余额 = 期初余额 + 本期增加 − 本期减少（逐行）；"
                        "各明细行之和 = 合计行；合计行期末余额 = 上表合计行期末减值准备。"
                    ),
                },
                {
                    "aliases": ["期末重要的债权投资"],
                    "headers": _headers_of(end_important),
                    "columns": end_important,
                    "rows": _blanks_then_total(3),
                    "guidance": (
                        "逐项列示期末重要的债权投资（两级表头，父表头「期末余额」）。"
                        "源模版合计行的票面利率 / 实际利率 / 到期日列示为「--」（不加总）。"
                        "勾稽：合计行面值 ≤ 上表合计行期末账面余额；存在逾期本金时应在"
                        "减值准备阶段划分中体现（一般应划入第二或第三阶段）。"
                    ),
                },
                {
                    "aliases": ["续：", "期末重要的债权投资（续：上年年末余额）"],
                    "new_name": "期末重要的债权投资（续：上年年末余额）",
                    "headers": _headers_of(prior_important),
                    "columns": prior_important,
                    "rows": _blanks_then_total(3),
                    "guidance": (
                        "上表的续表（父表头「上年年末余额」）。源模版表名是裸「续：」，"
                        "为避免与其他章节的续表撞键，统一改为「主表名（续：上年年末余额）」。"
                        "勾稽：项目集合应与上表一致；合计行面值 ≤ 主表合计行上年年末账面余额。"
                    ),
                },
                *[
                    {
                        "aliases": [name],
                        "headers": _headers_of(_ecl_stage_cols(rate, reason)),
                        "columns": _ecl_stage_cols(rate, reason),
                        "rows": _ECL_STAGE_ROWS_LISTED,
                        "guidance": _ECL_INPUT_GUIDANCE + (
                            "勾稽：账面价值 = 账面余额 − 减值准备；"
                            "减值准备 ≈ 账面余额 × 预期信用损失率；"
                            "「其中：」下逐项 / 逐组合明细之和 = 对应的单项 / 组合计提行；"
                            "单项 + 组合 = 合计行。三个阶段的合计行减值准备之和 = "
                            "债权投资表对应期间的合计行减值准备。"
                            + _STAGE_JUDGEMENT_NOTE
                        ),
                    }
                    for name, rate, reason in _LISTED_STAGE_SPECS("债权投资")
                ],
                _stage_move_plan(["本期计提、收回或转回的减值准备情况"], None, soe=False),
                {
                    "aliases": ["本期实际核销的债权投资"],
                    "headers": ["项目", "核销金额"],
                    "columns": _flat_columns([
                        ("label", "项目", None),
                        ("writeoff_amount", "核销金额", AMOUNT),
                    ]),
                    "rows": [_data("实际核销的债权投资")],
                    "guidance": _WRITEOFF_GUIDANCE + (
                        "勾稽：本行核销金额 = 下表「重要的债权投资核销情况」合计行核销金额 + "
                        "不重要款项核销金额；并与三阶段迁移表「本期核销」行合计一致。"
                    ),
                },
                {
                    "aliases": ["重要的债权投资核销情况（逐项披露）"],
                    "headers": _headers_of(_writeoff_detail_cols("债权投资性质")),
                    "columns": _writeoff_detail_cols("债权投资性质"),
                    "rows": _blanks_then_total(3),
                    "guidance": _WRITEOFF_GUIDANCE + (
                        "完整性：核销金额非零的行，款项性质 / 核销原因 / 履行的核销程序均不得为空；"
                        "由关联交易产生的须单独披露（本列填「是」并索引至关联方交易附注）。"
                    ),
                },
            ],
        },
        "soe": {
            "section": "八、15",
            "plan": [
                {
                    "aliases": ["债权投资情况"],
                    "headers": _headers_of(soe_main),
                    "columns": soe_main,
                    "rows": _blanks_then_total(4),
                    "guidance": (
                        "两级表头：期末数 / 期初数 各含账面余额、减值准备、账面价值。"
                        "勾稽：账面价值 = 账面余额 − 减值准备（逐行）；各明细行之和 = 合计行；"
                        "合计行期末账面价值 = 资产负债表「债权投资」期末数 = G4-1 审定表审定数。"
                    ),
                },
                {
                    "aliases": ["期末重要的债权投资"],
                    "headers": ["债权项目", "面值", "票面利率%", "实际利率（%）", "到期日"],
                    "columns": _flat_columns([
                        ("label", "债权项目", None),
                        ("face_value", "面值", AMOUNT),
                        ("coupon_rate", "票面利率%", "percent"),
                        ("effective_rate", "实际利率（%）", "percent"),
                        ("maturity_date", "到期日", None),
                    ]),
                    "rows": _blanks_then_total(4),
                    "guidance": (
                        "逐项列示期末重要的债权投资（国企版单级表头，仅期末口径）。"
                        "勾稽：合计行面值 ≤ 上表合计行期末账面余额；"
                        "实际利率与票面利率差异较大时应结合溢折价摊销核对。"
                    ),
                },
                *[
                    {
                        "aliases": [name],
                        "headers": _headers_of(_ecl_stage_cols(rate, "理由")),
                        "columns": _ecl_stage_cols(rate, "理由"),
                        "rows": _ECL_STAGE_ROWS_SOE,
                        "guidance": (
                            "勾稽：账面价值 = 账面余额 − 减值准备；"
                            "减值准备 ≈ 账面余额 × 预期信用损失率；"
                            "「其中：」下明细之和 = 对应的单项 / 组合计提行；单项 + 组合 = 合计行。"
                            "三个阶段的合计行减值准备之和 = 债权投资情况表合计行期末减值准备。"
                        ),
                    }
                    for name, rate in (
                        ("期末，处于第一阶段的债权投资的减值准备", "未来12个月内预期信用损失率(%)"),
                        ("期末，处于第二阶段的债权投资的减值准备", "整个存续期预期信用损失率(%)"),
                        ("期末，处于第三阶段的债权投资的减值准备", "整个存续期预期信用损失率(%)"),
                    )
                ],
                _stage_move_plan(
                    ["债权投资（表6）", "本期计提、收回或转回的减值准备情况"],
                    "本期计提、收回或转回的减值准备情况",
                    soe=True,
                ),
            ],
        },
    }


def _g5_plans() -> dict[str, dict[str, Any]]:
    # 长期应收款按性质披露：账面余额/坏账准备/账面价值 × 两期 + 折现率区间（rowspan=2 独立列）
    def _nature_cols(end_group: str, prior_group: str, rate_label: str) -> list[dict[str, Any]]:
        return _grouped_columns(
            ("label", "项目"),
            [
                ("end_gross", "账面余额", AMOUNT, end_group),
                ("end_provision", "坏账准备", AMOUNT, end_group),
                ("end_net", "账面价值", AMOUNT, end_group),
                ("prior_gross", "账面余额", AMOUNT, prior_group),
                ("prior_provision", "坏账准备", AMOUNT, prior_group),
                ("prior_net", "账面价值", AMOUNT, prior_group),
                ("discount_rate_range", rate_label, None, None),
            ],
        )

    # 🔴 源模版是**三级**表头（期末余额 > 账面余额 > 金额/比例）；平台只支持两级 →
    #    父级取期间，子级用限定名（`账面余额-金额`），信息不丢且两个维度都保留。
    def _provision_cols(end_group: str, prior_group: str) -> list[dict[str, Any]]:
        leaves = [
            ("gross_amount", "账面余额-金额", AMOUNT),
            ("gross_pct", "账面余额-比例(%)", "percent"),
            ("provision_amount", "坏账准备-金额", AMOUNT),
            ("provision_rate", "坏账准备-预期信用损失率(%)", "percent"),
            ("net", "账面价值", AMOUNT),
        ]
        specs: list[tuple[str, str, str | None, str | None]] = []
        for prefix, group in (("end", end_group), ("prior", prior_group)):
            for key, label, fmt in leaves:
                specs.append((f"{prefix}_{key}", label, fmt, group))
        return _grouped_columns(("label", "类别"), specs)

    def _single_cols(group: str, prefix: str) -> list[dict[str, Any]]:
        return _grouped_columns(
            ("label", "名称"),
            [
                (f"{prefix}_gross", "账面余额", AMOUNT, group),
                (f"{prefix}_provision", "坏账准备", AMOUNT, group),
                (f"{prefix}_rate", "预期信用损失率(%)", "percent", group),
                (f"{prefix}_reason", "计提理由", None, group),
            ],
        )

    portfolio_cols = _grouped_columns(
        ("label", "账龄"),
        [
            ("end_gross", "长期应收款", AMOUNT, "期末余额"),
            ("end_provision", "坏账准备", AMOUNT, "期末余额"),
            ("end_rate", "预期信用损失率(%)", "percent", "期末余额"),
            ("prior_gross", "长期应收款", AMOUNT, "上年年末余额"),
            ("prior_provision", "坏账准备", AMOUNT, "上年年末余额"),
            ("prior_rate", "预期信用损失率(%)", "percent", "上年年末余额"),
        ],
    )
    listed_nature = _nature_cols("期末余额", "上年年末余额", "折现率区间")
    listed_provision = _provision_cols("期末余额", "上年年末余额")
    soe_nature = _nature_cols("期末余额", "期初余额", "期末折现率区间")

    # 🔴 权威模板（backend/wp_templates）上市侧只保留 3 类性质 + 3 个空行，
    #    **已删除**旧参考副本里的「应收保证金 / 应收关联方款项 / 其他」三行。
    #    「可无限量添加行」是占位说明，不落数据行（语义移入 guidance）。
    nature_rows = [
        _data("融资租赁款"), _data("其中：未实现融资收益"),
        _data("分期收款销售商品"), _data("其中：未实现融资收益"),
        _data("分期收款提供劳务"), _data("其中：未实现融资收益"),
        _data(), _data(), _data(),
        _subtotal(), _data("减：1年内到期的长期应收款"), _total(),
    ]
    _NATURE_GUIDANCE = (
        "两级表头：期末 / 期初各含账面余额、坏账准备、账面价值；折现率区间为独立列（跨两行）。"
        "勾稽：账面价值 = 账面余额 − 坏账准备（逐行）；「其中：未实现融资收益」是上一行的"
        "内含项、不参与加总；各性质行之和 = 小计行；合计行 = 小计行 − 减：1年内到期的"
        "长期应收款行；合计行期末账面价值 = 资产负债表「长期应收款」期末数 = G5-1 审定数。"
        "源模版的「可无限量添加行」是占位说明（非披露数据行），明细行数按项目实际情况增减。"
    )
    _PROVISION_GUIDANCE = (
        "源模版为三级表头（期末/期初 > 账面余额·坏账准备·账面价值 > 金额·比例），"
        "平台按两级投影：父表头取期间，子列名用限定名（如「账面余额-金额」）。"
        "勾稽：账面余额-比例(%) = 该行账面余额-金额 ÷ 合计行账面余额-金额 × 100；"
        "坏账准备-预期信用损失率(%) = 该行坏账准备-金额 ÷ 该行账面余额-金额 × 100；"
        "账面价值 = 账面余额-金额 − 坏账准备-金额；单项 + 组合 = 合计行；"
        "合计行账面价值 = 按性质披露表合计行对应期间账面价值。"
        "【提示：若采用三阶段模型对长期应收款计提坏账准备，请参考其他应收款坏账准备的披露。】"
    )
    return {
        "listed": {
            "section": "五、16",
            # 源模版有 5 张同名占位表「组合计提项目：XXX」→ 按 name 建键必互相覆盖丢表。
            # 只留 1 张作骨架，实际组合由底稿同步为「组合计提项目：{组合名}」（与 D2 同款命名空间）。
            "drop_duplicates": ["组合计提项目：XXX"],
            "plan": [
                {
                    "aliases": ["长期应收款按性质披露"],
                    "headers": _headers_of(listed_nature),
                    "columns": listed_nature,
                    "rows": nature_rows,
                    "guidance": _NATURE_GUIDANCE,
                },
                {
                    "aliases": ["坏账准备计提情况"],
                    "headers": _headers_of(listed_provision),
                    "columns": listed_provision,
                    "rows": [
                        _data("按单项计提坏账准备"), _data("其中："), _data(), _data(),
                        _data("按组合计提坏账准备【注意：与会计政策中披露的组合保持一致】"),
                        _data("其中："), _data(), _data(),
                        _total(),
                    ],
                    "guidance": _PROVISION_GUIDANCE,
                },
                {
                    "aliases": ["按单项计提坏账准备"],
                    "headers": _headers_of(_single_cols("期末余额", "end")),
                    "columns": _single_cols("期末余额", "end"),
                    "rows": _blanks_then_total(4),
                    "guidance": (
                        "逐个债务人列示单项计提的坏账准备（父表头「期末余额」）。"
                        "源模版合计行的计提理由列示为「/」（不加总）。"
                        "勾稽：明细行之和 = 合计行；合计行 = 坏账准备计提情况表"
                        "「按单项计提坏账准备」行对应期间的金额。"
                    ),
                },
                {
                    "aliases": ["续：", "按单项计提坏账准备（续：上年年末余额）"],
                    "new_name": "按单项计提坏账准备（续：上年年末余额）",
                    "headers": _headers_of(_single_cols("上年年末余额", "prior")),
                    "columns": _single_cols("上年年末余额", "prior"),
                    "rows": _blanks_then_total(4),
                    "guidance": (
                        "上表的续表（父表头「上年年末余额」）。源模版表名是裸「续：」，"
                        "统一改为「主表名（续：上年年末余额）」以免跨章节撞键。"
                        "勾稽：债务人集合应与上表一致；合计行 = 坏账准备计提情况表"
                        "「按单项计提坏账准备」行上年年末金额。"
                    ),
                },
                {
                    "aliases": ["组合计提项目：XXX"],
                    "headers": _headers_of(portfolio_cols),
                    "columns": portfolio_cols,
                    "rows": [_data("1年以内"), _data("1至2年"), _data("2至3年"), _total()],
                    "guidance": (
                        "组合计提坏账准备按账龄段列示（两级表头：期末余额 / 上年年末余额）。"
                        "本表是**骨架**：实际每个组合一张表，表名为「组合计提项目：{组合名}」，"
                        "账龄段随项目账龄配置（3年段 / 5年段 / 自定义）由底稿同步整表覆盖。"
                        "勾稽：预期信用损失率(%) = 坏账准备 ÷ 长期应收款 × 100；"
                        "各账龄段之和 = 合计行；各组合表合计行之和 = 坏账准备计提情况表"
                        "「按组合计提坏账准备」行。"
                    ),
                },
                {
                    "aliases": ["本期计提、收回或转回的坏账准备情况"],
                    "headers": ["项目", "坏账准备金额"],
                    "columns": _flat_columns([
                        ("label", "项目", None),
                        ("amount", "坏账准备金额", AMOUNT),
                    ]),
                    "rows": [
                        _data("期初余额"), _data("本期计提"), _data("本期收回或转回"),
                        _data("本期核销"), _data("[本期转销]"), _data("[其他]"),
                        _data("期末余额"),
                    ],
                    "guidance": (
                        "源模版首列表头留空，平台统一取「项目」以免出现空列头。"
                        "带方括号的行（[本期转销] / [其他]）为源模版可选行，无金额时可删。"
                        "勾稽：期末余额 = 期初余额 + 本期计提 − 本期收回或转回 − 本期核销 "
                        "− [本期转销] ± [其他]；期末余额 = 坏账准备计提情况表合计行"
                        "期末坏账准备-金额。"
                        "【提示：若采用三阶段模型对长期应收款计提坏账准备，请参考其他应收款坏账准备的披露。】"
                    ),
                },
                {
                    "aliases": ["本期实际核销的长期应收款"],
                    "headers": ["项目", "核销金额"],
                    "columns": _flat_columns([
                        ("label", "项目", None),
                        ("writeoff_amount", "核销金额", AMOUNT),
                    ]),
                    "rows": [_data("实际核销的长期应收款")],
                    "guidance": (
                        "勾稽：本行核销金额 = 下表「重要的长期应收款核销情况」合计行核销金额 + "
                        "不重要款项核销金额；并与上表「本期核销」行一致。"
                    ),
                },
                {
                    "aliases": ["重要的长期应收款核销情况（逐项披露）"],
                    "headers": _headers_of(_writeoff_detail_cols("长期应收款性质")),
                    "columns": _writeoff_detail_cols("长期应收款性质"),
                    "rows": _blanks_then_total(3),
                    "guidance": (
                        "完整性：核销金额非零的行，款项性质 / 核销原因 / 履行的核销程序均不得为空；"
                        "由关联交易产生的须单独披露（本列填「是」并索引至关联方交易附注）。"
                    ),
                },
            ],
        },
        "soe": {
            "section": "八、17",
            "plan": [
                {
                    "aliases": ["长期应收款按性质披露"],
                    "headers": _headers_of(soe_nature),
                    "columns": soe_nature,
                    # 权威模板国企侧：3 类性质 + 2 空行 + 其他（无 应收保证金/应收关联方款项）
                    "rows": [
                        _data("融资租赁款"), _data("其中：未实现融资收益"),
                        _data("分期收款销售商品"), _data("分期收款提供劳务"),
                        _data(), _data(), _data("其他"),
                        _subtotal(), _data("减：1年内到期的长期应收款"), _total(),
                    ],
                    "guidance": _NATURE_GUIDANCE.replace("期末 / 期初", "期末 / 期初").replace(
                        "「可无限量添加行」是占位说明（非披露数据行），", "",
                    ),
                },
                {
                    "aliases": ["终止确认的长期应收款"],
                    "headers": ["项目", "转移方式", "终止确认金额", "与终止确认相关的利得或损失"],
                    "columns": _flat_columns([
                        ("label", "项目", None),
                        ("transfer_method", "转移方式", None),
                        ("derecognized_amount", "终止确认金额", AMOUNT),
                        ("gain_or_loss", "与终止确认相关的利得或损失", AMOUNT),
                    ]),
                    "rows": _blanks_then_total(3),
                    "guidance": (
                        "注：报告期内因金融资产转移而终止确认的长期应收款，应披露资产转移的方式、"
                        "终止确认的长期应收款金额，以及与终止确认相关的利得或损失。"
                        "源模版合计行的「与终止确认相关的利得或损失」列示为「--」。"
                        "勾稽：明细行之和 = 合计行终止确认金额；相关利得或损失应与利润表"
                        "「投资收益」或「资产处置收益」中对应项目一致。"
                    ),
                },
                {
                    "aliases": ["转移长期应收款且继续涉入形成的资产、负债的金额"],
                    "headers": ["项目", "期末数"],
                    "columns": _flat_columns([
                        ("label", "项目", None),
                        ("end_amount", "期末数", AMOUNT),
                    ]),
                    "rows": [
                        _data("资产："), _data(), _subtotal("资产小计"),
                        _data("负债："), _data(), _subtotal("负债小计"),
                    ],
                    "guidance": (
                        "注：转移长期应收款且继续涉入形成的资产、负债金额。"
                        "「资产：」「负债：」为分区标题行，其下逐项列示。"
                        "勾稽：资产小计 = 资产区各明细行之和；负债小计 = 负债区各明细行之和；"
                        "两者应能在资产负债表相应项目中找到列示位置。"
                    ),
                },
            ],
        },
    }


def _g6_plans() -> dict[str, dict[str, Any]]:
    end_important = _important_bond_cols("期末余额", "end")
    prior_important = _important_bond_cols("上年年末余额", "prior")
    return {
        "listed": {
            "section": "五、15",
            "plan": [
                {
                    "aliases": ["其他债权投资"],
                    "headers": ["项目", "期末余额", "上年年末余额"],
                    "columns": _flat_columns([
                        ("label", "项目", None),
                        ("end_balance", "期末余额", AMOUNT),
                        ("prior_balance", "上年年末余额", AMOUNT),
                    ]),
                    "rows": [_data(), _data(), _data(), _subtotal(),
                             _data("减：一年内到期的其他债权投资"), _total()],
                    "guidance": (
                        "按项目列示其他债权投资期末 / 上年年末余额（源模版为单级表头）。"
                        "勾稽：各明细行之和 = 小计行；"
                        "合计行 = 小计行 − 减：一年内到期的其他债权投资行；"
                        "合计行期末余额 = 资产负债表「其他债权投资」期末数 = G6-1 审定数。"
                    ),
                },
                {
                    "aliases": ["其他债权投资情况"],
                    "headers": [
                        "项目", "期初余额", "应计利息", "本期公允价值变动", "期末余额",
                        "成本", "累计公允价值变动", "累计在其他综合收益中确认的减值准备",
                    ],
                    "columns": _flat_columns([
                        ("label", "项目", None),
                        ("opening_fv", "期初余额", AMOUNT),
                        ("accrued_interest", "应计利息", AMOUNT),
                        ("fv_change_current", "本期公允价值变动", AMOUNT),
                        ("closing_fv", "期末余额", AMOUNT),
                        ("cost", "成本", AMOUNT),
                        ("fv_change_cumulative", "累计公允价值变动", AMOUNT),
                        ("oci_impairment", "累计在其他综合收益中确认的减值准备", AMOUNT),
                    ]),
                    "rows": _blanks_then_total(3),
                    "guidance": (
                        "【提示：期末公允价值D=期初公允价值A+当期应计利息B（即实际利息收入-实收利息）"
                        "+当期公允价值变动C=初始成本E+累计应计利息∑B+累计公允价值变动F"
                        "（即期末公允价值D-期末摊余成本）】"
                        "【G：对于以公允价值计量且其变动计入其他综合收益的金融资产，企业应当在"
                        "其他综合收益中确认其损失准备，并将减值损失或利得计入当期损益，"
                        "且不应减少该金融资产在资产负债表中列示的账面价值】"
                        "勾稽：期末余额 = 期初余额 + 应计利息 + 本期公允价值变动（逐行）；"
                        "合计行期末余额 = 上表合计行期末余额。"
                    ),
                },
                {
                    "aliases": ["其他债权投资减值准备本期变动情况"],
                    "headers": ["项目", "期初余额", "本期增加", "本期减少", "期末余额"],
                    "columns": _flat_columns([
                        ("label", "项目", None),
                        ("opening", "期初余额", AMOUNT),
                        ("increase", "本期增加", AMOUNT),
                        ("decrease", "本期减少", AMOUNT),
                        ("closing", "期末余额", AMOUNT),
                    ]),
                    # 权威模板：2 空行 + 「其他（如有）」+ 合计
                    "rows": [_data(), _data(), _data("其他（如有）"), _total()],
                    "guidance": (
                        "勾稽：期末余额 = 期初余额 + 本期增加 − 本期减少（逐行）；"
                        "各明细行之和 = 合计行；合计行期末余额 = 其他债权投资情况表"
                        "合计行「累计在其他综合收益中确认的减值准备」，并与坏账准备明细表"
                        "G6-3 期末审定数勾稽。"
                    ),
                },
                {
                    "aliases": ["期末重要的其他债权投资"],
                    "headers": _headers_of(end_important),
                    "columns": end_important,
                    "rows": _blanks_then_total(3),
                    "guidance": (
                        "逐项列示期末重要的其他债权投资（两级表头，父表头「期末余额」）。"
                        "勾稽：合计行面值 ≤ 其他债权投资表合计行期末余额；"
                        "存在逾期本金时应在减值准备阶段划分中体现。"
                    ),
                },
                {
                    "aliases": ["续：", "期末重要的其他债权投资（续：上年年末余额）"],
                    "new_name": "期末重要的其他债权投资（续：上年年末余额）",
                    "headers": _headers_of(prior_important),
                    "columns": prior_important,
                    "rows": _blanks_then_total(3),
                    "guidance": (
                        "上表的续表（父表头「上年年末余额」）。源模版表名是裸「续：」，"
                        "统一改为「主表名（续：上年年末余额）」以免跨章节撞键。"
                        "勾稽：项目集合应与上表一致。"
                    ),
                },
                *[
                    {
                        "aliases": [name],
                        "headers": _headers_of(_ecl_stage_cols(rate, reason)),
                        "columns": _ecl_stage_cols(rate, reason),
                        "rows": _ECL_STAGE_ROWS_LISTED,
                        "guidance": _ECL_INPUT_GUIDANCE + (
                            "勾稽：账面价值 = 账面余额 − 减值准备；"
                            "减值准备 ≈ 账面余额 × 预期信用损失率；"
                            "「其中：」下明细之和 = 对应的单项 / 组合计提行；单项 + 组合 = 合计行。"
                            "🔴 其他债权投资的损失准备在**其他综合收益**中确认，不冲减"
                            "资产负债表列示的账面价值 → 本区「账面价值」属减值分析口径，"
                            "不得与资产负债表公允价值列示口径混同（权威模板编制说明第 2、3 条）。"
                            + _STAGE_JUDGEMENT_NOTE
                        ),
                    }
                    for name, rate, reason in _LISTED_STAGE_SPECS("其他债权投资")
                ],
                _stage_move_plan(["本期计提、收回或转回的减值准备情况"], None, soe=False),
                {
                    "aliases": ["本期实际核销的其他债权投资"],
                    "headers": ["项目", "核销金额"],
                    "columns": _flat_columns([
                        ("label", "项目", None),
                        ("writeoff_amount", "核销金额", AMOUNT),
                    ]),
                    "rows": [_data("实际核销的其他债权投资")],
                    "guidance": _WRITEOFF_GUIDANCE + (
                        "勾稽：本行核销金额 = 下表合计行核销金额 + 不重要款项核销金额；"
                        "并与三阶段迁移表「本期核销」行合计一致。"
                    ),
                },
                {
                    "aliases": ["重要的其他债权投资核销情况（逐项披露）"],
                    "headers": _headers_of(_writeoff_detail_cols("其他债权投资性质")),
                    "columns": _writeoff_detail_cols("其他债权投资性质"),
                    "rows": _blanks_then_total(3),
                    "guidance": _WRITEOFF_GUIDANCE + (
                        "完整性：核销金额非零的行，款项性质 / 核销原因 / 履行的核销程序均不得为空；"
                        "由关联交易产生的须单独披露（本列填「是」并索引至关联方交易附注）。"
                    ),
                },
            ],
        },
        "soe": {
            "section": "八、16",
            "plan": [
                {
                    "aliases": ["其他债权投资情况"],
                    "headers": ["项目", "期末余额", "期初余额"],
                    "columns": _flat_columns([
                        ("label", "项目", None),
                        ("end_balance", "期末余额", AMOUNT),
                        ("opening_balance", "期初余额", AMOUNT),
                    ]),
                    "rows": _blanks_then_total(3),
                    "guidance": (
                        "按项目列示其他债权投资期末 / 期初余额（国企版单级表头）。"
                        "勾稽：各明细行之和 = 合计行；合计行期末余额 = 资产负债表"
                        "「其他债权投资」期末数 = G6-1 审定表审定数。"
                        "减值准备计提情况参照「附注八、15、债权投资（3）减值准备计提情况」披露。"
                    ),
                },
                {
                    "aliases": ["期末重要的其他债权投资"],
                    "headers": [
                        "其他债权投资项目", "面值", "摊余成本", "公允价值",
                        "累计计入其他综合收益的公允价值变动金额", "已计提减值准备金额",
                    ],
                    "columns": _flat_columns([
                        ("label", "其他债权投资项目", None),
                        ("face_value", "面值", AMOUNT),
                        ("amortized_cost", "摊余成本", AMOUNT),
                        ("fair_value", "公允价值", AMOUNT),
                        ("oci_fv_change_cumulative", "累计计入其他综合收益的公允价值变动金额", AMOUNT),
                        ("provision", "已计提减值准备金额", AMOUNT),
                    ]),
                    "rows": _blanks_then_total(4),
                    "guidance": (
                        "逐项列示期末重要的其他债权投资（国企版单级表头）。"
                        "勾稽：公允价值 = 摊余成本 + 累计计入其他综合收益的公允价值变动金额；"
                        "合计行公允价值 = 上表合计行期末余额；"
                        "已计提减值准备在其他综合收益中确认，不减少资产负债表列示的账面价值。"
                    ),
                },
            ],
        },
    }


SECTION_PLANS["G4"] = _g4_plans()
SECTION_PLANS["G5"] = _g5_plans()
SECTION_PLANS["G6"] = _g6_plans()


# ─────────────────────────── 应用 ───────────────────────────

def _find_section(doc: dict[str, Any], section_number: str) -> dict[str, Any] | None:
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")) == section_number:
            return sec
    return None


def apply_plan(section: dict[str, Any], plan: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """按计划就地修订 ``section.tables``（游标只前进，重名表由位置区分）。"""
    tables: list[dict[str, Any]] = section.get("tables") or []
    changes: list[str] = []
    warnings: list[str] = []
    cursor = 0

    for rule in plan:
        aliases = rule["aliases"]
        idx = next(
            (i for i in range(cursor, len(tables)) if str(tables[i].get("name", "")) in aliases),
            None,
        )
        if idx is None:
            warnings.append(f"未找到表：{aliases[-1]}（游标 {cursor}）→ 跳过")
            continue

        tbl = tables[idx]
        old_name = str(tbl.get("name", ""))
        new_name = rule.get("new_name")
        if new_name and old_name != new_name:
            dup = next(
                (j for j, t in enumerate(tables) if j != idx and str(t.get("name", "")) == new_name),
                None,
            )
            if dup is not None:
                warnings.append(f"表名迁移跳过：「{old_name}」→「{new_name}」，索引 {dup} 已占用")
            else:
                tbl["name"] = new_name
                changes.append(f"[{idx}] 表名：「{old_name}」→「{new_name}」")

        for key in ("headers", "columns", "rows"):
            want = rule.get(key)
            if want is None:
                continue
            if tbl.get(key) != want:
                old_len = len(tbl.get(key) or [])
                tbl[key] = json.loads(json.dumps(want, ensure_ascii=False))
                changes.append(f"[{idx}] {tbl.get('name')}.{key}：{old_len} → {len(want)} 项")

        # `_column_groups`：两级表头由 columns 的 group 派生；单级表头显式删除
        # （seed 误留的分组会让附注渲染出凭空父表头）
        want_groups = _derive_column_groups(rule.get("columns") or tbl.get("columns") or [])
        if want_groups:
            if tbl.get("_column_groups") != want_groups:
                tbl["_column_groups"] = json.loads(json.dumps(want_groups, ensure_ascii=False))
                changes.append(
                    f"[{idx}] {tbl.get('name')}._column_groups：{len(want_groups)} 组（两级表头）"
                )
        elif tbl.pop("_column_groups", None) is not None:
            changes.append(f"[{idx}] {tbl.get('name')}._column_groups：删除（单级表头）")

        guidance = rule.get("guidance")
        if guidance and tbl.get("guidance") != guidance:
            tbl["guidance"] = guidance
            changes.append(f"[{idx}] {tbl.get('name')}.guidance → {len(guidance)} 字")

        cursor = idx + 1

    return changes, warnings


def drop_duplicate_tables(section: dict[str, Any], names: list[str]) -> list[str]:
    """删除指定表名的**重复项**（只留第一张）。

    🔴 源模版把「组合计提项目：XXX」这类占位表复制了 5 份（G5 上市）。附注侧按
    `tables[].name` 建键 → 5 张同名表必互相覆盖，只有最后一张能存活，其余是死表。
    只留 1 张作骨架，实际组合由底稿同步为「组合计提项目：{组合名}」（与 D2 同款命名空间）。
    """
    if not names:
        return []
    tables: list[dict[str, Any]] = section.get("tables") or []
    changes: list[str] = []
    for target in names:
        idxs = [i for i, t in enumerate(tables) if str(t.get("name", "")) == target]
        if len(idxs) <= 1:
            continue
        for i in reversed(idxs[1:]):
            tables.pop(i)
        changes.append(f"删除重名占位表「{target}」×{len(idxs) - 1}（只留第 {idxs[0]} 张作骨架）")
    return changes


def _stamp(section: dict[str, Any]) -> None:
    section["_aligned_by"] = ALIGNED_BY
    section["_aligned_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────── 校验 ───────────────────────────

def validate_section(section: dict[str, Any], expected: list[str]) -> list[str]:
    """表名唯一齐备 / 无 header_label / columns 表态（flat 或 group）/ 分组自洽 / guidance 齐备。"""
    errs: list[str] = []
    tables = section.get("tables") or []
    seen: dict[str, int] = {}

    for i, tbl in enumerate(tables):
        name = str(tbl.get("name", ""))
        if name in seen:
            errs.append(f"[{i}] 表名重复：「{name}」（首现于 {seen[name]}）")
        seen[name] = i
        if name not in expected:
            continue  # 本脚本只对计划内的表负责

        headers = tbl.get("headers") or []
        if any(not str(h).strip() for h in headers):
            errs.append(f"[{i}] {name} headers 含空串：{headers}")
        if any("<" in str(h) for h in headers):
            errs.append(f"[{i}] {name} headers 含 HTML：{headers}")

        for j, row in enumerate(tbl.get("rows") or []):
            if str(row.get("row_type", "")) == "header_label":
                errs.append(f"[{i}] {name} 第 {j} 行仍为 header_label（压扁的第二行表头）")

        cols = tbl.get("columns") or []
        has_group = any(c.get("group") for c in cols)
        if not cols:
            errs.append(f"[{i}] {name} 缺 columns")
        else:
            if len(cols) != len(headers):
                errs.append(f"[{i}] {name} columns={len(cols)} ≠ headers={len(headers)}")
            if str(cols[0].get("label", "")) != str(headers[0] if headers else ""):
                errs.append(
                    f"[{i}] {name} columns[0].label={cols[0].get('label')!r} ≠ headers[0]="
                    f"{(headers[0] if headers else None)!r}"
                )
            if cols[0].get("is_label") is not True:
                errs.append(f"[{i}] {name} 首列未标 is_label")
            has_flat = any(c.get("flat") for c in cols)
            if has_flat and has_group:
                errs.append(f"[{i}] {name} flat 与 group 并存（表态冲突）")
            if not has_flat and not has_group:
                errs.append(f"[{i}] {name} columns 未表态（既无 flat 也无 group）")
            if has_group and cols[0].get("group"):
                errs.append(f"[{i}] {name} 标签列不得带 group")
            # 列标签在同一 group 内不得重复（否则附注侧两列同名无法区分）
            by_group: dict[str, list[str]] = {}
            for c in cols[1:]:
                by_group.setdefault(str(c.get("group") or ""), []).append(str(c.get("label")))
            for g, labels in by_group.items():
                dup = {x for x in labels if labels.count(x) > 1}
                if dup:
                    errs.append(f"[{i}] {name} 分组「{g or '(无)'}」内列名重复：{sorted(dup)}")

        groups = tbl.get("_column_groups")
        if has_group:
            want = _derive_column_groups(cols)
            if groups != want:
                errs.append(f"[{i}] {name} _column_groups 与 columns.group 不一致")
            occupied: set[int] = set()
            for g in groups or []:
                start, span = int(g.get("start", 0)), int(g.get("span", 0))
                if start < 1:
                    errs.append(f"[{i}] {name} 分组「{g.get('group')}」start={start} < 1")
                if start + span > len(headers):
                    errs.append(
                        f"[{i}] {name} 分组「{g.get('group')}」越界：{start}+{span} > {len(headers)}"
                    )
                rng = set(range(start, start + span))
                if rng & occupied:
                    errs.append(f"[{i}] {name} 分组「{g.get('group')}」区间重叠")
                occupied |= rng
        elif groups:
            errs.append(f"[{i}] {name} 单级表头却残留 _column_groups")

        if not str(tbl.get("guidance", "")).strip():
            errs.append(f"[{i}] {name} 缺 guidance")

    for want in expected:
        if want not in seen:
            errs.append(f"缺表：「{want}」")
    return errs


# ─────────────────────────── 入口 ───────────────────────────

def _process(
    cycle: str,
    variant: str,
    spec: dict[str, Any],
    *,
    dry_run: bool,
    check_only: bool,
) -> tuple[bool, list[str]]:
    path = TEMPLATE_PATH[variant]
    section_number = spec["section"]
    plan: list[dict[str, Any]] = spec["plan"]
    expected = [str(r.get("new_name") or r["aliases"][-1]) for r in plan]

    raw = path.read_text(encoding="utf-8")
    doc = json.loads(raw)
    section = _find_section(doc, section_number)
    if section is None:
        return False, [f"[FATAL] {path.name} 未找到 section_number={section_number}（{cycle}/{variant}）"]

    log = [f"=== {cycle} [{variant}] {path.name} §{section_number} {section.get('section_title')} ==="]

    if check_only:
        errs = validate_section(section, expected)
        if section.get("_aligned_by") != ALIGNED_BY:
            errs.append("尚未对齐（缺 _aligned_by 标记）")
        log.extend(errs or ["结构校验通过"])
        return not errs, log

    changes, warnings = apply_plan(section, plan)
    changes += drop_duplicate_tables(section, spec.get("drop_duplicates") or [])
    log.extend(changes or ["无需修改（已对齐）"])
    log.extend(f"[WARN] {w}" for w in warnings)

    errs = validate_section(section, expected)
    if errs:
        log.append("[FATAL] 修订后结构校验失败，未写入：")
        log.extend(f"  {e}" for e in errs)
        return False, log
    log.append(f"结构校验通过（计划内 {len(expected)} 张表）")

    if dry_run:
        log.append("[dry-run] 未写文件")
        return True, log
    if not changes and section.get("_aligned_by") == ALIGNED_BY:
        log.append("已对齐且无变更，跳过写入")
        return True, log

    _stamp(section)
    trailing = "\n" if raw.endswith("\n") else ""
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + trailing, encoding="utf-8")
    log.append(f"已写入 {path}")
    return True, log


def main() -> int:
    ap = argparse.ArgumentParser(description="附注 G 循环披露章节结构对齐源模版（幂等）")
    ap.add_argument("--cycle", action="append", help="只处理指定循环（可重复），默认全部")
    ap.add_argument("--dry-run", action="store_true", help="只打印 diff 摘要，不写文件")
    ap.add_argument("--check", action="store_true", help="仅校验对齐状态（供 CI）")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

    cycles = [c.upper() for c in (args.cycle or SECTION_PLANS.keys())]
    unknown = [c for c in cycles if c not in SECTION_PLANS]
    if unknown:
        print(f"[FATAL] 未登记的循环：{unknown}；可用：{sorted(SECTION_PLANS)}")
        return 2

    ok_all = True
    for cycle in cycles:
        for variant, spec in SECTION_PLANS[cycle].items():
            ok, log = _process(
                cycle, variant, spec, dry_run=args.dry_run, check_only=args.check,
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
