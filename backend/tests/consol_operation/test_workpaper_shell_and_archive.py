"""批 6：薄底稿壳幂等创建 + 归档 provider fail-closed。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401
from app.models.base import Base, ProjectStatus
from app.models.consol_operation_models import ConsolOperation
from app.models.core import Project, User
from app.models.report_generation_models import ConsolArtifact, ReportGenerationRun
from app.models.workpaper_models import WpIndex, WorkingPaper
from app.services.consol_archive_provider import (
    archive_items_complete,
    collect_consol_archive_items,
)
from app.services.consol_workpaper_shell import (
    WP_CODE,
    ensure_consol_workpaper_shell,
    get_consol_workpaper_shell,
)

YEAR = 2025
_TABLES = [
    User.__table__, Project.__table__, ConsolOperation.__table__,
    ReportGenerationRun.__table__, ConsolArtifact.__table__,
    WpIndex.__table__, WorkingPaper.__table__,
]


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _project() -> Project:
    return Project(
        id=uuid.uuid4(), name="【测试】归档壳_2025", client_name="【测试】归档壳",
        company_code="SH", audit_year=YEAR, report_scope="consolidated",
        status=ProjectStatus.execution,
    )


class TestWorkpaperShell:
    @pytest.mark.asyncio
    async def test_idempotent_create_and_update(self, db: AsyncSession):
        p = _project(); db.add(p); await db.commit()
        first = await ensure_consol_workpaper_shell(db, p.id)
        await db.commit()
        assert first["created"] is True
        assert first["wp_code"] == WP_CODE

        second = await ensure_consol_workpaper_shell(db, p.id, artifact_path="consol://new/path.xlsx")
        await db.commit()
        assert second["created"] is False
        assert second["wp_index_id"] == first["wp_index_id"]
        assert second["working_paper_id"] == first["working_paper_id"]

        shell = await get_consol_workpaper_shell(db, p.id)
        assert shell is not None
        assert shell["file_path"] == "consol://new/path.xlsx"

    @pytest.mark.asyncio
    async def test_no_shell_returns_none(self, db: AsyncSession):
        p = _project(); db.add(p); await db.commit()
        assert await get_consol_workpaper_shell(db, p.id) is None


class TestArchiveProvider:
    @pytest.mark.asyncio
    async def test_no_operation_is_missing(self, db: AsyncSession):
        p = _project(); db.add(p); await db.commit()
        items = await collect_consol_archive_items(db, p.id, YEAR)
        assert not archive_items_complete(items)
        assert items[0]["status"] == "missing"

    @pytest.mark.asyncio
    async def test_complete_archive_with_all_artifacts(self, db: AsyncSession):
        p = _project(); db.add(p); await db.commit()
        now = datetime.now(timezone.utc)
        op = ConsolOperation(
            id=uuid.uuid4(), project_id=p.id, year=YEAR, operation_type="refresh_all",
            idempotency_key="k", idempotency_keys={}, request_hash="h" * 64,
            request_payload={}, context_json={}, version_vector={}, status="succeeded",
            revision=1, trigger_source="manual", steps=[], errors=[],
            result_refs={}, metrics={}, finished_at=now,
        )
        run = ReportGenerationRun(
            id=uuid.uuid4(), project_id=p.id, year=YEAR, trigger="manual",
            operation_id=op.id, operation_revision=1, node_key="SH:consol",
            status="succeeded", calc_version=1, row_digest="d" * 64,
            row_count=5, rows_json={}, finished_at=now,
        )
        op.result_refs = {"report_run_id": str(run.id)}
        db.add_all([op, run])
        for kind in ("report_excel", "consol_workpaper"):
            db.add(ConsolArtifact(
                id=uuid.uuid4(), project_id=p.id, year=YEAR,
                operation_id=op.id, report_run_id=run.id, node_key="SH:consol",
                kind=kind, status="ready", file_name=f"{kind}.xlsx",
                storage_path=f"consol/{kind}.xlsx", content_type="application/xlsx",
                size_bytes=1024, sha256="a" * 64, ready_at=now,
            ))
        await ensure_consol_workpaper_shell(db, p.id)
        await db.commit()

        items = await collect_consol_archive_items(db, p.id, YEAR)
        assert archive_items_complete(items)
        kinds = {item["kind"]: item["status"] for item in items}
        assert kinds["consol_operation"] == "ready"
        assert kinds["report_run"] == "ready"
        assert kinds["report_excel"] == "ready"
        assert kinds["consol_workpaper"] == "ready"
        assert kinds["workpaper_shell"] == "ready"

    @pytest.mark.asyncio
    async def test_missing_artifact_blocks_archive(self, db: AsyncSession):
        """缺少任何 artifact 时 fail-closed。"""
        p = _project(); db.add(p); await db.commit()
        now = datetime.now(timezone.utc)
        op = ConsolOperation(
            id=uuid.uuid4(), project_id=p.id, year=YEAR, operation_type="push",
            idempotency_key="k2", idempotency_keys={}, request_hash="h" * 64,
            request_payload={}, context_json={}, version_vector={}, status="succeeded",
            revision=1, trigger_source="manual", steps=[], errors=[],
            result_refs={}, metrics={}, finished_at=now,
        )
        run = ReportGenerationRun(
            id=uuid.uuid4(), project_id=p.id, year=YEAR, trigger="push",
            operation_id=op.id, operation_revision=1, node_key="SH:consol",
            status="succeeded", calc_version=1, row_digest="d" * 64,
            row_count=3, rows_json={}, finished_at=now,
        )
        op.result_refs = {"report_run_id": str(run.id)}
        db.add_all([op, run])
        # 只有 report_excel，缺 consol_workpaper
        db.add(ConsolArtifact(
            id=uuid.uuid4(), project_id=p.id, year=YEAR,
            operation_id=op.id, report_run_id=run.id, node_key="SH:consol",
            kind="report_excel", status="ready", file_name="report.xlsx",
            storage_path="consol/report.xlsx", content_type="application/xlsx",
            size_bytes=512, sha256="b" * 64, ready_at=now,
        ))
        await db.commit()

        items = await collect_consol_archive_items(db, p.id, YEAR)
        assert not archive_items_complete(items)
        missing = [item for item in items if item["status"] == "missing"]
        assert any("工作底稿包" in item.get("reason", "") for item in missing)
