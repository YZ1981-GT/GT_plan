"""deliverable-center 完整性 + 一致性属性化测试（Property 18 / 19）

后端 PBT 用 Hypothesis，遵循项目铁律 max_examples=5。
每个 hypothesis 样例独立建内存库，避免函数级 fixture 与多样例共享脏数据。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Project, User
from app.models.phase13_models import (
    WordExportStatus,
    WordExportTask,
    WordExportTaskVersion,
)
from app.models.report_models import AuditReport
from app.services.completeness_service import CompletenessService

# Feature: audit-report-deliverable-center

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_TABLES = [
    User.__table__,
    Project.__table__,
    WordExportTask.__table__,
    WordExportTaskVersion.__table__,
    AuditReport.__table__,
]

TRIO = ("audit_report", "financial_report", "disclosure_notes")
_HASH_POOL = ["tb_h1", "tb_h2"]


# 单类交付物规格：(present, confirmed, hash_idx, fr_covers_bs_is)
_doc_spec = st.tuples(
    st.booleans(),                       # present
    st.booleans(),                       # confirmed
    st.integers(min_value=0, max_value=1),  # hash idx
    st.booleans(),                       # 仅 financial_report 用：是否含 BS+IS
)


def _build_and_check(ar_spec, fr_spec, dn_spec, year=2024):
    """在独立内存库中按三件套规格建任务并执行完整性检查，返回 (result, expected)。"""

    async def _runner():
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                user_id = uuid.uuid4()
                project_id = uuid.uuid4()
                suffix = user_id.hex[:8]
                session.add(
                    User(
                        id=user_id,
                        username=f"cmp_{suffix}",
                        email=f"cmp_{suffix}@test.com",
                        hashed_password="x",
                        role=UserRole.manager,
                    )
                )
                session.add(
                    Project(
                        id=project_id,
                        name="完整性测试项目",
                        client_name="完整性客户",
                        project_type=ProjectType.annual,
                        status=ProjectStatus.planning,
                        created_by=user_id,
                    )
                )
                await session.flush()

                base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
                specs = {
                    "audit_report": ar_spec,
                    "financial_report": fr_spec,
                    "disclosure_notes": dn_spec,
                }
                # 独立计算期望值
                present = {dt: specs[dt][0] for dt in TRIO}
                confirmed = {dt: (specs[dt][0] and specs[dt][1]) for dt in TRIO}
                hashes = {dt: _HASH_POOL[specs[dt][2]] for dt in TRIO if present[dt]}
                fr_covers = specs["financial_report"][3]

                for i, dt in enumerate(TRIO):
                    if not present[dt]:
                        continue
                    status = (
                        WordExportStatus.confirmed.value
                        if confirmed[dt]
                        else WordExportStatus.editing.value
                    )
                    created = base_time + timedelta(seconds=i)
                    task = WordExportTask(
                        project_id=project_id,
                        doc_type=dt,
                        status=status,
                        file_path=f"/storage/{dt}.docx",
                        created_by=user_id,
                        created_at=created,
                        updated_at=created,
                        source_snapshot_refs={"tb_hash": hashes[dt], "year": year},
                    )
                    if dt == "financial_report":
                        task.selected_sections = (
                            ["balance_sheet", "income_statement"]
                            if fr_covers
                            else ["cash_flow"]
                        )
                    session.add(task)
                await session.flush()

                result = await CompletenessService(session).check(project_id, year)

                # 期望值推导
                all_present = all(present.values())
                fr_complete = present["financial_report"] and fr_covers
                qualified = all_present and fr_complete  # 三件套齐全
                has_confirmed = any(confirmed.values())
                present_hashes = list(hashes.values())
                if len(present_hashes) < 2:
                    trio_consistent = True
                else:
                    trio_consistent = len(set(present_hashes)) == 1
                passed = qualified and has_confirmed and trio_consistent

                expected = {
                    "qualified": qualified,
                    "has_confirmed": has_confirmed,
                    "trio_consistent": trio_consistent,
                    "passed": passed,
                }
                return result, expected
        finally:
            await engine.dispose()

    return asyncio.run(_runner())


@given(ar=_doc_spec, fr=_doc_spec, dn=_doc_spec)
@settings(max_examples=5, deadline=None)
def test_trio_completeness_decision(ar, fr, dn):
    # Feature: audit-report-deliverable-center, Property 18: 三件套齐全性判定
    """Property 18: 齐全 当且仅当 三类必需件均存在（财务报表至少含 BS+IS）。"""
    result, expected = _build_and_check(ar, fr, dn)
    # 服务以 missing_doc_types + missing_financial_reports 表达「不齐全」
    service_qualified = (
        not result.missing_doc_types and not result.missing_financial_reports
    )
    assert service_qualified == expected["qualified"]


@given(ar=_doc_spec, fr=_doc_spec, dn=_doc_spec)
@settings(max_examples=5, deadline=None)
def test_completeness_pass_decision(ar, fr, dn):
    # Feature: audit-report-deliverable-center, Property 19: 完整性通过判定
    """Property 19: passed 当且仅当 (三件套齐全 且 至少一类 confirmed 且 三件套一致)。"""
    result, expected = _build_and_check(ar, fr, dn)
    assert result.passed == expected["passed"]
    assert result.has_confirmed == expected["has_confirmed"]
    assert result.trio_consistent == expected["trio_consistent"]
