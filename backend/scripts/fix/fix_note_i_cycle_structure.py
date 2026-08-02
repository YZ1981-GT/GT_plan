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
    TEXT,
    flat_columns,
    rule,
    run_section,
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

# I5 第 2 张表暂留 TODO（合同取得成本结构复杂且源 xlsx 用动态列）
_I5_TABLE2_NAME = "合同取得成本"


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
        # TODO: I5 第 2 张表「合同取得成本」列结构复杂（动态列），暂不补
    ]
    return run_section(
        LISTED_PATH,
        "五、31",
        plan,
        [_I5_TABLE_NAME],  # 只校验主表
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
        # TODO: I5 第 2 张表「合同取得成本」列结构复杂（动态列），暂不补
    ]
    return run_section(
        SOE_PATH,
        "八、32",
        plan,
        [_I5_TABLE_NAME],  # 只校验主表
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
)

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
        # 表3：只正名 + 补 guidance，不改 columns（其示例列名是合理的动态结构）
        {
            "aliases": [_I3_LISTED_TABLE3_ALIAS, _I3_LISTED_TABLE3_NAME],
            "new_name": _I3_LISTED_TABLE3_NAME,
            "headers": None,
            "columns": None,
            "rows": None,
            "guidance": _I3_LISTED_TABLE3_GUIDANCE,
            "insert": False,
        },
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
        [_I3_LISTED_TABLE1_NAME, _I3_LISTED_TABLE2_NAME,
         _I3_LISTED_TABLE4_NAME],  # 表3 排除校验（不改 columns，动态结构）
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
_I1_SOE_TABLE1_GUIDANCE = ""

# 表2：确认为无形资产的数据资源 — 列结构复杂（H7 式列转置），暂不改 columns 只补 guidance
_I1_SOE_TABLE2_NAME = "确认为无形资产的数据资源"
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
            None,  # rows 不动（四层 52 行，差异留 TODO）
            _I1_SOE_TABLE1_GUIDANCE or "根据企业实际情况逐层列示原价、累计摊销、减值准备及账面价值。",
        ),
        # 数据资源表：columns 暂不改（H7 式列转置），只补 guidance
        {
            "aliases": [_I1_SOE_TABLE2_NAME],
            "new_name": _I1_SOE_TABLE2_NAME,
            "headers": None,
            "columns": None,
            "rows": None,
            "guidance": _I1_SOE_TABLE2_GUIDANCE,
            "insert": False,
        },
    ]
    return run_section(
        SOE_PATH,
        "八、27",
        plan,
        [_I1_SOE_TABLE1_NAME],  # 只校验主表（数据资源表不补 columns，排除 --check 误报）
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
    )


# --- I1 上市（五、26）— 4 张表 ---

# 表1：无形资产情况 — 列转置（列=11 个动态类别+数据资源+合计，行=四层 38 行）
# 现模板 columns=0，需前端 i1CategoryScope.ts 动态列能力才能对齐（Wave 5/6），暂只补 guidance
_I1_LISTED_TABLE1_NAME = "无形资产情况"
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

# 表3：确认为无形资产的数据资源 — 列结构复杂（暂不改 columns 只补 guidance）
_I1_LISTED_TABLE3_NAME = "确认为无形资产的数据资源"
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


def _i1_listed(dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    """I1 上市（五、26）：表1 只补 guidance；表2 正名+补列；表3 只补 guidance；表4 正名+补列。"""
    plan = [
        # 表1：只补 guidance，columns 不改（列转置需前端动态列）
        {
            "aliases": [_I1_LISTED_TABLE1_NAME],
            "new_name": _I1_LISTED_TABLE1_NAME,
            "headers": None,
            "columns": None,
            "rows": None,
            "guidance": _I1_LISTED_TABLE1_GUIDANCE,
            "insert": False,
        },
        # 表2：正名 + 补 3 列 flat + guidance
        rule(
            _I1_LISTED_TABLE2_NAME,
            _I1_LISTED_TABLE2_COLUMNS,
            None,  # rows 不动（动态行）
            _I1_LISTED_TABLE2_GUIDANCE,
            aliases=[_I1_LISTED_TABLE2_ALIAS],
        ),
        # 表3：只补 guidance，columns 暂不改
        {
            "aliases": [_I1_LISTED_TABLE3_NAME],
            "new_name": _I1_LISTED_TABLE3_NAME,
            "headers": None,
            "columns": None,
            "rows": None,
            "guidance": _I1_LISTED_TABLE3_GUIDANCE,
            "insert": False,
        },
        # 表4：正名（「项  目」→ 正名）+ 补 3 列 flat + guidance
        rule(
            _I1_LISTED_TABLE4_NAME,
            _I1_LISTED_TABLE4_COLUMNS,
            None,  # rows 不动
            _I1_LISTED_TABLE4_GUIDANCE,
            aliases=[_I1_LISTED_TABLE4_ALIAS],
        ),
    ]
    return run_section(
        LISTED_PATH,
        "五、26",
        plan,
        # 只校验补了 columns 的表（表1/表3 不补 columns，排除 --check 误报）
        [_I1_LISTED_TABLE2_NAME, _I1_LISTED_TABLE4_NAME],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
    )


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
