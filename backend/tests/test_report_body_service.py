"""ReportBodyService 单元测试与属性化测试 — deliverable-center Task 4

覆盖：
- render_html bug 修复回归
- Property 38-50（意见矩阵 / 强调结构 / 形成基础段 / 段落增删往返 /
  KAM 判定+守卫+多条目 / 占位符自动·财务·手工填充 / 渲染往返 / 注册表可扩展）

Feature: audit-report-deliverable-center
"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Project, User
from app.models.report_models import (
    AuditReport,
    AuditReportTemplate,
    CompanyType,
    FinancialReport,
    FinancialReportType,
    OpinionType,
    ReportStatus,
)
from app.services import report_body_service as rbs_module
from app.services.audit_report_service import AuditReportService
from app.services.report_body_service import (
    OPINION_UNQUALIFIED_WITH_EMPHASIS,
    ReportBodyService,
)

# Feature: audit-report-deliverable-center

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
YEAR = 2025

_RB_TABLES = [
    User.__table__,
    Project.__table__,
    AuditReport.__table__,
    AuditReportTemplate.__table__,
    FinancialReport.__table__,
]

DEFAULT_BASIC_INFO = {
    "client_name": "测试股份有限公司",
    "entity_short_name": "测试股份",
    "report_scope": "standalone",
    "signing_partner_name": "张三",
}


async def _seed(
    session: AsyncSession,
    *,
    basic_info: dict | None = None,
    financial: list[tuple[FinancialReportType, str, Decimal]] | None = None,
) -> uuid.UUID:
    """建用户+项目+模板（可选财务行），返回 project_id。"""
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    suffix = user_id.hex[:8]
    session.add(
        User(
            id=user_id,
            username=f"rb_{suffix}",
            email=f"rb_{suffix}@test.com",
            hashed_password="x",
            role=UserRole.admin,
        )
    )
    await session.flush()
    wizard_state = {
        "steps": {"basic_info": {"data": basic_info if basic_info is not None else DEFAULT_BASIC_INFO}}
    }
    session.add(
        Project(
            id=project_id,
            name="报告正文测试项目",
            client_name="报告正文测试",
            project_type=ProjectType.annual,
            status=ProjectStatus.planning,
            created_by=user_id,
            wizard_state=wizard_state,
        )
    )
    await session.flush()

    # 加载意见×公司类型模板矩阵种子
    await AuditReportService(session).load_seed_templates()

    for report_type, row_code, amount in financial or []:
        session.add(
            FinancialReport(
                project_id=project_id,
                year=YEAR,
                report_type=report_type,
                row_code=row_code,
                current_period_amount=amount,
            )
        )
    await session.flush()
    return project_id


def _run(coro_factory, **seed_kwargs):
    """独立内存库运行 coro_factory(session, project_id)。"""

    async def _runner():
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=_RB_TABLES)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                project_id = await _seed(session, **seed_kwargs)
                await session.commit()
                return await coro_factory(session, project_id)
        finally:
            await engine.dispose()

    return asyncio.run(_runner())


# ===========================================================================
# render_html bug 修复回归（Task 4.5）
# ===========================================================================


def test_render_html_method_exists_and_renders():
    """回归：render_html 必须是已定义方法，正确渲染段落名+content+KAM items。"""
    svc = ReportBodyService.__new__(ReportBodyService)  # 无需 db 即可调纯渲染方法
    body = {
        "sections": [
            {"section_id": "opinion", "section_name": "审计意见段", "section_order": 1,
             "content": "第一行\n第二行"},
            {"section_id": "kam", "section_name": "关键审计事项段", "section_order": 2,
             "content": "导语", "items": [{"matter": "收入确认", "response": "我们执行了..."}]},
        ]
    }
    html = svc.render_html(body)
    assert "<h3>审计意见段</h3>" in html
    assert "第一行<br/>第二行" in html
    assert "<h3>关键审计事项段</h3>" in html
    # KAM 多条目渲染
    assert "<strong>收入确认</strong>" in html
    assert "我们执行了..." in html
    # 按 section_order 排序：审计意见段在关键审计事项段之前
    assert html.index("审计意见段") < html.index("关键审计事项段")


# ===========================================================================
# Property 38: 意见×公司类型模板加载矩阵
# ===========================================================================

ALL_OPINIONS = ["unqualified", "qualified", "adverse", "disclaimer",
                OPINION_UNQUALIFIED_WITH_EMPHASIS]
ALL_COMPANY_TYPES = ["listed", "non_listed"]


@given(
    opinion=st.sampled_from(ALL_OPINIONS),
    company_type=st.sampled_from(ALL_COMPANY_TYPES),
)
@settings(max_examples=3, deadline=None)
def test_opinion_company_matrix_loads_nonempty(opinion, company_type):
    # Feature: audit-report-deliverable-center, Property 38: 意见×公司类型模板加载矩阵
    """Property 38: 任一 (意见, 公司类型) 组合均加载到非空正文模板。"""

    async def _body(session, project_id):
        svc = ReportBodyService(session)
        body = await svc.load_body_template(
            opinion, company_type, include_emphasis=True
        )
        assert body["opinion_type"] == opinion
        assert body["company_type"] == company_type
        assert len(body["sections"]) >= 1
        # 段落含稳定 section_id 与段落名
        for sec in body["sections"]:
            assert sec.get("section_id")
            assert sec.get("section_name")

    _run(_body)


# ===========================================================================
# Property 39: 强调意见模板结构
# ===========================================================================


@given(company_type=st.sampled_from(ALL_COMPANY_TYPES))
@settings(max_examples=3, deadline=None)
def test_emphasis_template_structure(company_type):
    # Feature: audit-report-deliverable-center, Property 39: 强调意见模板结构
    """Property 39: unqualified_with_emphasis 段落集 = 标准无保留意见段落集 ∪ {可删强调事项段}。"""

    async def _body(session, project_id):
        svc = ReportBodyService(session)
        unq = await svc.load_body_template("unqualified", company_type)
        uwe = await svc.load_body_template(
            OPINION_UNQUALIFIED_WITH_EMPHASIS, company_type, include_emphasis=True
        )
        unq_ids = {s["section_id"] for s in unq["sections"]}
        uwe_ids = {s["section_id"] for s in uwe["sections"]}
        assert uwe_ids == unq_ids | {"emphasis"}
        emphasis = svc.get_section(uwe, "emphasis")
        assert emphasis is not None
        assert emphasis["deletable"] is True
        assert emphasis["is_required"] is False

    _run(_body)


# ===========================================================================
# Property 40: 非无保留意见含形成基础段
# ===========================================================================


@given(
    opinion=st.sampled_from(["qualified", "adverse", "disclaimer"]),
    company_type=st.sampled_from(ALL_COMPANY_TYPES),
)
@settings(max_examples=3, deadline=None)
def test_non_unqualified_has_basis_section(opinion, company_type):
    # Feature: audit-report-deliverable-center, Property 40: 非无保留意见含形成基础段
    """Property 40: qualified/adverse/disclaimer 模板均含「形成X意见的基础」段。"""

    async def _body(session, project_id):
        svc = ReportBodyService(session)
        body = await svc.load_body_template(opinion, company_type)
        basis = [
            s for s in body["sections"]
            if "形成" in s["section_name"] and "基础" in s["section_name"]
        ]
        assert len(basis) >= 1

    _run(_body)


# ===========================================================================
# Property 41: 可选段落增删往返
# ===========================================================================


@given(company_type=st.sampled_from(ALL_COMPANY_TYPES))
@settings(max_examples=3, deadline=None)
def test_optional_section_delete_add_roundtrip(company_type):
    # Feature: audit-report-deliverable-center, Property 41: 可选段落增删往返
    """Property 41: 删除可删段后以模板默认内容增回，正文段落结构恢复一致。"""

    async def _body(session, project_id):
        svc = ReportBodyService(session)
        body = await svc.load_body_template(
            OPINION_UNQUALIFIED_WITH_EMPHASIS, company_type, include_emphasis=True
        )
        original_ids = [s["section_id"] for s in body["sections"]]
        emphasis = svc.get_section(body, "emphasis")
        assert emphasis is not None and emphasis["deletable"] is True

        # 删除
        removed = svc.delete_section(body, "emphasis")
        assert svc.get_section(removed, "emphasis") is None
        # 增回（以原段落内容）
        restored = svc.add_section(removed, emphasis)
        restored_ids = [s["section_id"] for s in restored["sections"]]
        # section_id 集合恢复
        assert set(restored_ids) == set(original_ids)
        # 段落结构恢复一致：按 (section_order, section_id) 确定性排序后逐段等价
        # （emphasis 与 kam 可能共享 section_order，需以 section_id 二级排序消除并列歧义）
        key = lambda s: (s["section_order"], s["section_id"])
        assert sorted(restored["sections"], key=key) == sorted(body["sections"], key=key)

    _run(_body)


# ===========================================================================
# Property 42: KAM 必填判定
# ===========================================================================


@given(
    company_type=st.sampled_from(ALL_COMPANY_TYPES),
    is_pie=st.booleans(),
    opinion=st.sampled_from(["unqualified", "qualified", "adverse", "disclaimer"]),
)
@settings(max_examples=3, deadline=None)
def test_kam_required_decision(company_type, is_pie, opinion):
    # Feature: audit-report-deliverable-center, Property 42: KAM 必填判定
    """Property 42: KAM 必填 ⟺ (listed 或 is_pie) 且非 disclaimer；disclaimer 正文不含 KAM 段。"""

    async def _body(session, project_id):
        svc = ReportBodyService(session)
        required = svc.kam_required(
            company_type=company_type, is_pie=is_pie, opinion_type=opinion
        )
        expected = (company_type == "listed" or is_pie) and opinion != "disclaimer"
        assert required is expected

        # disclaimer 正文不含 KAM 段
        if opinion == "disclaimer":
            body = await svc.load_body_template(opinion, company_type)
            assert svc.get_section(body, "kam") is None
            assert all(s["section_name"] != "关键审计事项段" for s in body["sections"])

    _run(_body)


# ===========================================================================
# Property 43: KAM 必填定稿守卫（沿用 AuditReportService._validate_finalize）
# ===========================================================================


@given(
    has_kam=st.booleans(),
    use_pie=st.booleans(),
)
@settings(max_examples=3, deadline=None)
def test_kam_finalize_guard(has_kam, use_pie):
    # Feature: audit-report-deliverable-center, Property 43: KAM 必填定稿守卫
    """Property 43: 上市/PIE 报告 KAM 为空时 finalize 被阻止；非空时放行。"""

    async def _body(session, project_id):
        ar_svc = AuditReportService(session)
        company_type = CompanyType.non_listed if use_pie else CompanyType.listed
        kam_section = {
            "section_id": "kam",
            "section_name": "关键审计事项段",
            "section_order": 3,
            "items": ([{"matter": "收入确认", "response": "我们执行了..."}] if has_kam else []),
            "content": "" if has_kam else "[请在此处添加关键审计事项]",
        }
        report = AuditReport(
            project_id=project_id,
            year=YEAR,
            opinion_type=OpinionType.unqualified,
            company_type=company_type,
            is_pie=use_pie,
            status=ReportStatus.review,
            report_body_json={"sections": [kam_section]},
            # 预置 dataset 绑定，避免放行路径触发 dataset 绑定查询
            bound_dataset_id=uuid.uuid4(),
        )
        session.add(report)
        await session.flush()

        if has_kam:
            updated = await ar_svc.update_status(report.id, ReportStatus.final)
            assert updated.status == ReportStatus.final
        else:
            with pytest.raises(ValueError):
                await ar_svc.update_status(report.id, ReportStatus.final)

    _run(_body)


# ===========================================================================
# Property 44: KAM 多条目结构
# ===========================================================================


@given(
    items=st.lists(
        st.tuples(
            st.text(min_size=1, max_size=20),
            st.text(min_size=1, max_size=20),
        ),
        min_size=1,
        max_size=5,
    )
)
@settings(max_examples=3, deadline=None)
def test_kam_multi_item_structure(items):
    # Feature: audit-report-deliverable-center, Property 44: KAM 多条目结构
    """Property 44: KAM 条目为数组，每条同含「事项描述」与「审计应对」。"""
    svc = ReportBodyService.__new__(ReportBodyService)
    kam_items = [svc.make_kam_item(m, r) for m, r in items]
    assert isinstance(kam_items, list)
    for (m, r), item in zip(items, kam_items):
        assert set(item.keys()) == {"matter", "response"}
        assert item["matter"] == m
        assert item["response"] == r


def test_kam_section_items_is_array_for_listed():
    """Property 44 配套：上市公司正文 KAM 段 items 为数组形式。"""

    async def _body(session, project_id):
        svc = ReportBodyService(session)
        body = await svc.load_body_template("unqualified", "listed")
        kam = svc.get_section(body, "kam")
        assert kam is not None
        assert isinstance(kam["items"], list)

    _run(_body)


# ===========================================================================
# Property 45: 自动映射占位符填充
# ===========================================================================

AUTO_KEYS = [
    "entity_name", "entity_short_name", "audit_period", "audit_year",
    "report_scope", "signing_partner", "report_date",
]


@given(company_type=st.sampled_from(ALL_COMPANY_TYPES))
@settings(max_examples=3, deadline=None)
def test_auto_placeholder_filled(company_type):
    # Feature: audit-report-deliverable-center, Property 45: 自动映射占位符填充
    """Property 45: 填充后自动映射类占位符全部被替换，正文无残留自动占位符。"""

    async def _body(session, project_id):
        svc = ReportBodyService(session)
        body = await svc.load_body_template("unqualified", company_type)
        filled = await svc.fill_placeholders(
            body, project_id, YEAR, report_date=date(2025, 3, 31)
        )
        for sec in filled["sections"]:
            content = sec["content"]
            for key in AUTO_KEYS:
                assert f"{{{key}}}" not in content, f"残留自动占位符 {key}"
        # 实体名已替换为项目信息
        opinion_sec = svc.get_section(filled, "opinion")
        assert "测试股份有限公司" in opinion_sec["content"]

    _run(_body)


# ===========================================================================
# Property 46: 财务占位符映射正确
# ===========================================================================


@given(
    total_assets=st.integers(min_value=0, max_value=9_999_999),
)
@settings(max_examples=3, deadline=None)
def test_financial_placeholder_mapping(total_assets):
    # Feature: audit-report-deliverable-center, Property 46: 财务占位符映射正确
    """Property 46: 财务占位符填充值 = 注册表所指 financial_report 行的当期金额。"""
    amount = Decimal(total_assets)

    async def _body(session, project_id):
        svc = ReportBodyService(session)
        # 构造含财务占位符的正文段落
        body = {
            "opinion_type": "unqualified",
            "company_type": "non_listed",
            "sections": [
                {
                    "section_id": "opinion",
                    "section_name": "审计意见段",
                    "section_order": 1,
                    "content": "资产总计为 {total_assets} 元。",
                    "items": [],
                }
            ],
        }
        filled = await svc.fill_placeholders(body, project_id, YEAR)
        # 与服务读取同一行金额比对（消除 Decimal/str 表示差异）
        import sqlalchemy as sa

        val = (
            await session.execute(
                sa.select(FinancialReport.current_period_amount).where(
                    FinancialReport.project_id == project_id,
                    FinancialReport.year == YEAR,
                    FinancialReport.report_type == FinancialReportType.balance_sheet,
                    FinancialReport.row_code == "BS-039",
                )
            )
        ).scalar_one()
        expected = str(val)
        content = filled["sections"][0]["content"]
        assert expected in content
        assert "{total_assets}" not in content

    _run(
        _body,
        financial=[(FinancialReportType.balance_sheet, "BS-039", amount)],
    )


# ===========================================================================
# Property 47: 手工占位符保留
# ===========================================================================


@given(company_type=st.sampled_from(ALL_COMPANY_TYPES))
@settings(max_examples=3, deadline=None)
def test_manual_placeholder_preserved(company_type):
    # Feature: audit-report-deliverable-center, Property 47: 手工占位符保留
    """Property 47: 手工填写类占位符（[请...] 提示）在自动填充后保持不变。"""

    async def _body(session, project_id):
        svc = ReportBodyService(session)
        body = await svc.load_body_template(
            OPINION_UNQUALIFIED_WITH_EMPHASIS, company_type, include_emphasis=True
        )
        # 收集填充前所有手工提示
        before = []
        for sec in body["sections"]:
            before.extend(rbs_module._MANUAL_HINT_RE.findall(sec.get("content", "")))
        assert before, "用例前置：应存在手工提示文本"

        filled = await svc.fill_placeholders(
            body, project_id, YEAR, report_date=date(2025, 3, 31)
        )
        after = []
        for sec in filled["sections"]:
            after.extend(rbs_module._MANUAL_HINT_RE.findall(sec.get("content", "")))
        # 手工提示文本逐条保留
        for hint in before:
            assert hint in after

    _run(_body)


# ===========================================================================
# Property 49: 正文生成渲染往返（结构等价）
# ===========================================================================


@given(
    section_specs=st.lists(
        st.tuples(
            st.text(alphabet="甲乙丙丁戊己庚辛", min_size=2, max_size=4),
            st.text(alphabet="abcDEF文本内容", min_size=1, max_size=12),
        ),
        min_size=1,
        max_size=5,
        unique_by=lambda t: t[0],
    )
)
@settings(max_examples=3, deadline=None)
def test_render_roundtrip_structure_equivalence(section_specs):
    # Feature: audit-report-deliverable-center, Property 49: 正文生成渲染往返
    """Property 49: docx 渲染后重解析，段落数量与 section_id 集合与原 JSON 一致。"""
    svc = ReportBodyService.__new__(ReportBodyService)
    sections = []
    for i, (name, content) in enumerate(section_specs):
        sections.append(
            {
                "section_id": f"sec_{i}",
                "section_name": name,
                "section_order": i + 1,
                "content": content,
                "items": [],
            }
        )
    body = {"sections": sections}
    original_ids = {s["section_id"] for s in sections}

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "roundtrip.docx"
        svc.render_docx(body, out)
        assert out.exists()
        parsed_ids = svc.parse_docx_to_section_ids(out, body)
        count = svc.count_docx_paragraph_sections(out, body)

    assert parsed_ids == original_ids
    assert count == len(sections)


# ===========================================================================
# Property 50: 占位符注册表可扩展
# ===========================================================================


def test_placeholder_registry_extensible(monkeypatch):
    # Feature: audit-report-deliverable-center, Property 50: 占位符注册表可扩展
    """Property 50: 注册表新增占位符项，渲染管线无需改核心逻辑即可识别并填充。"""
    base = rbs_module._load_registry()
    extended = {
        "auto": dict(base.get("auto", {})),
        "financial": {
            **base.get("financial", {}),
            # 全新财务占位符项（核心逻辑零改动）
            "new_metric": {"report_type": "balance_sheet", "row_code": "BS-999"},
        },
        "manual": list(base.get("manual", [])),
    }
    monkeypatch.setattr(rbs_module, "_load_registry", lambda: extended)

    async def _body(session, project_id):
        svc = ReportBodyService(session)
        body = {
            "opinion_type": "unqualified",
            "company_type": "non_listed",
            "sections": [
                {
                    "section_id": "opinion",
                    "section_name": "审计意见段",
                    "section_order": 1,
                    "content": "新指标为 {new_metric} 元。",
                    "items": [],
                }
            ],
        }
        filled = await svc.fill_placeholders(body, project_id, YEAR)
        content = filled["sections"][0]["content"]
        assert "{new_metric}" not in content
        assert "888" in content
        # placeholders_resolved 记录了新占位符
        assert "new_metric" in filled["sections"][0]["placeholders_resolved"]

    _run(
        _body,
        financial=[(FinancialReportType.balance_sheet, "BS-999", Decimal(888))],
    )


# ===========================================================================
# Property 48: 财务占位符随源刷新
# ===========================================================================


@given(
    old_assets=st.integers(min_value=0, max_value=9_999_999),
    new_assets=st.integers(min_value=0, max_value=9_999_999),
)
@settings(max_examples=3, deadline=None)
def test_financial_placeholder_refresh_on_source_change(old_assets, new_assets):
    # Feature: audit-report-deliverable-center, Property 48: 财务占位符随源刷新
    """Property 48: 上游财务数据经 REPORTS_UPDATED 变更后，正文中财务数据类占位符
    的值刷新为最新报表值（refresh_financial_placeholders 链路）；
    且自动/手工类占位符（已解析 entity_name / [请...] 提示）不被破坏。
    """
    import sqlalchemy as sa

    old_amount = Decimal(old_assets)
    new_amount = Decimal(new_assets)

    async def _read_bs039(session, project_id) -> str:
        """读取 BS-039 当期金额并以 service 同样的 str() 表示返回（消除 Decimal 标度差异）。"""
        val = (
            await session.execute(
                sa.select(FinancialReport.current_period_amount).where(
                    FinancialReport.project_id == project_id,
                    FinancialReport.year == YEAR,
                    FinancialReport.report_type == FinancialReportType.balance_sheet,
                    FinancialReport.row_code == "BS-039",
                )
            )
        ).scalar_one()
        return str(val)

    async def _body(session, project_id):
        svc = ReportBodyService(session)
        # 1) 用旧财务值构造并填充正文，含财务占位符 + 自动占位符 + 手工提示
        template = {
            "opinion_type": "unqualified",
            "company_type": "non_listed",
            "is_pie": False,
            "sections": [
                {
                    "section_id": "opinion",
                    "section_name": "审计意见段",
                    "section_order": 1,
                    "content": (
                        "{entity_name}资产总计为 {total_assets} 元，"
                        "保留意见事项：[请填写保留意见事项]。"
                    ),
                    "items": [],
                }
            ],
        }
        expected_old = await _read_bs039(session, project_id)
        filled_old = await svc.fill_placeholders(template, project_id, YEAR)
        old_resolved = filled_old["sections"][0]["placeholders_resolved"]
        assert old_resolved["total_assets"]["value"] == expected_old
        # 自动占位符已替换为实体名，手工提示保留
        assert "测试股份有限公司" in filled_old["sections"][0]["content"]
        assert "[请填写保留意见事项]" in filled_old["sections"][0]["content"]

        # 2) 落库 audit_report.report_body_json（模拟“生成正文”后状态）
        report = AuditReport(
            project_id=project_id,
            year=YEAR,
            opinion_type=OpinionType.unqualified,
            company_type=CompanyType.non_listed,
            is_pie=False,
            status=ReportStatus.draft,
            report_body_json=filled_old,
        )
        session.add(report)
        await session.flush()

        # 3) 模拟上游财务数据变更：更新 BS-039 当期金额为新值
        await session.execute(
            sa.update(FinancialReport)
            .where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == YEAR,
                FinancialReport.report_type == FinancialReportType.balance_sheet,
                FinancialReport.row_code == "BS-039",
            )
            .values(current_period_amount=new_amount)
        )
        await session.flush()

        # 4) REPORTS_UPDATED 链路核心：刷新财务占位符
        expected_new = await _read_bs039(session, project_id)
        refreshed = await svc.refresh_financial_placeholders(project_id, YEAR)
        assert refreshed is not None

        new_resolved = refreshed.report_body_json["sections"][0]["placeholders_resolved"]
        # 财务占位符 resolved 值刷新为最新报表值
        assert new_resolved["total_assets"]["type"] == "financial"
        assert new_resolved["total_assets"]["value"] == expected_new
        # 自动/手工类占位符不被破坏：实体名仍在、手工提示仍保留
        new_content = refreshed.report_body_json["sections"][0]["content"]
        assert "测试股份有限公司" in new_content
        assert "[请填写保留意见事项]" in new_content

    _run(
        _body,
        financial=[(FinancialReportType.balance_sheet, "BS-039", old_amount)],
    )
