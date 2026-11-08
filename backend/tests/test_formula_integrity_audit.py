"""真实严格代入和审核：仅替换下一层隔离来源，不替换求值入口。"""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.amount_resolver import TrialBalanceResolver
from app.services.formula_settings.cross_check_rules import evaluate_strict
from app.services.report_audit_checks import config_audit_checks, split_by_severity
from app.services.report_engine import evaluate_formula_result
from tests.formula_integrity_support import add_report, report_config
from tests.formula_integrity_support import integrity_world as integrity_world


@pytest.mark.parametrize("strict", (False, True))
@pytest.mark.parametrize("formula", (
    "PREV('1001','审定数')", "PREV('E1','明细','审定数')",
    "AUX('1122','客户','期末余额')", "AUX('1122','客户','甲','期末余额')",
))
async def test_formula_integrity_raw_prev_aux_are_not_silent_zero(integrity_world, strict, formula):
    world = integrity_world
    result = await evaluate_formula_result(formula, resolver=TrialBalanceResolver(
        world.db, world.project.id, 2025), strict_context=strict)
    assert not result.ok
    assert result.value is None
    assert "不支持" in "；".join(result.errors)


@pytest.mark.parametrize("value", (None, Decimal("0"), Decimal("12.50")))
async def test_formula_integrity_strict_prev_three_args(integrity_world, monkeypatch, value):
    from app.services.prev_wp_field import PriorWpFieldResolver, PrevFieldValue

    world, calls = integrity_world, []

    async def source(self, wp, sheet, field):
        calls.append((self.project_id, self.year, wp, sheet, field))
        return PrevFieldValue(value, "隔离上年来源缺失" if value is None else "")

    monkeypatch.setattr(PriorWpFieldResolver, "resolve", source)
    amount, error = await evaluate_strict("PREV('E1','明细','审定数')+2",
        TrialBalanceResolver(world.db, world.project.id, 2025), {})
    assert calls == [(world.project.id, 2025, "E1", "明细", "审定数")]
    if value is None:
        assert amount is None
        assert "隔离上年来源缺失" in error
    else:
        assert amount == value + Decimal(2)
        assert error == ""


@pytest.mark.parametrize("value", (Decimal("0"), Decimal("12.50")))
@pytest.mark.parametrize("formula", (
    "AUX('1122','客户')", "AUX('1122','甲','期末余额')",
    "AUX('1122','客户','甲','期末余额')",
))
async def test_formula_integrity_strict_aux_real_substitution(integrity_world, monkeypatch, formula, value):
    from app.services import formula_ref_preload

    world, calls = integrity_world, []

    async def rows(db, project_id, year, account):
        calls.append((db, project_id, year, account))
        return [SimpleNamespace(aux_type="客户", aux_code="01", aux_name="甲",
            closing_balance=value, opening_balance=Decimal(7),
            debit_amount=Decimal(3), credit_amount=Decimal(1))]

    monkeypatch.setattr(formula_ref_preload, "_aux_rows", rows)
    amount, error = await evaluate_strict(formula + "+2",
        TrialBalanceResolver(world.db, world.project.id, 2025), {})
    assert amount == value + Decimal(2), error
    assert error == ""
    assert calls == [(world.db, world.project.id, 2025, "1122")]


@pytest.mark.parametrize("shape,reason", (("empty", "本年无辅助核算余额"),
    ("missing_item", "没有「乙」"), ("ambiguous", "多个辅助类型"),
    ("invalid_column", "列名「未知」无法识别")))
async def test_formula_integrity_strict_aux_missing_is_not_zero(integrity_world, monkeypatch, shape, reason):
    from app.services import formula_ref_preload

    world = integrity_world
    data = [SimpleNamespace(aux_type="客户", aux_code="01", aux_name="甲",
                            closing_balance=Decimal(0))]
    if shape == "empty":
        data = []
    elif shape == "ambiguous":
        data.append(SimpleNamespace(aux_type="供应商", aux_code="01", aux_name="甲",
                                    closing_balance=Decimal(0)))

    async def rows(*args):
        return data

    monkeypatch.setattr(formula_ref_preload, "_aux_rows", rows)
    item = "乙" if shape == "missing_item" else "甲"
    column = "未知" if shape == "invalid_column" else "期末余额"
    amount, error = await evaluate_strict(f"AUX('1122','{item}','{column}')=0",
        TrialBalanceResolver(world.db, world.project.id, 2025), {})
    assert amount is None
    assert reason in error


