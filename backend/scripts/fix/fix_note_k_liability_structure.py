#!/usr/bin/env python
"""附注 K 系负债/递延类章节结构对齐源模版（幂等修订，批 2 = K3/K4/K5/K7）。

**范围**（四循环两版共 8 个章节、20 张表）：

| 循环 | listed 章节号 | 表数 | soe 章节号 | 表数 |
|------|--------------|------|-----------|------|
| K3 其他应付款   | 五、42 | 7 | 八、42 | 6 |
| K4 其他流动负债 | 五、44 | 3 | 八、48 | 1 |
| K5 预计负债     | 五、50 | 1 | 八、55 | 1 |
| K7 递延收益     | 五、51 | 1 | 八、56 | 2 |

历史问题（2026-07-30 实测）：

1. **泄漏 / 假表名 3 处**：
   - K3 listed 表 7 名为表头首格 ``项  目``（应为「其中，账龄超过1年的重要其他应付款」，
     见该章 ``text_sections`` 的 ``#### 其中，账龄超过1年的重要其他应付款``）；
   - K3 soe 表 6 名为 ``其他应付款（表6）``（md 重建对重名表的机械消歧产物，
     应为「账龄超过1年的重要其他应付款项」）；
   - K4 listed 表 3 名为表头首格 ``债券名称``（应为「短期应付债券（续）」，见源 xlsx A24）。
2. **占位说明行 5 处**：K3 listed ``可无限量添加行`` ×3、K4 soe ``……``。
3. 20 张表**全部**缺 ``columns``（未表态）+ 缺 ``guidance``。

**权威源**（三者互证）：

- ``backend/wp_templates/K/K{3,4,5,7} *.xlsx`` 的两个披露 tab（逐格实证）：
  K3 两版都是「主表 3 行 + 按款项性质列示 + 账龄超1年重要款项」三段，
  上市第三段表头 ``项目/金额/未偿还或未结转的原因``、国企 ``债权单位名称/期末余额/未偿还原因``；
  K4 上市有短期应付债券两块（基本信息 6 列 + 续表 8 列）与递延收益-政府补助块；
  K5 两版都有「形成原因」列；K7 上市 6 列、国企 5 列 + 政府补助明细 10 列。
- ``note_template_{listed,soe}.json``（交付物权威）：列名与固定行名以此为准。
  **两处已知与 xlsx 不同、以模板为准**：K3 上市账龄超1年表第 2 列模板作「期末余额」
  （xlsx 作「金额」）；K5 国企模板只有 3 列（xlsx 有第 4 列「形成原因」）——
  形成原因由该章 ``text_sections``「注：应逐项说明未决诉讼、待执行的亏损合同的形成原因和进展」承载。

裁决要点：

- 八个章节的表在源 xlsx 里都是**单行表头** → 20 张表一律显式 ``flat``，删 ``_column_groups``。
- K4 上市源 xlsx 的「（2）递延收益-政府补助情况」块不进 §五、44（该章模板无对应表，
  递延收益归 §五、51 / §八、56），避免孤儿表。
- K5 国企不擅自补第 4 列（附注是交付物，随模板）。

Usage::

    python backend/scripts/fix/fix_note_k_liability_structure.py --dry-run
    python backend/scripts/fix/fix_note_k_liability_structure.py
    python backend/scripts/fix/fix_note_k_liability_structure.py --check

spec: .kiro/specs/k-cycle-disclosure-alignment/ R4（Task 6）
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"

ALIGNED_BY = "k-cycle-disclosure-alignment/liability"

LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

# 泄漏 / 假表名 → 正名
LEAKED_NAMES = {
    "项  目": "其中，账龄超过1年的重要其他应付款",
    "其他应付款（表6）": "账龄超过1年的重要其他应付款项",
    "债券名称": "短期应付债券（续）",
}

PLACEHOLDER_ROW_LABELS = {"可无限量添加行", "......", "……", "…", "...."}


def _norm(v: Any) -> str:
    return str(v or "").replace(" ", "").replace("\u3000", "").strip()


_PLACEHOLDER_NORM = {_norm(x) for x in PLACEHOLDER_ROW_LABELS}


# ─────────────────────────── 列构造 ───────────────────────────

def _col(key: str, label: str, fmt: str | None = None, *, is_label: bool = False, flat: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {"key": key, "label": label}
    if is_label:
        out["is_label"] = True
    if flat:
        out["flat"] = True
    if fmt:
        out["format"] = fmt
    return out


def _label_col(label: str) -> dict[str, Any]:
    """标签列：`flat` 标在此列即对整表生效（源模板皆单行表头）。"""
    return _col("label", label, is_label=True, flat=True)


def _amt(key: str, label: str) -> dict[str, Any]:
    return _col(key, label, "amount")


def _txt(key: str, label: str) -> dict[str, Any]:
    return _col(key, label, "text")


def _pct(key: str, label: str) -> dict[str, Any]:
    return _col(key, label, "percent")


def _two_period(label_head: str, end_head: str, prior_head: str) -> list[dict[str, Any]]:
    return [_label_col(label_head), _amt("end_amount", end_head), _amt("prior_amount", prior_head)]


# ─────────────────────────── guidance ───────────────────────────

_G = {
    # ── K3 其他应付款 ────────────────────────────────────────────────────────
    "k3_main": (
        "其他应付款按「应付利息 / 应付股利 / 其他应付款」三类汇总列示，各类明细见后续分表。"
        "勾稽：合计行期末余额 = 资产负债表「其他应付款」期末数；「其他应付款」行 = 按款项性质列示表合计行。"
        "数据来源：审定表 K3-1。"
    ),
    "k3_interest": (
        "【提示：根据财会（2019）6号文的规定，应付利息仅反映相关金融工具已到期应支付但于资产负债表日"
        "尚未支付的利息。基于实际利率法计提的金融工具的利息应包含在相应金融工具的账面余额中。】"
        "勾稽：本表合计行 = 主表「应付利息」行。"
    ),
    "k3_interest_overdue": (
        "源模板要求：重要的逾期未付利息应披露借款单位、逾期金额与逾期原因。"
        "本表为明细披露表，行数按实际情况增删；不存在时整表不披露。"
    ),
    "k3_dividend": "勾稽：本表合计行 = 主表「应付股利」行。划分为权益工具的优先股／永续债股利须按工具逐项列示。",
    "k3_dividend_overdue": (
        "源模板要求：重要的超过1年未支付的应付股利应披露股东名称、金额与未支付原因。"
        "行数按实际情况增删；不存在时整表不披露。"
    ),
    "k3_by_nature": (
        "按款项性质列示（押金 / 质保金 / 往来款等），明细项目随项目实际情况增删。"
        "勾稽：本表合计行 = 主表「其他应付款」行。数据来源：审定表 K3-1。"
    ),
    "k3_aging_over1y": (
        "源模板要求：账龄超过1年的重要其他应付款须说明未偿还或未结转的原因。"
        "第 2 列列头以附注模版为准（源 xlsx 作「金额」）。数据来源：长期挂账检查表 K3-5。"
    ),
    "k3_soe_aging_over1y": (
        "源模板要求：账龄超过1年的重要其他应付款项须披露债权单位名称与未偿还原因。"
        "数据来源：长期挂账检查表 K3-5。"
    ),
    # ── K4 其他流动负债 ──────────────────────────────────────────────────────
    "k4_main_listed": (
        "【提示：1、公司根据《企业会计准则》规定计入“递延收益”科目的金额，应按如下原则确定所属的"
        "报表项目：（1）受益期预计在一年以内（含一年）的，应在“其他流动负债”项目列报；"
        "（2）自资产负债表日起算的受益期限超过一年的，在“递延收益”项目中列报。"
        "2、待转销项税额属于其他非流动负债的，在“其他非流动负债”科目列示。】"
        "勾稽：合计行期末余额 = 资产负债表「其他流动负债」期末数；各明细行之和 = 合计行。"
        "数据来源：明细表 K4-2。"
    ),
    "k4_main_soe": (
        "注：发行债券应披露债券名称、面值、发行日期、债券期限、发行金额、期初余额、本期发行金额、"
        "按面值计提利息、溢折价摊销、本期偿还的金额、期末余额等相关信息。"
        "【待转销项税额属于其他非流动负债的，在“其他非流动负债”科目列示。】"
        "勾稽：合计行期末余额 = 资产负债表「其他流动负债」期末数。数据来源：明细表 K4-2。"
    ),
    "k4_bond": (
        "短期应付债券基本信息：逐只债券列示面值、票面利率、发行日期、债券期限与发行金额。"
        "勾稽：小计行发行金额 = 续表本期发行合计。"
    ),
    "k4_bond_cont": (
        "短期应付债券变动：期末余额 = 期初余额 + 本期发行 + 按面值计提利息 − 溢折价摊销 − 本期偿还。"
        "勾稽：合计行期末余额 = 主表「短期应付债券」行期末余额。"
        "「是否违约」按实际情况点选。"
    ),
    # ── K5 预计负债 ─────────────────────────────────────────────────────────
    "k5_listed": (
        "重要的预计负债，应披露相关重要假设、估计。"
        "【《关于严格执行企业会计准则 切实做好企业2025年年报工作的通知》：企业应当正确划分流动负债和"
        "非流动负债，合理确定资产负债表中“预计负债”项目的列示金额。对于期限在一年或一个营业周期以上的"
        "保证类质量保证形成的预计负债，应将预计未来一年或一个营业周期以内清偿的金额计入流动负债并在"
        "“一年内到期的非流动负债”项目列示，其余计入非流动负债；不能合理预计的全部计入流动负债，"
        "在“其他流动负债”项目列示。】"
        "勾稽：合计行期末余额 = 资产负债表「预计负债」期末数；各明细行之和 = 合计行。"
        "数据来源：审定表 K5-1 / 明细表 K5-2。"
    ),
    "k5_soe": (
        "注：应逐项说明未决诉讼、待执行的亏损合同的形成原因和进展。"
        "（对于期限在一年或一个营业周期以内的预计负债，在“其他流动负债”项目列报，其他预计负债在"
        "非流动负债中的“预计负债”项目列报；将于一年内到期的“预计负债”应当重分类至"
        "“一年内到期的非流动负债”。）"
        "本表列结构以附注模版为准（3 列）；源 xlsx 的「形成原因」列由本章说明段落承载。"
        "勾稽：合计行期末余额 = 资产负债表「预计负债」期末数。数据来源：审定表 K5-1 / 明细表 K5-2。"
    ),
    # ── K7 递延收益 ─────────────────────────────────────────────────────────
    "k7_listed": (
        "【提示：公司根据《企业会计准则》规定计入“递延收益”科目的金额，应按如下原则确定所属的报表项目："
        "（1）受益期预计在一年以内（含一年）的，应在“其他流动负债”项目列报；"
        "（2）自资产负债表日起算的受益期限超过一年的，在“递延收益”项目中列报。"
        "摊销期限只剩一年或不足一年的，或预计在一年内（含一年）进行摊销的部分，不得归类为流动负债，"
        "仍在本项目中填列，不转入“一年内到期的非流动负债”项目。】"
        "计入递延收益的政府补助详见政府补助章节。"
        "勾稽：期末余额 = 期初余额 + 本期增加 − 本期减少（逐行）；合计行期末余额 = 资产负债表"
        "「递延收益」期末数。数据来源：审定表 K7-1。"
    ),
    "k7_soe_main": (
        "注：企业还应当披露与政府补助有关的下列信息：1.政府补助的种类及金额；"
        "2.计入当期损益的政府补助金额；3.本期返还的政府补助金额及原因。"
        "勾稽：期末余额 = 期初余额 + 本期增加 − 本期减少（逐行）；合计行期末余额 = 资产负债表"
        "「递延收益」期末数。数据来源：审定表 K7-1。"
    ),
    "k7_soe_grant": (
        "【提示：1、仅披露金额重大的政府补助项目；2、应和相关科目明细项“政府补助”金额核对一致。】"
        "勾稽：期末余额 = 期初余额 + 本期新增补助金额 − 本期计入损益金额 − 本期返还的金额 − 其他变动；"
        "本表合计行期末余额 = 主表「政府补助」行期末余额。"
        "「与资产相关/与收益相关」「本期计入损益的列报项目」按实际情况点选或填列。"
    ),
}


# ─────────────────────────── 修订计划 ───────────────────────────

PLAN: list[dict[str, Any]] = [
    # ── K3 listed §五、42（7 表）──────────────────────────────────────────
    {
        "cycle": "K3",
        "variant": "listed",
        "section": "五、42",
        "tables": [
            {"name": "其他应付款", "columns": _two_period("项目", "期末余额", "上年年末余额"), "guidance": _G["k3_main"]},
            {"name": "应付利息", "columns": _two_period("项目", "期末余额", "上年年末余额"), "guidance": _G["k3_interest"]},
            {
                "name": "重要的逾期未付利息",
                "columns": [_label_col("借款单位"), _amt("overdue_amount", "逾期金额"), _txt("overdue_reason", "逾期原因")],
                "guidance": _G["k3_interest_overdue"],
            },
            {
                "name": "应付股利",
                "columns": _two_period("项目（或股东名称）", "期末余额", "上年年末余额"),
                "guidance": _G["k3_dividend"],
            },
            {
                "name": "重要的超过1年未支付的应付股利",
                "columns": [_label_col("股东名称"), _amt("dividend_amount", "应付股利金额"), _txt("unpaid_reason", "未支付原因")],
                "guidance": _G["k3_dividend_overdue"],
            },
            {
                "name": "其他应付款（按款项性质列示）",
                "columns": _two_period("项目", "期末余额", "上年年末余额"),
                "guidance": _G["k3_by_nature"],
            },
            {
                "rename_from": "项  目",
                "name": "其中，账龄超过1年的重要其他应付款",
                "columns": [_label_col("项目"), _amt("end_amount", "期末余额"), _txt("unpaid_reason", "未偿还或未结转的原因")],
                "guidance": _G["k3_aging_over1y"],
            },
        ],
    },
    # ── K3 soe §八、42（6 表）─────────────────────────────────────────────
    {
        "cycle": "K3",
        "variant": "soe",
        "section": "八、42",
        "tables": [
            {"name": "其他应付款", "columns": _two_period("类别", "期末余额", "期初余额"), "guidance": _G["k3_main"]},
            {"name": "应付利息", "columns": _two_period("项目", "期末余额", "期初余额"), "guidance": _G["k3_interest"]},
            {
                "name": "重要的已逾期未支付的利息情况",
                "columns": [_label_col("债权单位"), _amt("overdue_amount", "逾期金额"), _txt("overdue_reason", "逾期原因")],
                "guidance": _G["k3_interest_overdue"],
            },
            {"name": "应付股利", "columns": _two_period("项目", "期末余额", "期初余额"), "guidance": _G["k3_dividend"]},
            {"name": "按款项性质列示", "columns": _two_period("项目", "期末余额", "期初余额"), "guidance": _G["k3_by_nature"]},
            {
                "rename_from": "其他应付款（表6）",
                "name": "账龄超过1年的重要其他应付款项",
                "columns": [_label_col("债权单位名称"), _amt("end_amount", "期末余额"), _txt("unpaid_reason", "未偿还原因")],
                "guidance": _G["k3_soe_aging_over1y"],
            },
        ],
    },
    # ── K4 listed §五、44（3 表）──────────────────────────────────────────
    {
        "cycle": "K4",
        "variant": "listed",
        "section": "五、44",
        "tables": [
            {
                "name": "其他流动负债",
                "columns": _two_period("项目", "期末余额", "上年年末余额"),
                "guidance": _G["k4_main_listed"],
            },
            {
                # 列键与 `k4NoteSectionMap.ts` 既有 builder 逐字一致（模板 seed 与同步载荷同形）
                "name": "短期应付债券",
                "columns": [
                    _col("bond_name", "债券名称", is_label=True, flat=True),
                    _amt("face_value", "面值"),
                    _pct("coupon_rate", "票面利率"),
                    _txt("issue_date", "发行日期"),
                    _txt("term", "债券期限"),
                    _amt("issue_amount", "发行金额"),
                ],
                "guidance": _G["k4_bond"],
            },
            {
                "rename_from": "债券名称",
                "name": "短期应付债券（续）",
                "columns": [
                    _col("bond_name", "债券名称", is_label=True, flat=True),
                    _amt("begin_amount", "期初余额"),
                    _amt("issued", "本期发行"),
                    _amt("interest_accrued", "按面值计提利息"),
                    _amt("premium_amort", "溢折价摊销"),
                    _amt("repaid", "本期偿还"),
                    _amt("end_amount", "期末余额"),
                    _txt("defaulted", "是否违约"),
                ],
                "guidance": _G["k4_bond_cont"],
            },
        ],
    },
    # ── K4 soe §八、48（1 表）─────────────────────────────────────────────
    {
        "cycle": "K4",
        "variant": "soe",
        "section": "八、48",
        "tables": [
            {"name": "其他流动负债", "columns": _two_period("项目", "期末余额", "期初余额"), "guidance": _G["k4_main_soe"]},
        ],
    },
    # ── K5 listed §五、50（1 表，4 列含形成原因）──────────────────────────
    {
        "cycle": "K5",
        "variant": "listed",
        "section": "五、50",
        "tables": [
            {
                "name": "预计负债",
                # 列键与 `k5NoteSectionMap.ts` 既有 builder 逐字一致
                "columns": [
                    *_two_period("项目", "期末余额", "上年年末余额"),
                    _txt("reason", "形成原因"),
                ],
                "guidance": _G["k5_listed"],
            },
        ],
    },
    # ── K5 soe §八、55（1 表，3 列）────────────────────────────────────────
    {
        "cycle": "K5",
        "variant": "soe",
        "section": "八、55",
        "tables": [
            {"name": "预计负债", "columns": _two_period("项目", "期末余额", "期初余额"), "guidance": _G["k5_soe"]},
        ],
    },
    # ── K7 listed §五、51（1 表，6 列 roll-forward）────────────────────────
    {
        "cycle": "K7",
        "variant": "listed",
        "section": "五、51",
        "tables": [
            {
                "name": "递延收益",
                # 列键与 `k7NoteSectionMap.ts` 既有 builder 逐字一致
                "columns": [
                    _label_col("项目"),
                    _amt("begin_amount", "期初余额"),
                    _amt("increase", "本期增加"),
                    _amt("decrease", "本期减少"),
                    _amt("end_amount", "期末余额"),
                    _txt("reason", "形成原因"),
                ],
                "guidance": _G["k7_listed"],
            },
        ],
    },
    # ── K7 soe §八、56（2 表）─────────────────────────────────────────────
    {
        "cycle": "K7",
        "variant": "soe",
        "section": "八、56",
        "tables": [
            {
                "name": "递延收益",
                # 列键与 `k7NoteSectionMap.ts` 既有 builder 逐字一致（国企无「形成原因」列）
                "columns": [
                    _label_col("项目"),
                    _amt("begin_amount", "期初余额"),
                    _amt("increase", "本期增加"),
                    _amt("decrease", "本期减少"),
                    _amt("end_amount", "期末余额"),
                ],
                "guidance": _G["k7_soe_main"],
            },
            {
                "name": "其中：递延收益-政府补助情况",
                "columns": [
                    _col("grant_item", "补助项目", is_label=True, flat=True),
                    _amt("begin_amount", "期初余额"),
                    _amt("new_grant", "本期新增补助金额"),
                    _amt("to_pl", "本期计入损益金额"),
                    _txt("pl_line_item", "本期计入损益的列报项目"),
                    _amt("refund", "本期返还的金额"),
                    _amt("other_change", "其他变动"),
                    _amt("end_amount", "期末余额"),
                    _txt("grant_kind", "与资产相关/与收益相关"),
                    _txt("refund_reason", "本期返还的原因"),
                ],
                "guidance": _G["k7_soe_grant"],
            },
        ],
    },
]


# ─────────────────────────── 应用 ───────────────────────────

def _find_section(doc: dict[str, Any], section_number: str) -> dict[str, Any] | None:
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")) == section_number:
            return sec
    return None


def _strip_placeholder_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        r
        for r in rows
        if str(r.get("row_type", "")) != "header_label" and _norm(r.get("label")) not in _PLACEHOLDER_NORM
    ]


def apply_section(section: dict[str, Any], entry: dict[str, Any]) -> tuple[list[str], list[str]]:
    tables: list[dict[str, Any]] = section.get("tables") or []
    changes: list[str] = []
    warnings: list[str] = []
    cursor = 0

    for spec in entry["tables"]:
        want_name = spec["name"]
        aliases = [want_name]
        if spec.get("rename_from"):
            aliases.insert(0, spec["rename_from"])
        idx = next(
            (i for i in range(cursor, len(tables)) if str(tables[i].get("name", "")) in aliases),
            None,
        )
        if idx is None:
            warnings.append(f"未找到表 {aliases}（游标 {cursor}）→ 跳过")
            continue

        tbl = tables[idx]
        old_name = str(tbl.get("name", ""))
        if old_name != want_name:
            dup = next(
                (j for j, t in enumerate(tables) if j != idx and str(t.get("name", "")) == want_name),
                None,
            )
            if dup is not None:
                warnings.append(f"表名迁移跳过：「{old_name}」→「{want_name}」，索引 {dup} 已占用")
            else:
                tbl["name"] = want_name
                changes.append(f"[{idx}] 表名：「{old_name}」→「{want_name}」")

        want_cols = spec["columns"]
        want_headers = [str(c["label"]) for c in want_cols]
        if tbl.get("headers") != want_headers:
            changes.append(f"[{idx}] {want_name}.headers：{tbl.get('headers')} → {want_headers}")
            tbl["headers"] = want_headers
        if tbl.get("columns") != want_cols:
            old_n = len(tbl.get("columns") or [])
            tbl["columns"] = json.loads(json.dumps(want_cols, ensure_ascii=False))
            changes.append(f"[{idx}] {want_name}.columns：{old_n} → {len(want_cols)} 项")
        if tbl.pop("_column_groups", None) is not None:
            changes.append(f"[{idx}] {want_name}._column_groups：删除（单级表头，靠 flat 表态）")

        old_rows = tbl.get("rows") or []
        new_rows = _strip_placeholder_rows(old_rows)
        if new_rows != old_rows:
            dropped = [str(r.get("label")) for r in old_rows if r not in new_rows]
            tbl["rows"] = new_rows
            changes.append(f"[{idx}] {want_name}.rows：{len(old_rows)} → {len(new_rows)} 行（删 {dropped}）")

        if tbl.get("guidance") != spec["guidance"]:
            tbl["guidance"] = spec["guidance"]
            changes.append(f"[{idx}] {want_name}.guidance → {len(spec['guidance'])} 字")

        cursor = idx + 1

    return changes, warnings


def _stamp(section: dict[str, Any]) -> None:
    section["_aligned_by"] = ALIGNED_BY
    section["_aligned_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────── 校验 ───────────────────────────

def validate_section(section: dict[str, Any], entry: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    tables = section.get("tables") or []
    names = [str(t.get("name", "")) for t in tables]

    for n in set(names):
        if names.count(n) > 1:
            errs.append(f"表名重复：「{n}」")
    for leaked in LEAKED_NAMES:
        if leaked in names:
            errs.append(f"泄漏/假表名残留：「{leaked}」")

    by_name = {str(t.get("name", "")): t for t in tables}
    for spec in entry["tables"]:
        name = spec["name"]
        tbl = by_name.get(name)
        if tbl is None:
            errs.append(f"缺表：「{name}」")
            continue

        want_cols = spec["columns"]
        cols = tbl.get("columns") or []
        headers = tbl.get("headers") or []
        if len(cols) != len(want_cols):
            errs.append(f"{name} columns={len(cols)} ≠ 期望 {len(want_cols)}")
        if [str(c.get("label")) for c in cols] != [str(c["label"]) for c in want_cols]:
            errs.append(f"{name} columns 标签与期望不一致：{[c.get('label') for c in cols]}")
        if [str(c.get("key")) for c in cols] != [str(c["key"]) for c in want_cols]:
            errs.append(f"{name} columns 键与期望不一致：{[c.get('key') for c in cols]}")
        if headers != [str(c["label"]) for c in want_cols]:
            errs.append(f"{name} headers 与 columns 不同形：{headers}")
        if cols and not cols[0].get("is_label"):
            errs.append(f"{name} columns[0] 未标 is_label")
        if not any(c.get("flat") for c in cols):
            errs.append(f"{name} 未显式 flat")
        if any(c.get("group") for c in cols):
            errs.append(f"{name} 不应有 group")
        if tbl.get("_column_groups"):
            errs.append(f"{name} 标了 flat 却仍留 _column_groups")
        if not str(tbl.get("guidance", "")).strip():
            errs.append(f"{name} 缺 guidance")

        for j, row in enumerate(tbl.get("rows") or []):
            if str(row.get("row_type", "")) == "header_label":
                errs.append(f"{name} 第 {j} 行仍为 header_label 假数据行")
            if _norm(row.get("label")) in _PLACEHOLDER_NORM:
                errs.append(f"{name} 第 {j} 行仍为占位说明行「{row.get('label')}」")
            vals = row.get("values")
            if isinstance(vals, list) and len(vals) != max(len(headers) - 1, 0):
                errs.append(f"{name} 第 {j} 行 values={len(vals)} ≠ headers-1")

    want_count = len(entry["tables"])
    if len(tables) != want_count:
        errs.append(f"表数 {len(tables)} ≠ 期望 {want_count}")

    return errs


# ─────────────────────────── 入口 ───────────────────────────

def _process(*, dry_run: bool, check_only: bool) -> tuple[bool, list[str]]:
    docs: dict[str, tuple[Path, dict[str, Any], str]] = {}
    for key, path in (("listed", LISTED_PATH), ("soe", SOE_PATH)):
        raw = path.read_text(encoding="utf-8")
        docs[key] = (path, json.loads(raw), raw)

    log: list[str] = []
    ok_all = True
    dirty: set[str] = set()

    for entry in PLAN:
        variant = entry["variant"]
        _path, doc, _raw = docs[variant]
        section = _find_section(doc, entry["section"])
        head = f"=== {entry['cycle']} {variant} §{entry['section']} ==="
        if section is None:
            log.append(head)
            log.append("[FATAL] 未找到章节")
            ok_all = False
            continue

        log.append(f"{head} {section.get('section_title')}")

        if check_only:
            errs = validate_section(section, entry)
            if section.get("_aligned_by") != ALIGNED_BY:
                errs.append("尚未对齐（缺 _aligned_by 标记）")
            if errs:
                log.extend(f"  {e}" for e in errs)
            else:
                log.append("  结构校验通过")
            ok_all = ok_all and not errs
            continue

        changes, warnings = apply_section(section, entry)
        if changes:
            log.extend(f"  {c}" for c in changes)
        else:
            log.append("  无需修改（已对齐）")
        log.extend(f"  [WARN] {w}" for w in warnings)

        errs = validate_section(section, entry)
        if errs:
            log.append("  [FATAL] 修订后校验失败：")
            log.extend(f"    {e}" for e in errs)
            ok_all = False
            continue

        if changes or section.get("_aligned_by") != ALIGNED_BY:
            _stamp(section)
            dirty.add(variant)

    if not check_only and not dry_run and ok_all:
        for variant in sorted(dirty):
            path, doc, raw = docs[variant]
            trailing = "\n" if raw.endswith("\n") else ""
            path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + trailing, encoding="utf-8")
            log.append(f"已写入 {path}")
        if not dirty:
            log.append("全部已对齐，无需写入")
    elif dry_run:
        log.append(f"[dry-run] 未写文件（待写变体：{sorted(dirty)}）")

    return ok_all, log


def main() -> int:
    ap = argparse.ArgumentParser(description="附注 K 系负债/递延类章节结构对齐源模版（幂等，K3/K4/K5/K7）")
    ap.add_argument("--dry-run", action="store_true", help="只打印 diff 摘要，不写文件")
    ap.add_argument("--check", action="store_true", help="仅校验对齐状态（供 CI）")
    args = ap.parse_args()

    ok, log = _process(dry_run=args.dry_run, check_only=args.check)
    print("\n".join(log))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
