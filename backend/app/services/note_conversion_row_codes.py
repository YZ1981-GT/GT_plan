"""跨变体 row_code 双清单 —— 国企↔上市转换时的报表行编码映射真源。

spec: soe-listed-note-conversion-correctness / Requirements 3.1~3.8, 4.4

本模块是**判据真源**，不含 IO、不连库。生成与复核脚本：
``backend/scripts/diagnose/diagnose_cross_variant_row_codes.py``（只读 report_config）。

------------------------------------------------------------------------------
三类 row_code（2026-08-06 report_config 四变体全表实证，1222 行）
------------------------------------------------------------------------------

1. **稳定码 STABLE**：同一 row_code 在 soe 与 listed 下 ``row_name`` 相同
   ⇒ 转换时**不需要**改写（改了才是 bug）。

2. **同义两码 TWO_CODES**：同一 ``(report_type, row_name)`` 在两侧各挂**不同**
   row_code ⇒ 转换时公式引用**需要**改写。实测 **12 条**，见
   :data:`CROSS_VARIANT_ROW_CODE_MAP`。

3. **两侧异名 TWO_MEANINGS**：同一 row_code 在两侧是**不同科目**。实测 **78 条**
   （spec 立项只列了 3 条）。

**关键区分（一次立项返工的根因）**：第 3 类**本身不构成禁止改写的理由**。
``soe BS-111 -> listed BS-077`` 是正确映射，尽管 ``BS-077`` 在两侧异名 —— 因为
转换后读的就是 listed 那套配置行。实测 12 条映射的 value **12/12 都是两侧异名**，
这是码位偏移的必然结果。

故「两清单互斥」（Requirement 3.8）的正确落法**不是**「MAP 不含全部 78 个两侧异名码」
（那不可满足），而是：

- :data:`CROSS_VARIANT_ROW_CODE_MAP` 的 key/value **都不得是稳定码**
  （稳定码不需要改写，出现即说明映射是编造的）；
- 且与 :data:`ONE_CODE_TWO_MEANINGS_FORBIDDEN` 无交集（实测可满足）。

------------------------------------------------------------------------------
立项初稿的三条错误映射（已由实证推翻，禁止复活）
------------------------------------------------------------------------------

立项曾要求改写 ``BS-013->BS-016`` / ``BS-053->BS-058`` / ``BS-043->BS-059``。
三条的 **key 全是稳定码**（两侧同名，本不需改写），而 value 在目标侧是另一科目：

============  ==================  ============================  ==============
row_code      两侧属性            soe row_name                  listed row_name
============  ==================  ============================  ==============
``BS-013``    STABLE              一年内到期的非流动资产        一年内到期的非流动资产
``BS-016``    TWO_MEANINGS        其中：应收股利                一年内到期的非流动资产
``BS-053``    STABLE              其他流动负债                  其他流动负债
``BS-058``    TWO_MEANINGS        交易性金融负债                其他流动负债
``BS-043``    STABLE              衍生金融负债                  衍生金融负债
``BS-059``    TWO_MEANINGS        衍生金融负债                  流动负债合计
============  ==================  ============================  ==============

按初稿改写，在 soe 项目上会把「一年内到期的非流动资产」指向「应收股利」；
``BS-043->BS-059`` 更把明细行指向**合计行**。

**生成判据天然排除这三条**（实测 False/False/False）：判据要求
「同 ``(report_type, row_name)`` 在两侧**各恰有 1 个** row_code」，而
`一年内到期的非流动资产` 在 listed 侧有 2 个码（BS-013 与 BS-016）=> 该 row_name
整体被排除。这是「宁缺勿造」的结构性保证，不是靠人工排除。

------------------------------------------------------------------------------
公式改写在 report_config 域内**当前无对象**（Requirement 3.4 / 4.4 的实证）
------------------------------------------------------------------------------

2026-08-06 全库实测：

- ``report_config`` **无 project_id 列** —— 它是纯模板表，按 ``applicable_standard``
  分行；切 ``template_type`` 后自然读另一套行，不存在「项目级公式需要改写」。
- 全库 ``report_config.formula`` 中引用上述 12 个 row_code 的行数 = **0**
  （``ROW()`` 引用集只覆盖 BS-002~BS-128 / CFS / CFSS / EQ / IMP / IS-001~IS-030
  等主表行，无一条命中）。
- ``wp_formula`` 表 **0 行**。
- 附注侧公式的 ``binding_id`` 形如 ``五、11.分公司B.prior_year_value``
  （章节号 + 行标签 + 列键），``note_source_resolvers`` 里的 ``ROW()`` 参数是
  **单元格坐标**（``R2C1``）而非报表行码 => **不存在 row_code 级附注公式**。

=> :data:`FORMULA_REWRITE_REASON` 为 ``no_mapping_needed``（「已按清单扫描、
确无可改写对象」），与 ``not_implemented``（「未实现」）必须可区分。
清单仍必须维护：它是判据真源，且一旦将来出现 row_code 级公式即刻生效。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

__all__ = [
    "RowCodePair",
    "ForbiddenTarget",
    "CROSS_VARIANT_ROW_CODE_MAP",
    "LISTED_TO_SOE_ROW_CODE_MAP",
    "ONE_CODE_TWO_MEANINGS_FORBIDDEN",
    "STABLE_ROW_CODES_MUST_NOT_BE_MAPPED",
    "FORMULA_REWRITE_REASON",
    "ROW_REF_RE",
    "is_forbidden_rewrite",
    "rewrite_row_code",
    "rewrite_row_refs_in_formula",
]


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RowCodePair:
    """一条「同义两码」映射及其 report_config 对账依据。"""

    soe: str
    listed: str
    report_type: str
    row_name: str
    evidence: str


@dataclass(frozen=True, slots=True)
class ForbiddenTarget:
    """一个禁止作为改写目标的 row_code 及其两侧实测 row_name。"""

    soe_row_name: str
    listed_row_name: str
    reason: str


# ---------------------------------------------------------------------------
# 原因码（Requirement 4.4：0 值必须可区分成因）
# ---------------------------------------------------------------------------

#: 已按清单扫描，确认无可改写对象（实证结论，非「未实现」）。
FORMULA_REWRITE_REASON: Final = "no_mapping_needed"


# ---------------------------------------------------------------------------
# 清单 1：同义两码（soe -> listed），需要改写
# ---------------------------------------------------------------------------

_PAIRS: Final[tuple[RowCodePair, ...]] = (
    RowCodePair(
        soe="BS-111",
        listed="BS-077",
        report_type="balance_sheet",
        row_name="其中：优先股",
        evidence="report_config 四变体实证：soe 侧仅 BS-111 名为「其中：优先股」，"
        "listed 侧仅 BS-077 同名；两侧各恰 1 码且不等",
    ),
    RowCodePair(
        soe="BS-112",
        listed="BS-078",
        report_type="balance_sheet",
        row_name="永续债",
        evidence="report_config 四变体实证：soe 侧仅 BS-112 名为「永续债」，"
        "listed 侧仅 BS-078 同名；两侧各恰 1 码且不等",
    ),
    RowCodePair(
        soe="CFS-038",
        listed="CFS-016",
        report_type="cash_flow_statement",
        row_name="处置子公司及其他营业单位收到的现金净额",
        evidence="report_config 四变体实证：现金流量表投资活动段整段偏移，"
        "该 row_name 在 soe 侧仅 CFS-038、listed 侧仅 CFS-016",
    ),
    RowCodePair(
        soe="IS-055",
        listed="IS-033",
        report_type="income_statement",
        row_name="（一）不能重分类进损益的其他综合收益",
        evidence="report_config 四变体实证：其他综合收益明细段整段偏移 22 位，"
        "该 row_name 在 soe 侧仅 IS-055、listed 侧仅 IS-033",
    ),
    RowCodePair(
        soe="IS-056",
        listed="IS-034",
        report_type="income_statement",
        row_name="1. 重新计量设定受益计划变动额",
        evidence="report_config 四变体实证：其他综合收益明细段整段偏移 22 位，"
        "该 row_name 在 soe 侧仅 IS-056、listed 侧仅 IS-034",
    ),
    RowCodePair(
        soe="IS-057",
        listed="IS-035",
        report_type="income_statement",
        row_name="2. 权益法下不能转损益的其他综合收益",
        evidence="report_config 四变体实证：其他综合收益明细段整段偏移 22 位，"
        "该 row_name 在 soe 侧仅 IS-057、listed 侧仅 IS-035",
    ),
    RowCodePair(
        soe="IS-058",
        listed="IS-036",
        report_type="income_statement",
        row_name="3. 其他权益工具投资公允价值变动",
        evidence="report_config 四变体实证：其他综合收益明细段整段偏移 22 位，"
        "该 row_name 在 soe 侧仅 IS-058、listed 侧仅 IS-036",
    ),
    RowCodePair(
        soe="IS-059",
        listed="IS-037",
        report_type="income_statement",
        row_name="4. 企业自身信用风险公允价值变动",
        evidence="report_config 四变体实证：其他综合收益明细段整段偏移 22 位，"
        "该 row_name 在 soe 侧仅 IS-059、listed 侧仅 IS-037",
    ),
    RowCodePair(
        soe="IS-062",
        listed="IS-039",
        report_type="income_statement",
        row_name="（二）将重分类进损益的其他综合收益",
        evidence="report_config 四变体实证：其他综合收益明细段整段偏移，"
        "该 row_name 在 soe 侧仅 IS-062、listed 侧仅 IS-039",
    ),
    RowCodePair(
        soe="IS-066",
        listed="IS-043",
        report_type="income_statement",
        row_name="4. 其他债权投资信用减值准备",
        evidence="report_config 四变体实证：其他综合收益明细段整段偏移，"
        "该 row_name 在 soe 侧仅 IS-066、listed 侧仅 IS-043",
    ),
    RowCodePair(
        soe="IS-068",
        listed="IS-045",
        report_type="income_statement",
        row_name="6. 外币财务报表折算差额",
        evidence="report_config 四变体实证：其他综合收益明细段整段偏移，"
        "该 row_name 在 soe 侧仅 IS-068、listed 侧仅 IS-045",
    ),
    RowCodePair(
        soe="IS-071",
        listed="IS-048",
        report_type="income_statement",
        row_name="9. 其他",
        evidence="report_config 四变体实证：其他综合收益明细段整段偏移，"
        "该 row_name 在 soe 侧仅 IS-071、listed 侧仅 IS-048",
    ),
)

#: soe_code -> RowCodePair。人工确认后冻结的字面量（Requirement 3.2 禁推导式生成）。
CROSS_VARIANT_ROW_CODE_MAP: Final[dict[str, RowCodePair]] = {p.soe: p for p in _PAIRS}

#: 反向映射（listed_code -> soe_code），由正向反转生成，不手写第二份。
LISTED_TO_SOE_ROW_CODE_MAP: Final[dict[str, str]] = {p.listed: p.soe for p in _PAIRS}


# ---------------------------------------------------------------------------
# 清单 2：禁止作为改写目标的 row_code
# ---------------------------------------------------------------------------

#: 立项初稿曾把这三条当作改写目标，实证证明会把明细行指向另一科目/合计行。
#:
#: 这不是「全部 78 个两侧异名码」的清单 —— 两侧异名本身不构成禁止理由
#: （12 条正确映射的 value 全部两侧异名）。这里只登记**被编造过、必须钉死**的目标码。
ONE_CODE_TWO_MEANINGS_FORBIDDEN: Final[dict[str, ForbiddenTarget]] = {
    "BS-016": ForbiddenTarget(
        soe_row_name="其中：应收股利",
        listed_row_name="一年内到期的非流动资产",
        reason="曾被当作 BS-013 的改写目标；BS-013 两侧同名（稳定码）本不需改写，"
        "改写后 soe 项目的「一年内到期的非流动资产」会指向「其中：应收股利」",
    ),
    "BS-058": ForbiddenTarget(
        soe_row_name="交易性金融负债",
        listed_row_name="其他流动负债",
        reason="曾被当作 BS-053 的改写目标；BS-053 两侧同名（稳定码）本不需改写，"
        "改写后 soe 项目的「其他流动负债」会指向「交易性金融负债」",
    ),
    "BS-059": ForbiddenTarget(
        soe_row_name="衍生金融负债",
        listed_row_name="流动负债合计",
        reason="曾被当作 BS-043 的改写目标；BS-043 两侧同名（稳定码）本不需改写，"
        "改写后会把明细行指向合计行（listed BS-059 = 流动负债合计）",
    ),
}

#: 稳定码（两侧 ``row_name`` 完全相同）=> 出现在 MAP 的 key 或 value 里
#: 即说明映射是编造的。值为登记理由。
#:
#: 这里只登记初稿踩过的三个作为守卫锚点；完整稳定码集合由 opt-in 连库守卫动态求。
STABLE_ROW_CODES_MUST_NOT_BE_MAPPED: Final[dict[str, str]] = {
    "BS-013": "两侧 row_name 均为「一年内到期的非流动资产」，稳定码不需改写；"
    "初稿曾要求改写为 BS-016（soe 侧 = 其中：应收股利）",
    "BS-043": "两侧 row_name 均为「衍生金融负债」，稳定码不需改写；"
    "初稿曾要求改写为 BS-059（listed 侧 = 流动负债合计，明细指向合计行）",
    "BS-053": "两侧 row_name 均为「其他流动负债」，稳定码不需改写；"
    "初稿曾要求改写为 BS-058（soe 侧 = 交易性金融负债）",
}


# ---------------------------------------------------------------------------
# 改写
# ---------------------------------------------------------------------------

#: 匹配 ``ROW('BS-002')`` / ``SUM_ROW('IS-055','IS-062')`` 里的单个引号包裹码。
#: 与 ``report_formula_service`` / ``formula_reverse_index`` 的既有正则同形。
ROW_REF_RE: Final = re.compile(r"(?<=')([A-Z]+-\d+)(?=')")


def is_forbidden_rewrite(row_code: str) -> bool:
    """该 row_code 是否禁止作为改写目标（一码两义）。"""
    return row_code in ONE_CODE_TWO_MEANINGS_FORBIDDEN


def _resolve_map(current_type: str, target_type: str) -> dict[str, str]:
    """按转换方向取「旧码 -> 新码」表；方向相同或非法一律返回空 dict（空操作）。"""
    if current_type == "soe" and target_type == "listed":
        return {p.soe: p.listed for p in _PAIRS}
    if current_type == "listed" and target_type == "soe":
        return {p.listed: p.soe for p in _PAIRS}
    return {}


def rewrite_row_code(row_code: str, current_type: str, target_type: str) -> str:
    """改写单个 row_code；清单未覆盖或命中禁止清单一律**原样返回**（宁缺勿造）。"""
    mapping = _resolve_map(current_type, target_type)
    new = mapping.get(row_code)
    if not new or is_forbidden_rewrite(new):
        return row_code
    return new


def rewrite_row_refs_in_formula(
    formula: str | None,
    current_type: str,
    target_type: str,
) -> tuple[str | None, int]:
    """改写公式中全部 ``ROW('X')`` / ``SUM_ROW('X','Y')`` 引用。

    Returns:
        ``(new_formula, rewritten_count)``。无改动时返回原对象与 0，
        便于调用方判「是否真的发生变更」。
    """
    if not formula:
        return formula, 0
    mapping = _resolve_map(current_type, target_type)
    if not mapping:
        return formula, 0

    count = 0

    def _sub(m: re.Match[str]) -> str:
        nonlocal count
        old = m.group(1)
        new = mapping.get(old)
        if not new or is_forbidden_rewrite(new):
            return old
        count += 1
        return new

    result = ROW_REF_RE.sub(_sub, formula)
    if count == 0:
        return formula, 0
    return result, count
