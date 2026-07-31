#!/usr/bin/env python
"""附注 K 系损益类章节结构对齐源模版（幂等修订，批 1 = K8~K13）。

**范围**（六循环两版共 12 个章节、13 张表）：

| 循环 | listed 章节号 | soe 章节号 |
|------|--------------|-----------|
| K8 销售费用     | 五、64 | 八、65 |
| K9 管理费用     | 五、65 | 八、66 |
| K10 其他收益    | 五、68 | 八、69 |
| K11 资产减值损失 | 三、资产减值损失（损 | 八、74 |
| K12 营业外收入  | 三、营业外收入（注： | 八、76 |
| K13 营业外支出  | 三、营业外支出（注： | 八、77 |

🔴 **listed 侧三个章节号带截断后缀是模板既有形态，不是笔误** —— listed 模板
``三、`` 整章 70+ 条 ``section_number`` 都被 ``rebuild_note_from_md.py`` 截断为
10 字符（``三、重要性标准确定方`` / ``三、投资性房地产【不`` …）。改章节号会波及
全章与并发 spec，故本脚本**只改表名/行/列/guidance，不动 section_number**，
由前端常量对齐模板实测值。

历史问题（2026-07-30 实测）：

1. K11/K12/K13 listed 表名是**表头首格泄漏** ``项  目`` → TAB 页签显示列名；
2. K12/K13 listed 与 soe 的 ``rows`` 残留**占位说明行**（``可无限量添加行`` /
   ``......`` / ``……``）→ 渲染成一行空披露数据；
3. 13 张表**全部**缺 ``columns``（未表态）+ 缺 ``guidance``
   → seed 路径回退 ``_infer_groups_from_headers`` 前缀推断、TAB 无编制提示。

**权威源**（三者互证）：

- ``backend/wp_templates/K/K{8..13} *.xlsx`` 的两个披露 tab（逐格实证：
  K8/K9 三列且分「个别报表 / 合并报表」两块；K10 三列 + 提示；K11 三列 +
  「注：本科目明细表按照正数填列、披露表按照负数填列」；K12/K13 **四列**
  含「计入当期非经常性损益的金额」）；
- ``note_template_{listed,soe}.json``（交付物权威）：列名与固定行名以此为准，
  其中 **K10 国企是 4 列**（末列「是否为政府补助」，行含「其中：政府补助」）；
- ``note_check_preset_formulas.json``：损益类勾稽为「报表科目 = 合计行本期发生额」
  + 「各明细行之和 = 合计行」。

裁决要点：

- 六循环源 xlsx 披露表都是**单行表头** → 13 张表一律显式 ``flat``，删 ``_column_groups``。
- K8/K9 源 xlsx 的「合并报表」块不进附注（该章模板只有 1 张表，推两张会造孤儿表）。
- K12 国企源 xlsx 的「与企业日常活动无关的政府补助明细」不进附注（§八、76 无落点）。

Usage::

    python backend/scripts/fix/fix_note_k_pl_structure.py --dry-run
    python backend/scripts/fix/fix_note_k_pl_structure.py
    python backend/scripts/fix/fix_note_k_pl_structure.py --check

spec: .kiro/specs/k-cycle-disclosure-alignment/ R4（Task 1）
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"

ALIGNED_BY = "k-cycle-disclosure-alignment/pl"

LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

# ── 泄漏表名（表头首格被 md 重建当成表名）───────────────────────────────────
LEAKED_TABLE_NAME = "项  目"

# ── 占位说明行（渲染成空披露数据行，须删）───────────────────────────────────
PLACEHOLDER_ROW_LABELS = {"可无限量添加行", "......", "……", "…", "...."}


def _norm(label: Any) -> str:
    return str(label or "").replace(" ", "").replace("\u3000", "").strip()


# ─────────────────────────── 列结构 ───────────────────────────

def _cols3(label_head: str, cur_head: str, prior_head: str) -> list[dict[str, Any]]:
    """三列单行表头：项目 + 本期 / 上期发生额。``flat`` 标在标签列即整表生效。"""
    return [
        {"key": "label", "label": label_head, "is_label": True, "flat": True},
        {"key": "current_amount", "label": cur_head, "format": "amount"},
        {"key": "prior_amount", "label": prior_head, "format": "amount"},
    ]


def _cols4_amount(label_head: str, cur_head: str, prior_head: str, extra_head: str) -> list[dict[str, Any]]:
    return [
        *_cols3(label_head, cur_head, prior_head),
        {"key": "non_recurring_amount", "label": extra_head, "format": "amount"},
    ]


def _cols4_text(label_head: str, cur_head: str, prior_head: str, extra_head: str) -> list[dict[str, Any]]:
    return [
        *_cols3(label_head, cur_head, prior_head),
        {"key": "is_gov_grant", "label": extra_head, "format": "text"},
    ]


# ─────────────────────────── guidance ───────────────────────────

_G_K8 = (
    "【提示：对于与履行客户合同无关的运输费用，若运输费用属于使存货达到目前场所和状态的"
    "必要支出，形成了预期会给企业带来经济利益的资源时，运输费用应当计入存货成本，"
    "否则应计入期间费用。对于为履行客户合同而发生的运输费用，属于收入准则规范下的"
    "合同履约成本，最终计入到营业成本中。】"
    "按费用性质列示，明细项目随项目实际情况增删。"
    "勾稽：合计行本期发生额 = 利润表「销售费用」本期金额；各明细行之和 = 合计行（逐列）。"
    "数据来源：审定表 K8-1。源模板另有「销售费用（合并报表）」块，合并口径在合并附注模板列示，本表为个别报表口径。"
)

_G_K9 = (
    "【提示：企业根据《残疾人就业保障金征收使用管理办法》（财税〔2015〕72号）的规定，"
    "应缴纳的残疾人就业保障金，应当计入“管理费用”科目。】"
    "【提示：不符合固定资产资本化后续支出条件的固定资产日常修理费用，在发生时应当按照"
    "受益对象计入当期损益或计入相关资产的成本。与存货的生产和加工相关的固定资产日常"
    "修理费用按照存货成本确定原则进行处理，行政管理部门、企业专设的销售机构等发生的"
    "固定资产日常修理费用按照功能分类计入管理费用或销售费用。】"
    "按费用性质列示。勾稽：合计行本期发生额 = 利润表「管理费用」本期金额；各明细行之和 = 合计行（逐列）。"
    "数据来源：审定表 K9-1。源模板另有「管理费用（合并报表）」块，合并口径在合并附注模板列示。"
)

_G_K10_LISTED = (
    "【提示：（1）与日常活动相关的政府补助，采用总额法时计入其他收益；"
    "（2）填列企业作为个人所得税的扣缴义务人，根据《中华人民共和国个人所得税法》收到的"
    "扣缴税款手续费；（3）进项税加计扣除；在“实际缴纳增值税时”，将增值税进项税额加计"
    "扣除金额计入“其他收益”科目；（4）债务重组中，债务人以非金融资产清偿债务的，"
    "所清偿债务账面价值与存货等账面价值之间的差额，记入“其他收益”；"
    "（5）企业超比例安排残疾人就业或者为安排残疾人就业做出显著成绩，按规定收到的奖励，"
    "计入“其他收益”科目；（6）小微企业达到增值税制度规定的免征增值税条件时，"
    "将有关应交增值税转入“其他收益”科目；（7）当期直接减免的增值税，"
    "借记“应交税费——应交增值税（减免税款）”，贷记“其他收益”。】"
    "政府补助的具体信息，详见附注政府补助章节。"
    "勾稽：合计行本期发生额 = 利润表「其他收益」本期金额；各明细行之和 = 合计行（逐列）。"
    "数据来源：明细表 K10-2。"
)

_G_K10_SOE = (
    "【提示：（1）与日常活动相关的政府补助，采用总额法时计入其他收益；"
    "（2）填列企业作为个人所得税的扣缴义务人收到的扣缴税款手续费；（3）进项税加计扣除；"
    "（4）债务重组中债务人以非金融资产清偿债务形成的差额；"
    "（5）超比例安排残疾人就业收到的奖励；（6）小微企业免征增值税转入；"
    "（7）当期直接减免的增值税。】"
    "第 4 列「是否为政府补助」按项目性质点选；「其中：政府补助」为结构行，用于单独反映"
    "政府补助部分，不参与明细行求和。"
    "勾稽：合计行本期发生额 = 利润表「其他收益」本期金额；各明细行之和 = 合计行（逐列）。"
    "数据来源：明细表 K10-2。"
)

_G_K11 = (
    "源模板要求：资产减值损失（注：损失以“—”号填列，以下不存在的项目可以删除）；"
    "本科目明细表按照正数填列、披露表按照负数填列。"
    "勾稽：合计行本期发生额 = 利润表「资产减值损失」本期金额；各明细行之和 = 合计行（逐列）；"
    "各资产类别减值损失与对应循环减值准备变动表本期计提数一致。"
    "数据来源：审定表 K11-1。"
)

_G_K12_LISTED = (
    "【提示：1、“营业外收入”，反映企业发生的营业利润以外的收益，主要包括与企业日常活动"
    "无关的政府补助、盘盈利得、捐赠利得（企业接受股东或股东的子公司直接或间接的捐赠，"
    "经济实质属于股东对企业的资本性投入的除外）等。不包括存货盘盈利得；不包括固定资产"
    "盘盈利得。2、“政府补助”仅列示与日常活动无关（如与自然灾害等不可抗力发生的停工、"
    "停产损失有关的政府补助）且采用总额法进行处理的政府补助。】"
    "源模板注：以下不存在的项目可以删除；明细项目可按实际情况增行。"
    "（1）政府补助的具体信息，详见附注政府补助章节；（2）作为经常性损益的政府补助，"
    "具体原因见非经常性损益章节。"
    "勾稽：合计行本期发生额 = 利润表「营业外收入」本期金额；各明细行之和 = 合计行（逐列，"
    "含「计入当期非经常性损益的金额」列）。数据来源：审定表 K12-1 / 明细表 K12-2。"
)

_G_K12_SOE = (
    "（注：企业可根据实际情况，单独披露金额较大的项目。）"
    "【提示：“营业外收入”，反映企业发生的营业利润以外的收益，主要包括与企业日常活动无关的"
    "政府补助、非流动资产毁损报废利得、捐赠利得（企业接受股东或股东的子公司直接或间接的"
    "捐赠，经济实质属于股东对企业的资本性投入的除外）等。】"
    "勾稽：合计行本期发生额 = 利润表「营业外收入」本期金额；各明细行之和 = 合计行（逐列，"
    "含「计入当期非经常性损益的金额」列）。数据来源：审定表 K12-1 / 明细表 K12-2。"
    "源模板另有「与企业日常活动无关的政府补助明细」块，本章节无对应表，保留在底稿侧作审计明细。"
)

_G_K13_LISTED = (
    "【提示：1、“营业外支出”，反映企业发生的营业利润以外的支出，主要包括公益性捐赠支出、"
    "非常损失、盘亏损失、非流动资产毁损报废损失等。不包括存货盘亏损失。"
    "2、企业未按规定缴纳残疾人就业保障金，按规定缴纳的滞纳金，计入“营业外支出”科目。】"
    "源模板注：以下不存在的项目可以删除；明细项目可按实际情况增行。"
    "勾稽：合计行本期发生额 = 利润表「营业外支出」本期金额；各明细行之和 = 合计行（逐列，"
    "含「计入当期非经常性损益的金额」列）。数据来源：审定表 K13-1 / 明细表 K13-2。"
)

_G_K13_SOE = (
    "（注：企业可根据实际情况，单独披露金额较大的项目。）"
    "【提示：“营业外支出”反映企业发生的营业利润以外的支出，主要包括对外捐赠支出、"
    "非流动资产毁损报废损失、非常损失、盘亏损失等。】"
    "【提示：企业未按规定缴纳残疾人就业保障金，按规定缴纳的滞纳金，计入“营业外支出”科目。】"
    "勾稽：合计行本期发生额 = 利润表「营业外支出」本期金额；各明细行之和 = 合计行（逐列，"
    "含「计入当期非经常性损益的金额」列）。数据来源：审定表 K13-1 / 明细表 K13-2。"
)


# ─────────────────────────── 修订计划 ───────────────────────────
# 每条 = 一个章节；tables 按位置（游标）匹配，rename 用于泄漏表名迁移。

PLAN: list[dict[str, Any]] = [
    {
        "cycle": "K8",
        "variant": "listed",
        "section": "五、64",
        "tables": [
            {
                "name": "销售费用（按费用性质列示）",
                "columns": _cols3("项目", "本期发生额", "上期发生额"),
                "guidance": _G_K8,
            }
        ],
    },
    {
        "cycle": "K8",
        "variant": "soe",
        "section": "八、65",
        "tables": [
            {"name": "销售费用", "columns": _cols3("项目", "本期发生额", "上期发生额"), "guidance": _G_K8}
        ],
    },
    {
        "cycle": "K9",
        "variant": "listed",
        "section": "五、65",
        "tables": [
            {
                "name": "管理费用（按费用性质列示）",
                "columns": _cols3("项目", "本期发生额", "上期发生额"),
                "guidance": _G_K9,
            }
        ],
    },
    {
        "cycle": "K9",
        "variant": "soe",
        "section": "八、66",
        "tables": [
            {"name": "管理费用", "columns": _cols3("项目", "本期发生额", "上期发生额"), "guidance": _G_K9}
        ],
    },
    {
        "cycle": "K10",
        "variant": "listed",
        "section": "五、68",
        "tables": [
            {"name": "其他收益", "columns": _cols3("项目", "本期发生额", "上期发生额"), "guidance": _G_K10_LISTED}
        ],
    },
    {
        "cycle": "K10",
        "variant": "soe",
        "section": "八、69",
        "tables": [
            {
                "name": "其他收益",
                "columns": _cols4_text("项目", "本期发生额", "上期发生额", "是否为政府补助"),
                "guidance": _G_K10_SOE,
            }
        ],
    },
    {
        "cycle": "K11",
        "variant": "listed",
        "section": "三、资产减值损失（损",
        "tables": [
            {
                "rename_from": LEAKED_TABLE_NAME,
                "name": "资产减值损失",
                "columns": _cols3("项目", "本期发生额", "上期发生额"),
                "guidance": _G_K11,
            }
        ],
    },
    {
        "cycle": "K11",
        "variant": "soe",
        "section": "八、74",
        "tables": [
            {"name": "资产减值损失", "columns": _cols3("项目", "本期发生额", "上期发生额"), "guidance": _G_K11}
        ],
    },
    {
        "cycle": "K12",
        "variant": "listed",
        "section": "三、营业外收入（注：",
        "tables": [
            {
                "rename_from": LEAKED_TABLE_NAME,
                "name": "营业外收入",
                "columns": _cols4_amount("项目", "本期发生额", "上期发生额", "计入当期非经常性损益的金额"),
                "guidance": _G_K12_LISTED,
            }
        ],
    },
    {
        "cycle": "K12",
        "variant": "soe",
        "section": "八、76",
        "tables": [
            {
                "name": "营业外收入",
                "columns": _cols4_amount("项目", "本期发生额", "上期发生额", "计入当期非经常性损益的金额"),
                "guidance": _G_K12_SOE,
            }
        ],
    },
    {
        "cycle": "K13",
        "variant": "listed",
        "section": "三、营业外支出（注：",
        "tables": [
            {
                "rename_from": LEAKED_TABLE_NAME,
                "name": "营业外支出",
                "columns": _cols4_amount("项目", "本期发生额", "上期发生额", "计入当期非经常性损益的金额"),
                "guidance": _G_K13_LISTED,
            }
        ],
    },
    {
        "cycle": "K13",
        "variant": "soe",
        "section": "八、77",
        "tables": [
            {
                "name": "营业外支出",
                "columns": _cols4_amount("项目", "本期发生额", "上期发生额", "计入当期非经常性损益的金额"),
                "guidance": _G_K13_SOE,
            }
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
    """删占位说明行与 ``header_label`` 假数据行。"""
    out: list[dict[str, Any]] = []
    for r in rows:
        if str(r.get("row_type", "")) == "header_label":
            continue
        if _norm(r.get("label")) in {_norm(x) for x in PLACEHOLDER_ROW_LABELS}:
            continue
        out.append(r)
    return out


def apply_section(section: dict[str, Any], entry: dict[str, Any]) -> tuple[list[str], list[str]]:
    """按计划就地修订单个章节。返回 ``(changes, warnings)``。"""
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
            changes.append(
                f"[{idx}] {want_name}.rows：{len(old_rows)} → {len(new_rows)} 行（删占位行 {dropped}）"
            )

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
    """结构自洽校验：表名齐备唯一 / 列同形 / 显式 flat / guidance / 无占位行。"""
    errs: list[str] = []
    tables = section.get("tables") or []
    names = [str(t.get("name", "")) for t in tables]

    for n in set(names):
        if names.count(n) > 1:
            errs.append(f"表名重复：「{n}」")

    if LEAKED_TABLE_NAME in names:
        errs.append(f"泄漏表名残留：「{LEAKED_TABLE_NAME}」")

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
        if len(headers) != len(want_cols):
            errs.append(f"{name} headers={len(headers)} ≠ columns={len(want_cols)}")
        elif cols and str(cols[0].get("label", "")) != str(headers[0]):
            errs.append(f"{name} columns[0].label ≠ headers[0]")
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
            if _norm(row.get("label")) in {_norm(x) for x in PLACEHOLDER_ROW_LABELS}:
                errs.append(f"{name} 第 {j} 行仍为占位说明行「{row.get('label')}」")
            vals = row.get("values")
            if isinstance(vals, list) and len(vals) != max(len(headers) - 1, 0):
                errs.append(f"{name} 第 {j} 行 values={len(vals)} ≠ headers-1")

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
            log.extend(f"  {e}" for e in errs) if errs else log.append("  结构校验通过")
            ok_all = ok_all and not errs
            continue

        changes, warnings = apply_section(section, entry)
        log.extend(f"  {c}" for c in changes) if changes else log.append("  无需修改（已对齐）")
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
    ap = argparse.ArgumentParser(description="附注 K 系损益类章节结构对齐源模版（幂等，K8~K13）")
    ap.add_argument("--dry-run", action="store_true", help="只打印 diff 摘要，不写文件")
    ap.add_argument("--check", action="store_true", help="仅校验对齐状态（供 CI）")
    args = ap.parse_args()

    ok, log = _process(dry_run=args.dry_run, check_only=args.check)
    print("\n".join(log))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
