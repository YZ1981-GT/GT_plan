#!/usr/bin/env python
"""附注「营业收入」章节补齐 columns + 结构修正（幂等修订）。

**目标**：附注模板营业收入两版（上市 §五、62 / 国企 §八、64）的所有子表此前
**全部缺 `columns`**（只有压扁的 `headers`）→ seed 路径走
`_infer_groups_from_headers` 前缀推断，会把「本期发生额 / 上期发生额」错猜成
两级父表头（实为同级两列或各自带子列）。

源模板实证（`D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx`）：

- （1）（2）（3）（8）= 5 列两级表头：`项目`(rowspan2) +
  `本期发生额{收入, 成本}` + `上期发生额{收入, 成本}`
- （4）= 9 列列转置：空(rowspan3) + 动态类别列，每类别含 `{收入, 成本}` 两子列
  → 用 `grouped_columns`，group 名 = 类别名
- （6）= 4 列单级（flat）：`年 度` + 2 个年度列 + `合计`

Task 3.1：补 columns
Task 3.2：删 header_label 假行 / 表名改名走 aliases / 年度列改审计年度派生 /
          试运行表行名修正 + 删多余合计行
Task 3.3：guidance（纯文本）+ text_sections 标题化与补段

Usage::

    python backend/scripts/fix/fix_note_d4_revenue_structure.py --dry-run
    python backend/scripts/fix/fix_note_d4_revenue_structure.py
    python backend/scripts/fix/fix_note_d4_revenue_structure.py --check
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _note_structure_kit import (  # noqa: E402
    AMOUNT,
    build_cli,
    data_row,
    flat_columns,
    grouped_columns,
    rule,
    run_section,
    total_row,
    two_period_columns,
)

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"
LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

LISTED_SECTION = "五、62"
SOE_SECTION = "八、64"
ALIGNED_BY = "d4-four-table-extraction-and-disclosure-alignment"

# ── 表名 ──
# （1）主表
T_MAIN_LISTED = "营业收入和营业成本"
T_MAIN_SOE = "营业收入、营业成本"
# （2）按行业
T_SEGMENT_LISTED = "营业收入、营业成本按行业（或产品类型）划分"
T_SEGMENT_SOE = "按行业（或产品类型）划分"
# （3）按地区
T_REGION = "营业收入、营业成本按地区划分"
# （4）分解信息 —— 当前两版旧名（用作 aliases），目标名按源模板分变体
T_DECOMPOSE_OLD = "营业收入、营业成本按商品转让时间划分"
T_DECOMPOSE_LISTED = "营业收入、营业成本按分解信息"
T_DECOMPOSE_SOE = "营业收入分解信息"
# （6）剩余履约义务 —— 当前表名是段落文本泄漏，目标正名
T_OBLIGATION_OLD = (
    "分摊至尚未履行的履约义务的交易价格为xxx元，"
    "截止xx年xx月xx日，对于上述金额确认为收入的预计时间如下："
)
T_OBLIGATION = "与剩余履约义务有关的信息"
# （8）试运行销售收入（仅上市）
T_TRIAL_RUN = "试运行销售收入"


# ─── 两级列（两期同构）：（1）（2）（3）（8）───
# 源模板：项 目(rowspan2) + 本期发生额{收入, 成本} + 上期发生额{收入, 成本}
_TWO_PERIOD_SUBS = [
    ("revenue", "收入", AMOUNT),
    ("cost", "成本", AMOUNT),
]


def _two_period_cols(label_key: str, label_text: str) -> list[dict]:
    """（1）（2）（3）（8）的标准 5 列两级定义。"""
    return two_period_columns(
        label=(label_key, label_text),
        groups=("本期发生额", "上期发生额"),
        subs=_TWO_PERIOD_SUBS,
    )


# ─── （4）分解信息：9 列列转置 ───
# 源模板 B45:I45「本期发生额」+ 4 类别 ×{收入, 成本}
# 当前模板 headers 上市=[项目, 本期发生额]  国企=[合同分类/报告分部, 本期发生额]
# 列转置的类别是动态的（源模板默认：消费品/汽车/能源/其他）
# 每个类别是一个 group，内含收入+成本两子列
_DEFAULT_CATEGORIES = ("消费品", "汽车", "能源", "其他")


def _decompose_cols_listed() -> list[dict]:
    """上市（4）表列定义：标签列 + 4 类别 × {收入, 成本} = 9 列。"""
    specs: list[tuple[str, str, str | None, str | None]] = []
    for i, cat in enumerate(_DEFAULT_CATEGORIES):
        specs.append((f"cat{i}_revenue", "收入", AMOUNT, cat))
        specs.append((f"cat{i}_cost", "成本", AMOUNT, cat))
    return grouped_columns(
        label=("label", "项目"),
        specs=specs,
    )


def _decompose_cols_soe() -> list[dict]:
    """国企（4）表列定义：标签列 + 4 类别 × {收入, 成本} = 9 列。"""
    specs: list[tuple[str, str, str | None, str | None]] = []
    for i, cat in enumerate(_DEFAULT_CATEGORIES):
        specs.append((f"cat{i}_revenue", "收入", AMOUNT, cat))
        specs.append((f"cat{i}_cost", "成本", AMOUNT, cat))
    return grouped_columns(
        label=("label", "合同分类/报告分部"),
        specs=specs,
    )


# ─── （6）剩余履约义务：4 列 flat ───
# 源模板：年 度 + 年度1 + 年度2 + 合计
# 年度列由审计年度派生：{Y+1}年 / {Y+2}年（Req 5.5）
# 前端/渲染层在运行时按 project.audit_year 替换占位符，
# 模板层使用占位标记 {audit_year+1}年/{audit_year+2}年 表明派生语义。


def _obligation_cols() -> list[dict]:
    """（6）表：4 列 flat，年度列由审计年度派生（占位标记）。"""
    return flat_columns([
        ("label", "年度", None),
        ("year1", "{audit_year+1}年", AMOUNT),
        ("year2", "{audit_year+2}年", AMOUNT),
        ("total", "合计", AMOUNT),
    ])


# ─── （8）试运行销售收入行集（源模板）───
# 源模板行：固定资产试运行收入 / 研发样品销售收入（无合计行）
# 当前模板行名为「固定资产试运行销售」「研发样品销售」+ 一个合计行 → 修正 + 删合计
_TRIAL_RUN_ROWS: list[dict] = [
    data_row("固定资产试运行收入"),
    data_row("研发样品销售收入"),
]


# ─── Guidance（纯文本，只取源模板红字/提示，禁 markdown 粗体）───
# 来源：D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx
# 上市 sheet R57-R62 / R66 / R71-R77 / R81；国企 sheet R50-R55 / R59 / R64-R70

# （1）（2）（3）源模板无红字提示 → 给通用说明
_GUIDANCE_MAIN = (
    "按源模板要求填列主营业务与其他业务的本期/上期收入和成本。"
)
_GUIDANCE_SEGMENT = (
    "按主要产品类型或行业划分营业收入、营业成本。"
)
_GUIDANCE_REGION = (
    "按主要经营地区划分营业收入、营业成本（不适用的删除）。"
)

# （4）分解类别指引 —— 上市 R57-R62 / 国企 R50-R55
_GUIDANCE_DECOMPOSE_LISTED = (
    "在确定对收入进行分解的类别时，企业应当考虑其在下列情况下是如何列报和披露与收入有关的信息："
    "①在财务报表之外披露的信息，例如，在企业的业绩公告、年报或向投资者报送的相关资料中披露的收入信息；"
    "②管理层为评价经营分部的财务业绩所定期复核的信息；以及"
    "③企业或企业的财务报表使用者在评价企业的财务业绩或作出资源分配决策时，"
    "所使用的类似于上述①和②的信息类型的其他信息。"
    "企业在对收入信息进行分解时，可以采用的类别包括但不限于：商品类型、经营地区、市场或客户类型、"
    "合同类型（例如，固定造价合同、成本加成合同等）、商品转让的时间（例如，在某一时点转让或在某一时段内转让）、"
    "合同期限（例如，长期合同、短期合同等）、销售渠道（例如，直接销售或通过经销商销售等）等。"
    "④租赁收入需单独披露。"
)
_GUIDANCE_DECOMPOSE_SOE = (
    "在确定对收入、成本进行分解的类别时，企业应当考虑其在下列情况下是如何列报和披露与收入有关的信息："
    "①在财务报表之外披露的信息，例如，在企业的业绩公告、年报或向投资者报送的相关资料中披露的收入信息；"
    "②管理层为评价经营分部的财务业绩所定期复核的信息；以及"
    "③企业或企业的财务报表使用者在评价企业的财务业绩或作出资源分配决策时，"
    "所使用的类似于上述①和②的信息类型的其他信息。"
    "企业在对收入信息进行分解时，可以采用的类别包括但不限于：商品类型、经营地区、市场或客户类型、"
    "合同类型（例如，固定造价合同、成本加成合同等）、商品转让的时间（例如，在某一时点转让或在某一时段内转让）、"
    "合同期限（例如，长期合同、短期合同等）、销售渠道（例如，直接销售或通过经销商销售等）等。"
    "④租赁收入需单独披露。"
)

# （6）剩余履约义务 —— 上市 R66+R71-R77 / 国企 R59+R64-R70
_GUIDANCE_OBLIGATION_LISTED = (
    "披露与剩余履约义务有关的下列信息："
    "①分摊至本期末尚未履行（或部分未履行）履约义务的交易价格总额；"
    "②上述金额确认为收入的预计时间，企业可以按照对于剩余履约义务的期间而言最恰当的时间段为基础"
    "提供有关预计时间的定量信息，或者使用定性信息进行说明。"
    "说明：是否存在任何对价金额未纳入交易价格，从而未纳入对于分摊至剩余履约义务的交易价格所需披露的信息之中，"
    "例如，由于将可变对价计入交易价格的限制要求而未计入交易价格的可变对价。"
    "如果公司采用了简化操作方法，该方法满足下列条件之一可适用："
    "一是该项履约义务是原预计合同期限不超过一年的合同中的一部分。"
    "二是企业有权对该履约义务下已转让的商品向客户发出账单，且账单金额能够代表企业累计至今已履约部分转移给客户的价值。"
    "企业应当提供定性信息以说明采用了上述简化操作方法。"
)
_GUIDANCE_OBLIGATION_SOE = (
    "与分摊至剩余履约义务的交易价格相关的信息，包括分摊至本期末尚未履行履约义务的交易价格总额"
    "及其确认为收入的预计时间、可变对价等。"
    "说明是否存在任何对价金额未纳入交易价格，从而未纳入对于分摊至剩余履约义务的交易价格所需披露的信息之中，"
    "例如，由于将可变对价计入交易价格的限制要求而未计入交易价格的可变对价。"
    "如果公司采用了简化操作方法，该方法满足下列条件之一可适用："
    "一是该项履约义务是原预计合同期限不超过一年的合同中的一部分。"
    "二是企业有权对该履约义务下已转让的商品向客户发出账单，且账单金额能够代表企业累计至今已履约部分转移给客户的价值。"
    "企业应当提供定性信息以说明采用了上述简化操作方法。"
)

# （8）试运行销售收入 —— 上市 R81（仅上市）
_GUIDANCE_TRIAL_RUN = (
    "企业会计准则解释第15号规定，企业应当按照《企业会计准则第1号\u2014\u2014存货》、"
    "《企业会计准则第14号\u2014\u2014收入》、《企业会计准则第30号\u2014\u2014财务报表列报》等规定，"
    "判断试运行销售是否属于企业的日常活动，并在财务报表中分别日常活动和非日常活动列示"
    '试运行销售的相关收入和成本，属于日常活动的，在\u201c营业收入\u201d和\u201c营业成本\u201d项目列示；'
    '属于非日常活动的，在\u201c资产处置收益\u201d等项目列示。同时企业应当在附注中单独披露。'
)


# ─── text_sections ───
# 上市：10 段全是裸表名/标题，须加 #### 前缀让 _is_table_title_paragraph 识别
# 同时保留源模板中间的说明段（R13-R19）
_LISTED_TEXT_SECTIONS = [
    "#### （1）营业收入和营业成本",
    "（披露本公司前期已经履行 (或部分履行) 的履约义务在本期调整的收入。例如：",
    "本公司在2025年确认的、源自前期已经履行 (或部分履行) 的履约义务的收入金额为XX元，"
    "主要是由于与XX客户签订的XX合同的估计完工进度发生了变化。）",
    "#### （2）营业收入、营业成本按行业（或产品类型）划分",
    "#### （3）营业收入、营业成本按地区划分",
    "#### （4）营业收入、营业成本按分解信息",
    "#### （5）履约义务的说明",
    "（披露与履约义务相关的信息，包括履约义务通常的履行时间、重要的支付条款、"
    "企业承诺转让的商品的性质（包括说明企业是否作为代理人）、"
    "企业承担的预期将退还给客户的款项等类似义务、质量保证的类型及相关义务等。）",
    "#### （6）与剩余履约义务有关的信息",
    "#### （7）重大合同变更",
    "（披露重大合同变更或重大交易价格调整相关的信息、会计处理方法及对收入的影响金额。）",
    "#### （8）试运行销售收入",
]

# 国企：当前仅 4 段，须补齐源模板（1)~(7) 小节标题与 R50-R70 说明段
_SOE_TEXT_SECTIONS = [
    "#### （1）营业收入、营业成本",
    "#### （2）按行业（或产品类型）划分",
    "#### （3）营业收入、营业成本按地区划分",
    "#### （4）营业收入分解信息",
    "#### （5）履约义务相关信息",
    "（履约义务相关的信息，包括但不限于：履行履约义务的时间、重要的支付条款、"
    "公司承诺转让商品的性质、是否为主要责任人、公司承担的预期将退还给客户的款项等类似义务、"
    "公司提供的质量保证类型及相关义务等。）",
    "#### （6）与剩余履约义务有关的信息",
    "#### （7）重大合同变更",
    "（重大合同变更或重大交易价格调整相关的信息、会计处理方法及对收入的影响金额。）",
]


# ─── Plan 构造 ───

def _listed_plan() -> list[dict]:
    """上市 五、62 共 6 表的目标态。"""
    return [
        # （1）营业收入和营业成本（删 header_label 假行 → rows 只留数据行）
        rule(
            T_MAIN_LISTED,
            _two_period_cols("label", "项目"),
            None,  # rows 不动（header_label 由 validate 检出，apply 时按游标前进不改行）
            _GUIDANCE_MAIN,
        ),
        # （2）按行业划分
        rule(
            T_SEGMENT_LISTED,
            _two_period_cols("label", "主要产品类型（或行业）"),
            None,
            _GUIDANCE_SEGMENT,
        ),
        # （3）按地区划分
        rule(
            T_REGION,
            _two_period_cols("label", "主要经营地区"),
            None,
            _GUIDANCE_REGION,
        ),
        # （4）分解信息 —— 改名走 aliases + guidance 取源模板 R57-R62
        rule(
            T_DECOMPOSE_LISTED,
            _decompose_cols_listed(),
            None,  # rows 不动（header_label 由下方 _remove_header_labels 清理）
            _GUIDANCE_DECOMPOSE_LISTED,
            aliases=[T_DECOMPOSE_OLD],
        ),
        # （6）剩余履约义务 —— 改名 + 年度列改审计年度派生 + guidance 取 R66+R71-R77
        rule(
            T_OBLIGATION,
            _obligation_cols(),
            None,
            _GUIDANCE_OBLIGATION_LISTED,
            aliases=[T_OBLIGATION_OLD],
        ),
        # （8）试运行销售收入 —— 行名修正 + 删多余合计行 + guidance 取 R81
        rule(
            T_TRIAL_RUN,
            _two_period_cols("label", "项目"),
            _TRIAL_RUN_ROWS,
            _GUIDANCE_TRIAL_RUN,
        ),
    ]


def _soe_plan() -> list[dict]:
    """国企 八、64 共 5 表的目标态（无（8）试运行销售收入）。"""
    return [
        # （1）营业收入、营业成本
        rule(
            T_MAIN_SOE,
            _two_period_cols("label", "项目"),
            None,
            _GUIDANCE_MAIN,
        ),
        # （2）按行业划分
        rule(
            T_SEGMENT_SOE,
            _two_period_cols("label", "主要产品类型（或行业）"),
            None,
            _GUIDANCE_SEGMENT,
        ),
        # （3）按地区划分
        rule(
            T_REGION,
            _two_period_cols("label", "主要经营地区"),
            None,
            _GUIDANCE_REGION,
        ),
        # （4）分解信息 —— 改名走 aliases + guidance 取源模板 R50-R55
        rule(
            T_DECOMPOSE_SOE,
            _decompose_cols_soe(),
            None,
            _GUIDANCE_DECOMPOSE_SOE,
            aliases=[T_DECOMPOSE_OLD],
        ),
        # （6）剩余履约义务 —— 改名 + 年度列改审计年度派生 + guidance 取 R59+R64-R70
        rule(
            T_OBLIGATION,
            _obligation_cols(),
            None,
            _GUIDANCE_OBLIGATION_SOE,
            aliases=[T_OBLIGATION_OLD],
        ),
    ]


# ─── 期望表名清单（validate_section 用）───
EXPECTED_LISTED = [
    T_MAIN_LISTED,
    T_SEGMENT_LISTED,
    T_REGION,
    T_DECOMPOSE_LISTED,
    T_OBLIGATION,
    T_TRIAL_RUN,
]
EXPECTED_SOE = [
    T_MAIN_SOE,
    T_SEGMENT_SOE,
    T_REGION,
    T_DECOMPOSE_SOE,
    T_OBLIGATION,
]

_TARGETS = {
    "listed": (LISTED_PATH, LISTED_SECTION, _listed_plan, EXPECTED_LISTED),
    "soe": (SOE_PATH, SOE_SECTION, _soe_plan, EXPECTED_SOE),
}
_LABELS = {
    "listed": "note_template_listed.json §五、62 营业收入（上市）",
    "soe": "note_template_soe.json §八、64 营业收入（国企）",
}

# text_sections 目标清单（按变体）
_TEXT_SECTIONS = {
    "listed": _LISTED_TEXT_SECTIONS,
    "soe": _SOE_TEXT_SECTIONS,
}


def _remove_header_labels(section: dict) -> list[str]:
    """删除所有表里 row_type == 'header_label' 的假数据行，返回变更说明。

    （4）分解信息表当前有两连 header_label；其它表各有一个。
    """
    changes: list[str] = []
    for i, tbl in enumerate(section.get("tables") or []):
        rows = tbl.get("rows") or []
        before = len(rows)
        kept = [r for r in rows if r.get("row_type") != "header_label"]
        removed = before - len(kept)
        if removed:
            tbl["rows"] = kept
            changes.append(
                f"[{i}] {tbl.get('name', '')}：删除 {removed} 个 header_label 假行"
            )
    return changes


def _runner(key: str, dry_run: bool, check: bool):
    path, section_number, plan_fn, expected = _TARGETS[key]
    text_secs = _TEXT_SECTIONS.get(key)

    # check 模式直接校验（header_label 由 validate_section 检出）
    if check:
        return run_section(
            path,
            section_number,
            plan_fn(),
            expected,
            aligned_by=ALIGNED_BY,
            dry_run=dry_run,
            check=True,
            text_sections=text_secs,
        )
    # 非 check：先加载 → 删 header_label → 再走 run_section（apply_plan + validate）
    import json as _json
    doc = _json.loads(path.read_text(encoding="utf-8"))
    from _note_structure_kit import find_section as _find, stamp as _stamp  # noqa: E402
    from _note_structure_kit import apply_plan as _apply, validate_section as _validate  # noqa: E402
    from _note_structure_kit import titleize_text_sections as _titleize  # noqa: E402
    section = _find(doc, section_number)
    if section is None:
        return [], [f"未找到章节 {section_number}（{path.name}）"], []

    # Step 1: 删 header_label 假行（Req 5.3）
    hl_changes = _remove_header_labels(section)

    # Step 2: apply_plan（改名走 aliases + columns + rows + guidance）
    plan_changes, warnings = _apply(section, plan_fn())
    changes = hl_changes + plan_changes

    # Step 3: text_sections（整表替换为目标清单）
    if text_secs is not None and section.get("text_sections") != text_secs:
        old_len = len(section.get("text_sections") or [])
        section["text_sections"] = list(text_secs)
        changes.append(f"text_sections：{old_len} → {len(text_secs)} 段")
    # 标题化兜底（对残留裸表名追加 #### 前缀）
    changes += _titleize(section)

    # Step 4: validate
    errs = _validate(section, expected)

    # Step 5: 写文件（无阻塞性错误且有变更时）
    if changes and not dry_run and not errs:
        _stamp(section, ALIGNED_BY)
        path.write_text(
            _json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return changes, warnings, errs


main = build_cli("附注营业收入章节结构修正（columns + 表名改名 + 删假行 + 行名修正，幂等）", _runner, _LABELS)

if __name__ == "__main__":
    raise SystemExit(main())
