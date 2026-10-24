"""底稿求值器的「本期发生额」与未注册列名（spec formula-fetch-followup-defect-closure R7）。

修复前：``_COLUMN_MAP`` 没有「本期发生额」，``.get(列名, "audited_amount")`` 回退成审定数，专门处理发生额的
``_period_amount`` 分支永远走不到 ⇒ Tier A 预设 H10 / I6 / D4 等在底稿里取到审定数，而推送与 L1 取审定数 − 期初余额；
列名写错（如「期末数」）也静默按审定数取。
"""
from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.dataset_models import LedgerDataset
from app.services.formula_engine import execute
from app.services.formula_preloader import preload
from app.services.wp_formula_eval_service import evaluate_wp_formula_expression

from ._env import add_project, make_db

YEAR = 2025


def _tb(pid, code, audited, opening):
    return TrialBalance(project_id=pid, year=YEAR, company_code="001", standard_account_code=code,
                        account_name=code, account_category=AccountCategory.expense,
                        audited_amount=Decimal(audited), opening_balance=Decimal(opening))


async def _both(db, pid, expr):
    """（底稿求值器, L1 预载求值）两条路径的值与错误。"""
    wp_value, wp_errors = await evaluate_wp_formula_expression(db, project_id=pid, year=YEAR, expression=expr)
    ctx = await preload(db, pid, YEAR, [expr])
    l1 = execute(expr, ctx)
    return (wp_value, wp_errors), (l1.value, l1.errors)


@pytest.mark.asyncio
async def test_period_amount_is_audited_minus_opening_and_matches_l1():
    async with make_db(extra_models=(TrialBalance, LedgerDataset)) as factory, factory() as db:
        pid = await add_project(db, "发生额_2025")
        db.add_all([_tb(pid, "6601", "1500", "400"), _tb(pid, "6602", "300", "0"), _tb(pid, "1122", "900", "600")])
        await db.commit()

        for expr, expected in (("TB('6601','本期发生额')", Decimal("1100")),
                               ("TB('1122','本期发生额')", Decimal("300")),
                               ("SUM_TB('6601~6699','本期发生额')", Decimal("1400"))):
            (wp_value, wp_errors), (l1_value, l1_errors) = await _both(db, pid, expr)
            assert wp_errors == [] and l1_errors == [], expr
            assert wp_value == expected, f"{expr}: 底稿求值器得 {wp_value}（审定数是 1500 / 900 / 1800）"
            assert wp_value == l1_value, f"{expr}: 底稿求值器 {wp_value} ≠ L1 {l1_value}"


@pytest.mark.asyncio
async def test_unregistered_column_is_an_error_not_audited():
    async with make_db(extra_models=(TrialBalance, LedgerDataset)) as factory, factory() as db:
        pid = await add_project(db, "列名_2025")
        db.add(_tb(pid, "6601", "1500", "400"))
        await db.commit()

        for expr in ("TB('6601','期末数')", "SUM_TB('6601~6699','发生额')"):
            value, errors = await evaluate_wp_formula_expression(db, project_id=pid, year=YEAR, expression=expr)
            assert value == Decimal("0"), expr
            assert errors and "未注册" in errors[0], f"{expr}: {errors}"
        # 已注册的余额列不受影响
        value, errors = await evaluate_wp_formula_expression(db, project_id=pid, year=YEAR,
                                                             expression="TB('6601','期末余额') - TB('6601','期初余额')")
        assert (value, errors) == (Decimal("1100"), [])


_COLUMN_ARG_RE = re.compile(r"\b(?:SUM_TB|TB_SUM|TB)\(\s*'[^']*'\s*,\s*'([^']*)'\s*\)")


def test_every_preset_column_is_registered_in_wp_evaluator():
    """经底稿求值器求值的 Tier A 预设（D / H / I 循环 render 逐条求值）：TB / SUM_TB 的列名都已注册 ——
    未注册列名现在报错、不再静默按审定数取，预设里留一个就会让该锚点从「错数」变成「报错」。"""
    from app.services.d_cycle_extraction.presets import _PRESETS_PATH
    from app.services.wp_formula_eval_service import _COLUMN_MAP, _DERIVED_COLUMNS, _OCCURRENCE_COLUMNS

    registered = set(_COLUMN_MAP) | set(_DERIVED_COLUMNS) | set(_OCCURRENCE_COLUMNS)
    raw = json.loads(Path(_PRESETS_PATH).read_text(encoding="utf-8"))
    seen = [
        (wp_code, entry.get("anchor"), column)
        for wp_code, entries in raw.items() if not wp_code.startswith("_")
        for entry in entries
        for column in _COLUMN_ARG_RE.findall(str(entry.get("expression") or ""))
    ]
    assert len(seen) > 20, f"只扫到 {len(seen)} 处列名，扫描口径可能失效"
    assert [s for s in seen if s[2] not in registered] == []
    assert {c for _w, _a, c in seen} & set(_DERIVED_COLUMNS), "预设里应有本期发生额（H10 / I6 / D4 等损益类）"


def test_column_scan_catches_a_planted_unregistered_column():
    assert _COLUMN_ARG_RE.findall("TB('6601','期末数') + SUM_TB('6601~6699', '本期发生额')") == ["期末数", "本期发生额"]


@pytest.mark.asyncio
async def test_l1_preload_reads_occurrence_and_range_sums(monkeypatch):
    """L1 统一预载层：发生额原先 ``getattr(TrialBalance, 'debit_amount')`` 恒 0；区间 ``'1601~1699'`` 原先当前缀恒 0。"""
    calls: list[int] = []

    async def fake_occurrence(db, project_id, year):
        calls.append(year)
        return {"1601": {"本期借方": Decimal("70"), "本期贷方": Decimal("20")},
                "1602": {"本期借方": Decimal("5"), "本期贷方": Decimal("9")}}

    monkeypatch.setattr("app.services.four_table.occurrence_by_standard_code.fetch_occurrence_by_standard_code",
                        fake_occurrence)
    async with make_db(extra_models=(TrialBalance, LedgerDataset)) as factory, factory() as db:
        pid = await add_project(db, "发生额预载_2025")
        db.add_all([_tb(pid, "1601", "1000", "800"), _tb(pid, "1602", "300", "100")])
        await db.commit()

        expr = "TB('1601','本期借方') + SUM_TB('1601~1699','贷方发生额') + SUM_TB('1601~1699','期末余额')"
        result = execute(expr, await preload(db, pid, YEAR, [expr]))
        assert result.errors == []
        assert result.value == Decimal("70") + Decimal("29") + Decimal("1300")
        assert calls == [YEAR]

        calls.clear()
        plain = "TB('1601','期末余额')"
        assert execute(plain, await preload(db, pid, YEAR, [plain])).value == Decimal("1000")
        assert calls == [], "没用发生额列时不取 tb_balance 归集"
