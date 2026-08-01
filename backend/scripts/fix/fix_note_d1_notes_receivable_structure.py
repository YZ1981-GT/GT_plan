#!/usr/bin/env python
"""附注「应收票据」披露章节（上市 五、4 / 国企 八、4）结构对齐源模板（幂等修订）。

**目标**：补齐 D1 披露 → 附注同步链路的模板前置条件 —— `columns` 明确表态、
两级表头由 `ColumnDef.group` 承载、`guidance` 齐备、行骨架对齐源模板、
删除被 md 重建脚本压扁成假数据行的占位说明。

`diagnose_disclosure_sheet_vs_template.py --cycle D1` 跑出的欠账（2026-07-30）：

- **26 张表（上市 14 + 国企 12）全部 `columns` 未表态** → seed 路径会被
  `_infer_groups_from_headers` 按前缀反猜出凭空父表头
- **26 张表全部无 `guidance`** → 附注 TAB 页签无编制提示
- `headers` 被压扁成单级（源模板主表 / 分类表 / 组合表 / 变动表都是两级或三级表头）
- 占位说明「可无限量添加行」「出票人类型或账龄」「……」被当数据行落进 `rows`

**权威源与裁决**（详见 `.kiro/specs/d1-notes-receivable-disclosure-alignment/`）：

- 🔴 源 xlsx = ``backend/wp_templates/D/D1 应收票据.xlsx``（运行时权威）的两个披露 sheet
  ``附注披露信息（上市公司）`` / ``附注披露信息（国企）``
- ``note_check_preset_formulas.json`` 的 ``F4-*``（应收票据）= 勾稽与列语义裁决者

裁决要点：

- 源模板主表把期间标签写了两遍（父表头「期末余额」下首个子列也叫「期末余额」）。
  按预设 ``F4-3a``（账面余额 − 坏账准备 = 账面价值）取子列名
  **账面余额 / 坏账准备 / 账面价值**，父表头保留期间名，消除冗余。
- 🔴 平台只支持**两级**表头。前端 ``DisclosureEditor.activeTableColumns`` 只认扁平
  ``{group,start,span}``，``group`` 里带 ``/`` 会走后端树形分支（``children``/``headerIdx``）
  导致 ``g.start`` 为 ``undefined`` → 渲染崩。国企分类表源模板是三级
  （期末数 > 账面余额·坏账准备 > 金额·比例），顶层期间已在表名里
  （``（期末数）``/``（续：期初数）``）→ 只保留下两级。
- **同表并列双期 → `group`；拆表双期 / 单期 → `flat`**（期间已在表名中时，
  单组跨全部数据列不携带分组信息，且必须显式 `flat` 抑制前缀推断）。
- 上市核销逐项表源模板第 2 列字面是「应收票据」，预设 ``F4-29`` 明确为
  「应收票据性质」→ 取预设。
- 坏账准备变动公式取源模板（期初 + 计提 − 收回或转回 − 核销 − 其他变动 = 期末）；
  预设 ``F4-7`` 的「+ 其他变动」是从应收账款泛化复制而来，不采纳。

Usage::

    python backend/scripts/fix/fix_note_d1_notes_receivable_structure.py --dry-run
    python backend/scripts/fix/fix_note_d1_notes_receivable_structure.py
    python backend/scripts/fix/fix_note_d1_notes_receivable_structure.py --check

spec: .kiro/specs/d1-notes-receivable-disclosure-alignment/ Task 1
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"

ALIGNED_BY = "d1-notes-receivable-disclosure-alignment"

TEMPLATE_PATH = {
    "listed": DATA_DIR / "note_template_listed.json",
    "soe": DATA_DIR / "note_template_soe.json",
}

SECTION_NUMBER = {"listed": "五、4", "soe": "八、4"}

AMOUNT = "amount"
PERCENT = "percent"
TEXT = "text"

# 期间父表头（逐字取自源模板合并单元格）
G_END_LISTED = "期末余额"
G_PRIOR_LISTED = "上年年末余额"
G_END_SOE = "期末数"
G_PRIOR_SOE = "期初数"
G_GROSS = "账面余额"
G_PROVISION = "坏账准备"
G_MOVEMENT_SOE = "本期变动情况"


# ─────────────────────────── 行构造 ───────────────────────────

def _data(label: str = "") -> dict[str, Any]:
    return {"label": label, "row_type": "data"}


def _total(label: str = "合计") -> dict[str, Any]:
    return {"label": label, "is_total": True, "row_type": "total"}


def _subtotal(label: str) -> dict[str, Any]:
    return {"label": label, "is_total": True, "row_type": "subtotal"}


def _blanks_then_total(n: int, label: str = "合计") -> list[dict[str, Any]]:
    """n 个空白录入行 + 合计行。

    源模板的「可无限量添加行」「出票人类型或账龄」「……」是**占位说明**，
    被 md 重建脚本当数据行落进 `rows` 会渲染成一行空披露数据 → 必删，
    语义移入 `guidance`（铁律：模板 rows 里的占位说明是假数据行）。
    """
    return [_data() for _ in range(n)] + [_total(label)]


def _labels_then_total(labels: list[str]) -> list[dict[str, Any]]:
    return [_data(x) for x in labels] + [_total()]


# ─────────────────────────── 列构造 ───────────────────────────

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
        label: 标签列 `(key, label)`（源模板 rowspan=2 的首列）
        specs: `(key, label, format, group|None)`；``group=None`` 表示该列本身是
            rowspan=2 的独立列（如国企分类表的「账面价值」、变动表的「期初数」）。
            混合分组已被后端 `_extract_column_groups` 单级分支与前端
            `activeTableColumns` 的 `grouped` Set 同时支持。
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

    与后端 `note_sub_table_projector._extract_column_groups` 单级分支同口径：
    相邻同名 group 合并；无 group 的列不进任何条目。
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
# 🔴 每个值必须与前端 `d1NoteSectionMap.ts` 的 sub_table_data 键逐字一致，
#    否则同步产出孤儿子表（附注 TAB 永空 + 底稿数据丢失）。
#    守卫：`composables/__tests__/d1NoteSubtableContract.spec.ts`

L = {
    "main": "应收票据",
    "pledged": "期末已质押的应收票据",
    "endorsed": "期末已背书或贴现但尚未到期的应收票据",
    # 🔴 逐字取源模板 R31「（3）期末因出票人未履约而其转应收账款的票据」——**无「将」**。
    #    国企侧源模板 R74 是「而其转为应收账款」（多个「为」），两版措辞本就不同，
    #    按表各自对齐，不做统一（同 BILL_KINDS 口径）。旧名见 LEGACY_TABLE_NAMES。
    "transfer": "期末因出票人未履约而其转应收账款的票据",
    "class_end": "按坏账计提方法分类（期末余额）",
    "class_prior": "按坏账计提方法分类（续：上年年末余额）",
    "individual_end": "按单项计提坏账准备的应收票据（期末余额）",
    "individual_prior": "按单项计提坏账准备的应收票据（续：上年年末余额）",
    "portfolio_bank": "组合计提项目：银行承兑汇票",
    "portfolio_commercial": "组合计提项目：商业承兑汇票",
    "movement": "本期计提、收回或转回的坏账准备情况",
    "reversal": "本期转回或收回金额重要的坏账准备",
    "writeoff_amount": "本期实际核销的应收票据情况",
    "writeoff_detail": "重要的应收票据核销情况（逐项披露）",
}

S = {
    "main": "应收票据分类",
    "class_end": "按坏账准备计提方法分类披露应收票据（期末数）",
    "class_prior": "按坏账准备计提方法分类披露应收票据（续：期初数）",
    "individual_end": "按单项计提坏账准备的应收票据",
    "portfolio": "按组合计提坏账准备的应收票据",
    "movement": "本期计提、收回或转回的应收票据坏账准备情况",
    "reversal": "本期转回或收回金额重要的应收票据坏账准备",
    "pledged": "期末已质押的应收票据",
    "endorsed": "期末已背书或贴现但尚未到期的应收票据",
    "transfer": "期末因出票人未履约而其转为应收账款的票据",
    "writeoff_amount": "本期实际核销的应收票据",
    "writeoff_detail": "重要的应收票据核销情况",
}

# 历史表名（本脚本改名前写入过附注的键）。apply_plan 用它做 aliases 定位并改名；
# 前端 `d1NoteSectionMap.D1_LEGACY_OBSOLETE_TABLES` 用它清孤儿子表。
LEGACY_TABLE_NAMES = {
    "listed": {"transfer": ["期末因出票人未履约而将其转应收账款的票据"]},
    "soe": {},
}

NOTE_KINDS = ["银行承兑汇票", "商业承兑汇票"]
# 🔴 质押 / 背书贴现 / 转应收账款三表源模板用的是「票据」而非「汇票」（主表用「汇票」），
#    这是源模板的**逐表**措辞，按表各自对齐，不做全局统一。
BILL_KINDS = ["银行承兑票据", "商业承兑票据"]


# ─────────────────────────── guidance 文本 ───────────────────────────
# 只取源模板红字 / 附注括注 / 15 号文条款，或以「勾稽：」前缀标注的 F4-* 预设。

_G_MAIN_TIP = (
    "【提示：企业因销售商品、提供服务等取得的、不属于《中华人民共和国票据法》规范票据的"
    "“云信”“融信”等数字化应收账款债权凭证，不应当在“应收票据”项目中列示。企业管理"
    "“云信”“融信”等的业务模式以收取合同现金流量为目标的，应当在“应收账款”项目中列示；"
    "既以收取合同现金流量为目标又以出售为目标的，应当在“应收款项融资”项目中列示。"
    "如果法律上认定供应链票据属于《商业汇票承兑、贴现与再贴现管理办法》"
    "（中国人民银行中国银行保险监督管理委员会令〔2022〕第4号）的范围、具备《票据法》"
    "规定的要件，则持有方应当自法律认定生效日（2023年1月1日）起将其作为“应收票据”"
    "进行会计处理（根据其业务模式列示为应收票据或应收款项融资），"
    "且无需对前期比较期间数据进行追溯调整。】"
)

_G_MAIN_LINK = (
    "勾稽：合计行账面价值 = 报表应收票据（期末 / 期初各校验，F4-1、F4-2）；"
    "各票据种类行之和 = 合计行（每个数值列独立，F4-3）；"
    "账面余额 − 坏账准备 = 账面价值（F4-3a）；"
    "本表三列合计 = 按计提方法分类表对应合计（F4-8~F4-10）；"
    "坏账准备期末 / 期初合计 = 坏账准备变动表期末 / 期初合计（F4-6、F4-6a）。"
    "数据来源：审定表 D1-1。"
)

_G_ENDORSED = (
    "【提示：证监会《2014年上市公司年报会计监管报告》，对已背书或贴现且尚未到期的"
    "银行承兑汇票予以终止确认后，需在财务报表中补充披露终止确认的票据以及对票据被追索时"
    "可能存在的支付风险予以清晰说明。参考披露：用于贴现的银行承兑汇票是由信用等级较高的"
    "银行承兑，信用风险和延期付款风险很小，并且票据相关的利率风险已转移给银行，"
    "可以判断票据所有权上的主要风险和报酬已经转移，故终止确认。或：用于贴现的银行承兑汇票"
    "是由信用等级不高的银行承兑，贴现不影响追索权，票据相关的信用风险和延期付款风险仍没有"
    "转移，故未终止确认。】"
    # 🔴 源模板该括注紧跟在**本表**（已背书或贴现）合计行之后（上市 R27 / 国企 R72-R73），
    #    讲的是「终止确认的金额及相关利得损失」= 本表两列的口径，
    #    与下一张「转应收账款」表无关。此前误挂在 transfer 表 guidance 上。
    "（如根据《企业会计准则第23号——金融资产转移》终止确认的应收票据，"
    "列示其终止确认的金额，及与终止确认相关的利得和损失）"
    "本表可添加行项目。勾稽：各明细行之和 = 合计行（F4-22）。"
)

_G_PLEDGED = (
    "列示期末已质押的应收票据。本表可无限量添加行项目。"
    "勾稽：各明细行之和 = 合计行（每个数值列独立，F4-21）。"
)

_G_TRANSFER = (
    "列示期末因出票人未履约而转为应收账款的票据。"
    "【提示：票据逾期后应转入应收账款并计提坏账准备，账龄应连续计算，"
    "故本表只列示商业承兑票据。】勾稽：各明细行之和 = 合计行（F4-23）。"
)

_G_CLASS_TAIL = (
    "勾稽：比例(%) = 该行账面余额 ÷ 合计行账面余额 × 100（合计行应为 100，F4-25）；"
    "预期信用损失率(%) = 坏账准备 ÷ 账面余额 × 100（F4-12）；"
    "账面余额 − 坏账准备 = 账面价值（F4-11）；"
    "各明细行之和 = 合计行（F4-16）；"
    "按单项计提行 = 单项计提明细小计、按组合计提行 = 组合计提明细小计（F4-4、F4-5）。"
    "【提示：此处披露未逾期的应收票据计提的坏账准备。若票据逾期，"
    "则应转入应收账款并计提坏账准备，账龄应连续计算。】"
)

_G_INDIVIDUAL_TAIL = (
    "按单项计提坏账准备的应收票据逐项列示，可无限量添加行项目。"
    "勾稽：预期信用损失率(%) = 坏账准备 ÷ 账面余额 × 100（F4-13）；"
    "各明细行之和 = 合计行（F4-17）。"
    "完整性：账面余额 ≠ 0 时，名称、坏账准备、预期信用损失率、"
    "计提依据（理由）列均不应为空（F4-14）。"
)

_G_PORTFOLIO_TAIL = (
    # 🔴 guidance 是**纯文本**渲染（附注 TAB 提示 / Word 导出都不解析 markdown），
    #    写 `**加粗**` 会原样显示，且平台级 `fix_note_bold_markers.py` 会把它剥掉
    #    → 两个幂等脚本互相打架（本脚本写回、那个再剥离）。此处不带任何 markdown 标记。
    #    守卫：`test_note_d1_structure.test_guidance_has_no_markdown_bold`。
    "行维度为出票人类型或账龄（源模板占位说明），可无限量添加行项目；"
    "并需在下方说明按组合计提坏账准备的原因。"
    "勾稽：各明细行之和 = 合计行（F4-18）；合计 = 按计提方法分类表「按组合计提坏账准备」行"
    "（F4-4、F4-5）。【提示：此处披露未逾期的应收票据计提的坏账准备。若票据逾期，"
    "则应转入应收账款并计提坏账准备，账龄应连续计算。】"
)

_G_MOVEMENT_LISTED = (
    "勾稽：期末数 = 上年年末数 + 本期计提 − 本期收回或转回 − 本期核销 − 本期转销 − 其他"
    "（源模板 B100 公式）；期末数 = 应收票据分类表坏账准备期末合计（F4-6）；"
    "上年年末数 = 分类表坏账准备期初合计（F4-6a）。"
    "「本期转销」「其他」为源模板可选行，无发生额时可删除。"
)

_G_MOVEMENT_SOE = (
    "勾稽：期末数 = 期初数 + 计提 − 收回或转回 − 核销 − 其他变动（每行独立，源模板 G48 公式）；"
    "单项计提行 + 按组合计提行 = 合计行（每个数值列独立，F4-19）；"
    "「其中：」下方所有明细行之和 = 按组合计提行（F4-20）；"
    "合计行期末数 = 应收票据分类表坏账准备期末合计（F4-6）。"
)

_G_REVERSAL = (
    "列示本期转回或收回金额重要的坏账准备，可无限量添加行项目。"
    "勾稽：各明细行之和 = 合计行（F4-26）。"
    "完整性：转回或收回金额 ≠ 0 时，单位（债务人）名称、转回或收回原因 / 方式列"
    "均不应为空（F4-27）。"
)

_G_WRITEOFF_AMOUNT = (
    "列示本期实际核销的应收票据总额。"
    "勾稽：本表（含逐项披露子表）各明细行之和 = 合计行（F4-24）；"
    "核销金额应与坏账准备变动表「本期核销」列一致。"
)

_G_WRITEOFF_DETAIL = (
    "（对于其中重要的应收票据，应逐项披露款项性质、核销原因、履行的核销程序及核销金额。"
    "实际核销的款项由关联交易产生的，应单独披露。）"
    "勾稽：各明细行之和 = 合计行（F4-24）。"
    "完整性：核销金额 ≠ 0 时，单位名称、应收票据性质、核销原因、履行的核销程序、"
    "是否由关联交易产生列均不应为空（F4-29）。"
)


# ─────────────────────────── 列定义装配 ───────────────────────────

def _summary_columns(group_end: str, group_prior: str) -> list[dict[str, Any]]:
    """分类总表：票据种类 × 双期并列 × 账面余额 / 坏账准备 / 账面价值。

    源模板把期间标签写了两遍（父表头「期末余额」下首个子列也叫「期末余额」），
    子列名按预设 F4-3a（账面余额 − 坏账准备 = 账面价值）取，消除冗余。
    """
    return _grouped_columns(
        ("label", "票据种类"),
        [
            ("end_balance", "账面余额", AMOUNT, group_end),
            ("end_provision", "坏账准备", AMOUNT, group_end),
            ("end_book_value", "账面价值", AMOUNT, group_end),
            ("prior_balance", "账面余额", AMOUNT, group_prior),
            ("prior_provision", "坏账准备", AMOUNT, group_prior),
            ("prior_book_value", "账面价值", AMOUNT, group_prior),
        ],
    )


def _class_columns_listed(group: str) -> list[dict[str, Any]]:
    """上市按坏账计提方法分类：源模板 B38:F38 合并为期间父表头，子列 5 个。"""
    return _grouped_columns(
        ("label", "类别"),
        [
            ("balance", "金额", AMOUNT, group),
            ("ratio", "比例(%)", PERCENT, group),
            ("provision", "坏账准备", AMOUNT, group),
            ("loss_rate", "预期信用损失率(%)", PERCENT, group),
            ("book_value", "账面价值", AMOUNT, group),
        ],
    )


def _class_columns_soe() -> list[dict[str, Any]]:
    """国企按坏账准备计提方法分类：源模板三级（期间 > 账面余额·坏账准备 > 金额·比例）。

    顶层期间已在表名里（（期末数）/（续：期初数）），只保留下两级；
    「账面价值」是 rowspan 独立列（源模板 F14「账面」/ F15「价值」纵向合并）。
    """
    return _grouped_columns(
        ("label", "类别"),
        [
            ("balance", "金额", AMOUNT, G_GROSS),
            ("ratio", "比例(%)", PERCENT, G_GROSS),
            ("provision", "金额", AMOUNT, G_PROVISION),
            ("loss_rate", "预期信用损失率(%)", PERCENT, G_PROVISION),
            ("book_value", "账面价值", AMOUNT, None),
        ],
    )


def _individual_columns(basis_label: str) -> list[dict[str, Any]]:
    return _flat_columns([
        ("label", "名称", None),
        ("balance", "账面余额", AMOUNT),
        ("provision", "坏账准备", AMOUNT),
        ("loss_rate", "预期信用损失率(%)", PERCENT),
        ("basis", basis_label, TEXT),
    ])


def _portfolio_columns_listed() -> list[dict[str, Any]]:
    """上市组合计提项目：一张表双期并列（源模板 B77:D77 / E77:G77 合并）。"""
    return _grouped_columns(
        ("label", "名称"),
        [
            ("end_balance", "应收票据", AMOUNT, G_END_LISTED),
            ("end_provision", "坏账准备", AMOUNT, G_END_LISTED),
            ("end_loss_rate", "预期信用损失率(%)", PERCENT, G_END_LISTED),
            ("prior_balance", "应收票据", AMOUNT, G_PRIOR_LISTED),
            ("prior_provision", "坏账准备", AMOUNT, G_PRIOR_LISTED),
            ("prior_loss_rate", "预期信用损失率(%)", PERCENT, G_PRIOR_LISTED),
        ],
    )


def _movement_columns_soe() -> list[dict[str, Any]]:
    """国企坏账准备变动：源模板 C46:E46 合并为「本期变动情况」，期初 / 期末为独立列。"""
    return _grouped_columns(
        ("label", "类别"),
        [
            ("prior_balance", "期初数", AMOUNT, None),
            ("provision", "计提", AMOUNT, G_MOVEMENT_SOE),
            ("reversal", "收回或转回", AMOUNT, G_MOVEMENT_SOE),
            ("write_off", "核销", AMOUNT, G_MOVEMENT_SOE),
            ("other", "其他变动", AMOUNT, G_MOVEMENT_SOE),
            ("end_balance", "期末数", AMOUNT, None),
        ],
    )


def _rule(name: str, cols: list[dict[str, Any]], rows: list[dict[str, Any]],
          guidance: str, aliases: list[str] | None = None) -> dict[str, Any]:
    return {
        "aliases": (aliases or []) + [name],
        "new_name": name,
        "headers": _headers_of(cols),
        "columns": cols,
        "rows": rows,
        "guidance": guidance,
    }


def _build_listed_plan() -> list[dict[str, Any]]:
    return [
        _rule(L["main"], _summary_columns(G_END_LISTED, G_PRIOR_LISTED),
              _labels_then_total(NOTE_KINDS), _G_MAIN_TIP + _G_MAIN_LINK),
        _rule(L["pledged"], _flat_columns([
            ("label", "种类", None),
            ("pledged_amount", "期末已质押金额", AMOUNT),
        ]), _labels_then_total(BILL_KINDS), _G_PLEDGED),
        _rule(L["endorsed"], _flat_columns([
            ("label", "种类", None),
            ("derecognized", "期末终止确认金额", AMOUNT),
            ("not_derecognized", "期末未终止确认金额", AMOUNT),
        ]), _labels_then_total(BILL_KINDS), _G_ENDORSED),
        _rule(L["transfer"], _flat_columns([
            ("label", "种类", None),
            ("transfer_amount", "期末转应收账款金额", AMOUNT),
        ]), _labels_then_total(["商业承兑票据"]), _G_TRANSFER,
            aliases=LEGACY_TABLE_NAMES["listed"]["transfer"]),
        _rule(L["class_end"], _class_columns_listed(G_END_LISTED), [
            _data("按单项计提坏账准备"), _data("其中："),
            _data("按组合计提坏账准备"), _data("其中："),
            _data("银行承兑汇票"), _data("商业承兑汇票"), _total(),
        ], f"按坏账计提方法分类（{G_END_LISTED}）。" + _G_CLASS_TAIL),
        _rule(L["class_prior"], _class_columns_listed(G_PRIOR_LISTED), [
            _data("按单项计提坏账准备"), _data("其中："),
            _data("按组合计提坏账准备"), _data("其中："),
            _data("银行承兑汇票"), _data("商业承兑汇票"), _total(),
        ], f"按坏账计提方法分类（{G_PRIOR_LISTED}），与期末余额表同构。" + _G_CLASS_TAIL),
        _rule(L["individual_end"], _individual_columns("计提依据"),
              _blanks_then_total(2), f"（{G_END_LISTED}）" + _G_INDIVIDUAL_TAIL),
        _rule(L["individual_prior"], _individual_columns("计提依据"),
              _blanks_then_total(2), f"（{G_PRIOR_LISTED}）" + _G_INDIVIDUAL_TAIL),
        _rule(L["portfolio_bank"], _portfolio_columns_listed(),
              _blanks_then_total(3), "组合计提项目：银行承兑汇票。" + _G_PORTFOLIO_TAIL),
        _rule(L["portfolio_commercial"], _portfolio_columns_listed(),
              _blanks_then_total(3), "组合计提项目：商业承兑汇票。" + _G_PORTFOLIO_TAIL),
        _rule(L["movement"], _flat_columns([
            ("label", "项目", None),
            ("amount", "坏账准备金额", AMOUNT),
        ]), [
            _data("上年年末数"), _data("本期计提"), _data("本期收回或转回"),
            _data("本期核销"), _data("本期转销"), _data("其他"), _total("期末数"),
        ], _G_MOVEMENT_LISTED),
        _rule(L["reversal"], _flat_columns([
            ("label", "单位名称", None),
            ("reversal_reason", "转回原因", TEXT),
            ("recovery_method", "收回方式", TEXT),
            ("original_basis", "原确定坏账准备的依据", TEXT),
            ("amount", "转回或收回金额", AMOUNT),
        ]), _blanks_then_total(3), _G_REVERSAL),
        _rule(L["writeoff_amount"], _flat_columns([
            ("label", "项目", None),
            ("amount", "核销金额", AMOUNT),
        ]), [_data("实际核销的应收票据")], _G_WRITEOFF_AMOUNT),
        _rule(L["writeoff_detail"], _flat_columns([
            ("label", "单位名称", None),
            ("note_type", "应收票据性质", TEXT),
            ("amount", "核销金额", AMOUNT),
            ("reason", "核销原因", TEXT),
            ("procedure", "履行的核销程序", TEXT),
            ("related", "款项是否由关联交易产生", TEXT),
        ]), _blanks_then_total(3), _G_WRITEOFF_DETAIL),
    ]


def _build_soe_plan() -> list[dict[str, Any]]:
    return [
        _rule(S["main"], _summary_columns(G_END_SOE, G_PRIOR_SOE),
              _labels_then_total(NOTE_KINDS), _G_MAIN_TIP + _G_MAIN_LINK),
        _rule(S["class_end"], _class_columns_soe(), _labels_then_total([
            "按单项计提坏账准备", "按组合计提坏账准备",
        ]), f"按坏账准备计提方法分类披露应收票据（{G_END_SOE}）。" + _G_CLASS_TAIL),
        _rule(S["class_prior"], _class_columns_soe(), _labels_then_total([
            "按单项计提坏账准备", "按组合计提坏账准备",
        ]), f"按坏账准备计提方法分类披露应收票据（{G_PRIOR_SOE}），与期末数表同构。"
            + _G_CLASS_TAIL),
        _rule(S["individual_end"], _individual_columns("计提理由"),
              _blanks_then_total(3), _G_INDIVIDUAL_TAIL),
        _rule(S["portfolio"], _flat_columns([
            ("label", "名称", None),
            ("balance", "账面余额", AMOUNT),
            ("provision", "坏账准备", AMOUNT),
            ("loss_rate", "预期信用损失率(%)", PERCENT),
        ]), [
            _subtotal("商业承兑汇票小计："), _data(),
            _subtotal("银行承兑汇票小计："), _data(),
            _total(),
        ], _G_PORTFOLIO_TAIL),
        _rule(S["movement"], _movement_columns_soe(), _labels_then_total([
            "单项计提预期信用损失的应收票据",
            "按组合计提预期信用损失的应收票据",
            "其中：",
        ]), _G_MOVEMENT_SOE),
        _rule(S["reversal"], _flat_columns([
            ("label", "债务人名称", None),
            ("amount", "转回或收回金额", AMOUNT),
            ("cumulative_provision", "转回或收回前累计已计提坏账准备金额", AMOUNT),
            ("reason_method", "转回或收回原因、方式", TEXT),
        ]), _blanks_then_total(4), _G_REVERSAL),
        _rule(S["pledged"], _flat_columns([
            ("label", "种类", None),
            ("pledged_amount", "期末已质押金额", AMOUNT),
        ]), _labels_then_total(BILL_KINDS), _G_PLEDGED),
        _rule(S["endorsed"], _flat_columns([
            ("label", "种类", None),
            ("derecognized", "期末终止确认金额", AMOUNT),
            ("not_derecognized", "期末未终止确认金额", AMOUNT),
        ]), _labels_then_total(BILL_KINDS), _G_ENDORSED),
        _rule(S["transfer"], _flat_columns([
            ("label", "种类", None),
            ("transfer_amount", "期末转应收账款金额", AMOUNT),
        ]), _labels_then_total(["商业承兑票据"]), _G_TRANSFER),
        _rule(S["writeoff_amount"], _flat_columns([
            ("label", "项目", None),
            ("amount", "核销金额", AMOUNT),
        ]), [_data("实际核销的应收票据")], _G_WRITEOFF_AMOUNT),
        _rule(S["writeoff_detail"], _flat_columns([
            ("label", "单位名称", None),
            ("note_type", "应收票据的性质", TEXT),
            ("amount", "核销金额", AMOUNT),
            ("reason", "核销原因", TEXT),
            ("procedure", "履行的核销程序", TEXT),
            ("related", "是否由关联交易产生", TEXT),
        ]), _blanks_then_total(3), _G_WRITEOFF_DETAIL),
    ]


SECTION_PLANS: dict[str, dict[str, Any]] = {
    "listed": {
        "section": SECTION_NUMBER["listed"],
        "plan": _build_listed_plan(),
        "expected": list(L.values()),
    },
    "soe": {
        "section": SECTION_NUMBER["soe"],
        "plan": _build_soe_plan(),
        "expected": list(S.values()),
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
                changes.append(f"[{idx}] {tbl.get('name')}._column_groups：{len(want_groups)} 组（两级表头）")
        elif tbl.pop("_column_groups", None) is not None:
            changes.append(f"[{idx}] {tbl.get('name')}._column_groups：删除（单级表头）")

        guidance = rule.get("guidance")
        if guidance and tbl.get("guidance") != guidance:
            tbl["guidance"] = guidance
            changes.append(f"[{idx}] {tbl.get('name')}.guidance → {len(guidance)} 字")

        cursor = idx + 1

    return changes, warnings


# ─────────────────── text_sections 标题化（裸表名不得当正文）───────────────────

# 与后端 `disclosure_engine._NUMBERED_TITLE_RE` 同口径（`（N）xxx` / `N. xxx`）
_NUMBERED_TITLE_RE = re.compile(r"^(?:（(\d+)）|(\d+)[.、])")


def _is_title_paragraph(para: str) -> bool:
    """复刻 `disclosure_engine._is_table_title_paragraph`（stdlib-only，供 --check 独立跑）。

    ① `#` 开头 → 任意长度都算标题
    ② 非 `#` 时须 **≤20 字且匹配编号**
    """
    s = (para or "").strip()
    if not s:
        return False
    if s.startswith("#"):
        return True
    if len(s) > 20:
        return False
    return bool(_NUMBERED_TITLE_RE.match(s))


def titleize_text_sections(section: dict[str, Any]) -> list[str]:
    """把 `text_sections` 里的**裸表名**加上 `#### ` 前缀，返回变更说明。

    🔴 后端只把「`#` 开头」或「≤20 字的编号短标题」当标题（标题本身不进任何输出）。
    写成裸表名（如 `组合计提项目：银行承兑汇票`）既不是标题、也没有 `提示`/`【` 等
    guidance 关键词 → 落进 `text_content`，**附注正文与 Word 导出会凭空多出
    「只有一个表名」的段落**（D1 实测 6 条：上市 3 + 国企 3）。
    正确范式见 `fix_note_ar_soe_structure.TEXT_SECTIONS`（`#### xxx` / `（N）xxx`）。
    """
    paras = section.get("text_sections")
    if not isinstance(paras, list):
        return []
    names = {str(t.get("name", "")).strip() for t in (section.get("tables") or [])}
    changes: list[str] = []
    out: list[str] = []
    for p in paras:
        s = str(p)
        stripped = s.strip()
        if stripped in names and not _is_title_paragraph(s):
            out.append(f"#### {stripped}")
            changes.append(f"text_sections：裸表名「{stripped}」→ 加 #### 前缀（不再当正文渲染）")
        else:
            out.append(s)
    if changes:
        section["text_sections"] = out
    return changes


def find_bare_table_name_paragraphs(section: dict[str, Any]) -> list[str]:
    """返回仍会被当正文渲染的裸表名段落（供 validate / 测试）。"""
    names = {str(t.get("name", "")).strip() for t in (section.get("tables") or [])}
    return [
        str(p).strip()
        for p in (section.get("text_sections") or [])
        if str(p).strip() in names and not _is_title_paragraph(str(p))
    ]


def _stamp(section: dict[str, Any]) -> None:
    section["_aligned_by"] = ALIGNED_BY
    section["_aligned_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────── 校验 ───────────────────────────

def validate_section(section: dict[str, Any], expected: list[str]) -> list[str]:
    """表名齐备唯一 / 无 header_label / columns 表态 / 分组自洽 / guidance 齐备。"""
    errs: list[str] = []
    tables = section.get("tables") or []
    seen: dict[str, int] = {}

    for i, tbl in enumerate(tables):
        name = str(tbl.get("name", ""))
        if name in seen:
            errs.append(f"[{i}] 表名重复：「{name}」（首现于 {seen[name]}）")
        seen[name] = i
        if name not in expected:
            continue

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
                    f"[{i}] {name} columns[0].label={cols[0].get('label')!r} ≠ "
                    f"headers[0]={(headers[0] if headers else None)!r}"
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
            if any("/" in str(c.get("group") or "") for c in cols):
                errs.append(
                    f"[{i}] {name} group 含 '/'（多级）→ 前端 activeTableColumns 只认扁平"
                    " {group,start,span}，树形会渲染崩"
                )
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
            for g in groups or []:
                start, span = int(g.get("start", 0)), int(g.get("span", 0))
                if start < 1:
                    errs.append(f"[{i}] {name} 分组「{g.get('group')}」start={start} < 1")
                if start + span > len(headers):
                    errs.append(
                        f"[{i}] {name} 分组「{g.get('group')}」越界：{start}+{span} > {len(headers)}"
                    )
        elif groups is not None:
            errs.append(f"[{i}] {name} 单级表头仍残留 _column_groups")

        if not str(tbl.get("guidance") or "").strip():
            errs.append(f"[{i}] {name} 缺 guidance（附注 TAB 页签无编制提示）")

    missing = [n for n in expected if n not in seen]
    if missing:
        errs.append(f"缺表：{missing}")

    bare = find_bare_table_name_paragraphs(section)
    if bare:
        errs.append(
            f"text_sections 含裸表名 {bare} → 会被当披露正文渲染"
            "（附注正文与 Word 导出多出只有表名的段落），须加 #### 前缀"
        )
    return errs


# ─────────────────────────── CLI ───────────────────────────

def run(variant: str, *, dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    spec = SECTION_PLANS[variant]
    path = TEMPLATE_PATH[variant]
    doc = json.loads(path.read_text(encoding="utf-8"))
    section = _find_section(doc, spec["section"])
    if section is None:
        return [], [f"未找到章节 {spec['section']}（{path.name}）"], []

    if check:
        return [], [], validate_section(section, spec["expected"])

    changes, warnings = apply_plan(section, spec["plan"])
    changes += titleize_text_sections(section)
    errs = validate_section(section, spec["expected"])
    if changes and not dry_run and not errs:
        _stamp(section)
        path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return changes, warnings, errs


def main() -> int:
    ap = argparse.ArgumentParser(description="附注 D1 应收票据披露章节结构对齐（幂等）")
    ap.add_argument("--dry-run", action="store_true", help="只打印变更，不写文件")
    ap.add_argument("--check", action="store_true", help="只校验现状，返回非零表示欠账")
    ap.add_argument("--variant", choices=["listed", "soe"], help="只处理单个版本")
    args = ap.parse_args()

    variants = [args.variant] if args.variant else ["listed", "soe"]
    total_changes = 0
    total_errs = 0

    for variant in variants:
        changes, warnings, errs = run(variant, dry_run=args.dry_run, check=args.check)
        head = f"[{variant}] {SECTION_NUMBER[variant]} 应收票据"
        print(f"\n=== {head} ===")
        for c in changes:
            print(f"  ~ {c}")
        for w in warnings:
            print(f"  ! {w}")
        for e in errs:
            print(f"  x {e}")
        if not changes and not errs and not warnings:
            print("  = 已对齐（幂等空操作）")
        total_changes += len(changes)
        total_errs += len(errs) + len(warnings)

    if args.check:
        print(f"\n--check：{total_errs} 项欠账")
        return 1 if total_errs else 0
    print(f"\n{'[dry-run] ' if args.dry_run else ''}共 {total_changes} 处变更，{total_errs} 项问题")
    return 1 if total_errs else 0


if __name__ == "__main__":
    sys.exit(main())
