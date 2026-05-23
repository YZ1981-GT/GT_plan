"""L-4 task 4.1 — 附注公式引擎扩展测试

覆盖：
- generate_formulas_for_table 自动生成 =TB / =WP / =REPORT 公式
- _exec_cross_table 解析三源公式（含多公式 + 加减号）
- compute_formula_coverage 覆盖率统计 ≥ 80%
- 参数错误时返回 None / 0 不崩溃

Validates: proposal-remaining-18 task 4.1 (L-4)
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.report_models import (
    DisclosureNote,
    FinancialReport,
    FinancialReportType,
    NoteStatus,
    SourceTemplate,
)
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpReviewStatus,
    WpSourceType,
)
from app.services.note_formula_generator import (
    _exec_cross_table,
    _load_cross_table_data,
    _resolve_single_cross_ref,
    compute_formula_coverage,
    compute_project_formula_coverage,
    execute_note_formulas,
    generate_formulas_for_table,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    await test_engine.dispose()


# ---------------------------------------------------------------------------
# 单测 1：generate_formulas_for_table 自动生成 =TB 公式（明细行）
# ---------------------------------------------------------------------------


def _cash_template() -> dict:
    """货币资金附注表（3 明细 + 1 合计）"""
    return {
        "headers": ["项目", "期末余额", "期初余额"],
        "rows": [
            {"label": "库存现金", "account_codes": ["1001"], "is_total": False},
            {"label": "银行存款", "account_codes": ["1002"], "is_total": False},
            {"label": "其他货币资金", "account_codes": ["1012"], "is_total": False},
            {"label": "合计", "account_codes": [], "is_total": True},
        ],
    }


def test_generate_formulas_for_detail_rows_tb():
    """明细行带 account_codes → 自动生成 =TB() 公式（期末/期初两列）"""
    formulas = generate_formulas_for_table(_cash_template(), ["balance", "sub_item"])

    # 库存现金 row=0：期末 / 期初
    assert formulas["0:0"]["expression"] == "TB('1001','期末')"
    assert formulas["0:1"]["expression"] == "TB('1001','期初')"
    assert formulas["0:0"]["source"] == "account_codes"

    # 银行存款 row=1
    assert formulas["1:0"]["expression"] == "TB('1002','期末')"
    assert formulas["1:1"]["expression"] == "TB('1002','期初')"

    # 合计行（row=3）必须为 vertical_sum，覆盖了明细生成
    assert formulas["3:0"]["type"] == "vertical_sum"
    assert formulas["3:0"]["expression"] == "SUM(0:2, 0)"


def test_generate_formulas_multi_account_codes_sum():
    """单行多科目 → 多个 TB() 累加"""
    template = {
        "headers": ["项目", "期末余额"],
        "rows": [
            {"label": "应收账款合并", "account_codes": ["1122", "1123"], "is_total": False},
        ],
    }
    formulas = generate_formulas_for_table(template, [])
    assert formulas["0:0"]["expression"] == "TB('1122','期末') + TB('1123','期末')"


def test_generate_formulas_wp_mapping_priority():
    """wp_mapping 配置优先于 account_codes → 生成 =WP() 公式"""
    template = _cash_template()
    wp_mapping = {
        "库存现金": {
            "wp_code": "E1",
            "sheet": "审定表E1",
            "cell_closing": "B5",
            "cell_opening": "C5",
        }
    }
    formulas = generate_formulas_for_table(template, [], wp_mapping=wp_mapping)
    # 期末列用 cell_closing
    assert formulas["0:0"]["expression"] == "WP('E1','审定表E1','B5')"
    assert formulas["0:0"]["source"] == "wp_mapping"
    # 期初列用 cell_opening
    assert formulas["0:1"]["expression"] == "WP('E1','审定表E1','C5')"
    # 银行存款无 wp_mapping → 仍走 TB
    assert formulas["1:0"]["expression"] == "TB('1002','期末')"


def test_generate_formulas_report_row_code_fallback():
    """无 account_codes 但有 report_row_code → 生成 =REPORT() 公式"""
    template = {
        "headers": ["项目", "期末余额", "期初余额"],
        "rows": [
            {
                "label": "存货",
                "account_codes": [],
                "report_row_code": "BS-008",
                "is_total": False,
            },
        ],
    }
    formulas = generate_formulas_for_table(template, [])
    assert formulas["0:0"]["expression"] == "REPORT('BS-008','期末')"
    assert formulas["0:1"]["expression"] == "REPORT('BS-008','期初')"
    assert formulas["0:0"]["source"] == "report_row_code"


def test_generate_formulas_period_detection_revenue():
    """损益表：本期/上期列 → 期末/期初标签"""
    template = {
        "headers": ["项目", "本期金额", "上期金额"],
        "rows": [
            {"label": "主营业务收入", "account_codes": ["6001"], "is_total": False},
        ],
    }
    formulas = generate_formulas_for_table(template, [])
    assert formulas["0:0"]["expression"] == "TB('6001','期末')"
    assert formulas["0:1"]["expression"] == "TB('6001','期初')"


def test_generate_formulas_skip_unrecognized_columns():
    """非期间列（如"备注"）不生成公式"""
    template = {
        "headers": ["项目", "期末余额", "备注"],
        "rows": [
            {"label": "库存现金", "account_codes": ["1001"], "is_total": False},
        ],
    }
    formulas = generate_formulas_for_table(template, [])
    assert "0:0" in formulas  # 期末
    assert "0:1" not in formulas  # 备注列跳过


def test_generate_formulas_empty_template():
    """空模板返回空 dict（不崩溃）"""
    assert generate_formulas_for_table({}, []) == {}
    assert generate_formulas_for_table({"headers": [], "rows": []}, []) == {}
    assert generate_formulas_for_table({"headers": ["项目"], "rows": []}, []) == {}


# ---------------------------------------------------------------------------
# 单测 2：_exec_cross_table — 三源公式解析
# ---------------------------------------------------------------------------


def _sample_cross_data() -> dict:
    return {
        "report": {"BS-002": {"current": 1000.0, "prior": 800.0}},
        "tb": {
            "1001": {"audited": 50.0, "unadjusted": 48.0, "opening": 40.0},
            "1002": {"audited": 950.0, "unadjusted": 950.0, "opening": 760.0},
        },
        "notes": {"五、3": {"total_closing": 1200.0, "total_opening": 1100.0}},
        "wp": {"E1": {"审定表E1!B5": 50.0, "审定表E1!C5": 40.0}},
    }


def test_exec_tb_single():
    """TB('1001','期末') → audited"""
    assert _exec_cross_table("TB('1001','期末')", _sample_cross_data()) == 50.0
    assert _exec_cross_table("TB('1001','期初')", _sample_cross_data()) == 40.0
    assert _exec_cross_table("TB('1001','审定数')", _sample_cross_data()) == 50.0
    assert _exec_cross_table("TB('1001','未审数')", _sample_cross_data()) == 48.0


def test_exec_tb_sum_multiple():
    """TB('1001','期末') + TB('1002','期末') → 累加"""
    val = _exec_cross_table(
        "TB('1001','期末') + TB('1002','期末')", _sample_cross_data()
    )
    assert val == 1000.0


def test_exec_tb_subtraction():
    """TB('1002','期末') - TB('1001','期末') → 减法"""
    val = _exec_cross_table(
        "TB('1002','期末') - TB('1001','期末')", _sample_cross_data()
    )
    assert val == 900.0


def test_exec_report():
    """REPORT('BS-002','期末') → current"""
    assert _exec_cross_table("REPORT('BS-002','期末')", _sample_cross_data()) == 1000.0
    assert _exec_cross_table("REPORT('BS-002','期初')", _sample_cross_data()) == 800.0


def test_exec_wp():
    """WP('E1','审定表E1','B5') → cells 字典查值"""
    assert (
        _exec_cross_table("WP('E1','审定表E1','B5')", _sample_cross_data()) == 50.0
    )
    assert (
        _exec_cross_table("WP('E1','审定表E1','C5')", _sample_cross_data()) == 40.0
    )


def test_exec_note():
    """NOTE('五、3','合计','期末') → total_closing"""
    val = _exec_cross_table("NOTE('五、3','合计','期末')", _sample_cross_data())
    assert val == 1200.0


def test_exec_mixed_tb_wp():
    """TB + WP 混合公式"""
    val = _exec_cross_table(
        "TB('1001','期末') + WP('E1','审定表E1','C5')", _sample_cross_data()
    )
    assert val == 90.0  # 50 + 40


def test_exec_unknown_account_returns_zero():
    """不存在的科目 → audited 默认 0（不崩溃）"""
    val = _exec_cross_table("TB('9999','期末')", _sample_cross_data())
    # _resolve_single_cross_ref 对存在的 column 但不存在的 account 返回 0（audited=0）
    assert val == 0.0


def test_exec_unknown_wp_returns_none():
    """不存在的底稿 cell → None（被认为无法解析）"""
    val = _exec_cross_table("WP('UNKNOWN','sheet','A1')", _sample_cross_data())
    assert val is None


def test_exec_invalid_expression_returns_none():
    """非法表达式 / 空字符串 → None（不抛异常）"""
    assert _exec_cross_table("", _sample_cross_data()) is None
    assert _exec_cross_table("garbage()", _sample_cross_data()) is None
    assert _exec_cross_table(None, _sample_cross_data()) is None


def test_resolve_single_ref_with_invalid_period():
    """TB column 既非审定/未审/期初/期末 → 返回 None"""
    val = _resolve_single_cross_ref("TB('1001','xx')", _sample_cross_data())
    assert val is None


# ---------------------------------------------------------------------------
# 单测 3：compute_formula_coverage 覆盖率统计
# ---------------------------------------------------------------------------


def test_coverage_full_with_account_codes():
    """全部明细行带 account_codes → 覆盖率 100%（合计 + 明细全部生成）"""
    table_data = {
        **_cash_template(),
        "_check_presets": ["balance", "sub_item"],
    }
    stats = compute_formula_coverage(table_data)
    # 4 行 × 2 列 = 8 cells，全部可生成公式
    assert stats["total_cells"] == 8
    assert stats["configured_cells"] == 8
    assert stats["coverage_pct"] == 100.0


def test_coverage_partial_when_no_account_codes():
    """部分行无 account_codes → 覆盖率下降"""
    template = {
        "headers": ["项目", "期末余额", "期初余额"],
        "rows": [
            {"label": "应收账款", "account_codes": ["1122"], "is_total": False},
            {"label": "减：坏账准备", "account_codes": [], "is_total": False},  # 无源
            {"label": "合计", "account_codes": [], "is_total": True},
        ],
        "_check_presets": ["balance", "sub_item"],
    }
    stats = compute_formula_coverage(template)
    # 3 行 × 2 列 = 6 cells；明细第 0 行 2 + 合计行 2 = 4 配置
    assert stats["total_cells"] == 6
    assert stats["configured_cells"] == 4
    assert stats["coverage_pct"] == round(4 * 100 / 6, 1)


def test_coverage_target_meets_80pct_typical_seed():
    """种子模板典型场景下覆盖率 ≥ 80%（任务 4.1 验收目标）"""
    # 模拟实际种子模板（货币资金 + 应收账款 + 营业收入 3 个章节）
    sections = [
        {  # 货币资金 — 全有 account_codes
            "headers": ["项目", "期末余额", "期初余额"],
            "rows": [
                {"label": "库存现金", "account_codes": ["1001"], "is_total": False},
                {"label": "银行存款", "account_codes": ["1002"], "is_total": False},
                {"label": "合计", "account_codes": [], "is_total": True},
            ],
            "_check_presets": ["balance", "sub_item"],
        },
        {  # 应收账款 — 部分缺
            "headers": ["项目", "期末余额", "期初余额"],
            "rows": [
                {"label": "应收账款", "account_codes": ["1122"], "is_total": False},
                {"label": "减：坏账准备", "account_codes": ["1231"], "is_total": False},
                {"label": "合计", "account_codes": [], "is_total": True},
            ],
            "_check_presets": ["balance", "sub_item"],
        },
        {  # 营业收入 — 报表行兜底
            "headers": ["项目", "本期金额", "上期金额"],
            "rows": [
                {"label": "主营业务收入", "account_codes": ["6001"], "is_total": False},
                {"label": "合计", "account_codes": [], "is_total": True},
            ],
            "_check_presets": ["balance"],
        },
    ]
    total = 0
    configured = 0
    for td in sections:
        s = compute_formula_coverage(td)
        total += s["total_cells"]
        configured += s["configured_cells"]
    coverage = round(configured * 100 / total, 1)
    assert coverage >= 80.0, f"覆盖率 {coverage}% < 80% 目标"


def test_coverage_empty_table():
    """空表 → 0%"""
    assert compute_formula_coverage({}) == {
        "total_cells": 0,
        "configured_cells": 0,
        "coverage_pct": 0.0,
    }
    assert compute_formula_coverage(None)["coverage_pct"] == 0.0


# ---------------------------------------------------------------------------
# 集成测试：DB 加载 + execute_note_formulas
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def project_with_data(db_session: AsyncSession):
    pid = uuid.uuid4()
    uid = uuid.uuid4()
    project = Project(
        id=pid,
        name="附注L4_2025",
        client_name="测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=uid,
    )
    db_session.add(project)

    # 试算表
    db_session.add(
        TrialBalance(
            project_id=pid,
            year=2025,
            company_code="001",
            standard_account_code="1001",
            account_name="库存现金",
            account_category=AccountCategory.asset,
            unadjusted_amount=Decimal("50000"),
            audited_amount=Decimal("50000"),
            opening_balance=Decimal("40000"),
        )
    )
    db_session.add(
        TrialBalance(
            project_id=pid,
            year=2025,
            company_code="001",
            standard_account_code="1002",
            account_name="银行存款",
            account_category=AccountCategory.asset,
            unadjusted_amount=Decimal("950000"),
            audited_amount=Decimal("950000"),
            opening_balance=Decimal("760000"),
        )
    )

    # 报表
    db_session.add(
        FinancialReport(
            project_id=pid,
            year=2025,
            report_type=FinancialReportType.balance_sheet,
            row_code="BS-002",
            row_name="货币资金",
            current_period_amount=Decimal("1000000"),
            prior_period_amount=Decimal("800000"),
        )
    )

    # 底稿（带 wp_code 的 parsed_data）
    wp_index = WpIndex(
        project_id=pid,
        wp_code="E1",
        wp_name="货币资金审定表",
        audit_cycle="E",
    )
    db_session.add(wp_index)
    await db_session.flush()
    db_session.add(
        WorkingPaper(
            project_id=pid,
            wp_index_id=wp_index.id,
            file_path="/tmp/E1.xlsx",
            source_type=WpSourceType.template,
            status=WpFileStatus.draft,
            review_status=WpReviewStatus.not_submitted,
            parsed_data={
                "wp_code": "E1",
                "cells": {"审定表E1!B5": 50000.0, "审定表E1!C5": 40000.0},
            },
        )
    )

    # 附注（待执行公式）
    db_session.add(
        DisclosureNote(
            project_id=pid,
            year=2025,
            note_section="五、1",
            section_title="货币资金",
            content_type="table",
            sort_order=1,
            source_template=SourceTemplate.soe,
            status=NoteStatus.draft,
            table_data={
                "headers": ["项目", "期末余额", "期初余额"],
                "rows": [
                    {
                        "label": "库存现金",
                        "account_codes": ["1001"],
                        "is_total": False,
                        "values": [None, None],
                    },
                    {
                        "label": "银行存款",
                        "account_codes": ["1002"],
                        "is_total": False,
                        "values": [None, None],
                    },
                    {
                        "label": "合计",
                        "account_codes": [],
                        "is_total": True,
                        "values": [None, None],
                    },
                ],
                "_check_presets": ["balance", "sub_item"],
            },
        )
    )
    await db_session.commit()
    return pid


@pytest.mark.asyncio
async def test_load_cross_table_data_includes_wp(
    db_session: AsyncSession, project_with_data
):
    """_load_cross_table_data 同时加载 report/tb/notes/wp 四类"""
    cross = await _load_cross_table_data(db_session, project_with_data, 2025)
    # report
    assert "BS-002" in cross["report"]
    assert cross["report"]["BS-002"]["current"] == 1000000.0
    # tb
    assert cross["tb"]["1001"]["audited"] == 50000.0
    # wp（L-4 task 4.1 新增）
    assert "E1" in cross["wp"]
    assert cross["wp"]["E1"]["审定表E1!B5"] == 50000.0


@pytest.mark.asyncio
async def test_execute_note_formulas_fills_detail_via_tb(
    db_session: AsyncSession, project_with_data
):
    """execute_note_formulas 自动从 TB 填充明细行 + 合计自动汇总"""
    result = await execute_note_formulas(db_session, project_with_data, 2025, "五、1")
    await db_session.commit()

    assert result["updated"] >= 6  # 2 明细行 × 2 列 + 1 合计行 × 2 列
    # 重新加载验证
    import sqlalchemy as sa

    note_q = await db_session.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_with_data,
            DisclosureNote.note_section == "五、1",
        )
    )
    note = note_q.scalar_one()
    rows = note.table_data["rows"]
    # 库存现金期末
    assert rows[0]["values"][0] == 50000.0
    # 银行存款期初
    assert rows[1]["values"][1] == 760000.0
    # 合计行（=纵向求和）
    assert rows[2]["values"][0] == 1000000.0  # 50k + 950k
    assert rows[2]["values"][1] == 800000.0  # 40k + 760k


@pytest.mark.asyncio
async def test_compute_project_formula_coverage_aggregate(
    db_session: AsyncSession, project_with_data
):
    """项目级覆盖率统计返回 by_section + 总体"""
    stats = await compute_project_formula_coverage(db_session, project_with_data, 2025)
    assert stats["total_cells"] > 0
    assert stats["configured_cells"] > 0
    assert stats["coverage_pct"] >= 80.0
    assert any(s["note_section"] == "五、1" for s in stats["by_section"])