@pytest.mark.parametrize("category,severity", (("logic_check", "blocking"), ("reasonability", "warning")))
@pytest.mark.parametrize("amount", (None, Decimal(0), Decimal(11)))
async def test_formula_integrity_audit_retains_null_and_zero(integrity_world, monkeypatch, category, severity, amount):
    from app.services.formula_settings import effective_report

    world, calls = integrity_world, []
    await add_report(world, "BS001", amount)
    await add_report(world, "BS001", Decimal(999), project=world.other)
    await add_report(world, "BS001", Decimal(888), year=2024)
    config = report_config("CHECK001", "ROW('BS001')", formula_category=category)

    async def configs(db, *, standard, project_id):
        calls.append((db, standard, project_id))
        return [config, report_config("AMOUNT001"),
                report_config("EMPTY001", " ", formula_category=category)]

    monkeypatch.setattr(effective_report, "load_effective_report_configs", configs)
    checks = await config_audit_checks(world.db, world.project.id, 2025, "listed")
    assert calls == [(world.db, "listed", world.project.id)]
    assert len(checks) == 1
    check = checks[0]
    assert check["formula"] == config.formula
    assert check["severity"] == severity
    assert check["category"] == category
    if amount is None:
        assert check["passed"] is False
        assert "无法取数" in check["actual"]
        assert "空" in check["actual"]
    else:
        expected = amount != 0 if category == "logic_check" else amount == 0
        assert check["passed"] is expected
        assert Decimal(check["actual"]) == amount
    failures, hints = split_by_severity(checks)
    expected_failed = [] if check["passed"] else [check]
    assert failures == (expected_failed if severity == "blocking" else [])
    assert hints == (expected_failed if severity == "warning" else [])


@pytest.mark.parametrize("shape", ("missing", "other_project", "other_year", "deleted"))
async def test_formula_integrity_audit_cannot_use_out_of_scope_rows(integrity_world, monkeypatch, shape):
    from app.services.formula_settings import effective_report

    world = integrity_world
    if shape != "missing":
        await add_report(world, "BS001", Decimal(1),
            project=world.other if shape == "other_project" else world.project,
            year=2024 if shape == "other_year" else 2025, deleted=shape == "deleted")

    async def configs(*args, **kwargs):
        return [report_config("CHECK001", "ROW('BS001')=0", formula_category="logic_check")]

    monkeypatch.setattr(effective_report, "load_effective_report_configs", configs)
    checks = await config_audit_checks(world.db, world.project.id, 2025, "listed")
    assert len(checks) == 1
    assert checks[0]["passed"] is False
    assert "无法取数" in checks[0]["actual"]


async def test_formula_integrity_severity_split_preserves_builtin_blocking(integrity_world, monkeypatch):
    from app.services.formula_settings import effective_report
    from app.services.report_audit_checks import run_report_audit
    from app.services.report_engine import ReportEngine

    async def balance(self, project_id, year):
        assert project_id == integrity_world.project.id and year == 2025
        return [{"check_name": "【测试】内置平衡", "passed": False,
                 "expected_value": "0", "actual_value": "1", "difference": "1"}]

    async def configs(*args, **kwargs):
        return [report_config("WARN001", "1", formula_category="reasonability")]

    monkeypatch.setattr(ReportEngine, "check_balance", balance)
    monkeypatch.setattr(effective_report, "load_effective_report_configs", configs)
    world = integrity_world
    checks = await run_report_audit(world.db, world.project.id, 2025, "listed")
    failures, hints = split_by_severity(checks)
    assert len(failures) == len(hints) == 1
    assert failures[0]["source"] == "内置校验"
    assert failures[0]["severity"] == "blocking"
    assert hints[0]["severity"] == "warning"
    unknown = {"passed": False, "severity": "future"}
    assert split_by_severity([{"passed": True}, unknown]) == ([unknown], [])
