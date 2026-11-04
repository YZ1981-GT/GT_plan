"""报表合计行 / 取错科目的明细行修正（真源 ``app.services.report_total_formulas``）的守卫。

出事的形态：合计行公式按行名套 CAS 模板，行号却是 CAS 自己的 ⇒ 国企「资产总计 = 应收款项融资 + 应收资金集中管理款」，
SUM_ROW 区间求和把「其中：」子项一起加；明细行「其他非流动负债」与「递延所得税负债」同取 2901。

纯函数部分不连库；「引用的行真的存在、不是标题行也不是其中子项」要按库里 report_config 判（行号体系以库为准，
``data/report_config_seed.json`` 的编号与库不同，不能拿来判）。
"""
from __future__ import annotations

import ast
import asyncio
import json
import re
from pathlib import Path

import pytest

from app.services import report_formula_service as svc
from app.services.report_total_formulas import (
    FIXES,
    INVENTORY_FORMULA,
    STANDALONE_OVERRIDES,
    STANDARD_FAMILY,
    fix_for,
    fixes_for,
)
from tests._pg_shared_engine import run_and_dispose

_ROW_REF = re.compile(r"(?<!SUM_)ROW\('([A-Z]+-\d+)'\)")
_TB_REF = re.compile(r"TB\('([^']+)'")
_SVC_SRC = Path(svc.__file__).read_text(encoding="utf-8")


def _all_entries():
    for table in (FIXES, STANDALONE_OVERRIDES):
        for family, slots in table.items():
            for slot, (prefix, formula, desc) in slots.items():
                yield family, slot, prefix, formula, desc


# ─── 纯函数 ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("family", "slot", "prefix", "formula", "desc"), list(_all_entries()))
def test_entry_shape(family, slot, prefix, formula, desc):
    assert slot.split(":", 1)[0] in {"balance_sheet", "income_statement"}, slot
    assert prefix.strip() and desc.strip(), f"{family} {slot} 缺行名前缀或说明"
    if formula is None:
        return
    assert "SUM_ROW" not in formula, f"{slot}：区间求和会把「其中」子项一起加，必须逐行列出"
    rows = _ROW_REF.findall(formula)
    dup = sorted({r for r in rows if rows.count(r) > 1})
    assert not dup, f"{family} {slot} 同一行引用了两次（双算）：{dup}"
    report_code = slot.split(":", 1)[1]
    assert report_code not in rows, f"{slot} 引用了自己"
    codes = _TB_REF.findall(formula)
    dup_codes = sorted({c for c in codes if codes.count(c) > 1})
    assert not dup_codes, f"{family} {slot} 同一科目取了两次：{dup_codes}"


_CHART = {a["code"]: a for a in json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "standard_account_chart.json").read_text(encoding="utf-8-sig")
)["accounts"]}


@pytest.mark.parametrize(("family", "slot", "prefix", "formula", "desc"), list(_all_entries()))
def test_tb_codes_exist_in_standard_chart(family, slot, prefix, formula, desc):
    """公式取的科目必须在平台标准科目表里（试算表按标准科目编码汇总）。原权益公式取 4001 / 4002 / 4104，
    而这张表的 4001 是生产成本、4002 / 4104 根本没有 ⇒ 实收资本取到生产成本、资本公积恒空。"""
    missing = [c for c in _TB_REF.findall(formula or "") if c not in _CHART]
    assert not missing, f"{family} {slot} 取的科目不在标准科目表里：{missing}"


@pytest.mark.parametrize(("family", "slot", "prefix", "formula", "desc"), list(_all_entries()))
def test_equity_rows_take_equity_accounts(family, slot, prefix, formula, desc):
    """资产负债表权益行（实收资本 ~ 未分配利润）只能取权益类科目。"""
    if not slot.startswith("balance_sheet:") or formula is None:
        return
    if not any(prefix.endswith(k) for k in ("实收资本", "股本", "资本公积", "其他权益工具", "盈余公积", "未分配利润")):
        return
    wrong = [f"{c}={_CHART[c]['name']}" for c in _TB_REF.findall(formula) if _CHART.get(c, {}).get("category") != "equity"]
    assert not wrong, f"{family} {slot}（{prefix}）取了非权益类科目：{wrong}"


