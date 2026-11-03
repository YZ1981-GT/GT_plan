"""报表合计行生成器的两条约束（spec formula-hub-integrity-closure 任务 18 第一段 A；需求 6.2、6.3；ADR-FHIC-23；N1）。

N1 判定（证据见 tasks.md 任务 18 实施记录）：快照库四套利润表 8 条跨合计行 ``SUM_ROW``（国企 IS-074 / IS-075、上市
IS-051 / IS-052）由 2026-05-13 首版 ``_generate_sum_formula``（同级扫描只在「：」「:」「合计」「小计」处停）经 fill 策略 3
写入；现行生成器对这 8 行输出 None，但仍会把更深缩进的合计行、名字不带合计词的同级合计行收进区间。约束判定在
``app.services.report_total_formula_guard``，由生成器调用：

① 本行已有显式定义（去空白后非空的字符串公式）⇒ 不生成；
② 候选 ``SUM_ROW`` 区间（同表、起 ≤ 行次 ≤ 止）含本行以外的 ``is_total_row`` 行 ⇒ 不生成，warning 追加到调用方的列表；
   ``fill_all_formulas`` 把去重后的 warning 放进返回值 ``warnings`` 并逐条 ``logger.warning``。

用例：生成器直调（①、② 的两种布局、普通区间 / 单子行不回归、种子四套利润表按行名定位、小布局穷举不变式）+
``fill_all_formulas`` 端到端（SQLite 真 ORM，``tests/formula_settings/_env``，生产函数不 mock）。不连库的用例全部非 PG。
"""
from __future__ import annotations

import itertools
import json
import logging
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from app.models.report_models import FinancialReportType, ReportConfig
from app.services.report_formula_service import ReportFormulaService, _generate_sum_formula
from tests.formula_settings._env import STD, make_db

SEED = Path(__file__).resolve().parents[2] / "data" / "report_config_seed.json"
SUM_ROW = re.compile(r"SUM_ROW\('([^']+)','([^']+)'\)")
WARNING = re.compile(r"合计行 (?P<code>[^「 \t]+)「(?P<name>[^」]*)」未自动生成公式：候选 "
                     r"SUM_ROW\('(?P<a>[^']+)','(?P<b>[^']+)'\) 的区间含其他合计行 (?P<crossed>[^ \t]+)")
#: 四套利润表的归属行（按种子行名定位，种子行次与真库不同）
ATTRIBUTION_NAMES = {
    "soe_consolidated": ("归属于母公司所有者的综合收益总额", "*归属于少数股东的综合收益总额"),
    "soe_standalone": ("归属于母公司所有者的综合收益总额", "*归属于少数股东的综合收益总额"),
    "listed_consolidated": ("归属于母公司股东的综合收益总额", "归属于少数股东的综合收益总额"),
    "listed_standalone": ("归属于母公司股东的综合收益总额", "归属于少数股东的综合收益总额"),
}


