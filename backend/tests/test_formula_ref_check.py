"""公式引用是否存在按项目数据判定（spec formula-fetch-followup-defect-closure R5.1 / R5.2 / R5.3）。

原状（逐条可打红）：
* 地址库校验：试算表只认精确码（求值按前缀合计）⇒ ``TB('1122',…)`` 在只有 ``1122.01`` 的项目里判悬空；报表登记**全部准则**的行
  ⇒ 别的准则才有的行判存在；附注只登记模板「合计」行 ⇒ 引用明细行一律判悬空、附注已生成的章节不看。
* ACNR ``full_resolve`` 非底稿域只做写法换算即 ``found=True``：不看数据、复合表达式取第一个引用也判命中、没有项目也判存在。
* 附注公式执行器 NOTE 忽略行名一律取最后一个合计行、「期末」取第一列；TB 只认精确码；参数间有空格就整条取不到。

SQLite 真库 + 真 ORM 行；期望按需求原文写死，不由被测函数推出。
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.core import Project
from app.models.report_models import DisclosureNote, FinancialReportType, ReportConfig
from app.services import formula_ref_check as frc
from app.services.acnr.resolver import full_resolve
from app.services.address_registry import address_registry
from app.services.note_formula_generator import _load_cross_table_data, _resolve_single_cross_ref

YEAR = 2025
P = uuid.UUID("3b0f6a52-1c7e-4d2a-9f41-6e8d2c5a7b10")
NOTE_TABLE = {
    "name": "货币资金", "headers": ["项目", "期末余额", "期初余额", "备注金额"],
    "rows": [{"label": "库存现金", "values": [1, 2, 3]}, {"label": "银行存款", "values": [10, 20, 30]},
             {"label": "合计", "values": [11, 22, 33], "is_total": True}],
}
TEMPLATE = {"sections": [{"section_number": "九、9", "section_title": "模板章节", "tables": [{
    "name": "模板表", "headers": ["项目", "期末余额", "上年年末余额"],
    "rows": [{"label": "甲", "row_type": "data"}, {"label": "总计", "row_type": "total"}]}]}]}


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [Project.__table__, TrialBalance.__table__, ReportConfig.__table__, DisclosureNote.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: MetaData().create_all(c, tables=tables))
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        session.add(Project(id=P, name="引用校验_2025", client_name="引用校验", template_type="soe",
                            report_scope="standalone", audit_year=YEAR,
                            wizard_state={"steps": {"basic_info": {"data": {"template_type": "soe"}}}}))
        for year, code in ((YEAR, "1001"), (YEAR, "1122.01"), (YEAR - 1, "6001")):
            session.add(TrialBalance(project_id=P, year=year, company_code="001", standard_account_code=code,
                                     account_name=code, account_category=AccountCategory.asset,
                                     audited_amount=Decimal("1"), opening_balance=Decimal("0")))
        for code, std in (("BS-002", "soe_standalone"), ("BS-010", "soe_standalone"),
                          ("BS-099", "listed_standalone"), ("BS-200", f"project:{P}")):
            session.add(ReportConfig(report_type=FinancialReportType.balance_sheet, row_number=1, row_code=code,
                                     row_name=code, applicable_standard=std))
        session.add(DisclosureNote(project_id=P, year=YEAR, note_section="五、1", section_title="货币资金",
                                   table_data={**NOTE_TABLE, "_tables": [NOTE_TABLE]}))
        session.add(DisclosureNote(project_id=P, year=YEAR, note_section="五、2", section_title="已删除",
                                   table_data=NOTE_TABLE, is_deleted=True))
        await session.flush()
        yield session
    await engine.dispose()


@pytest.fixture
def template_dir(tmp_path, monkeypatch):
    (tmp_path / "note_template_soe.json").write_text(json.dumps(TEMPLATE, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(frc, "_DATA_DIR", tmp_path)


# ── 1. 判定口径（逐类，期望写死） ─────────────────────────────────────────────

_CASES = [
    # 试算表：按前缀（与求值同口径），列名须已注册，按本年度
    ("TB('1122','期末余额')", True), ("TB( '1122.01' , '审定数' )", True), ("TB('9999','期末余额')", False),
    ("TB('1001','不认识的列')", False), ("SUM_TB('1001~1122','期末余额')", True), ("SUM_TB('2001~2999','期末余额')", False),
    ("PREV('1001','期末余额')", True), ("PREV(TB('1122','期末余额'))", True), ("TB('6001','期末余额')", False),
    # 报表：只认本项目适用准则（soe_standalone）+ 本项目层的行
    ("ROW('BS-002')", True), ("ROW('BS-099')", False), ("ROW('BS-200')", True), ("SUM_ROW('BS-001','BS-005')", True),
    ("SUM_ROW('BS-300','BS-400')", False), ("REPORT('BS-010','期初')", True), ("REPORT('BS-010','某个期间')", False),
    # 附注：本年度已生成 ⇒ 按章节 / 行 / 列结构（明细行也认）；已删除的章节不算
    ("NOTE('五、1','库存现金','期末余额')", True), ("NOTE('五、1','合计','期初')", True), ("NOTE('五、1','银行存款')", True),
    ("NOTE('五、1','不存在的行','期末余额')", False), ("NOTE('五、1','合计','本期发生额')", False),
    ("NOTE('五、2','合计','期末余额')", False), ("NOTE('九、9','合计','期末余额')", False),
]


@pytest.mark.parametrize(("ref", "exists"), _CASES)
async def test_checker_verdicts(db, ref, exists):
    verdict = await frc.FormulaRefChecker(db, P, YEAR, "soe").check(ref)
    assert verdict is not None and verdict.exists is exists, (ref, verdict)
    assert bool(verdict.reason) is (not exists), "判不存在必须写明原因、判存在不带原因"


async def test_checker_reasons_name_what_is_missing(db):
    checker = frc.FormulaRefChecker(db, P, YEAR, "soe")
    assert "9999" in (await checker.check("TB('9999','期末余额')")).reason
    assert "soe_standalone" in (await checker.check("ROW('BS-099')")).reason
    assert "没有「不存在的行」行" in (await checker.check("NOTE('五、1','不存在的行','期末余额')")).reason
    assert "附注没有章节 五、2" in (await checker.check("NOTE('五、2','合计','期末余额')")).reason, "已删除的章节按没有该章节报"
    assert (await checker.check("AUX('1122','客户','期末')")) is None, "辅助余额 / 底稿不归本模块"
    assert (await checker.check("TB('1001','期末余额')+TB('1002','期末余额')")) is None, "复合表达式不是单个引用"
    bad = await frc.FormulaRefChecker(db, "p1", YEAR).check("TB('1001','期末余额')")
    assert bad is not None and not bad.exists and "无效" in bad.reason


async def test_note_template_fallback_when_notes_not_generated(db, template_dir):
    """本年度附注一节都没有（尚未生成）⇒ 按附注模板（章节 + 行名 + 表头）判定；只剩已删除的章节也算没有。"""
    db.add(DisclosureNote(project_id=P, year=YEAR + 1, note_section="八、1", section_title="已删除",
                          table_data=NOTE_TABLE, is_deleted=True))
    await db.flush()
    checker = frc.FormulaRefChecker(db, P, YEAR + 1, "soe")
    assert (await checker.check("NOTE('九、9','甲','上年年末余额')")).exists
    assert (await checker.check("NOTE('九、9','合计','期末')")).exists, \
        "「合计」找不到同名行时取合计行：模板的合计行写 row_type=total（附注里写 is_total），两种都要认"
    missing = await checker.check("NOTE('九、9','乙','期末余额')")
    assert not missing.exists and "按附注模板判定" in missing.reason
    assert not (await checker.check("NOTE('五、1','合计','期末余额')")).exists, "模板里没有的章节"
    assert (await checker.check_note_section("九、9")).exists and not (await checker.check_note_section("八、1")).exists


async def test_validate_formula_refs_routes_three_domains_through_checker(db):
    issues = await address_registry.validate_formula_refs(
        db, str(P), YEAR, "TB('1122','期末余额') + ROW('BS-099') - NOTE('五、1','库存现金','期末余额')", "soe")
    assert [i["ref"] for i in issues] == ["ROW('BS-099')"], issues
    assert issues[0]["status"] == "not_found" and "BS-099" in issues[0]["message"]


# ── 2. ACNR 单引用解析 ────────────────────────────────────────────────────────

async def test_full_resolve_checks_non_wp_refs_against_project_data(db):
    hit = await full_resolve(formula_ref="TB('1122','期末余额')", project_id=str(P), db=db)
    assert hit.found and hit.verified is True
    miss = await full_resolve(formula_ref="TB('9999','期末余额')", project_id=str(P), db=db)
    assert (miss.found, miss.error, miss.verified) == (False, "ref_not_found", True) and "9999" in miss.reason
    other_std = await full_resolve(uri="report://BS/BS-099#期末", project_id=str(P), db=db)
    assert not other_std.found and other_std.error == "ref_not_found"
    assert (await full_resolve(index_ref="Note:五、1", project_id=str(P), db=db)).found
    assert not (await full_resolve(index_ref="Note:五、9", project_id=str(P), db=db)).found


async def test_full_resolve_composite_and_missing_project_are_not_found(db):
    composite = await full_resolve(formula_ref="TB('1001','期末余额')+TB('9999','期末余额')", project_id=str(P), db=db)
    assert (composite.found, composite.error) == (False, "not_single_reference")
    no_project = await full_resolve(formula_ref="TB('1001','期末余额')")
    assert (no_project.found, no_project.error, no_project.verified) == (False, "project_context_required", False)
    # 复合表达式不论有没有项目都不是单个引用（不能落成「无法确认」——预设编辑弹窗对无法确认放行）
    composite_no_project = await full_resolve(formula_ref="TB('1001','期末余额')*2")
    assert (composite_no_project.found, composite_no_project.error) == (False, "not_single_reference")


async def test_full_resolve_request_memo_reuses_one_checker(db, monkeypatch):
    """同一请求 / 同一次报表生成逐个解析很多引用：判定器与报表配置只建 / 只读一次（报表生成对每个 ROW 引用都解析）。"""
    from app.services.formula_settings import effective_report

    calls = []
    real = effective_report.load_effective_report_configs

    async def _spy(*args, **kwargs):
        calls.append(1)
        return await real(*args, **kwargs)

    monkeypatch.setattr(effective_report, "load_effective_report_configs", _spy)
    memo: dict = {}
    for ref in ("ROW('BS-002')", "ROW('BS-010')", "ROW('BS-099')"):
        await full_resolve(formula_ref=ref, project_id=str(P), db=db, _instance_memo=memo)
    assert len(calls) == 1 and isinstance(memo[("formula_ref_check", str(P))], frc.FormulaRefChecker)


async def test_full_resolve_identity_only_callers_opt_out(db):
    """只建立引用身份的调用方显式不校验：照常返回身份，``verified=False`` 如实标注。"""
    rr = await full_resolve(formula_ref="TB('9999','期末余额')", project_id=str(P), db=db, verify_existence=False)
    assert rr.found and rr.verified is False and rr.uri == "tb://9999#期末余额"


def test_dangling_excludes_unconfirmable_and_fail_open():
    from app.services.formula_management.engine import ResolveRefResult

    assert ResolveRefResult(found=False, error="ref_not_found").dangling
    assert ResolveRefResult(found=False, error="not_single_reference").dangling
    assert not ResolveRefResult(found=False, error="project_context_required").dangling, "无法确认 ≠ 悬空"
    assert not ResolveRefResult(found=False, fail_open=True).dangling
    assert not ResolveRefResult(found=True).dangling


async def test_import_validation_flags_only_what_the_project_lacks(db):
    """公式导入 / 新增预设的逐条校验：有项目按数据判悬空；没有项目（全局预设）时非底稿域无法确认、不拦。"""
    from app.services.formula_management.formula_import_export import validate_single_formula_refs

    expr = "TB('9999','期末余额') + TB('1001','期末余额')"
    _, with_project = await validate_single_formula_refs(expression=expr, refs=None, project_id=str(P), db=db)
    assert with_project == ["TB('9999','期末余额')"]
    _, global_preset = await validate_single_formula_refs(expression=expr, refs=None, project_id=None, db=None)
    assert global_preset == []


async def test_identity_only_callers_keep_identity_for_missing_refs(db):
    """附注执行器 / 公式管理执行只建立引用身份：引用不存在也照常拿到 canonical 身份（取数另走本地数据）。"""
    from app.services.formula_management.engine import FormulaRecord, _resolve_formula_refs
    from app.services.note_formula_generator import _resolve_cross_refs_via_acnr

    refs = await _resolve_cross_refs_via_acnr("TB('9999','期末余额') + 1", P, db)
    assert refs == {"TB('9999','期末余额')": "tb://9999"}
    record = FormulaRecord(id="f1", formula_type="auto_calc", target_cell="B5", expression="TB('9999','期末余额')",
                           refs=["TB('9999','期末余额')"])
    (resolved,) = await _resolve_formula_refs(record, project_id=str(P), db=db)
    assert resolved.found and resolved.addr_id == "tb://9999"


# ── 3. 附注公式执行器 ─────────────────────────────────────────────────────────

def _cross(**extra):
    return {"report": {}, "tb": {}, "note_tables": {"五、1": NOTE_TABLE}, "wp": {}, "prior": {}, "aging": {}, **extra}


@pytest.mark.parametrize(("token", "value"), [
    ("NOTE('五、1','库存现金','期末余额')", 1.0),       # 原先：一律取合计行 ⇒ 11
    ("NOTE('五、1','合计','备注金额')", 33.0),           # 原先：没有「期末 / 期初」⇒ None
    ("NOTE('五、1','合计','期初')", 22.0),               # 只写期间按期间语义找唯一一列
    ("NOTE( '五、1' , '银行存款' )", 10.0),               # 两参（列缺省第一个数据列）+ 参数间空格：原先整条取不到
    ("NOTE('五、1','不存在的行','期末余额')", None),
    ("NOTE('五、9','合计','期末余额')", None),
])
def test_executor_note_reads_section_row_and_column(token, value):
    assert _resolve_single_cross_ref(token, _cross()) == value


def test_executor_tb_sums_by_prefix_and_tolerates_spaces():
    cross = _cross(tb={"1122.01": {"audited": 5.0}, "1122.02": {"audited": 7.0}, "1123": {"audited": 100.0}})
    assert _resolve_single_cross_ref("TB('1122','审定数')", cross) == 12.0   # 原先只认精确码 ⇒ 0
    assert _resolve_single_cross_ref("TB( '1122' , '审定数' )", cross) == 12.0
    assert _resolve_single_cross_ref("TB('9999','审定数')", cross) == 0.0


async def test_cross_table_data_keeps_live_note_tables_only(db):
    cross = await _load_cross_table_data(db, P, YEAR)
    assert set(cross["note_tables"]) == {"五、1"}, "已删除的附注不参与取数"
    assert "notes" not in cross, "旧的「合计前两列」结构已删除，NOTE 只走按行列取数"