def test_every_standard_has_a_family():
    assert set(STANDARD_FAMILY.values()) == set(FIXES)
    assert set(STANDARD_FAMILY) == {"soe_standalone", "soe_consolidated", "listed_standalone", "listed_consolidated"}


def test_fix_for_checks_row_name_prefix():
    assert fix_for("soe_standalone", "balance_sheet", "BS-053", "资产总计") == (
        True, "ROW('BS-027') + ROW('BS-052')")
    # 行名对不上（另一套行号体系）⇒ 不套用
    assert fix_for("soe_standalone", "balance_sheet", "BS-053", "其他应付款") == (False, None)
    # 有意置空的行：命中、公式为空
    assert fix_for("soe_standalone", "balance_sheet", "BS-097", "其他非流动负债") == (True, None)
    assert fix_for("unknown_standard", "balance_sheet", "BS-053", "资产总计") == (False, None)


@pytest.mark.parametrize(("standard", "slot"), [
    ("soe_standalone", "balance_sheet:BS-125"), ("listed_standalone", "balance_sheet:BS-084"),
])
def test_standalone_retained_earnings_include_unclosed_pl(standard, slot):
    """单体未分配利润含未结转损益（SAP 账套不结转、损益类调整不联动 3104 / 3201 ⇒ 不含则资产负债表差本年利润）；
    合并准则不含（合并试算表 resolver 没有这个口径）。spec citar-audited-balance-and-workpaper-coverage R1。"""
    assert fixes_for(standard)[slot][1].endswith("+PL_UNCLOSED()")
    consolidated = standard.replace("_standalone", "_consolidated")
    assert "PL_UNCLOSED" not in (fixes_for(consolidated)[slot][1] or "")
    assert fix_for(standard, "balance_sheet", slot.split(":")[1], "未分配利润")[1].endswith("+PL_UNCLOSED()")


def test_pl_unclosed_is_registered_function():
    """新函数必须在 L1 白名单里，否则保存 / 发布按「未注册函数」拦截（blocked）。"""
    from app.services.formula_engine import _REGISTRY

    assert "PL_UNCLOSED" in _REGISTRY.known_function_names()


def test_balance_identity_rows_present():
    """两边总计都要有公式，否则资产负债表对不平也看不出来。"""
    soe = FIXES["soe"]
    assert soe["balance_sheet:BS-053"][1] == "ROW('BS-027') + ROW('BS-052')"
    assert soe["balance_sheet:BS-100"][1] == "ROW('BS-082') + ROW('BS-099')"
    listed = FIXES["listed"]
    assert listed["balance_sheet:BS-042"][1] == "ROW('BS-018') + ROW('BS-041')"
    assert listed["balance_sheet:BS-088"][1] == "ROW('BS-073') + ROW('BS-087')"


def _dict_literal(name: str) -> dict:
    tree = ast.parse(_SVC_SRC)
    for node in tree.body:
        target = node.target if isinstance(node, ast.AnnAssign) else (
            node.targets[0] if isinstance(node, ast.Assign) else None)
        if isinstance(target, ast.Name) and target.id == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} 找不到")


def test_filler_inventory_matches_source_of_truth():
    """按名填充表的「存货」与真源逐字一致（不再是 SUM_TB(1400~1499)：把两个贷方备抵当正数加）。"""
    assert _dict_literal("_BS_SPECIAL")["存货"] == INVENTORY_FORMULA


@pytest.mark.parametrize("name", ["其他非流动负债", "利息费用", "利息收入", "汇兑收益", "基本每股收益",
                                  "稀释每股收益", "以摊余成本计量的金融资产终止确认收益"])
def test_wrong_detail_entries_removed(name):
    for table in ("_BS_SPECIAL", "_IS_SPECIAL", "_NAME_TO_ACCOUNT"):
        assert name not in _dict_literal(table), f"{table} 里还有「{name}」（取错科目）"