def _row(code: str, name: str, indent: int, total: bool = False, formula: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(row_code=code, row_name=name, indent_level=indent, is_total_row=total, formula=formula)


def _totals_in(rows: list, first: str, last: str, me: str) -> list[str]:
    """测试内独立写的区间口径：first ≤ 行次 ≤ last（字符串比较）、本行以外、is_total_row 为真。"""
    return [r.row_code for r in rows if first <= r.row_code <= last and r.row_code != me and r.is_total_row]


# ─── ① 已有显式定义 ⇒ 生成器不生成 ─────────────────────────────────────────────


@pytest.mark.parametrize(("formula", "expected"), [
    ("ROW('X-001')+ROW('X-002')", None),
    (None, "SUM_ROW('X-001','X-002')"),
    ("", "SUM_ROW('X-001','X-002')"),
    ("   ", "SUM_ROW('X-001','X-002')"),
], ids=["explicit", "none", "empty", "blank"])
def test_explicit_definition_is_kept_by_generator(formula, expected):
    rows = [_row("X-001", "项目甲", 1), _row("X-002", "项目乙", 1), _row("X-003", "合计", 0, True, formula)]
    warnings: list[str] = []
    assert _generate_sum_formula(rows, 2, warnings) == expected
    assert warnings == []


# ─── ② 候选区间含其他合计行 ⇒ 不生成 + warning ─────────────────────────────────────


def test_child_range_with_nested_total_is_blocked_with_warning():
    """更深缩进的子行里有一条「小计」合计行：候选区间 X-001..X-003 含它。"""
    rows = [_row("X-001", "项目甲", 1), _row("X-002", "小计", 1, True), _row("X-003", "项目乙", 1),
            _row("X-004", "合计", 0, True)]
    warnings: list[str] = []
    assert _generate_sum_formula(rows, 3, warnings) is None
    assert warnings == ["合计行 X-004「合计」未自动生成公式：候选 SUM_ROW('X-001','X-003') 的区间含其他合计行 X-002"]
    assert _generate_sum_formula(rows, 3) is None, "不给 warning 列表时同样不生成"


def test_same_level_range_with_unlabelled_total_is_blocked_with_warning():
    """同级扫描只在名字带合计词 / 冒号处停：名字不带合计词的同级合计行（净利润）会被收进区间。"""
    rows = [_row("X-001", "一、营业利润", 0), _row("X-002", "二、净利润", 0, True), _row("X-003", "三、其他", 0),
            _row("X-004", "四、收益总额", 0, True)]
    warnings: list[str] = []
    assert _generate_sum_formula(rows, 3, warnings) is None
    assert warnings == ["合计行 X-004「四、收益总额」未自动生成公式：候选 SUM_ROW('X-001','X-003') 的区间含其他合计行 X-002"]


# ─── 普通区间照常生成（不回归）──────────────────────────────────────────────────


def test_plain_ranges_still_generated():
    warnings: list[str] = []
    children = [_row("X-001", "项目甲", 1), _row("X-002", "项目乙", 1), _row("X-003", "项目丙", 1),
                _row("X-004", "合计", 0, True)]
    assert _generate_sum_formula(children, 3, warnings) == "SUM_ROW('X-001','X-003')"
    single = [_row("X-001", "项目甲", 1), _row("X-002", "合计", 0, True)]
    assert _generate_sum_formula(single, 1, warnings) == "ROW('X-001')"
    # 区间外紧邻的合计行（同级扫描在「流动资产合计」处停）不挡生成
    outside = [_row("X-001", "流动资产合计", 0, True), _row("X-002", "项目甲", 0), _row("X-003", "项目乙", 0),
               _row("X-004", "资产合计", 0, True)]
    assert _generate_sum_formula(outside, 3, warnings) == "SUM_ROW('X-002','X-003')"
    assert warnings == []


def test_seed_income_statements_never_get_cross_total_sum_row():
    """种子四套利润表（公式全部置空模拟首次填充）：生成器产出的 SUM_ROW 不含其他合计行；8 条归属行（按行名定位）不生成。"""
    seed = json.loads(SEED.read_text(encoding="utf-8-sig"))
    blocks = {b["applicable_standard"]: b["rows"] for b in seed
              if b.get("report_type") == "income_statement" and b.get("applicable_standard") in ATTRIBUTION_NAMES}
    assert sorted(blocks) == sorted(ATTRIBUTION_NAMES)
    for std, names in ATTRIBUTION_NAMES.items():
        rows = [_row(r["row_code"], r["row_name"], r.get("indent_level", 0), bool(r.get("is_total_row")))
                for r in blocks[std]]
        attribution = [i for i, r in enumerate(rows) if r.row_name in names]
        assert sorted(rows[i].row_name for i in attribution) == sorted(names), f"{std} 按行名没定位到两条归属行"
        assert all(rows[i].is_total_row for i in attribution), f"{std} 归属行在种子里不是合计行"
        bad = []
        for idx, row in enumerate(rows):
            got = _generate_sum_formula(rows, idx, [])
            for a, b in SUM_ROW.findall(got or ""):
                if _totals_in(rows, a, b, row.row_code):
                    bad.append(f"{row.row_code}「{row.row_name}」→ {got}")
        assert bad == [], f"{std}：生成器产出跨合计行区间 {bad}"
        assert [_generate_sum_formula(rows, i, []) for i in attribution] == [None, None], std


# ─── 小布局穷举：返回的 SUM_ROW 永不含其他合计行；warning 与候选区间一致 ─────────────


_KINDS = [(indent, total, name) for indent in (0, 1) for total in (False, True) for name in ("项目", "小计", "分类：")]


def _layouts(max_rows: int = 3):
    for n in range(1, max_rows + 1):
        for combo in itertools.product(_KINDS, repeat=n):
            for current_indent in (0, 1):
                rows = [_row(f"X-{i + 1:03d}", name.replace("：", f"{i + 1}：") if name.endswith("：")
                             else f"{name}{i + 1}", indent, total) for i, (indent, total, name) in enumerate(combo)]
                rows.append(_row(f"X-{n + 1:03d}", "合计", current_indent, True))
                yield rows


def test_exhaustive_small_layouts_invariant():
    """**Validates: Requirements 6.2, 6.3** —— 1~3 条前置行 × 缩进 / 合计标记 / 名字三种（12 种）× 本行两种缩进，全部穷举。"""
    generated = blocked = 0
    violations: list[str] = []
    for rows in _layouts():
        me = rows[-1].row_code
        warnings: list[str] = []
        got = _generate_sum_formula(rows, len(rows) - 1, warnings)
        shape = [(r.indent_level, r.is_total_row, r.row_name) for r in rows]
        for a, b in SUM_ROW.findall(got or ""):
            generated += 1
            if _totals_in(rows, a, b, me) or warnings:
                violations.append(f"{shape} → {got}（区间含合计行 {_totals_in(rows, a, b, me)}，warning {warnings}）")
        if warnings:
            blocked += 1
            parsed = WARNING.fullmatch(warnings[0]) if len(warnings) == 1 else None
            if got is not None or parsed is None or parsed["code"] != me or \
                    parsed["crossed"].split("、") != _totals_in(rows, parsed["a"], parsed["b"], me):
                violations.append(f"{shape} → {got}，warning 与候选区间不一致：{warnings}")
    assert violations == [], f"{len(violations)} 个布局违反不变式，前 5 个：{violations[:5]}"
    assert generated > 0 and blocked > 0, f"穷举空转：生成 SUM_ROW {generated} 次、拦下 {blocked} 次"


# ─── fill_all_formulas 端到端（SQLite 真 ORM）──────────────────────────────────────


IS = FinancialReportType.income_statement
EXPLICIT_REVENUE = "TB('6001','本期发生额')"  # 特殊表给的是 +TB('6051')；显式定义不能被它覆盖
WORLD = [  # (行次, 行名, 缩进, 合计行, 公式)
    ("IS-901", "一、营业收入", 0, False, EXPLICIT_REVENUE),
    ("IS-910", "项目甲", 1, False, None),
    ("IS-911", "小计", 1, True, "ROW('IS-910')"),
    ("IS-912", "项目乙", 1, False, None),
    ("IS-913", "合计", 0, True, None),
    ("IS-920", "项目丙", 1, False, None),
    ("IS-921", "项目丁", 1, False, None),
    ("IS-922", "收入合计", 0, True, None),
]
BLOCKED = "合计行 IS-913「合计」未自动生成公式：候选 SUM_ROW('IS-910','IS-912') 的区间含其他合计行 IS-911"
LOGGER = "app.services.report_formula_service"


async def _formulas(factory) -> dict[str, str | None]:
    async with factory() as db:
        rows = (await db.execute(sa.select(ReportConfig.row_code, ReportConfig.formula).where(
            ReportConfig.applicable_standard == STD))).all()
    return dict(rows)


async def test_fill_all_formulas_applies_both_constraints(caplog):
    async with make_db() as factory:
        async with factory() as db:
            for number, (code, name, indent, total, formula) in enumerate(WORLD, 1):
                db.add(ReportConfig(report_type=IS, row_code=code, row_name=name, row_number=number,
                                    indent_level=indent, is_total_row=total, formula=formula,
                                    formula_category="auto_calc", applicable_standard=STD, formula_version=1))
            await db.commit()
        with caplog.at_level(logging.WARNING, logger=LOGGER):
            async with factory() as db:
                stats = await ReportFormulaService().fill_all_formulas(db, standard=STD)
                await db.commit()
        after = await _formulas(factory)
        assert after["IS-901"] == EXPLICIT_REVENUE, "约束①：显式定义被覆盖"
        assert after["IS-911"] == "ROW('IS-910')", "约束①：显式定义的小计行被覆盖"
        assert after["IS-913"] is None, f"约束②：区间含合计行 IS-911 却写了 {after['IS-913']!r}"
        assert stats["warnings"] == [BLOCKED]
        assert after["IS-922"] == "SUM_ROW('IS-920','IS-921')", "普通合计行应照常生成"
        assert (stats["updated"], stats["skipped"]) == (1, 2)
        logged = [r.getMessage() for r in caplog.records if r.name == LOGGER and r.levelno == logging.WARNING]
        assert logged == [f"fill_all_formulas: {BLOCKED}"]
        async with factory() as db:
            again = await ReportFormulaService().fill_all_formulas(db, standard=STD)
        assert (again["updated"], again["warnings"]) == (0, [BLOCKED]), "幂等：再跑一次只剩同一条 warning"
