"""试算表行的上游溯源（spec voucher-workflow-linkage-lineage-closure R8.1 / R8.3，design §10.1）

SQLite 真 ORM 行，走生产路径 ``tb_row_upstream`` 与 ``UnifiedLineageService.query_lineage``：

- 构成：本年度、全部主体合计（别的年度、别的科目、已删的行不算）；本年度没有这个科目返回空；
- 已批准调整：与试算表调整列同口径（分录行标准科目 = 本科目、已批准、最终处理排除的组不算），逐组一条；
  底稿汇聚来的照样列出、注明随审定表发布计入，并带来源底稿；
- 发布底稿：映射表对应、本项目已生成的底稿，发布记录（审定表编码）归到所在底稿，时间按北京时间；
- 抽凭 / 挂凭：按底稿数凭证张数（同一凭证被两个批次抽到算一张），登记科目以本科目开头；
- 每类最多 50 条，超出写「另有 n 条未列出」；年度缺省取项目审计年度，取不到报 TB_LINEAGE_YEAR_REQUIRED；
- 统一溯源：tb_row 子源失败只标 partial，不影响别的子源（R8.3）。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import (
    AccountCategory,
    Adjustment,
    AdjustmentEntry,
    AdjustmentType,
    ReviewStatus,
    TbPublishAck,
    TrialBalance,
)
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.models.workpaper_models import SampledVoucher, WorkingPaper, WpIndex, WpSourceType, WpStatus
from app.services import adjustment_treatment_service, tb_row_lineage
from app.services.tb_row_lineage import MAX_ITEMS, TbLineageYearRequired, tb_row_upstream
from app.services.unified_lineage_service import UnifiedLineageService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
pytestmark = pytest.mark.asyncio

USER, PROJECT, NO_YEAR_PROJECT = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
WP_D2, WP_E1, WP_GONE = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
YEAR = 2025
G_MANUAL, G_RJE, G_DRAFT, G_DELETED, G_FROM_WP, G_OTHER_ACCOUNT, G_EXCLUDED, G_OTHER_YEAR = (uuid.uuid4() for _ in range(8))


def _tb(code: str, company: str, *, year: int = YEAR, deleted: bool = False, **amounts) -> TrialBalance:
    values = {"unadjusted_amount": Decimal("0"), "aje_adjustment": Decimal("0"), "rje_adjustment": Decimal("0"),
              "wp_adjustment": Decimal("0"), "audited_amount": Decimal("0")}
    values.update({k: Decimal(v) for k, v in amounts.items()})
    return TrialBalance(project_id=PROJECT, year=year, company_code=company, standard_account_code=code,
                        account_name=code, account_category=AccountCategory.asset, is_deleted=deleted, **values)


def _adjustment(group: uuid.UUID, no: str, lines: list[tuple[str, str, str]], *, status=ReviewStatus.approved,
                year: int = YEAR, deleted: bool = False, origin: str = "manual", source_ref: str | None = None,
                description: str = "补提坏账", kind=AdjustmentType.aje) -> list:
    """一组调整：每行 (标准科目, 借, 贷) 一条头表行 + 一条明细行。"""
    rows: list = []
    for line_no, (code, debit, credit) in enumerate(lines, start=1):
        head = Adjustment(id=uuid.uuid4(), project_id=PROJECT, year=year, company_code="001", adjustment_no=no,
                          adjustment_type=kind, description=description, account_code=code,
                          debit_amount=Decimal(debit), credit_amount=Decimal(credit), entry_group_id=group,
                          review_status=status, origin=origin, source_ref=source_ref, is_deleted=deleted,
                          created_by=USER)
        rows.append(head)
        rows.append(AdjustmentEntry(adjustment_id=head.id, entry_group_id=group, line_no=line_no,
                                    standard_account_code=code, debit_amount=Decimal(debit),
                                    credit_amount=Decimal(credit), is_deleted=deleted))
    return rows


def _sv(no: str, *, wp=WP_D2, batch: uuid.UUID | None = None, account: str = "1122.01", year: int = YEAR,
        deleted: bool = False, vdate: date = date(2025, 3, 5)) -> SampledVoucher:
    return SampledVoucher(project_id=PROJECT, year=year, voucher_no=no, voucher_date=vdate, company_code="001",
                          voucher_type="记", account_code=account, working_paper_id=wp, batch_id=batch,
                          is_deleted=deleted)


@pytest.fixture(autouse=True)
def _treatment_excludes_one_group(monkeypatch):
    """最终处理（客户已入账 / 不予更正）排除的组：在被测函数的下一层替换取数。"""
    async def _excluded(_db, *, project_id, year, group_ids=None):
        return {G_EXCLUDED} if project_id == PROJECT and year == YEAR else set()

    monkeypatch.setattr(adjustment_treatment_service, "effective_excluded_group_ids", _excluded)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(User(id=USER, username="u", email="u@t.com", hashed_password="x", role="auditor"))
        session.add(Project(id=PROJECT, name="溯源", client_name="测试", project_type=ProjectType.annual,
                            status=ProjectStatus.execution, created_by=USER, audit_period_end=date(2025, 12, 31)))
        session.add(Project(id=NO_YEAR_PROJECT, name="没年度", client_name="测试", project_type=ProjectType.annual,
                            status=ProjectStatus.execution, created_by=USER))
        for wp_id, code, deleted in ((WP_D2, "D2", False), (WP_E1, "E1", False), (WP_GONE, "D2-1", True)):
            wi = WpIndex(id=uuid.uuid4(), project_id=PROJECT, wp_code=code, wp_name=f"{code} 名称", audit_cycle=code[0],
                         status=WpStatus.not_started)
            session.add(wi)
            session.add(WorkingPaper(id=wp_id, project_id=PROJECT, wp_index_id=wi.id, file_path="x.xlsx",
                                     source_type=WpSourceType.template, file_version=1, is_deleted=deleted))
        session.add_all([
            _tb("1122", "001", unadjusted_amount="1000.50", aje_adjustment="1000", rje_adjustment="-300",
                wp_adjustment="20", audited_amount="1720.50"),
            _tb("1122", "002", unadjusted_amount="500", audited_amount="500"),
            _tb("1122", "003", unadjusted_amount="999999", audited_amount="999999", deleted=True),
            _tb("1122", "001", year=2024, unadjusted_amount="7", audited_amount="7"),
            _tb("1123", "001", unadjusted_amount="88", audited_amount="88"),
        ])
        session.add_all(
            _adjustment(G_MANUAL, "AJE-001", [("1122", "1000", "0"), ("6702", "0", "1000")])
            + _adjustment(G_RJE, "RJE-002", [("1122", "0", "300"), ("2241", "300", "0")], kind=AdjustmentType.rje,
                          description="重分类")
            + _adjustment(G_DRAFT, "AJE-003", [("1122", "50", "0")], status=ReviewStatus.draft)
            + _adjustment(G_DELETED, "AJE-004", [("1122", "60", "0")], deleted=True)
            + _adjustment(G_FROM_WP, "AJE-005", [("1122", "20", "0")], origin="workpaper",
                          source_ref=f"{WP_D2}:D2-adj-1", description="底稿调整")
            + _adjustment(G_OTHER_ACCOUNT, "AJE-006", [("1123", "70", "0")])
            + _adjustment(G_EXCLUDED, "AJE-007", [("1122", "80", "0")], description="客户已入账")
            + _adjustment(G_OTHER_YEAR, "AJE-008", [("1122", "90", "0")], year=2024)
        )
        session.add_all([
            TbPublishAck(project_id=PROJECT, year=YEAR, wp_code="D2-1", publish_token="t1",
                         created_at=datetime(2026, 10, 28, 9, 0, tzinfo=timezone.utc)),
            TbPublishAck(project_id=PROJECT, year=YEAR, wp_code="D2-1", publish_token="t2",
                         created_at=datetime(2026, 10, 29, 2, 8, tzinfo=timezone.utc)),
            TbPublishAck(project_id=PROJECT, year=2024, wp_code="D2-1", publish_token="t3",
                         created_at=datetime(2026, 11, 1, 2, 8, tzinfo=timezone.utc)),
        ])
        batch_a, batch_b = uuid.uuid4(), uuid.uuid4()
        session.add_all([
            _sv("0001", batch=batch_a), _sv("0001", batch=batch_b),       # 同一凭证两个批次：算一张
            _sv("0002", batch=batch_a, account="1122"),
            _sv("0003"),                                                  # 手工挂凭
            _sv("0004", batch=batch_a, account="1123.01"),                # 别的科目
            _sv("0005", deleted=True),                                    # 已删
            _sv("0006", year=2024),                                       # 别的年度
            _sv("0007", wp=WP_E1, account="1002"),                        # 别的底稿别的科目
            _sv("0008", wp=WP_GONE),                                      # 底稿已删除
        ])
        await session.commit()
        yield session
    await engine.dispose()


def _labels(items) -> list[str]:
    return [i.label for i in items]


async def test_four_kinds_of_upstream(db):
    items = await tb_row_upstream(db, PROJECT, "1122", YEAR)
    labels = _labels(items)
    # 1. 构成：两个主体合计；有底稿发布分量才显示
    assert labels[0] == "构成：未审 1,500.50 · 调整 1,000.00 · 重分类 -300.00 · 底稿发布 20.00 · 审定 2,220.50"
    assert items[0].wp_code == ""
    # 2. 已批准调整：草稿、已删、别的科目、最终处理排除、别的年度都不出；底稿汇聚的注明并带来源底稿
    adjustments = [i for i in items if i.label.startswith(("AJE-", "RJE-"))]
    assert _labels(adjustments) == [
        "AJE-001 补提坏账 借 1,000.00",
        "AJE-005 底稿调整 借 20.00（来自底稿 D2，随审定表发布计入）",
        "RJE-002 重分类 贷 300.00",
    ]
    assert [(i.wp_code, i.wp_id) for i in adjustments] == [("", None), ("D2", str(WP_D2)), ("", None)]
    # 3. 发布底稿：D2（映射表对应 1122）有 D2-1 的发布记录，取本年度最近一次，北京时间；已删的 D2-1 底稿不出
    published = [i for i in items if "发布审定数" in i.label]
    assert [(i.wp_code, i.wp_id, i.label) for i in published] == [
        ("D2", str(WP_D2), "D2 D2 名称 · 最近一次发布审定数 2026-10-29 10:08")]
    # 4. 抽凭 / 挂凭：同一凭证两个批次算一张；别的科目、已删、别的年度、已删底稿不算；E1 没有 1122 的登记
    sampling = [i for i in items if "抽凭" in i.label or "挂凭" in i.label]
    assert [(i.wp_code, i.wp_id, i.label) for i in sampling] == [("D2", str(WP_D2), "D2 抽凭 2 张 · 挂凭 1 张")]
    assert len(items) == 1 + len(adjustments) + len(published) + len(sampling)


async def test_account_not_in_trial_balance_returns_empty(db):
    # 本年度试算表没有这个科目（合并项目的试算表在合并模块，trial_balance 为空）：不列别的
    assert await tb_row_upstream(db, PROJECT, "6702", YEAR) == []
    assert await tb_row_upstream(db, PROJECT, "1122", 2023) == []
    assert await tb_row_upstream(db, PROJECT, "  ", YEAR) == []


async def test_year_defaults_to_project_audit_year_or_reports_missing(db):
    assert _labels(await tb_row_upstream(db, PROJECT, "1122", None)) == _labels(await tb_row_upstream(db, PROJECT, "1122", YEAR))
    with pytest.raises(TbLineageYearRequired):
        await tb_row_upstream(db, NO_YEAR_PROJECT, "1122", None)


async def test_each_kind_capped_at_max_items(db):
    groups = []
    for i in range(MAX_ITEMS + 2):
        groups += _adjustment(uuid.uuid4(), f"AJE-1{i:03d}", [("1122", "1", "0")], description=f"批量{i}")
    db.add_all(groups)
    await db.flush()
    labels = _labels(await tb_row_upstream(db, PROJECT, "1122", YEAR))
    adjustments = [label for label in labels if label.startswith(("AJE-", "RJE-"))]
    assert len(adjustments) == MAX_ITEMS
    assert "另有 5 条未列出" in labels  # 3 条原有 + 52 条新增，列 50 条


async def test_unified_lineage_tb_row_branch(db, monkeypatch):
    async def _no_attachments(self, project_id, object_type, object_id):
        return []

    monkeypatch.setattr(UnifiedLineageService, "_query_attachments", _no_attachments)
    service = UnifiedLineageService(db)
    result = await service.query_lineage(PROJECT, "tb_row", "1122", direction="both", year=YEAR)
    assert result["partial"] is False and result["errors"] == []
    assert [u["label"] for u in result["upstream"]] == _labels(await tb_row_upstream(db, PROJECT, "1122", YEAR))
    assert result["downstream"] == []
    # 只要下游：不跑试算表行子源
    down = await service.query_lineage(PROJECT, "tb_row", "1122", direction="downstream", year=YEAR)
    assert down["upstream"] == [] and down["partial"] is False


async def test_unified_lineage_tb_row_failure_is_partial_not_empty(db, monkeypatch):
    async def _attachments(self, project_id, object_type, object_id):
        return [{"id": "l1", "attachment_id": "a1", "target_type": object_type, "target_ref": object_id}]

    monkeypatch.setattr(UnifiedLineageService, "_query_attachments", _attachments)
    service = UnifiedLineageService(db)
    no_year = await service.query_lineage(NO_YEAR_PROJECT, "tb_row", "1122", direction="both")
    assert no_year["partial"] is True
    assert no_year["errors"] == [{"source": "tb_row", "status": 422, "error_code": "TB_LINEAGE_YEAR_REQUIRED",
                                  "message": "项目未设置审计年度，不能取试算表行的数据溯源"}]
    assert [a["id"] for a in no_year["attachments"]] == ["l1"]  # 附件子源不受影响（R8.3）

    async def _boom(*_a, **_kw):
        raise RuntimeError("trial_balance 读失败")

    monkeypatch.setattr(tb_row_lineage, "_composition", _boom)
    failed = await service.query_lineage(PROJECT, "tb_row", "1122", direction="both", year=YEAR)
    assert failed["partial"] is True and failed["upstream"] == []
    assert failed["errors"][0]["source"] == "tb_row" and "试算表行溯源查询失败" in failed["errors"][0]["message"]
    assert [a["id"] for a in failed["attachments"]] == ["l1"]
