"""报表「审核」里配置的勾稽 / 合理性公式真实求值（spec formula-governance-coverage-closure R1.6 / R7a）。

旧实现不求值：勾稽类「有公式就判通过」，合理性类只看该行有没有值 —— 配的审核公式写什么都「通过」。
"""
from __future__ import annotations

from decimal import Decimal

from app.models.audit_platform_models import TbAuxBalance, TrialBalance
from app.models.dataset_models import LedgerDataset
from app.models.report_models import FinancialReport, ReportConfig
from app.services import report_audit_checks as rac

from ._env import BS, STD, add_project, make_db


def _row(code, category, formula, *, std=STD, desc=None):
    return ReportConfig(report_type=BS, row_code=code, row_name=code, row_number=1, indent_level=0, formula=formula,
                        formula_category=category, formula_description=desc, applicable_standard=std,
                        formula_version=1)


async def test_config_audit_formulas_are_really_evaluated():
    async with make_db(extra_models=(TrialBalance, TbAuxBalance, LedgerDataset)) as factory, factory() as db:
        pid = await add_project(db, "审核公式")
        for code, amt in (("BS-001", "100"), ("BS-002", "100"), ("BS-003", "7")):
            db.add(FinancialReport(project_id=pid, year=2025, report_type=BS, row_code=code, row_name=code,
                                   current_period_amount=Decimal(amt)))
        db.add_all([
            _row("L1", "logic_check", "ROW('BS-001') == ROW('BS-002')", desc="合计相符"),
            _row("L2", "logic_check", "ROW('BS-001') == ROW('BS-003')", desc="明细相符"),
            _row("L3", "logic_check", "AUX('1122','客户','甲公司','期末余额') == 0", desc="取不到"),
            _row("R1", "reasonability", "ROW('BS-003') > 1000", desc="大额提醒"),
            _row("R2", "reasonability", "ROW('BS-001') > 50", desc="超阈值"),
            _row("A1", "auto_calc", "ROW('BS-001')"),  # 非审核类不执行
        ])
        await db.commit()
        got = {r["source"].split()[0]: r for r in await rac.config_audit_checks(db, pid, 2025, STD)}
        assert {k: v["passed"] for k, v in got.items()} == {
            "L1": True, "L2": False, "L3": False,  # 勾稽：成立（非 0）才通过
            "R1": True, "R2": False,              # 合理性：触发（非 0）即提醒 ⇒ 未通过
        }
        assert got["L3"]["actual"].startswith("无法取数（") and "无辅助核算余额" in got["L3"]["actual"]
        assert (got["L1"]["category"], got["R2"]["category"]) == ("logic_check", "reasonability")
        assert got["R2"]["formula"] == "ROW('BS-001') > 50"


async def test_project_adaptation_of_audit_formula_takes_effect():
    """本项目适配的审核公式生效（旧实现读准则行，本项目改了不生效）。"""
    async with make_db(extra_models=(TrialBalance, TbAuxBalance, LedgerDataset)) as factory, factory() as db:
        pid = await add_project(db, "本项目适配")
        db.add(FinancialReport(project_id=pid, year=2025, report_type=BS, row_code="BS-001", row_name="BS-001",
                               current_period_amount=Decimal("100")))
        db.add_all([_row("L1", "logic_check", "ROW('BS-001') == 1"),
                    _row("L1", "logic_check", "ROW('BS-001') == 100", std=f"project:{pid}")])
        await db.commit()
        (only,) = await rac.config_audit_checks(db, pid, 2025, STD)
        assert (only["passed"], only["formula"]) == (True, "ROW('BS-001') == 100")
