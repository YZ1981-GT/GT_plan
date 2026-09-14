#!/usr/bin/env python
"""附注 I 类 6 循环（I1~I6）× 2 变体 = 12 章节结构修订（幂等）。

I 类循环对应**无形资产与长期待摊费用**相关科目：

- I1 无形资产（五、26 / 八、27）
- I2 开发支出（五、27 / 八、28）
- I3 商誉（五、28 / 八、29）
- I4 长期待摊费用（五、29 / 八、30）
- I5 递延收益（五、31 / 八、32）
- I6 研发费用（五、66 / 八、67）

本脚本当前只实现 **I6 两版**，I1~I5 留 TODO 占位供后续 Task 4.2~4.5 补充。

Usage::

    python backend/scripts/fix/fix_note_i_cycle_structure.py --dry-run
    python backend/scripts/fix/fix_note_i_cycle_structure.py --check
    python backend/scripts/fix/fix_note_i_cycle_structure.py --check --cycle I6
    python backend/scripts/fix/fix_note_i_cycle_structure.py --cycle I6

"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _note_structure_kit import (  # noqa: E402
    AMOUNT,
    PERCENT,
    TEXT,
    carry_row_codes,
    data_row,
    flat_columns,
    rule,
    run_section,
    total_row,
)

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"
LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

ALIGNED_BY = "i-cycle-four-table-extraction-and-disclosure-alignment"

# ═══════════════════════════════════════════════════════════════════════════════
# I6 研发费用（五、66 / 八、67）
# ═══════════════════════════════════════════════════════════════════════════════

_I6_TABLE_NAME = "研发费用（按费用性质列示）"

_I6_COLUMNS = flat_columns([
    ("项目", "项目", None),
    ("本期发生额", "本期发生额", AMOUNT),
    ("上期发生额", "上期发生额", AMOUNT),
])

_I6_GUIDANCE_LISTED = (
    "【提示：根据财会〔2019〕6号，\u201c研发费用\u201d项目，"
    "反映企业进行研究与开发过程中发生的费用化支出，"
    "以及计入管理费用的自行开发无形资产的摊销。】"
)

_I6_GUIDANCE_SOE = ""  # 源 xlsx 国企版无红字


def _i6_listed(dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    """I6 上市（五、66）。"""
    plan = [
        rule(
            _I6_TABLE_NAME,
            _I6_COLUMNS,
            None,  # rows 不动
            _I6_GUIDANCE_LISTED,
        ),
    ]
    return run_section(
        LISTED_PATH,
        "五、66",
        plan,
        [_I6_TABLE_NAME],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
    )


def _i6_soe(dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    """I6 国企（八、67）：表名从「研发费用」改为「研发费用（按费用性质列示）」。"""
    plan = [
        rule(
            _I6_TABLE_NAME,
            _I6_COLUMNS,
            None,  # rows 不动
            _I6_GUIDANCE_SOE or "根据企业实际发生的研发费用按费用性质逐项列示。",
            aliases=["研发费用"],  # 旧名定位
        ),
    ]
    return run_section(
        SOE_PATH,
        "八、67",
        plan,
        [_I6_TABLE_NAME],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# I4 长期待摊费用（五、29 / 八、30）
# ═══════════════════════════════════════════════════════════════════════════════

_I4_TABLE_NAME = "长期待摊费用"

# 上市版：两级表头 — 「本期减少」下辖「本期摊销」/「其他减少」
_I4_LISTED_COLUMNS = [
    {"key": "项目", "label": "项  目", "is_label": True},
    {"key": "begin", "label": "期初数", "format": AMOUNT},
    {"key": "increase", "label": "本期增加", "format": AMOUNT},
    {"key": "amort", "label": "本期摊销", "group": "本期减少", "format": AMOUNT},
    {"key": "other_decrease", "label": "其他减少", "group": "本期减少", "format": AMOUNT},
    {"key": "end", "label": "期末数", "format": AMOUNT},
]

_I4_LISTED_GUIDANCE = (
    "说明：1年内到期的长期待摊费用X.XX元，详见附注五、11。"
)

# 国企版：单行表头 7 列全 flat
_I4_SOE_COLUMNS = flat_columns([
    ("项目", "项  目", None),
    ("begin", "期初余额", AMOUNT),
    ("increase", "本期增加额", AMOUNT),
    ("amort", "本期摊销额", AMOUNT),
    ("other_decrease", "其他减少额", AMOUNT),
    ("end", "期末余额", AMOUNT),
    ("reason", "其他减少的原因", TEXT),
])

_I4_SOE_GUIDANCE = "根据企业实际发生的长期待摊费用逐项列示各项目的期初期末变动情况及其他减少的原因。"


def _i4_listed(dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    """I4 上市（五、29）：两级表头 6 列。"""
    # 源模板行：动态项目行 + 合计（R5 第二行表头被 md 重建压成 header_label 假行，须清掉）
    from _note_structure_kit import data_row, total_row  # noqa: E402
    plan = [
        rule(
            _I4_TABLE_NAME,
            _I4_LISTED_COLUMNS,
            [data_row(), total_row("合计")],  # 清掉 header_label，保留动态行骨架+合计
            _I4_LISTED_GUIDANCE,
        ),
    ]
    return run_section(
        LISTED_PATH,
        "五、29",
        plan,
        [_I4_TABLE_NAME],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
    )


def _i4_soe(dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    """I4 国企（八、30）：单行表头 7 列 flat。"""
    plan = [
        rule(
            _I4_TABLE_NAME,
            _I4_SOE_COLUMNS,
            None,  # rows 不动
            _I4_SOE_GUIDANCE,
        ),
    ]
    return run_section(
        SOE_PATH,
        "八、30",
        plan,
        [_I4_TABLE_NAME],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# I5 其他非流动资产（五、31 / 八、32）
# ═══════════════════════════════════════════════════════════════════════════════

_I5_TABLE_NAME = "其他非流动资产"

# 上市版：两级表头 7 列 — 「期末数」/「上年年末数」各含 3 子列
_I5_LISTED_COLUMNS = [
    {"key": "项目", "label": "项  目", "is_label": True},
    {"key": "end_book", "label": "账面余额", "group": "期末数", "format": AMOUNT},
    {"key": "end_impair", "label": "减值准备", "group": "期末数", "format": AMOUNT},
    {"key": "end_carrying", "label": "账面价值", "group": "期末数", "format": AMOUNT},
    {"key": "prior_book", "label": "账面余额", "group": "上年年末数", "format": AMOUNT},
    {"key": "prior_impair", "label": "减值准备", "group": "上年年末数", "format": AMOUNT},
    {"key": "prior_carrying", "label": "账面价值", "group": "上年年末数", "format": AMOUNT},
]

_I5_LISTED_GUIDANCE = "注：根据实际情况列示；不存在的项目请删除"

# 国企版：单行表头 3 列 flat — 注意第 3 列是「年初余额」不是「期初余额」
_I5_SOE_COLUMNS = flat_columns([
    ("项目", "项  目", None),
    ("end", "期末余额", AMOUNT),
    ("begin", "年初余额", AMOUNT),
])

_I5_SOE_GUIDANCE = ""  # 源 xlsx 无红字说明

# ── I5 第 2 张表：段落文本泄漏成表名（Task 10 / R5.4）────────────────────────
#
# 🔴 现状表名是一段 90 字符的附注 docx 指引段落：
#     '[披露与合同取得成本有关的资产相关的信息，…期末账面价值以及本期确认的摊销及减值损失金额等。例如：'
# 表名是 `sub_table_data` 的**键**，泄漏名会让任何底稿推送产出孤儿子表。
#
# 处置 = **正名 + 指引文字移入 guidance**（不造列结构），三条实证依据：
#   ① 源 xlsx 披露 sheet **没有这张表** —— 「合同取得成本」在两版都只是主表的
#      一个行标签（上市 `附注披露（上市公司）!A15`、国企 `附注披露（国有企业）!A14`），
#      openpyxl 全 sheet 扫描确认无同名独立表格区（`_wip_i_t10leak` 实证）。
#   ② 该表 rows 是真实的变动行（期初余额 / 本年增加 / 本年摊销 /
#      [本年计提减值损失] / 期末余额），**有实质内容不能删**；它是附注 docx 独有的
#      补充表（源 xlsx 主表只列一行余额，附注 docx 另要求按资产类别披露其变动）。
#   ③ 载荷侧 `i5DisclosureSyncPayload.ts` 只声明 `I5_LISTED_COLUMNS` /
#      `I5_SOE_COLUMNS` 两组（均为主表），`buildI5{Listed,Soe}SubTableData`
#      **不推该表** ⇒ 给它编造列结构等于凭空造披露形态（违反「宁缺勿造」），
#      故 `columns` 保持 None，待前端真正接入按类别动态列时再补。
#
# 表头首格在 md 重建时丢了标签列（现 headers=`['[佣金支出]','合计']`，
# `[佣金支出]` 是源 docx 的示例类别占位），同样留待前端动态列收口。
_I5_TABLE2_NAME = "合同取得成本"

#: 泄漏名（正名前）—— 两版逐字相同，作 `aliases` 定位用
_I5_TABLE2_LEAKED_NAME = (
    "[披露与合同取得成本有关的资产相关的信息，包括确定该资产金额所做的判断、"
    "该资产的摊销方法、按该资产主要类别披露的期末账面价值以及本期确认的摊销及"
    "减值损失金额等。例如："
)

#: 第 2 张表的列定义 —— 列转置表（行=变动项，列=合同取得成本的类别）。
#
# 🔴 列真源 = 该表自身的 `headers`（`['[佣金支出]', '合计']`）。为什么不是源 xlsx：
# I5 源 workbook 里「合同取得成本」**只是主表的一行**（上市 `附注披露（上市公司）!A15`、
# 国企 `附注披露（国有企业）!A14`，openpyxl 实测），并无独立 sheet；这张表来自附注
# 源 docx 的收入准则披露要求。C spec 的 `note_columns_rules.json` 对它零裁决
# （实测「五、31」「八、32」出现 0 次）—— 因为当时它的表名还是段落泄漏名，
# 被全库扫描排除在外，规则生成器根本没看见它。
#
# 首列 `[佣金支出]` 的方括号是**模板占位语义**（「此处填实际类别名」），与
# I1 上市类别列同型：模板给一份默认骨架，运行态由审计师按实际类别增删列。
# 故列 key 用稳定 key `cat_1`（禁用中文 label 作 key —— memory 已记会撞键），
# label 保留源占位文本供审计师识别要替换什么。
_I5_TABLE2_COLUMNS = flat_columns([
    ("项目", "项  目", None),
    ("cat_1", "[佣金支出]", AMOUNT),
    ("合计", "合计", AMOUNT),
])

#: 由泄漏名派生的编制提示（剥 `[` 与尾部「例如：」，语义落到它该在的位置）
_I5_TABLE2_GUIDANCE = (
    "披露与合同取得成本有关的资产相关的信息，包括确定该资产金额所做的判断、"
    "该资产的摊销方法、按该资产主要类别披露的期末账面价值以及本期确认的摊销及"
    "减值损失金额等。"
)


def _i5_table2_rule() -> dict[str, Any]:
    """I5 第 2 张表：正名 + 补 3 列 flat + guidance。

    🔴 **为什么必须连列一起补**（2026-08-10 实证）：正名前它的表名是段落泄漏名
    （以 `[` 开头的整段披露要求文本），全库扫描守卫按「表名异常」把它排除在外，
    故 `columns=None` 一直不被计入 `stance_none` 基线。正名成真实表名后它进入
    扫描面，`test_stance_none_not_worse_than_baseline` 立刻把 listed 基线
    336 → 338 打红（两张表各 +1）。

    这不是「正名做错了」而是「正名把既有缺口暴露出来了」—— 正确处置是补完整，
    不是回退表名。回退等于用一个坏表名继续把缺口藏在扫描盲区里。
    """
    return {
        "aliases": [_I5_TABLE2_LEAKED_NAME, _I5_TABLE2_NAME],
        "new_name": _I5_TABLE2_NAME,
        # headers 与 columns 必须同长同序（`validate_section` 逐项比对 label）
        "headers": [c["label"] for c in _I5_TABLE2_COLUMNS],
        "columns": _I5_TABLE2_COLUMNS,
        "rows": None,  # rows 不动（期初/增加/摊销/减值/期末 是源披露要求的固定行）
        "guidance": _I5_TABLE2_GUIDANCE,
        "insert": False,
    }


def _i5_listed(dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    """I5 上市（五、31）：主表两级表头 7 列。"""
    # 先读当前 rows，剔除 header_label 假行（md 重建压扁的第二行表头残留）
    import json as _json
    _doc = _json.loads(LISTED_PATH.read_text(encoding="utf-8"))
    _sec = next(s for s in _doc["sections"] if str(s.get("section_number", "")) == "五、31")
    _tbl = _sec["tables"][0]
    _current_rows = _tbl.get("rows") or []
    _clean_rows = [r for r in _current_rows if str(r.get("row_type", "")) != "header_label"]
    plan = [
        rule(
            _I5_TABLE_NAME,
            _I5_LISTED_COLUMNS,
            _clean_rows if _clean_rows != _current_rows else None,
            _I5_LISTED_GUIDANCE,
        ),
        # 第 2 张表：段落泄漏名正名 + 指引移入 guidance（columns 保持 None）
        _i5_table2_rule(),
    ]
    return run_section(
        LISTED_PATH,
        "五、31",
        plan,
        # 两张表全部纳入校验（2026-08-10：第 2 张表已补 3 列 flat）
        [_I5_TABLE_NAME, _I5_TABLE2_NAME],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
    )


def _i5_soe(dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    """I5 国企（八、32）：主表 3 列 flat，第 3 列「年初余额」（源 xlsx C6）。"""
    plan = [
        rule(
            _I5_TABLE_NAME,
            _I5_SOE_COLUMNS,
            None,  # rows 不动
            _I5_SOE_GUIDANCE or "根据企业实际发生的其他非流动资产逐项列示。",
        ),
        # 第 2 张表：段落泄漏名正名 + 指引移入 guidance（columns 保持 None）
        _i5_table2_rule(),
    ]
    return run_section(
        SOE_PATH,
        "八、32",
        plan,
        # 两张表全部纳入校验（2026-08-10：第 2 张表已补 3 列 flat）
        [_I5_TABLE_NAME, _I5_TABLE2_NAME],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# I3 商誉（五、28 / 八、29）
# ═══════════════════════════════════════════════════════════════════════════════

# --- I3 上市（五、28）— 4 张表 ---

# 表1：商誉账面原值 — 两级表头 8 列
_I3_LISTED_TABLE1_NAME = "商誉账面原值"
_I3_LISTED_TABLE1_COLUMNS = [
    {"key": "项目", "label": "被投资单位名称或形成商誉的事项", "is_label": True},
    {"key": "begin", "label": "期初余额", "format": AMOUNT},
    {"key": "inc_merge", "label": "企业合并形成", "group": "本期增加", "format": AMOUNT},
    {"key": "inc_jv", "label": "取得构成业务的共同经营的利益份额形成", "group": "本期增加", "format": AMOUNT},
    {"key": "inc_other", "label": "其他", "group": "本期增加", "format": AMOUNT},
    {"key": "dec_disposal", "label": "处置", "group": "本期减少", "format": AMOUNT},
    {"key": "dec_other", "label": "其他", "group": "本期减少", "format": AMOUNT},
    {"key": "end", "label": "期末余额", "format": AMOUNT},
]
_I3_LISTED_TABLE1_GUIDANCE = "提示：其他增减变动原因包括境外子公司汇率变化的影响等"

# 表2：商誉减值准备 — 两级表头 7 列
_I3_LISTED_TABLE2_NAME = "商誉减值准备"
_I3_LISTED_TABLE2_COLUMNS = [
    {"key": "项目", "label": "被投资单位名称或形成商誉的事项", "is_label": True},
    {"key": "begin", "label": "期初余额", "format": AMOUNT},
    {"key": "inc_provision", "label": "计提", "group": "本期增加", "format": AMOUNT},
    {"key": "inc_other", "label": "其他增加", "group": "本期增加", "format": AMOUNT},
    {"key": "dec_disposal", "label": "处置", "group": "本期减少", "format": AMOUNT},
    {"key": "dec_other", "label": "其他减少", "group": "本期减少", "format": AMOUNT},
    {"key": "end", "label": "期末余额", "format": AMOUNT},
]
_I3_LISTED_TABLE2_GUIDANCE = "根据企业实际情况逐项填列商誉减值准备的变动。"

# 表3：商誉减值测试关键假设（正名，不改 columns）
_I3_LISTED_TABLE3_NAME = "商誉减值测试关键假设"
# aliases 用现模板中的实际表名（段落文本泄漏名，90 字符）
_I3_LISTED_TABLE3_ALIAS = "资产组的可收回金额是依据管理层编制的五年期预测，采用未来现金流量折合现值计算。超过该五年期的现金流量采用以下所述的估计增长率作出推算。采用未来现金流量折现方法所运用的假设主要包括："
_I3_LISTED_TABLE3_GUIDANCE = (
    "提示：应披露商誉减值测试所涉及的资产组或资产组组合，"
    "以及确定可收回金额所使用的关键假设和方法。"
    "列头「资产组/业务」按本项目实际资产组名称列示（源模板示例为「XX地区铁路运输业务」）；"
    "行为关键假设参数（毛利率/增长率/折现率）。"
)

# 🔴 columns 真源 = 源模板 `附注披露（上市公司）` 的减值测试示例段（该表在源 xlsx 里
# 是「资产组作列头、关键假设作行」的**列转置**形态，示例只给一个资产组列）。
# 与前端载荷 `I3_ASSUMPTION_COLUMNS`（`i3DisclosureSyncPayload.ts`）逐字同构 ——
# 后者已声明 `label='资产组/业务'` + 毛利率/增长率/折现率三个数据列，
# 而模板侧 `columns=0` 导致 seed 路径退回 `_infer_groups_from_headers` 前缀推断
# （实测 headers 只有 `['XX地区铁路运输业务']` 一列 = 示例资产组名泄漏成列头）。
# 单级表 ⇒ 必须显式 `flat`（否则「毛利率/增长率/折现率」无共享前缀虽不会被并组，
# 但 `None` 态会让投影器每次都走推断分支）。
_I3_LISTED_TABLE3_COLUMNS = flat_columns([
    ("label", "资产组/业务", None),
    ("毛利率", "毛利率", PERCENT),
    ("增长率", "增长率", PERCENT),
    ("折现率", "折现率", PERCENT),
])

# 表4：业绩承诺完成及商誉减值情况（正名，去尾冒号+去「如下」）
_I3_LISTED_TABLE4_NAME = "业绩承诺完成及商誉减值情况"
_I3_LISTED_TABLE4_ALIAS = "业绩承诺完成及对应商誉减值情况如下："
_I3_LISTED_TABLE4_COLUMNS = flat_columns([
    ("项目", "项目", None),
    ("commitment", "业绩承诺完成情况", TEXT),
    ("impairment", "商誉减值金额", AMOUNT),
])
_I3_LISTED_TABLE4_GUIDANCE = "根据业绩承诺协议逐项列示承诺完成情况及对应的商誉减值金额。"


def _i3_listed(dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    """I3 上市（五、28）：4 张表。"""
    # 读取当前 rows，剔除 header_label 假行（md 重建压扁的第二行表头残留）
    _doc = json.loads(LISTED_PATH.read_text(encoding="utf-8"))
    _sec = next(s for s in _doc["sections"] if str(s.get("section_number", "")) == "五、28")
    _tables = _sec.get("tables") or []

    def _clean_rows(tbl_idx: int) -> list[dict[str, Any]] | None:
        if tbl_idx >= len(_tables):
            return None
        rows = _tables[tbl_idx].get("rows") or []
        clean = [r for r in rows if str(r.get("row_type", "")) != "header_label"]
        return clean if clean != rows else None

    plan = [
        rule(
            _I3_LISTED_TABLE1_NAME,
            _I3_LISTED_TABLE1_COLUMNS,
            _clean_rows(0),  # 清 header_label
            _I3_LISTED_TABLE1_GUIDANCE,
        ),
        rule(
            _I3_LISTED_TABLE2_NAME,
            _I3_LISTED_TABLE2_COLUMNS,
            _clean_rows(1),  # 清 header_label
            _I3_LISTED_TABLE2_GUIDANCE,
        ),
        # 表3：正名 + 补 3 列 flat + guidance
        #
        # 🔴 改造前这里写 `"columns": None`，注释理由「其示例列名是合理的动态结构」——
        # 实测该判断站不住：模板 `headers` 是 `['XX地区铁路运输业务']` **单列**，
        # 而 rows 是 `毛利率 / 增长率 / 折现率` 三行 = **列缺了标签列**，投影器会
        # 退回 `_infer_groups_from_headers` 前缀推断，且 `columns=0` 时读时降级成
        # `_needs_columns`（只显示行名）。载荷侧 `I3_ASSUMPTION_COLUMNS` 早已是
        # 4 列（资产组/业务 + 毛利率/增长率/折现率），两侧不同构。
        # ⇒ 按载荷侧列集补齐（列 key 与 `i3DisclosureSyncPayload.ts` 逐字一致）。
        rule(
            _I3_LISTED_TABLE3_NAME,
            _I3_LISTED_TABLE3_COLUMNS,
            None,  # rows 不动（三行关键参数是源模板固定行）
            _I3_LISTED_TABLE3_GUIDANCE,
            aliases=[_I3_LISTED_TABLE3_ALIAS],
        ),
        rule(
            _I3_LISTED_TABLE4_NAME,
            _I3_LISTED_TABLE4_COLUMNS,
            _clean_rows(3),  # 清 header_label
            _I3_LISTED_TABLE4_GUIDANCE,
            aliases=[_I3_LISTED_TABLE4_ALIAS],
        ),
    ]
    return run_section(
        LISTED_PATH,
        "五、28",
        plan,
        # 四张表全部纳入校验（2026-08-10 Task 10：表3 已补 4 列 flat）
        [_I3_LISTED_TABLE1_NAME, _I3_LISTED_TABLE2_NAME,
         _I3_LISTED_TABLE3_NAME, _I3_LISTED_TABLE4_NAME],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
    )


# --- I3 国企（八、29）— 2 张表 ---

# 表1：（1）商誉账面价值 — 5 列 flat（源 xlsx R6 实为「商誉账面价值」不是「原值」）
_I3_SOE_TABLE1_NAME = "（1）商誉账面价值"
_I3_SOE_TABLE1_COLUMNS = flat_columns([
    ("项目", "被投资单位名称或形成商誉的事项", None),
    ("begin", "期初余额", AMOUNT),
    ("increase", "本期增加", AMOUNT),
    ("decrease", "本期减少", AMOUNT),
    ("end", "期末余额", AMOUNT),
])
_I3_SOE_TABLE1_GUIDANCE = "根据企业实际情况逐项填列商誉账面价值的变动。"

# 表2：（2）商誉减值准备 — 5 列 flat（名称正确）
_I3_SOE_TABLE2_NAME = "（2）商誉减值准备"
_I3_SOE_TABLE2_COLUMNS = flat_columns([
    ("项目", "被投资单位名称或形成商誉的事项", None),
    ("begin", "期初余额", AMOUNT),
    ("increase", "本期增加", AMOUNT),
    ("decrease", "本期减少", AMOUNT),
    ("end", "期末余额", AMOUNT),
])
_I3_SOE_TABLE2_GUIDANCE = (
    "说明：商誉的减值测试方法和减值准备计提方法，"
    "详细说明减值原因、减值金额确认依据。"
)


def _i3_soe(dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    """I3 国企（八、29）：2 张表。表1 从「（1）商誉账面原值」改为「（1）商誉账面价值」。"""
    plan = [
        rule(
            _I3_SOE_TABLE1_NAME,
            _I3_SOE_TABLE1_COLUMNS,
            None,  # rows 不动
            _I3_SOE_TABLE1_GUIDANCE,
            aliases=["（1）商誉账面原值"],  # 旧名定位
        ),
        rule(
            _I3_SOE_TABLE2_NAME,
            _I3_SOE_TABLE2_COLUMNS,
            None,  # rows 不动
            _I3_SOE_TABLE2_GUIDANCE,
        ),
    ]
    return run_section(
        SOE_PATH,
        "八、29",
        plan,
        [_I3_SOE_TABLE1_NAME, _I3_SOE_TABLE2_NAME],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# I2 开发支出（五、27 / 八、28）
# ═══════════════════════════════════════════════════════════════════════════════

# --- I2 上市（五、27）— 5 张表 ---

# 表1：研发支出（按费用性质披露）— 两级表头 5 列
# 源 xlsx R5~R18，排在「开发支出」之前（源模板第 0 张表）
_I2_LISTED_TABLE1_NAME = "研发支出"
_I2_LISTED_TABLE1_COLUMNS = [
    {"key": "项目", "label": "项  目", "is_label": True},
    {"key": "cur_expense", "label": "费用化金额", "group": "本期发生额", "format": AMOUNT},
    {"key": "cur_capitalize", "label": "资本化金额", "group": "本期发生额", "format": AMOUNT},
    {"key": "prior_expense", "label": "费用化金额", "group": "上期发生额", "format": AMOUNT},
    {"key": "prior_capitalize", "label": "资本化金额", "group": "上期发生额", "format": AMOUNT},
]
_I2_LISTED_TABLE1_GUIDANCE = (
    "按费用性质披露研发支出本期发生额、上期发生额，包括费用化研发支出和资本化研发支出。"
    "（15号文第二十六条）"
    "根据财会〔2019〕6号，\u201c研发费用\u201d项目，"
    "反映企业进行研究与开发过程中发生的费用化支出，"
    "以及计入管理费用的自行开发无形资产的摊销。"
    "费用化金额列请与研发费用对应，资本化金额请与开发支出对应。"
)

# 表2：开发支出（变动表）— 两级表头 7 列
# 源 xlsx R19~R32
_I2_LISTED_TABLE2_NAME = "开发支出"
_I2_LISTED_TABLE2_COLUMNS = [
    {"key": "项目", "label": "项  目", "is_label": True},
    {"key": "begin", "label": "期初数", "format": AMOUNT},
    {"key": "inc_internal", "label": "内部开发支出", "group": "本期增加", "format": AMOUNT},
    {"key": "inc_other", "label": "其他增加", "group": "本期增加", "format": AMOUNT},
    {"key": "dec_intangible", "label": "确认为无形资产", "group": "本期减少", "format": AMOUNT},
    {"key": "dec_expense", "label": "计入当期损益", "group": "本期减少", "format": AMOUNT},
    {"key": "end", "label": "期末数", "format": AMOUNT},
]
_I2_LISTED_TABLE2_GUIDANCE = "增减变动因素可根据实际情况自行添加"

# 表3：开发支出（续：资本化情况）— 单行表头 4 列 flat
# 源 xlsx R33~R42
_I2_LISTED_TABLE3_NAME = "开发支出（续：资本化情况）"
_I2_LISTED_TABLE3_COLUMNS = flat_columns([
    ("项目", "项  目", None),
    ("capitalize_start", "资本化开始时点", TEXT),
    ("capitalize_basis", "资本化的具体依据", TEXT),
    ("progress", "截至期末的研发进度", TEXT),
])
_I2_LISTED_TABLE3_GUIDANCE = (
    "说明：（披露上述项目的资本化开始时点、资本化的具体依据、截至期末的研发进度等。）"
    "尚未达到可使用状态的无形资产（开发支出），说明减值测试结果（每年进行减值测试）。"
)

# 表4：重要的资本化研发项目 — 单行表头 6 列 flat
# 源 xlsx R44~R49
_I2_LISTED_TABLE4_NAME = "重要的资本化研发项目"
_I2_LISTED_TABLE4_COLUMNS = flat_columns([
    ("项目", "项  目", None),
    ("progress", "研发进度", TEXT),
    ("expected_completion", "预计完成时间", TEXT),
    ("economic_benefit", "预计经济利益产生方式", TEXT),
    ("capitalize_start", "开始资本化的时点", TEXT),
    ("capitalize_basis", "开始资本化的具体依据", TEXT),
])
_I2_LISTED_TABLE4_GUIDANCE = (
    "对于重要的资本化研发项目，应结合研发进度、预计完成时间、预计经济利益产生方式等情况，"
    "分项说明开始资本化的时点和具体依据。分项列示开发支出减值准备的期初余额、"
    "期末余额和本期增减变动情况，以及减值测试情况。（15号文第二十七条）"
)

# 表5：开发支出减值准备 — 单行表头 5 列 flat
# 源 xlsx R50~R56
_I2_LISTED_TABLE5_NAME = "开发支出减值准备"
_I2_LISTED_TABLE5_COLUMNS = flat_columns([
    ("项目", "项  目", None),
    ("begin", "期初余额", AMOUNT),
    ("increase", "本期计提", AMOUNT),
    ("decrease", "本期减少", AMOUNT),
    ("end", "期末余额", AMOUNT),
])
_I2_LISTED_TABLE5_GUIDANCE = (
    "说明减值测试情况。"
    "证监会《2020年上市公司年报会计监管报告》指出个别上市公司对于内部研究开发项目，"
    "以前年度将相关支出确认为开发支出，报告期公司进行战略调整，暂缓相关研究开发项目，"
    "因而将开发支出累计发生余额转入当期管理费用。上市公司应判断以前年度相关支出是否满足资本化条件，"
    "对于不满足资本化条件的，应按照《企业会计准则第28号\u2014\u2014会计政策、会计估计变更和差错更正》"
    "相关规定进行会计处理。若以前年度相关支出满足资本化条件，上市公司应按照资产减值准则的规定，"
    "对已资本化的开发支出恰当计提减值损失，而非转入管理费用。"
)


def _i2_listed(dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    """I2 上市（五、27）：5 张表。

    现有模板只有 1 张表「开发支出」（4 列），需扩为 5 张表。
    - 表1「研发支出」是新增的第 0 张表（insert=True，排在开发支出前面）
    - 表2「开发支出」已存在，补 columns/guidance + 改为两级 7 列
    - 表3~5 是完全缺失的，全部 insert=True
    """
    # 先读当前表，剔除 header_label 假行
    _doc = json.loads(LISTED_PATH.read_text(encoding="utf-8"))
    _sec = next(
        (s for s in _doc["sections"] if str(s.get("section_number", "")) == "五、27"),
        None,
    )
    _tables = (_sec.get("tables") or []) if _sec else []

    def _clean_rows(tbl_idx: int) -> list[dict[str, Any]] | None:
        if tbl_idx >= len(_tables):
            return None
        rows = _tables[tbl_idx].get("rows") or []
        clean = [r for r in rows if str(r.get("row_type", "")) != "header_label"]
        return clean if clean != rows else None

    plan = [
        rule(
            _I2_LISTED_TABLE1_NAME,
            _I2_LISTED_TABLE1_COLUMNS,
            None,  # 动态行，rows 不预设
            _I2_LISTED_TABLE1_GUIDANCE,
            insert=True,  # 模板里没有这张表，需插入
        ),
        rule(
            _I2_LISTED_TABLE2_NAME,
            _I2_LISTED_TABLE2_COLUMNS,
            _clean_rows(0),  # 清 header_label（现有的第 0 张就是「开发支出」）
            _I2_LISTED_TABLE2_GUIDANCE,
        ),
        rule(
            _I2_LISTED_TABLE3_NAME,
            _I2_LISTED_TABLE3_COLUMNS,
            None,  # 动态行
            _I2_LISTED_TABLE3_GUIDANCE,
            insert=True,
        ),
        rule(
            _I2_LISTED_TABLE4_NAME,
            _I2_LISTED_TABLE4_COLUMNS,
            None,  # 动态行
            _I2_LISTED_TABLE4_GUIDANCE,
            aliases=["（1）重要的资本化研发项目"],
            insert=True,
        ),
        rule(
            _I2_LISTED_TABLE5_NAME,
            _I2_LISTED_TABLE5_COLUMNS,
            None,  # 动态行
            _I2_LISTED_TABLE5_GUIDANCE,
            aliases=["（2）开发支出减值准备"],
            insert=True,
        ),
    ]
    return run_section(
        LISTED_PATH,
        "五、27",
        plan,
        [_I2_LISTED_TABLE1_NAME, _I2_LISTED_TABLE2_NAME,
         _I2_LISTED_TABLE3_NAME, _I2_LISTED_TABLE4_NAME,
         _I2_LISTED_TABLE5_NAME],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
    )


# --- I2 国企（八、28）— 1 张表 ---

# 开发支出（变动表）— 两级表头 8 列
# 源 xlsx 国企版 R6~R17
_I2_SOE_TABLE_NAME = "开发支出"
_I2_SOE_COLUMNS = [
    {"key": "项目", "label": "项  目", "is_label": True},
    {"key": "begin", "label": "期初余额", "format": AMOUNT},
    {"key": "inc_internal", "label": "内部开发支出", "group": "本期增加", "format": AMOUNT},
    {"key": "inc_other", "label": "其他", "group": "本期增加", "format": AMOUNT},
    {"key": "dec_intangible", "label": "确认为无形资产", "group": "本期减少", "format": AMOUNT},
    {"key": "dec_expense", "label": "转入当期损益", "group": "本期减少", "format": AMOUNT},
    {"key": "dec_other", "label": "其他", "group": "本期减少", "format": AMOUNT},
    {"key": "end", "label": "期末余额", "format": AMOUNT},
]
_I2_SOE_GUIDANCE = ""  # 源 xlsx 国企版无红字


def _i2_soe(dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    """I2 国企（八、28）：1 张表，两级 8 列。"""
    # 读当前 rows，剔除 header_label 假行（md 重建压扁的第二行表头残留）
    _doc = json.loads(SOE_PATH.read_text(encoding="utf-8"))
    _sec = next(
        (s for s in _doc["sections"] if str(s.get("section_number", "")) == "八、28"),
        None,
    )
    _tables = (_sec.get("tables") or []) if _sec else []
    _clean_rows: list[dict[str, Any]] | None = None
    if _tables:
        rows = _tables[0].get("rows") or []
        clean = [r for r in rows if str(r.get("row_type", "")) != "header_label"]
        if clean != rows:
            _clean_rows = clean

    plan = [
        rule(
            _I2_SOE_TABLE_NAME,
            _I2_SOE_COLUMNS,
            _clean_rows,  # 清 header_label
            _I2_SOE_GUIDANCE or "根据企业实际发生的开发支出逐项列示各项目的期初期末变动情况。",
        ),
    ]
    return run_section(
        SOE_PATH,
        "八、28",
        plan,
        [_I2_SOE_TABLE_NAME],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# I1 无形资产（五、26 / 八、27）
# ═══════════════════════════════════════════════════════════════════════════════

def _i1_categories() -> list[Any]:
    """按 seq 取 `i1_asset_categories.I1_ASSET_CATEGORIES`（类别真源，逐条带 `source_ref`）。

    上市侧当**列**用、国企侧当**行**用，故两个 runner 共用这一个入口 ——
    类别清单在本脚本里零字面量，改类别只改 `i1_asset_categories.py` 一处。
    """
    import importlib.util as _ilu
    import sys as _sys

    _cat_path = _BACKEND / "app" / "services" / "four_table" / "i1_asset_categories.py"
    _spec = _ilu.spec_from_file_location("_i1_cats_for_note", _cat_path)
    _mod = _ilu.module_from_spec(_spec)
    # 🔴 Py3.12 坑：加载含 @dataclass 的模块前必须先注册进 sys.modules，
    # 否则 dataclass 装饰器反查 sys.modules.get(cls.__module__) 得 None 而崩
    # （AttributeError: 'NoneType' object has no attribute '__dict__'）。
    _sys.modules[_spec.name] = _mod
    _spec.loader.exec_module(_mod)
    return sorted(_mod.I1_ASSET_CATEGORIES, key=lambda c: c.seq)


# --- I1 国企（八、27）— 1 张主表 + 1 张数据资源表 ---

# 表1：无形资产情况 — 5 列 flat（四层 52 行）
# 源 xlsx 国企 R7 表头：项  目 | 期初余额 | 本期增加 | 本期减少 | 期末余额
_I1_SOE_TABLE1_NAME = "无形资产情况"
_I1_SOE_TABLE1_COLUMNS = flat_columns([
    ("项目", "项  目", None),
    ("begin", "期初余额", AMOUNT),
    ("increase", "本期增加", AMOUNT),
    ("decrease", "本期减少", AMOUNT),
    ("end", "期末余额", AMOUNT),
])
# 源 xlsx 无红字，说明文字走 text_sections

#: 四层标题，逐字取自源 xlsx `附注披露信息（国有企业）!A8/A21/A34/A47`（`row_type=total`）
_I1_SOE_LAYER_TITLES: tuple[str, ...] = (
    "一、原价合计",
    "二、累计摊销合计",
    "三、无形资产减值准备合计",
    "四、账面价值合计",
)


def _i1_soe_table1_rows() -> list[dict[str, Any]]:
    """国企主表 52 行骨架 = 4 层 ×（层标题 + 11 类别 + 1 可扩位）。

    行真源 = 源 xlsx `附注披露信息（国有企业）!A8:A59`（openpyxl 逐格实测 52 行）：
    每层首个类别带「其中：」前缀，层末一处 `……`（A20/A33/A46/A59）。

    🔴🔴 改造前模板 JSON 是 **48 行**且类别与源模板不符（2026-08-15 逐行实测）：
    ①只有 10 个类别（缺「其他」）②首类别是「其中：软件」而源模板是「其中：土地使用权」
    ③把源模板的「矿产权」拆成「采矿权」+「探矿权」④「特许经营权」写成「特许权」。
    运行态推送产出的是正确的 52 行（Task 24 浏览器实测「56 行 → 52 行」），
    **只有 seed 路径**（新建项目 / 重新生成附注）用这份错骨架 ⇒ 新项目附注开局就是错类别。
    类别不在此处写死，由 `_i1_categories()` 派生。
    """
    rows: list[dict[str, Any]] = []
    cats = _i1_categories()
    for title in _I1_SOE_LAYER_TITLES:
        rows.append(total_row(title))
        for idx, cat in enumerate(cats):
            rows.append(data_row(("其中：" if idx == 0 else "") + cat.label))
        rows.append(data_row("……"))
    return rows


_I1_SOE_TABLE1_GUIDANCE = ""

# 表2：确认为无形资产的数据资源 — 列转置（列=取得方式，行=四层 27 行）
#
# 🔴 列真源不是源 xlsx 的披露 sheet —— 该 sheet **没有这张表**（openpyxl 实测 I1
# 两个披露 sheet 里「数据资源」只作**主表的一个类别列**出现：上市 K10、国企 A18）。
# 这张表是《企业数据资源相关会计处理暂行规定》（财会〔2023〕11 号）要求的独立披露，
# 平台按该规定补建，列真源 = 前端载荷 `buildI1ListedColumns()[dataResource]`
# （4 个数据列：外购 / 自行开发 / 其他方式取得 / 合计），两侧由守卫三向锁死。
#
# 列 key 与载荷侧逐字相同（载荷用中文 key），改 key 会让已推送数据失落点。
#
# 🔴 `_I1_DATA_RESOURCE_COLUMNS` 是这张表列定义的**唯一真源** —— 上市（表3）与
# 国企（表2）是同一张《数据资源规定》独立披露表，结构逐字同构，两侧 runner
# 共用此常量避免双写漂移。别再各写一份。
_I1_SOE_TABLE2_NAME = "确认为无形资产的数据资源"
_I1_DATA_RESOURCE_COLUMNS = flat_columns([
    ("label", "项目", None),
    ("外购的数据资源无形资产", "外购的数据资源无形资产", AMOUNT),
    ("自行开发的数据资源无形资产", "自行开发的数据资源无形资产", AMOUNT),
    ("其他方式取得的数据资源无形资产", "其他方式取得的数据资源无形资产", AMOUNT),
    ("合计", "合计", AMOUNT),
])
_I1_SOE_TABLE2_COLUMNS = _I1_DATA_RESOURCE_COLUMNS
_I1_SOE_TABLE2_GUIDANCE = (
    "根据《企业数据资源相关会计处理暂行规定》（财会〔2023〕11号），"
    "列示确认为无形资产的数据资源的账面原值、累计摊销、减值准备及账面价值。"
)


def _i1_soe(dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    """I1 国企（八、27）：主表补 5 列 flat + guidance；数据资源表只补 guidance。"""
    plan = [
        rule(
            _I1_SOE_TABLE1_NAME,
            _I1_SOE_TABLE1_COLUMNS,
            # 52 行骨架对齐源模板 A8:A59（改造前 48 行 / 10 个错类别，见函数 docstring）。
            # 可扩位数前后都是 4 ⇒ kit 的 `carry_expandable_rows` 不会插回旧行，可走 rule 路径
            # （上市侧要把 4 减到 3，故只能走独立前置步，两者形态不同是有意为之）。
            _i1_soe_table1_rows(),
            _I1_SOE_TABLE1_GUIDANCE or "根据企业实际情况逐层列示原价、累计摊销、减值准备及账面价值。",
        ),
        # 数据资源表：补 5 列 flat（列头逐字取自模板 headers，与上市侧同构）
        rule(
            _I1_SOE_TABLE2_NAME,
            _I1_DATA_RESOURCE_COLUMNS,
            None,  # rows 不动（27 行四层结构）
            _I1_SOE_TABLE2_GUIDANCE,
        ),
    ]
    return run_section(
        SOE_PATH,
        "八、27",
        plan,
        # 两张表全部纳入校验（2026-08-10 Task 10：数据资源表已补 columns）
        [_I1_SOE_TABLE1_NAME, _I1_SOE_TABLE2_NAME],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
    )


# --- I1 上市（五、26）— 4 张表 ---

# 表1：无形资产情况 — 列转置（列=类别，行=四层 38 行）
#
# 🔴 **这是动态列表，模板 columns 只是「全类别基线」不是最终形态**：
# 运行时列由 `buildI1ListedColumns(state)` 按项目实际类别生成（审计师可增删改名），
# 模板这份服务 **seed 路径**（新建项目 / 重新生成附注时还没有底稿数据）。
# 两者的关系与 G7 的「seed 基线 ↔ 运行时动态列」同构。
#
# 列集真源 = 源 xlsx `附注披露信息（上市公司）!A10:M10`（openpyxl 实测
# **项目 + 11 个类别列 + 合计 = 13 列**，`N10` 为空），逐字为：土地使用权/住房使用权/
# 专利权/非专利技术/商标权/著作权/特许经营权/软件/矿产权/数据资源/其他。
# 🔴 别写「12 个类别」——`底稿目录!A9:A19` 只有 11 个单元格（`A20` 是可扩位 `……`），
# spec 正文与 design.md Property 19 的「12 类」是错基线，守卫按实测 11 断言。
# 类别清单**不在此处写死** —— 从 `i1_asset_categories.I1_ASSET_CATEGORIES` 按 seq
# 派生（该模块每条带 `source_ref` 指向 `底稿目录!A9:A19`），改类别只需改那一处。
#
# 列 key 用稳定 key `{cat.key}_{seq}`（2026-08-10 Task 12 收敛）——
# 与前端载荷 `i1CategoryColumnKey(slot)`（`i1CategoryScope.ts`）逐字同构。
# 🔴 禁用中文 label 作 key：两个类别改成同名 label 会撞键、列与数据串台（H7 已踩）。
# key 是 `sub_table_data` 行内字段名 + 列头 key，seed 侧与 push 侧必须用同一规则，
# 否则 note 投影器 `r.get(column.key)` 对不上。不做存量迁移：每次推送的
# columns+rows 同批生成、快照内自洽，旧快照保持旧 key 自洽、再推送即自愈（零失落点）。
_I1_LISTED_TABLE1_NAME = "无形资产情况"


def _i1_listed_table1_columns() -> list[dict[str, Any]]:
    """按 `i1_asset_categories` 的 seq 顺序派生上市主表列（零类别字面量）。"""
    # 🔴 列 key = 稳定 key `{cat.key}_{cat.seq}`（Task 12 / Property 20），与前端载荷
    # `i1CategoryColumnKey(slot)` 逐字同构 —— seed 列 key 与 push 列 key 收敛为同一形态，
    # 消除「同一表 seed 侧用中文 label 作 key、push 侧用稳定 key」的双真源与表头漂移。
    # 禁用中文 label 作 key：默认类别名可能被改成同名 → 撞键、列串台（H7 已踩）。
    pairs: list[tuple[str, str, str | None]] = [("label", "项目", None)]
    for cat in _i1_categories():
        pairs.append((f"{cat.key}_{cat.seq}", cat.label, AMOUNT))
    pairs.append(("合计", "合计", AMOUNT))
    return flat_columns(pairs)


_I1_LISTED_TABLE1_COLUMNS = _i1_listed_table1_columns()
_I1_LISTED_TABLE1_GUIDANCE = (
    "【提示：列头按实际无形资产类别列示（参见底稿目录!A9~A19），"
    "不存在的类别可删除；数据资源列为固定列。"
    "行按四层结构列示：一、账面原值→二、累计摊销→三、减值准备→四、账面价值。"
    "各层结构含期初余额、本期增减明细（购置/内部研发/企业合并等）、期末余额。】"
)

# 表2：重要单项无形资产 — 3 列 flat
# 源 xlsx R55~R56 区域，当前名是段落文本泄漏（⑥（按照《知识产权相关会计信息披露规定》...）开头的整段）
_I1_LISTED_TABLE2_NAME = "重要单项无形资产"
_I1_LISTED_TABLE2_ALIAS = "⑥（按照《知识产权相关会计信息披露规定》（财会〔2018〕30号），应当单独披露对企业财务报表具有重要影响的单项无形资产的内容、账面价值和剩余摊销期限。）"
_I1_LISTED_TABLE2_COLUMNS = flat_columns([
    ("项目", "项  目", None),
    ("carrying_value", "账面价值", AMOUNT),
    ("remaining_period", "剩余摊销期限", TEXT),
])
_I1_LISTED_TABLE2_GUIDANCE = (
    "按照《知识产权相关会计信息披露规定》（财会〔2018〕30号），"
    "应当单独披露对企业财务报表具有重要影响的单项无形资产的内容、账面价值和剩余摊销期限。"
)

# 表3：确认为无形资产的数据资源 — 5 列 flat（列转置：列=取得方式，行=四层 27 行）
# 与国企侧 `_I1_SOE_TABLE2_COLUMNS` 逐字同构（同一张表在两版模板结构相同），
# 故两侧共用同一份列定义常量（避免两处各写一份漂移）。
_I1_LISTED_TABLE3_NAME = "确认为无形资产的数据资源"
_I1_LISTED_TABLE3_COLUMNS = _I1_SOE_TABLE2_COLUMNS
_I1_LISTED_TABLE3_GUIDANCE = (
    "根据《企业数据资源相关会计处理暂行规定》（财会〔2023〕11号），"
    "列示确认为无形资产的数据资源的账面原值、累计摊销、减值准备及账面价值。"
)

# 表4：未办妥产权证书的土地使用权情况 — 3 列 flat
# 源 xlsx R60~R62 区域，当前名是「项  目」（表头首格泄漏）
_I1_LISTED_TABLE4_NAME = "未办妥产权证书的土地使用权情况"
_I1_LISTED_TABLE4_ALIAS = "项  目"  # 表头首格泄漏名（两个空格）
_I1_LISTED_TABLE4_COLUMNS = flat_columns([
    ("项目", "项  目", None),
    ("carrying_value", "账面价值", AMOUNT),
    ("reason", "未办妥产权证书原因", TEXT),
])
_I1_LISTED_TABLE4_GUIDANCE = "披露未办妥产权证书的土地使用权账面价值及原因。"


# 表1 行骨架真源 = 源 xlsx `附注披露信息（上市公司）!A11:A48`（openpyxl 逐格实测 38 行，
# 去空白归一后逐字如下）。三层增加段末各一处 `……` 可扩位（源 A18/A29/A40），
# **减少段一律三个明细、无扩位**。`data_row()` 会按 `row_type_for_label` 自动把 `……`
# 标成 `expandable`，故此处只声明 label、不写 row_type。
#
# 🔴🔴 为什么必须把行骨架收进脚本（2026-08-15 三向实测）：改造前模板 JSON 的第 33/34 行是
# `（2）其他减少` + `……`，而源模板是 `（2）失效且终止确认的部分` + `（3）其他减少`
# ⇒ 减值准备减少段**丢了一个真实披露项、并凭空多出第 4 个可扩位**（账面原值与累计摊销
# 两层都有「失效且终止确认的部分」，只有减值准备层没有 = 复制漏改）。前端
# `i1ListedDisclosureModel.I1_LISTED_MOVEMENT_ROWS` 是同一处错（同批生成），
# 两侧同错故任何「模板 ↔ 载荷」自洽型判据都放行 —— 只有拿源 xlsx 当第三边才抓得到。
_I1_LISTED_TABLE1_ROW_LABELS: tuple[str, ...] = (
    "一、账面原值",
    "1.期初余额",
    "2.本期增加金额",
    "（1）购置",
    "（2）内部研发",
    "（3）企业合并增加",
    "（4）其他增加",
    "……",
    "3.本期减少金额",
    "（1）处置",
    "（2）失效且终止确认的部分",
    "（3）其他减少",
    "4.期末余额",
    "二、累计摊销",
    "1.期初余额",
    "2.本期增加金额",
    "（1）计提",
    "（2）其他增加",
    "……",
    "3.本期减少金额",
    "（1）处置",
    "（2）失效且终止确认的部分",
    "（3）其他减少",
    "4.期末余额",
    "三、减值准备",
    "1.期初余额",
    "2.本期增加金额",
    "（1）计提",
    "（2）其他增加",
    "……",
    "3.本期减少金额",
    "（1）处置",
    "（2）失效且终止确认的部分",
    "（3）其他减少",
    "4.期末余额",
    "四、账面价值",
    "1.期末账面价值",
    "2.期初账面价值",
)


def _normalize_i1_listed_table1_rows(
    dry_run: bool, check: bool
) -> tuple[list[str], list[str]]:
    """把「无形资产情况」的 rows 对齐源模板 A11:A48（38 行 / 3 处可扩位）。

    🔴 **不走 `rule(rows=...)` 而是独立前置步**：共享 kit 的
    :func:`_note_structure_kit.carry_expandable_rows` 在「新骨架的可扩位数 < 旧数」时会
    把多出来的旧可扩位**再插回来**（它的职责是防结构脚本抹掉合法可扩位），且不提供
    opt-out。本 spec 边界写明「`_note_structure_kit` 只调用不改」⇒ 减少可扩位这件事
    只能在 kit 之外做。做完之后旧 = 新，`--check` 归零、二次 `--apply` 空转。

    Returns:
        ``(changes, errs)``；``check``/``dry_run`` 下只报告不写盘。
    """
    doc = json.loads(LISTED_PATH.read_text(encoding="utf-8"))
    section = next(
        (s for s in doc.get("sections", []) if str(s.get("section_number", "")) == "五、26"),
        None,
    )
    if section is None:
        return [], ["未找到章节 五、26（note_template_listed.json）"]
    tbl = next(
        (
            t
            for t in (section.get("tables") or [])
            if str(t.get("name", "")) == _I1_LISTED_TABLE1_NAME
        ),
        None,
    )
    if tbl is None:
        return [], [f"五、26 缺表「{_I1_LISTED_TABLE1_NAME}」"]

    want = [data_row(label) for label in _I1_LISTED_TABLE1_ROW_LABELS]
    # 保留 `report_row_code`（段首码由 `fix_note_k_report_row_codes.py` 落，与结构正交）
    want = carry_row_codes(
        tbl.get("rows"), want, table_name=_I1_LISTED_TABLE1_NAME
    )
    old = tbl.get("rows") or []
    if old == want:
        return [], []

    old_labels = [str(r.get("label") or "") for r in old if isinstance(r, dict)]
    new_labels = [str(r.get("label") or "") for r in want]
    diff = [
        f"第 {i} 行「{o}」→「{n}」"
        for i, (o, n) in enumerate(zip(old_labels, new_labels))
        if o != n
    ]
    if len(old_labels) != len(new_labels):
        diff.append(f"行数 {len(old_labels)} → {len(new_labels)}")
    changes = [
        f"[{_I1_LISTED_TABLE1_NAME}] rows 对齐源模板 A11:A48："
        + ("；".join(diff) if diff else "行序调整")
    ]
    if not (dry_run or check):
        tbl["rows"] = want
        LISTED_PATH.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return changes, []


def _i1_listed(dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    """I1 上市（五、26）：表1 补列+行骨架；表2 正名+补列；表3 只补 guidance；表4 正名+补列。"""
    row_changes, row_errs = _normalize_i1_listed_table1_rows(dry_run, check)
    plan = [
        # 表1：补 13 列（源模板 B10:M10 全类别）+ guidance
        #
        # 🔴 改造前写 `"columns": None`，理由「列转置需前端动态列」——**该理由不成立**：
        # 「前端按项目实际类别动态增删列」与「模板 seed 有一份默认列定义」不冲突，
        # 前者走推送路径（`buildI1ListedColumns(state)` 按 `state.categories` 出列），
        # 后者只服务 seed 路径（新建项目/重新生成附注时的默认骨架）。留 `None` 的
        # 后果是 seed 路径 `columns=0` → 投影降级 `_needs_columns` 只显示行名。
        # ⇒ 补源模板 `附注披露信息（上市公司）!B10:M10` 的 12 类别 + 合计。
        rule(
            _I1_LISTED_TABLE1_NAME,
            _I1_LISTED_TABLE1_COLUMNS,
            # rows 由 `_normalize_i1_listed_table1_rows()` 前置步负责（38 行四层结构 +
            # **3** 个 expandable 可扩位，源 A18/A29/A40）。此处必须留 None：
            # 走 kit 的话 `carry_expandable_rows` 会把改造前多出的第 4 个可扩位插回来。
            None,
            _I1_LISTED_TABLE1_GUIDANCE,
        ),
        # 表2：正名 + 补 3 列 flat + guidance
        rule(
            _I1_LISTED_TABLE2_NAME,
            _I1_LISTED_TABLE2_COLUMNS,
            None,  # rows 不动（动态行）
            _I1_LISTED_TABLE2_GUIDANCE,
            aliases=[_I1_LISTED_TABLE2_ALIAS],
        ),
        # 表3：补 5 列 flat + guidance（列名逐字取自载荷侧 `buildI1ListedColumns`
        # 的 `dataResource` 条目，两侧同构；单级表头故标 flat）
        rule(
            _I1_LISTED_TABLE3_NAME,
            _I1_DATA_RESOURCE_COLUMNS,
            None,  # rows 不动（27 行四层结构）
            _I1_LISTED_TABLE3_GUIDANCE,
        ),
        # 表4：正名（「项  目」→ 正名）+ 补 3 列 flat + guidance
        rule(
            _I1_LISTED_TABLE4_NAME,
            _I1_LISTED_TABLE4_COLUMNS,
            None,  # rows 不动
            _I1_LISTED_TABLE4_GUIDANCE,
            aliases=[_I1_LISTED_TABLE4_ALIAS],
        ),
    ]
    changes, warnings, errs = run_section(
        LISTED_PATH,
        "五、26",
        plan,
        # 四张表全部纳入校验（2026-08-10 Task 10：表1/表3 已补 columns）
        [
            _I1_LISTED_TABLE1_NAME,
            _I1_LISTED_TABLE2_NAME,
            _I1_LISTED_TABLE3_NAME,
            _I1_LISTED_TABLE4_NAME,
        ],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
    )
    # 行骨架欠账并入本章节结果：`--check` 计为 errs（与 columns 欠账同等级），
    # `--dry-run`/`--apply` 计为 changes
    if check:
        errs = list(errs) + [f"结构未对齐（rows）：{c}" for c in row_changes] + row_errs
    else:
        changes = row_changes + list(changes)
        errs = list(errs) + row_errs
    return changes, warnings, errs


# ═══════════════════════════════════════════════════════════════════════════════
# Runner & CLI
# ═══════════════════════════════════════════════════════════════════════════════

_RUNNERS: dict[str, tuple[str, Any]] = {
    "I1_LISTED": ("I1 上市 §五、26 无形资产", _i1_listed),
    "I1_SOE": ("I1 国企 §八、27 无形资产", _i1_soe),
    "I2_LISTED": ("I2 上市 §五、27 开发支出", _i2_listed),
    "I2_SOE": ("I2 国企 §八、28 开发支出", _i2_soe),
    "I3_LISTED": ("I3 上市 §五、28 商誉", _i3_listed),
    "I3_SOE": ("I3 国企 §八、29 商誉", _i3_soe),
    "I4_LISTED": ("I4 上市 §五、29 长期待摊费用", _i4_listed),
    "I4_SOE": ("I4 国企 §八、30 长期待摊费用", _i4_soe),
    "I5_LISTED": ("I5 上市 §五、31 其他非流动资产", _i5_listed),
    "I5_SOE": ("I5 国企 §八、32 其他非流动资产", _i5_soe),
    "I6_LISTED": ("I6 上市 §五、66 研发费用", _i6_listed),
    "I6_SOE": ("I6 国企 §八、67 研发费用", _i6_soe),
}

# 按循环分组，用于 --cycle 过滤
_CYCLE_KEYS: dict[str, list[str]] = {
    "I1": ["I1_LISTED", "I1_SOE"],
    "I2": ["I2_LISTED", "I2_SOE"],
    "I3": ["I3_LISTED", "I3_SOE"],
    "I4": ["I4_LISTED", "I4_SOE"],
    "I5": ["I5_LISTED", "I5_SOE"],
    "I6": ["I6_LISTED", "I6_SOE"],
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="附注 I 类循环结构修订（I1~I6 × listed/soe）"
    )
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="只打印修订方案（默认）")
    mode.add_argument("--apply", action="store_true", help="写库（写文件）")
    mode.add_argument("--check", action="store_true",
                      help="校验是否有欠账，有则非零退出")
    ap.add_argument("--cycle", choices=sorted(_CYCLE_KEYS), help="只跑某一循环")
    args = ap.parse_args()

    dry_run = not args.apply
    check = args.check

    # 决定跑哪些 runner
    if args.cycle:
        keys = _CYCLE_KEYS.get(args.cycle, [])
        if not keys:
            print(f"循环 {args.cycle} 尚未实现（TODO）。")
            return 0
    else:
        keys = list(_RUNNERS.keys())

    total_changes = 0
    total_errs = 0

    for key in keys:
        label, runner_fn = _RUNNERS[key]
        changes, warnings, errs = runner_fn(dry_run, check)
        print(f"\n=== {label} ===")
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

    if check:
        print(f"\n--check：{total_errs} 项欠账")
        return 1 if total_errs else 0
    mode_label = "[dry-run]" if dry_run else "[apply]"
    print(f"\n{mode_label} 共 {total_changes} 处变更，{total_errs} 项问题")
    return 1 if total_errs else 0


if __name__ == "__main__":
    sys.exit(main())
