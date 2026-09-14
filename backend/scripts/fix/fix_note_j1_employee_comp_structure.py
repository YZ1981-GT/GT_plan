#!/usr/bin/env python
"""附注 J1 应付职工薪酬披露章节结构对齐源模板（幂等修订）。

**目标**：修掉 `j1-disclosure-note-linkage`（已归档）遗留的模板欠账，让
「披露表 → 附注」推送链路的**模板前置条件**成立。

`diagnose_disclosure_sheet_vs_template.py --cycle J1 --section-listed 五、40
--section-soe 八、40` + 逐格精读源 xlsx 跑出的欠账（2026-07-30）：

- 🔴 **soe 八、40 第 3 张表名与第 2 张重名**（都叫 `短期薪酬列示`）。前端
  `j1NoteSectionMap.J1_SUB_TABLE_KEYS.soe.postEmployment` 推的是 `设定提存计划列示`
  → 模板里没有该表名 → **孤儿子表**（模板第 3 张表永空 + 契约 P1 必失败）。
  原 spec 的 "Decision 3：允许偏离模板，键取 text_sections 章节标题" 是绕行而非修复。
  `consol_note_sections_soe.json` 五-41-3 的 `title` 就是 `设定提存计划列示`
  → 证明这是致同原本措辞，改模板不是自造。
- **6 张表全部 `columns` 未表态**：5 列里「本期增加」「本期减少」共享前缀「本期」，
  seed 路径会被 `_infer_groups_from_headers` 反猜出源模板**不存在**的「本期」父表头
  （与 F2 房企 3 表同款缺陷）。→ 标签列标 `flat` 即对整表生效。
- **6 张表全部无 `guidance`**（附注 TAB 页签无编制提示）。
- listed 五、40 表2 残留 `……` 占位行（源模板"可添行"提示被 md 重建脚本落成假数据行
  → 附注渲染出一行空披露数据）→ 删除，语义移入 `guidance`。
- **两侧说明文本区几乎全缺**：
  listed `text_sections` 只有【提示】块（辞退福利 / 一年内到期），源模板 R37/R38/R50/R53
  的 4 段说明**一条都没有**；soe `text_sections` 只有 3 个 `###` 表标题
  （`_is_table_title_paragraph` 判为标题 → 不进任何输出 → 国企附注 J1 文本区 seed 恒空），
  源模板 R42~R44 的 3 条说明全缺。

**权威源**：

- 🔴 源 xlsx = ``backend/wp_templates/J/J1 应付职工薪酬.xlsx``（**运行时权威**；本循环
  **无参考副本**，不存在两处不一致风险）。两个披露 sheet 各 3 张五列变动表 + 说明区。
- ``backend/data/consol_note_sections_{listed,soe}.json``（第 4 方印证：表名 / 表头 / 行序）
- ``backend/data/note_template_variant_matrix.json``（章节号 listed 五、40 / soe 八、40）

裁决要点（详见 spec design）：

- **列头取附注交付口径**「期初余额 / 本期增加 / 本期减少 / 期末余额」。源 xlsx 上市侧写
  「上年年末数 / 期末数」、国企侧写「期初余额 / 期末余额」，而 `consol_note_sections_listed`
  五-40-1/2/3 三张表**都是**期初/期末余额 → 附注侧统一，底稿 UI 各自保留源模板列头
  （已冻结的 Decision 2，前端 `j1MovementColumns()` 负责投影）。
- **不加空白预留行**：源 xlsx 的预留行（listed R11 / R25~R27 / R34）与 `……` 都是
  "可添行"提示。本章节 12~13 个项目**全部具名**，空行在交付物里会被读者当成缺数据 →
  一律不落 `rows`，语义写进 `guidance`。
- **soe 表2 社保「其中」项保持模板的 3 项**（`医疗保险费及生育保险费` / `工伤保险费` /
  `其他`）。源 xlsx 是 4 项（医疗 / 工伤 / 生育 / 其他），但这是**行**差异而非列差异，
  且 `_source=workpaper` 时投影器只渲染底稿推送、不与模板合并 → 底稿推 4 行附注就显示
  4 行，信息更细且不丢。模板 seed 只服务从未同步过的项目，保持致同原文，**不做聚合**
  （聚合会让「生育保险费」在附注里不可见，且引入不可逆变换）。
- **soe 说明第 3 条的交叉引用改指 `八、54`**：源 xlsx 写"详见附注八、47"，但平台现行
  编号 `八、47` = 「（3）一年内到期的长期应付款」，`八、54` = 「长期应付职工薪酬」
  （8 张设定受益计划表在此）→ 源模板编号已过时，按实证指向正确章节。

Usage::

    python backend/scripts/fix/fix_note_j1_employee_comp_structure.py --dry-run
    python backend/scripts/fix/fix_note_j1_employee_comp_structure.py
    python backend/scripts/fix/fix_note_j1_employee_comp_structure.py --check

spec: .kiro/specs/j1-disclosure-template-alignment/ Task 1
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

ALIGNED_BY = "j1-disclosure-template-alignment"

TEMPLATE_PATH = {
    "listed": DATA_DIR / "note_template_listed.json",
    "soe": DATA_DIR / "note_template_soe.json",
}

AMOUNT = "amount"


# ─────────────────────────── 行 / 列构造 ───────────────────────────

def _data(label: str) -> dict[str, Any]:
    return {"label": label, "row_type": "data"}


def _total(label: str = "合计") -> dict[str, Any]:
    return {"label": label, "is_total": True, "row_type": "total"}


def _labels_then_total(labels: list[str]) -> list[dict[str, Any]]:
    return [_data(x) for x in labels] + [_total()]


def _movement_columns() -> list[dict[str, Any]]:
    """J1 三张表共用的 5 列单级表头（与前端 `j1MovementColumns()` 逐字一致）。

    🔴 标签列标 `flat`：本表是单行表头，但「本期增加」「本期减少」共享前缀「本期」，
    不表态会被后端 `_infer_groups_from_headers` 反猜出凭空的「本期」父表头。
    """
    return [
        {"key": "项目", "label": "项目", "is_label": True, "flat": True},
        {"key": "期初余额", "label": "期初余额", "format": AMOUNT},
        {"key": "本期增加", "label": "本期增加", "format": AMOUNT},
        {"key": "本期减少", "label": "本期减少", "format": AMOUNT},
        {"key": "期末余额", "label": "期末余额", "format": AMOUNT},
    ]


MOVEMENT_HEADERS = ["项目", "期初余额", "本期增加", "本期减少", "期末余额"]


# ─────────────────────────── 表名常量 ───────────────────────────
# 🔴 每个值必须与前端 `j1NoteSectionMap.J1_SUB_TABLE_KEYS` 逐字一致，
#    否则同步产出孤儿子表（附注 TAB 永空 + 底稿数据丢失）。

T_LISTED_SUMMARY = "应付职工薪酬"
T_LISTED_SHORT_TERM = "短期薪酬"
T_LISTED_POST = "设定提存计划"

T_SOE_SUMMARY = "应付职工薪酬列示"
T_SOE_SHORT_TERM = "短期薪酬列示"
T_SOE_POST = "设定提存计划列示"


# ─────────────────────────── guidance 片段 ───────────────────────────
# 只取：源 xlsx 红字 / CAS 9 条款 / 以「勾稽：」前缀标注的**源模板 Excel 公式**实证关系。

_G_SUMMARY_COMMON = (
    "勾稽：逐行 期末余额 = 期初余额 + 本期增加 − 本期减少；各类别行之和 = 合计行"
    "（四列各自独立校验）；「短期薪酬」行 = 下方「短期薪酬」表合计行，"
    "「离职后福利-设定提存计划」行 = 下方「设定提存计划」表合计行"
    "（源模板三张表同引「明细表J1-2 」，互为勾稽关系而非派生）；"
    "合计行期末余额 = 资产负债表「应付职工薪酬」期末数 = J1-1 审定表期末审定合计。"
)

_G_SUMMARY_LISTED = (
    "按 CAS 9 分类列示应付职工薪酬的期初、本期增减与期末。"
    "【提示：辞退福利包括（1）预期在其确认的年度报告期间期末后12个月内完全支付的辞退福利；"
    "（2）补偿款超过1年支付的辞退计划将于年度报告期间期末后12个月内支付的款项，"
    "例如内退计划将于下一年支付的金额。"
    "一年内到期的其他福利：指一年内到期的其他长期福利（不含设定受益计划），"
    "应根据「长期应付职工薪酬」项目分析填列。】"
    + _G_SUMMARY_COMMON
    + "另注：应付职工薪酬、设定受益计划净负债（净资产）、一年后支付的辞退福利及其他长期"
    "职工福利的本期减少，一般与现金流量表「支付给职工以及为职工支付的现金」一致，"
    "除非存在代扣税未交、实物发放等情形。"
)

_G_SUMMARY_SOE = (
    "按国企口径分类列示应付职工薪酬的期初余额、本期增减与期末余额（不适用的类别可删除）。"
    + _G_SUMMARY_COMMON
)

_G_SHORT_TERM_COMMON = (
    "勾稽：「社会保险费」行 = 其下「其中：」各险种之和（源模板父行为 SUM 公式，"
    "不应手工录入）；合计行 = 各非「其中：」行之和（源模板合计公式显式排除「其中：」"
    "明细行，避免双算）；逐行 期末余额 = 期初余额 + 本期增加 − 本期减少；"
    "合计行 = 上方汇总表「短期薪酬」行。"
)

_G_SHORT_TERM_LISTED = (
    "上市公司口径的短期薪酬明细。源模板在「其中：」区与「其他短期薪酬」之后各留有"
    "可插入行的空白区（原表以「……」标注），如实际险种多于示例，请在对应区间内新增行，"
    "不要改动父行的汇总范围。"
    + _G_SHORT_TERM_COMMON
    + "说明区须披露本期非货币性福利的形式及其计算依据，以及短期利润分享计划的薪酬计算依据。"
)

_G_SHORT_TERM_SOE = (
    "国企口径的短期薪酬明细。本表 seed 骨架按附注模板列「其中：医疗保险费及生育保险费 / "
    "工伤保险费 / 其他」3 项；源底稿（J1 国企披露 sheet）按医疗 / 工伤 / 生育 / 其他 4 项"
    "录入，同步后附注按底稿实际行呈现（更细，不做聚合）。"
    "国企版无独立「非货币性福利」行，源模板将其并入「其他短期薪酬」。"
    + _G_SHORT_TERM_COMMON
)

_G_POST_COMMON = (
    "勾稽：「离职后福利」行 = 其下「其中：」四项之和（基本养老保险费 / 失业保险费 / "
    "企业年金缴费 / 其他）；「其他长期职工福利」行 = 其下「其中：」各项之和；"
    "合计行 = 「离职后福利」+「其他长期职工福利」（源模板合计公式只加这两个父行，"
    "不含「其中：」明细）；逐行 期末余额 = 期初余额 + 本期增加 − 本期减少；"
    "合计行 = 上方汇总表「离职后福利-设定提存计划」行。"
)

_G_POST_LISTED = (
    "设定提存计划（CAS 9）：企业每期将应缴存金额确认为负债并计入当期损益或相关资产成本。"
    "【提示：其他长期职工福利指符合设定提存计划条件的其他长期职工福利。】"
    + _G_POST_COMMON
    + "说明区须披露设定提存计划的性质、计算缴费金额的公式或依据。"
)

_G_POST_SOE = (
    "国企口径的设定提存计划列示（不适用的类别可删除）。"
    + _G_POST_COMMON
    + "说明区须披露设定提存计划的性质与缴费金额计算依据；存在设定受益计划的，"
    "另见附注八、54「长期应付职工薪酬」。"
)


# ─────────────────────────── text_sections ───────────────────────────
# 🔴 不得以 `####` 开头：`_is_table_title_paragraph` 认 `#` 即标题，标题本身不进任何输出
#    → 实质披露正文会被静默丢弃（H1 上市 R84 曾中招）。
# listed：保留原【提示】块（含 IAS19 括注）+ 补源模板 R36~R38 / R50 / R53 的说明段
#         + R54 现金流量勾稽注。
# soe：保留 3 个 `###` 表标题（正确对应 3 张表）+ 补源模板 R41~R44 的 3 条说明。

LISTED_TEXT_SECTIONS = [
    "【提示：",
    "1、辞退福利包括（1）预期在其确认的年度报告期间期末后12个月内完全支付的辞退福利；"
    "（2）补偿款超过1年支付的辞退计划将于年度报告期间期末后12个月内支付的款项，"
    "例如内退计划将于下一年支付的金额。",
    "2、一年内到期的其他福利：指一年内到期的其他长期福利（不含设定受益计划）；"
    "应根据“长期应付职工薪酬”项目分析填列。",
    "IAS19-雇员福利-200 ・国际会计准则委员会决定，不规定主体是否应区分离职后福利产生的"
    "资产和负债的流动和非流动部分，因为这一区分有时可能是武断的。】",
    "说明：",
    "1、企业本期为职工提供的各项非货币性福利形式、其计算依据。",
    "2、企业依据短期利润分享计划提供的职工薪酬计算依据。",
    "3、设定提存计划的性质、计算缴费金额的公式或依据。",
    "4、辞退福利的性质、内容及计算依据。",
    "【提示：其他长期职工福利指符合设定提存计划条件的其他长期职工福利】",
    "（注：应付职工薪酬、设定受益计划净负债（净资产）、一年后支付的辞退福利及其他长期"
    "职工福利本期减少一般与现金流量中“支付职工”项一致，除非代扣税未交、实物发放等）",
]

SOE_TEXT_SECTIONS = [
    "### 应付职工薪酬列示",
    "### 短期薪酬列示",
    "### 设定提存计划列示",
    "说明：",
    "1.企业本期为职工提供的各项非货币性福利的形式、金额及其计算依据。",
    "2.企业应说明设立或参与的设定提存计划的性质、计算缴费金额的公式或依据。",
    "3.存在设定受益计划的企业，应说明设定受益计划的特征及与之相关的风险、在财务报表中"
    "确认的金额及其变动、对未来现金流的影响、重大精算假设及有关敏感性分析等。"
    "设定受益计划情况详见附注八、54「长期应付职工薪酬」。",
]


# ─────────────────────────── 修订计划 ───────────────────────────

SECTION_PLANS: dict[str, dict[str, Any]] = {
    "listed": {
        "section": "五、40",
        "text_sections": LISTED_TEXT_SECTIONS,
        "plan": [
            {
                "aliases": [T_LISTED_SUMMARY],
                "headers": MOVEMENT_HEADERS,
                "columns": _movement_columns(),
                "rows": _labels_then_total([
                    "短期薪酬",
                    "离职后福利-设定提存计划",
                    "辞退福利",
                    "一年内到期的其他福利",
                ]),
                "guidance": _G_SUMMARY_LISTED,
            },
            {
                "aliases": [T_LISTED_SHORT_TERM],
                "headers": MOVEMENT_HEADERS,
                "columns": _movement_columns(),
                # 🔴 删掉源模板的 `……` 占位行（"可添行"提示，非数据行）
                "rows": _labels_then_total([
                    "工资、奖金、津贴和补贴",
                    "职工福利费",
                    "社会保险费",
                    "其中：1．医疗保险费",
                    "2．工伤保险费",
                    "3．生育保险费",
                    "住房公积金",
                    "工会经费和职工教育经费",
                    "短期带薪缺勤",
                    "短期利润分享计划",
                    "非货币性福利",
                    "其他短期薪酬",
                ]),
                "guidance": _G_SHORT_TERM_LISTED,
            },
            {
                "aliases": [T_LISTED_POST],
                "headers": MOVEMENT_HEADERS,
                "columns": _movement_columns(),
                "rows": _labels_then_total([
                    "离职后福利",
                    "其中：基本养老保险费",
                    "失业保险费",
                    "企业年金缴费",
                    "其他",
                    "其他长期职工福利（不适用的删除）",
                    "其中：xxx",
                    "其他",
                ]),
                "guidance": _G_POST_LISTED,
            },
        ],
    },
    "soe": {
        "section": "八、40",
        "text_sections": SOE_TEXT_SECTIONS,
        "plan": [
            {
                "aliases": [T_SOE_SUMMARY],
                "headers": MOVEMENT_HEADERS,
                "columns": _movement_columns(),
                "rows": _labels_then_total([
                    "短期薪酬",
                    "离职后福利-设定提存计划",
                    "辞退福利",
                    "一年内到期的其他福利",
                    "其他",
                ]),
                "guidance": _G_SUMMARY_SOE,
            },
            {
                "aliases": [T_SOE_SHORT_TERM],
                "headers": MOVEMENT_HEADERS,
                "columns": _movement_columns(),
                "rows": _labels_then_total([
                    "工资、奖金、津贴和补贴",
                    "职工福利费",
                    "社会保险费",
                    "其中：医疗保险费及生育保险费",
                    "工伤保险费",
                    "其他",
                    "住房公积金",
                    "工会经费和职工教育经费",
                    "短期带薪缺勤",
                    "短期利润分享计划",
                    "其他短期薪酬",
                ]),
                "guidance": _G_SHORT_TERM_SOE,
            },
            {
                # 🔴 第 3 张表在模板里与第 2 张重名（都叫 `短期薪酬列示`）；游标已走过第 2 张，
                #    故此处按 alias 命中第 3 张并改名。`consol_note_sections_soe` 五-41-3
                #    的 title 即 `设定提存计划列示`（致同原本措辞）。
                "aliases": [T_SOE_SHORT_TERM, T_SOE_POST],
                "new_name": T_SOE_POST,
                "headers": MOVEMENT_HEADERS,
                "columns": _movement_columns(),
                "rows": _labels_then_total([
                    "离职后福利",
                    "其中：基本养老保险费",
                    "失业保险费",
                    "企业年金缴费",
                    "其他",
                    "其他长期职工福利（不适用的删除）",
                    "其中：xxx",
                    "其他",
                ]),
                "guidance": _G_POST_SOE,
            },
        ],
    },
}


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
        aliases: list[str] = rule["aliases"]
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

        # J1 三张表均为单级表头 → 显式删除 seed 可能误留的 `_column_groups`
        # （残留分组会让附注渲染出凭空父表头）
        if tbl.pop("_column_groups", None) is not None:
            changes.append(f"[{idx}] {tbl.get('name')}._column_groups：删除（单级表头）")

        guidance = rule.get("guidance")
        if guidance and tbl.get("guidance") != guidance:
            tbl["guidance"] = guidance
            changes.append(f"[{idx}] {tbl.get('name')}.guidance → {len(guidance)} 字")

        cursor = idx + 1

    return changes, warnings


def apply_text_sections(section: dict[str, Any], want: list[str] | None) -> list[str]:
    """整体替换 ``text_sections``（源模板说明段是有序整体，逐条 diff 无意义）。"""
    if want is None:
        return []
    if section.get("text_sections") == want:
        return []
    old = len(section.get("text_sections") or [])
    section["text_sections"] = list(want)
    return [f"text_sections：{old} → {len(want)} 段"]


def _stamp(section: dict[str, Any]) -> None:
    section["_aligned_by"] = ALIGNED_BY
    section["_aligned_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────── 校验 ───────────────────────────

_PLACEHOLDER_ROW_LABELS = {"……", "...", "…"}


def validate_section(
    section: dict[str, Any],
    expected: list[str],
    want_text_sections: list[str] | None,
) -> list[str]:
    """表名唯一齐备 / 单级表头表态 / guidance 齐备 / 无占位行 / text_sections 到位。"""
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
            label = str(row.get("label", "")).strip()
            if str(row.get("row_type", "")) == "header_label":
                errs.append(f"[{i}] {name} 第 {j} 行仍为 header_label（压扁的第二行表头）")
            if label in _PLACEHOLDER_ROW_LABELS:
                errs.append(f"[{i}] {name} 第 {j} 行是占位行「{label}」（应移入 guidance）")
            if not label:
                errs.append(f"[{i}] {name} 第 {j} 行 label 为空（交付物不应出现无名空行）")

        cols = tbl.get("columns") or []
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
            has_group = any(c.get("group") for c in cols)
            if has_group:
                errs.append(f"[{i}] {name} 不应有 group（J1 三张表均为单级表头）")
            if not has_flat:
                errs.append(
                    f"[{i}] {name} columns 未标 flat → seed 路径会被反猜出凭空「本期」父表头"
                )
            labels = [str(c.get("label")) for c in cols[1:]]
            dup = {x for x in labels if labels.count(x) > 1}
            if dup:
                errs.append(f"[{i}] {name} 列名重复：{sorted(dup)}")

        if tbl.get("_column_groups"):
            errs.append(f"[{i}] {name} 单级表头却残留 _column_groups")

        if not str(tbl.get("guidance", "")).strip():
            errs.append(f"[{i}] {name} 缺 guidance")

    for want in expected:
        if want not in seen:
            errs.append(f"缺表：「{want}」")

    if want_text_sections is not None:
        actual = section.get("text_sections") or []
        if list(actual) != list(want_text_sections):
            errs.append(
                f"text_sections 未对齐（现 {len(actual)} 段 / 应 {len(want_text_sections)} 段）"
            )
        for k, para in enumerate(actual):
            if str(para).startswith("####"):
                errs.append(f"text_sections[{k}] 以 #### 开头 → 会被判为标题并静默丢弃")
    return errs


# ─────────────────────────── 入口 ───────────────────────────

def _process(variant: str, spec: dict[str, Any], *, dry_run: bool, check_only: bool) -> tuple[bool, list[str]]:
    path = TEMPLATE_PATH[variant]
    section_number = spec["section"]
    plan: list[dict[str, Any]] = spec["plan"]
    want_texts: list[str] | None = spec.get("text_sections")
    expected = [str(r.get("new_name") or r["aliases"][-1]) for r in plan]

    raw = path.read_text(encoding="utf-8")
    doc = json.loads(raw)
    section = _find_section(doc, section_number)
    if section is None:
        return False, [f"[FATAL] {path.name} 未找到 section_number={section_number}（{variant}）"]

    log = [f"=== J1 [{variant}] {path.name} §{section_number} {section.get('section_title')} ==="]

    if check_only:
        errs = validate_section(section, expected, want_texts)
        if section.get("_aligned_by") != ALIGNED_BY:
            errs.append("尚未对齐（缺 _aligned_by 标记）")
        log.extend(errs or ["结构校验通过"])
        return not errs, log

    changes, warnings = apply_plan(section, plan)
    changes += apply_text_sections(section, want_texts)
    log.extend(changes or ["无需修改（已对齐）"])
    log.extend(f"[WARN] {w}" for w in warnings)

    errs = validate_section(section, expected, want_texts)
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
    ap = argparse.ArgumentParser(
        description="附注 J1 应付职工薪酬披露章节结构对齐源模板（幂等）"
    )
    ap.add_argument("--variant", action="append", choices=sorted(SECTION_PLANS), help="只处理指定变体")
    ap.add_argument("--dry-run", action="store_true", help="只打印 diff 摘要，不写文件")
    ap.add_argument("--check", action="store_true", help="仅校验对齐状态（供 CI）")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

    ok_all = True
    for variant in (args.variant or list(SECTION_PLANS)):
        ok, log = _process(
            variant, SECTION_PLANS[variant], dry_run=args.dry_run, check_only=args.check
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
