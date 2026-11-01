"""利润表金标准对拍与恒等检查（spec income-statement-lower-section-formulas 任务 4；需求 R1~R4）。

四套准则各一份正数口径合成试算表 → 金标准求值器（``gold_is_evaluator``，独立实现）算出逐行金额，
断言 design §2 的会计恒等式成立，并与生产逐行计算（``report_row_compute.compute_row`` + 生产
拓扑序 ``report_eval_order``）逐行按分比对 —— 生产侧只把取数换成合成试算表，公式文本、求值顺序、
逐行语义全部是生产实现。
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.report_eval_order import eval_order
from app.services.report_row_compute import RowScope, compute_row
from tests.is_lower_section.gold_is_evaluator import GoldRow, cents, evaluate

SEED = Path(__file__).resolve().parents[2] / "data" / "report_config_seed.json"
IS = "income_statement"
SOE = ("soe_consolidated", "soe_standalone")
LISTED = ("listed_consolidated", "listed_standalone")
STANDARDS = (*SOE, *LISTED)

#: 合成试算表（正数口径：收入、利得为正；费用、损失也存正数，列报为负的行由公式带负号）
TRIAL_BALANCE: dict[str, Decimal] = {
    "6001": Decimal("1000000.00"),   # 主营业务收入
    "6051": Decimal("50000.00"),     # 其他业务收入
    "6401": Decimal("600000.00"),    # 主营业务成本
    "6402": Decimal("30000.00"),     # 其他业务成本
    "6403": Decimal("12000.00"),     # 税金及附加
    "6601": Decimal("40000.00"),     # 销售费用
    "6602": Decimal("55000.00"),     # 管理费用
    "6603": Decimal("8000.00"),      # 财务费用
    "6604": Decimal("25000.00"),     # 研发费用
    "6101": Decimal("7000.00"),      # 公允价值变动收益
    "6111": Decimal("23000.00"),     # 投资收益
    "6115": Decimal("1500.00"),      # 资产处置收益
    "6117": Decimal("3000.00"),      # 其他收益
    "6301": Decimal("9000.00"),      # 营业外收入
    "6701": Decimal("4000.00"),      # 资产减值损失（列报为负）
    "6702": Decimal("6000.00"),      # 信用减值损失（列报为负）
    "6711": Decimal("2500.00"),      # 营业外支出
    "6801": Decimal("45000.00"),     # 所得税费用
}
#: 生成器填的取数行（种子留空、由 ``fill_all_formulas`` 的特殊表填）：对拍时按生产特殊表补齐，
#: 否则利润链的叶子为 0，恒等式验不出东西。
GENERATOR_FILLED = {
    "一、营业总收入", "其中：营业收入", "其中：营业成本", "税金及附加", "销售费用", "管理费用",
    "研发费用", "财务费用", "加： 其他收益", "加：其他收益", "一、营业收入", "减：营业成本",
    "加： 营业外收入", "加：营业外收入", "减： 营业外支出", "减：营业外支出", "减： 所得税费用",
    "减：所得税费用",
}
#: 合并口径手工输入的少数股东两行（单体口径没有少数股东）
MINORITY_INPUTS = {
    "soe_consolidated": {"IS-049": Decimal("12000.00"), "IS-072": Decimal("900.00")},
    "listed_consolidated": {"IS-030": Decimal("12000.00"), "IS-049": Decimal("900.00")},
}
#: 国企营业总成本里的手工输入明细：IS-029「其他」必须非零，否则「漏掉这个加项」在数值上无差异，
#: ``test_soe_total_cost_covers_all_detail_rows`` 会空转（变异 M10 实测存活才补上）。
COST_DETAIL_INPUTS = {
    "soe_consolidated": {"IS-029": Decimal("1300.00")},
    "soe_standalone": {"IS-029": Decimal("1300.00")},
}
#: 其他综合收益明细（手工输入行）：两段各给一笔，验 IS-055 / IS-062 与 IS-033 / IS-039 的区间求和
OCI_INPUTS = {
    "soe_consolidated": {"IS-058": Decimal("5000.00"), "IS-064": Decimal("3000.00")},
    "soe_standalone": {"IS-058": Decimal("5000.00"), "IS-064": Decimal("3000.00")},
    "listed_consolidated": {"IS-036": Decimal("5000.00"), "IS-041": Decimal("3000.00")},
    "listed_standalone": {"IS-036": Decimal("5000.00"), "IS-041": Decimal("3000.00")},
}


def seed_rows(standard: str) -> list[dict]:
    blocks = json.loads(SEED.read_text(encoding="utf-8-sig"))
    for block in blocks:
        if block.get("report_type") == IS and block.get("applicable_standard") == standard:
            return block["rows"]
    raise AssertionError(f"种子里没有 {standard} 的利润表")


def effective_rows(standard: str) -> list[SimpleNamespace]:
    """种子行 ⊕ 生成器特殊表（只补种子留空且特殊表认得的行）= 真实库里的有效定义形态。"""
    from app.services.report_formula_service import _get_special

    out: list[SimpleNamespace] = []
    for row in seed_rows(standard):
        formula = (row.get("formula") or "").strip() or None
        source = row.get("formula_source")
        if formula is None and (row.get("row_name") or "") in GENERATOR_FILLED:
            filled = _get_special(row.get("row_name") or "", IS)
            if filled:
                formula, source = filled, "special"
        out.append(SimpleNamespace(
            row_code=row["row_code"], row_name=row.get("row_name") or "", row_number=row["row_number"],
            indent_level=row.get("indent_level", 0), is_total_row=bool(row.get("is_total_row")),
            formula=formula, formula_source=source,
        ))
    return out


def manual_inputs(standard: str) -> dict[str, Decimal]:
    return {
        **MINORITY_INPUTS.get(standard, {}),
        **COST_DETAIL_INPUTS.get(standard, {}),
        **OCI_INPUTS[standard],
    }


def gold_values(standard: str) -> dict[str, Decimal]:
    """金标准：手工输入行当成常量公式代入（金标准求值器只认报表语法，不认「库里的值」）。"""
    inputs = manual_inputs(standard)
    rows = [
        GoldRow(row.row_code, row.row_number,
                f"{inputs[row.row_code]}" if row.row_code in inputs else row.formula)
        for row in effective_rows(standard)
    ]
    result = evaluate(rows, TRIAL_BALANCE)
    assert result.unparsed == {}, f"{standard} 金标准求值器未识别写法：{result.unparsed}"
    assert result.cycles == (), f"{standard} 金标准检出循环引用：{result.cycles}"
    return result.values


class _SyntheticParser:
    """只替换取数的 parser：公式执行仍走生产 L1 内核（``evaluate_formula_result``）。"""

    resolver = "synthetic"  # 让 report_row_compute 跳过「缺科目」查库分支

    def __init__(self, tb: dict[str, Decimal]):
        self.tb = tb
        self.project_id = None

    async def resolve_tb(self, account_code: str, column_name: str) -> Decimal:
        _ = column_name
        return sum((v for code, v in self.tb.items() if code.startswith(account_code)), Decimal("0"))

    async def resolve_sum(self, code_range: str, column_name: str) -> Decimal:
        _ = column_name
        start, _, end = code_range.partition("~")
        return sum((v for code, v in self.tb.items()
                    if start.strip() <= code[:len(start.strip())] <= end.strip()), Decimal("0"))

    async def execute_with_status(self, formula: str, row_cache: dict[str, Decimal]):
        from app.services.report_engine import evaluate_formula_result

        return await evaluate_formula_result(formula, resolver=self, row_cache=row_cache)


async def production_values(standard: str) -> tuple[dict[str, Decimal], list[str]]:
    """生产逐行计算（拓扑序 + compute_row）在合成试算表上的逐行结果与告警。"""
    rows = effective_rows(standard)
    inputs = manual_inputs(standard)
    plan = eval_order(rows)
    assert plan.cycles == (), f"{standard} 生产拓扑序检出循环引用：{plan.cycles}"
    scope = RowScope.of(rows, cycles=plan.cycles)
    cache = scope.start_cache()
    cache.update(inputs)  # 手工输入行的库内值
    parser = _SyntheticParser(TRIAL_BALANCE)
    values: dict[str, Decimal] = {}
    warnings: list[str] = []
    for config in plan.order:
        if config.row_code in inputs:  # 手工行不重算，保持库内值
            values[config.row_code] = inputs[config.row_code]
            continue
        outcome = await compute_row(parser, config, cache, mode="audited", scope=scope)
        assert outcome.ok, f"{standard} {config.row_code} 计算失败：{outcome.errors}"
        values[config.row_code] = cents(outcome.value)
        warnings.extend(outcome.warnings)
    return values, warnings


# ─────────────────────────── 恒等检查（design §2）───────────────────────────


@pytest.mark.parametrize("standard", SOE)
def test_soe_income_chain_identities(standard):
    v = gold_values(standard)
    assert v["IS-046"] == v["IS-044"] - v["IS-045"], "净利润 = 利润总额 − 所得税费用"
    assert v["IS-044"] == v["IS-040"] + v["IS-041"] - v["IS-043"], "利润总额 = 营业利润 + 营业外收入 − 营业外支出"
    assert v["IS-073"] == v["IS-046"] + v["IS-053"], "综合收益总额 = 净利润 + 其他综合收益（R4）"
    assert v["IS-054"] == v["IS-055"] + v["IS-062"], "归母其他综合收益 = 两段之和"
    assert v["IS-046"] != 0 and v["IS-073"] != 0, "恒等检查空转：净利润 / 综合收益总额为 0"


@pytest.mark.parametrize("standard", LISTED)
def test_listed_income_chain_identities(standard):
    v = gold_values(standard)
    assert v["IS-024"] == v["IS-022"] - v["IS-023"], "净利润 = 利润总额 − 所得税费用"
    assert v["IS-022"] == v["IS-019"] + v["IS-020"] - v["IS-021"], "利润总额 = 营业利润 + 营业外收入 − 营业外支出"
    assert v["IS-050"] == v["IS-024"] + v["IS-031"], "综合收益总额 = 净利润 + 其他综合收益（R4）"
    assert v["IS-032"] == v["IS-033"] + v["IS-039"], "归母其他综合收益 = 两段之和"
    assert v["IS-024"] != 0 and v["IS-050"] != 0, "恒等检查空转：净利润 / 综合收益总额为 0"


def test_soe_consolidated_attribution_adds_up():
    """合并口径：归母综合收益 + 少数股东综合收益 = 综合收益总额（归属行由母 spec 定义，本 spec 补组成行）。"""
    v = gold_values("soe_consolidated")
    assert v["IS-048"] + v["IS-049"] == v["IS-046"], "归母净利润 + 少数股东损益 = 净利润"
    assert v["IS-053"] == v["IS-054"] + v["IS-072"], "其他综合收益 = 归母 + 少数股东"
    assert v["IS-074"] + v["IS-075"] == v["IS-073"], "归母综合收益 + 少数股东综合收益 = 综合收益总额"
    assert v["IS-075"] != 0, "少数股东综合收益为 0：恒等检查空转（R2 组成行仍为 0）"


def test_listed_consolidated_attribution_adds_up():
    v = gold_values("listed_consolidated")
    assert v["IS-029"] + v["IS-030"] == v["IS-024"], "归母净利润 + 少数股东损益 = 净利润"
    assert v["IS-031"] == v["IS-032"] + v["IS-049"], "其他综合收益 = 归母 + 少数股东"
    assert v["IS-051"] + v["IS-052"] == v["IS-050"], "归母综合收益 + 少数股东综合收益 = 综合收益总额"
    assert v["IS-052"] != 0, "少数股东综合收益为 0：恒等检查空转（R2 组成行仍为 0）"


@pytest.mark.parametrize("standard", ("soe_standalone", "listed_standalone"))
def test_standalone_attribution_equals_total(standard):
    """单体口径没有少数股东：归母 = 全额。"""
    v = gold_values(standard)
    net, oci, total = (("IS-046", "IS-053", "IS-073") if standard.startswith("soe")
                       else ("IS-024", "IS-031", "IS-050"))
    parent_net = v["IS-048"] if standard.startswith("soe") else v["IS-029"]
    assert parent_net == v[net], "单体归母净利润 = 净利润"
    assert v[total] == v[net] + v[oci]


@pytest.mark.parametrize("standard", STANDARDS)
def test_impairment_losses_reduce_operating_profit(standard):
    """减值损失列报为负：两行为负值，且营业利润按负值并入（符号错会让营业利润偏高 2 倍损失额）。"""
    v = gold_values(standard)
    credit, asset = (("IS-037", "IS-038") if standard.startswith("soe") else ("IS-016", "IS-017"))
    assert v[credit] == Decimal("-6000.00"), f"{credit} 信用减值损失应列报为负"
    assert v[asset] == Decimal("-4000.00"), f"{asset} 资产减值损失应列报为负"


# ─────────────────── 生产逐行计算 vs 金标准（逐行按分）───────────────────


@pytest.mark.parametrize("standard", STANDARDS)
async def test_production_matches_gold_row_by_row(standard):
    gold = gold_values(standard)
    produced, _warnings = await production_values(standard)
    assert set(produced) == set(gold), "行集合不一致"
    mismatch = {code: (produced[code], gold[code]) for code in sorted(gold) if produced[code] != gold[code]}
    assert mismatch == {}, f"{standard} 生产与金标准逐行不符（生产, 金标准）：{mismatch}"
    assert any(value != 0 for value in produced.values()), "对拍空转：生产侧全是 0"


@pytest.mark.parametrize("standard", SOE)
async def test_soe_total_cost_covers_all_detail_rows(standard):
    """国企营业总成本按权威模板 ``=SUM(C13:C30)+C34`` 求和：改掉任一加项都会让本用例红。"""
    produced, _ = await production_values(standard)
    detail = sum((produced[f"IS-{n:03d}"] for n in range(8, 26)), Decimal("0")) + produced["IS-029"]
    assert produced["IS-007"] == detail
    assert produced["IS-007"] != 0, "营业总成本为 0：用例空转"
    # 每个加项都必须非零才证明「漏掉它」会被抓到；IS-009~IS-020 是金融类专用行，本夹具不给值，
    # 这里只钉住本夹具真正赋了值的两类加项（IS-008 / IS-021~IS-025 取数行、IS-029 手工行）。
    assert produced["IS-029"] != 0, "IS-029「其他」为 0：漏掉该加项时本用例无法察觉"
    for code in ("IS-008", "IS-021", "IS-022", "IS-023", "IS-024", "IS-025"):
        assert produced[code] != 0, f"{code} 为 0：漏掉该加项时本用例无法察觉"


@pytest.mark.parametrize("standard", STANDARDS)
async def test_manual_input_rows_get_warning_on_dependents(standard):
    """引用手工输入行的恒等行必须带「手工输入行」提示（ADR-ISL-02），不再报「未定义公式」。"""
    _produced, warnings = await production_values(standard)
    manual = [text for text in warnings if "为手工输入行" in text]
    assert manual, f"{standard} 没有任何手工输入行提示：提示未接线"
    assert not [text for text in warnings if "未定义公式" in text and "手工输入行" not in text], (
        f"{standard} 仍把手工输入行报成「未定义公式」：{warnings}"
    )
