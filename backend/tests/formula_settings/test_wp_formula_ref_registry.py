"""底稿公式保存时的引用校验能认 ROW / NOTE / AUX（spec formula-governance-coverage-closure R6）。

R6 前这三类引用在底稿可编辑公式里先被函数门拒绝，所以下面三处地址库缺陷一直没暴露 —— 函数门放开后，
它们会让合法公式在保存时被判「悬空引用」：

* ROW 一律转成 ``#本期``，而资产负债表行登记的期间是「期末 / 期初」⇒ 资产负债表 ROW 恒判悬空；
* 附注域按「模板是列表」遍历，而模板文件是 ``{"sections": [...]}`` ⇒ 附注域恒为空、任何 NOTE 都判悬空；
  章节键用了内部 ``section_id``，与 NOTE 第一参（附注章节编号，如「八、1」）对不上；
* 辅助余额只登记辅助项，``AUX('科目','辅助类型','列')``（类型合计）判悬空；且地址按明细科目（1122.01）登记，
  而 AUX 求值按科目前缀合计，``AUX('1122',…)`` 判悬空。
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.models.audit_platform_models import TbAuxBalance
from app.models.report_models import DisclosureNote, FinancialReportType, ReportConfig
from app.services import address_registry as ar

from ._env import add_project, make_db


@pytest.mark.parametrize(("ref", "uri"), [
    ("ROW('BS-002')", "report://BS/BS-002#期末"),
    ("SUM_ROW('BS-002','BS-009')", "report://BS/BS-002#期末"),
    ("ROW('IS-001')", "report://IS/IS-001#本期"),
    ("ROW('EQ-003')", "report://EQ/EQ-003#本年"),
])
def test_row_uri_uses_the_current_period_label_of_its_report(ref, uri):
    assert ar.formula_ref_to_uri(ref) == uri


@pytest.mark.parametrize(("template_type", "ref"), [
    ("soe", "NOTE('八、1','合计','期末余额')"),
    ("listed", "NOTE('五、1','合计','期末余额')"),
])
async def test_note_domain_is_built_from_sections_with_section_numbers(template_type, ref):
    entries = await ar.build_note_entries(None, str(uuid.uuid4()), 2025, template_type)
    refs = {e.formula_ref for e in entries}
    assert len(entries) > 100, len(entries)  # 防空转：模板上百个章节
    assert ref in refs
    assert not any(r.startswith("NOTE('chapter-") for r in refs)  # 不再用内部 section_id 当章节


async def test_save_validation_accepts_bs_row_note_and_aux_type_refs(monkeypatch):
    svc = ar.AddressRegistryService()
    monkeypatch.setattr(svc, "_redis_get", AsyncMock(return_value=None))
    monkeypatch.setattr(svc, "_redis_set", AsyncMock())
    # 附注引用按本年度附注结构判定、未生成时按模板（spec formula-fetch-followup-defect-closure R5.2）⇒ 要有附注表
    async with make_db(extra_models=(TbAuxBalance, DisclosureNote)) as factory, factory() as db:
        pid = await add_project(db, "地址库")
        db.add_all([
            ReportConfig(report_type=FinancialReportType.balance_sheet, row_code="BS-002", row_name="货币资金",
                         row_number=2, indent_level=0, applicable_standard="soe_standalone"),
            # 辅助余额登记在明细科目上（真库形如 1122.01）；AUX 按科目前缀合计，校验同口径
            TbAuxBalance(project_id=pid, year=2025, company_code="001", account_code="1122.01", account_name="应收账款",
                         aux_type="客户", aux_code="C01", aux_name="甲公司", closing_balance=Decimal("1")),
        ])
        await db.commit()
        ok = ("ROW('BS-002') + NOTE('八、1','合计','期末余额') + AUX('1122','客户','期末')"
              " + AUX('1122','甲公司','期末')")
        assert await svc.validate_formula_refs(db, str(pid), 2025, ok, "soe") == []
        bad = await svc.validate_formula_refs(db, str(pid), 2025, "ROW('BS-404') + AUX('1122','供应商','期末')", "soe")
        assert sorted(i["ref"] for i in bad) == ["AUX('1122','供应商','期末')", "ROW('BS-404')"]  # 真悬空仍拦