def test_is_special_has_no_total_income_by_tax():
    """「综合收益总额」原取 6801 所得税费用；利润表侧改由合计行公式给出。"""
    assert "综合收益总额" not in _dict_literal("_IS_SPECIAL")


def _fill_body() -> str:
    tree = ast.parse(_SVC_SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "fill_all_formulas":
            return ast.get_source_segment(_SVC_SRC, node) or ""
    raise AssertionError("fill_all_formulas 找不到")


def test_filler_consults_total_fix_first():
    body = _fill_body()
    fix_at, special_at = body.find("_total_fix_for("), body.find("_get_special(")
    assert fix_at >= 0, "fill_all_formulas 没有查合计行真源"
    assert special_at > fix_at, "合计行真源必须在按名特殊公式之前查"


def test_filler_skips_cas_row_references():
    """CAS 模板公式里的 ROW() 行号是 CAS 自己的，套到别的模板上指向不相干的行。"""
    body = _fill_body()
    assert '"ROW(" not in' in body, "fill_all_formulas 仍会套用含 ROW() 的 CAS 公式"


# ─── 真库：引用的行在各准则下真的是本层项目 ───────────────────────────────


async def _load_rows():
    import sqlalchemy as sa

    from app.core.database import async_session

    async with async_session() as db:
        rows = (await db.execute(sa.text(
            # 项目层的行 applicable_standard = 'project:<id>'，这里只取四个准则的全局行
            "SELECT applicable_standard, report_type::text, row_code, row_name FROM report_config "
            "WHERE applicable_standard = ANY(:stds) AND is_deleted = false "
            "AND report_type::text IN ('balance_sheet','income_statement')"
        ), {"stds": sorted(STANDARD_FAMILY)})).fetchall()
    return {(s, rt, rc): (name or "").strip() for s, rt, rc, name in rows}


try:
    _ROWS = asyncio.run(run_and_dispose(_load_rows()))
    _DB_REASON = "" if _ROWS else "report_config 全局行为空"
except Exception as exc:  # noqa: BLE001 - 连不上库就跳过真库用例
    _ROWS, _DB_REASON = {}, f"无法连库：{exc}"

_needs_db = pytest.mark.skipif(not _ROWS, reason=_DB_REASON)


def _directly_below(ref: str, total: str) -> bool:
    prefix, _, num = ref.rpartition("-")
    return f"{prefix}-{int(num) - 1:03d}" == total


def test_directly_below():
    assert _directly_below("IS-002", "IS-001")
    assert not _directly_below("BS-016", "BS-027")


@_needs_db
@pytest.mark.parametrize("standard", sorted(STANDARD_FAMILY))
def test_db_targets_and_references(standard):
    problems = []
    for slot, (prefix, formula, _desc) in fixes_for(standard).items():
        report_type, code = slot.split(":", 1)
        name = _ROWS.get((standard, report_type, code))
        if name is None or not name.startswith(prefix):
            problems.append(f"{slot} 行名 {name!r} 不以 {prefix!r} 开头")
            continue
        for ref in _ROW_REF.findall(formula or ""):
            ref_name = _ROWS.get((standard, report_type, ref))
            if ref_name is None:
                problems.append(f"{slot} 引用的 {ref} 不存在")
            elif ref_name.endswith(("：", ":")):
                problems.append(f"{slot} 引用了标题行 {ref}「{ref_name}」")
            elif ref_name.startswith(("其中", "#其中")) and not _directly_below(ref, code):
                # 「其中」紧跟在本合计行下面 = 列明构成（国企「营业总收入 / 其中：营业收入 / △利息收入…」）；
                # 跟在明细行下面 = 该明细的子集（「其他应收款 / 其中：应收股利」），加进合计就双算
                problems.append(f"{slot} 引用了「其中」子项 {ref}「{ref_name}」（与父项双算）")
    assert not problems, f"{standard}：\n" + "\n".join(problems)
