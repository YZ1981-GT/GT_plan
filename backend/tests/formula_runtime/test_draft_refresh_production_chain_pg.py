"""真实 PG：standalone 公式从 coordinator 到 parsed_data/outbox/audit 的生产链。"""

from __future__ import annotations

import copy
import json
import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.audit_log_models import AuditLogEntry
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.models.workpaper_models import (
    DraftMarker,
    DraftRefreshAudit,
    DraftRefreshSnapshot,
    FormulaRuntimeOutbox,
    WorkingPaper,
    WpFileStatus,
    WpFormula,
    WpIndex,
    WpReviewStatus,
    WpSourceType,
    WpStatus,
)
from app.services.draft_refresh_service import DraftRefreshService
from app.services.formula_management.draft_refresh_orchestrator import DraftRefreshOrchestrator
from app.services.formula_runtime.adapters.workpaper import WorkpaperMutationAdapter
from app.services.formula_runtime.contracts import CanonicalFormulaTarget, FormulaMutation

pytestmark = pytest.mark.pg_only


def _pg_url() -> str:
    url = str(settings.DATABASE_URL)
    return url.replace("postgresql://", "postgresql+asyncpg://", 1) if url.startswith("postgresql://") else url


def _cell_value(parsed_data: dict | None, sheet: str, cell: str):
    data = parsed_data or {}
    value = (((data.get("html_data") or {}).get(sheet) or {}).get("cells") or {}).get(cell)
    if isinstance(value, dict):
        return value.get("value", value.get("v"))
    return value


async def _seed_case(session, *, formula_id: uuid.UUID, sheet: str, cell: str, expression: str):
    user_id, project_id, wp_index_id, wp_id = (uuid.uuid4() for _ in range(4))
    user = User(
        id=user_id, username=f"fm_runtime_{user_id.hex[:10]}",
        email=f"fm_runtime_{user_id.hex[:10]}@example.test",
        hashed_password="x", role=UserRole.admin,
    )
    session.add(user)
    session.add(Project(
        id=project_id, name=f"【测试】公式运行_{project_id.hex[:8]}", client_name="公式运行测试",
        project_type=ProjectType.annual, status=ProjectStatus.planning,
        template_type="soe", report_scope="standalone",
    ))
    await session.flush()
    session.add(WpIndex(
        id=wp_index_id, project_id=project_id, wp_code="A99", wp_name="公式运行测试底稿",
        status=WpStatus.not_started, is_deleted=False,
    ))
    await session.flush()
    session.add(WorkingPaper(
        id=wp_id, project_id=project_id, wp_index_id=wp_index_id,
        file_path="/tmp/formula-runtime.xlsx", source_type=WpSourceType.template,
        status=WpFileStatus.draft, review_status=WpReviewStatus.not_submitted,
        # 目标工作表须已存在：formula-hub-integrity-closure 需求 1.8 起 Runtime 任何路径不新建工作表，
        # 目标表不存在 ⇒ 计划阶段 blocked（原夹具 parsed_data={} 会让本文件前两条用例
        # 一条被 blocked、一条在业务写入之前就失败而空转通过）
        is_deleted=False, parsed_data={"html_data": {sheet: {"cells": {}}}},
    ))
    await session.flush()
    session.add(WpFormula(
        id=formula_id, project_id=project_id, wp_id=wp_id,
        sheet_name=sheet, target_cell=cell, expression=expression,
        formula_type="auto_calc", category="auto_calc", definition_version=1,
        created_by=user_id,
    ))
    await session.commit()
    return user_id, project_id, wp_index_id, wp_id


@pytest.mark.asyncio
async def test_production_chain_applies_value_and_links_one_run_id():
    url = _pg_url()
    assert url.startswith("postgresql+asyncpg://")
    connect_args = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(url, poolclass=NullPool, connect_args=connect_args)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    formula_id = uuid.uuid4()
    sheet = f"_FMRUNTIME_{uuid.uuid4().hex}"
    target_cell = "Z998"
    run_id = None
    hash_audit_id = None
    user_id = project_id = wp_index_id = wp_id = None

    try:
        async with Session() as setup:
            user_id, project_id, wp_index_id, wp_id = await _seed_case(
                setup,
                formula_id=formula_id,
                sheet=sheet,
                cell=target_cell,
                expression="100 + 23",
            )

        async with Session() as run_session:
            operator = await run_session.get(User, user_id)
            result, _ = await DraftRefreshOrchestrator(run_session).generate(
                project_id=project_id,
                year=2025,
                operator=operator,
                scopes=["workpaper:A"],
                transaction_mode="all_or_nothing",
                idempotency_key=f"formula-runtime-pg-{formula_id}",
            )
            assert result.status == "success", result.failures
            assert result.applied_count == 1
            run_id = result.run_id
            await run_session.commit()

        async with Session() as verify:
            paper = await verify.get(WorkingPaper, wp_id)
            formula = await verify.get(WpFormula, formula_id)
            audit = await verify.get(DraftRefreshAudit, run_id)
            snapshots = (await verify.execute(sa.select(DraftRefreshSnapshot).where(
                DraftRefreshSnapshot.refresh_id == run_id
            ))).scalars().all()
            outbox = (await verify.execute(sa.select(FormulaRuntimeOutbox).where(
                FormulaRuntimeOutbox.run_id == run_id
            ))).scalars().all()
            hash_audit = (await verify.execute(sa.select(AuditLogEntry).where(
                AuditLogEntry.object_type == "formula_runtime"
            ).order_by(AuditLogEntry.ts.desc()))).scalars().first()
            hash_audit_id = hash_audit.id if hash_audit is not None else None
            assert _cell_value(paper.parsed_data, sheet, target_cell) == 123
            assert formula.last_computed_at is not None
            assert formula.lifecycle_state == "succeeded"
            assert audit is not None and audit.affected_count == 1
            assert len(snapshots) == 1
            assert snapshots[0].source_formula_id == formula_id
            assert snapshots[0].refresh_id == run_id
            assert len(outbox) == 1 and outbox[0].run_id == run_id
            assert hash_audit is not None
            assert (hash_audit.payload or {}).get("run_id") == str(run_id)

            evidence_path = os.getenv("FORMULA_RUNTIME_EVIDENCE_PATH", "").strip()
            if evidence_path:
                path = Path(evidence_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({
                    "schema_version": 1,
                    "commit": os.getenv("FORMULA_RUNTIME_EVIDENCE_COMMIT", "working-tree"),
                    "working_tree": os.getenv("FORMULA_RUNTIME_EVIDENCE_WORKTREE", "true").lower() == "true",
                    "test": "test_production_chain_applies_value_and_links_one_run_id",
                    "run_id": str(run_id),
                    "project_id": str(project_id),
                    "wp_id": str(wp_id),
                    "formula_id": str(formula_id),
                    "target": {"sheet": sheet, "cell": target_cell},
                    "before_value": None,
                    "after_value": 123,
                    "audit_count": 1,
                    "snapshot_count": len(snapshots),
                    "outbox_count": len(outbox),
                    "last_computed_at_set": formula.last_computed_at is not None,
                    "query_basis": "ORM direct read after commit; test cleanup follows evidence capture",
                }, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    finally:
        try:
            async with Session() as cleanup:
                if run_id is not None:
                    await cleanup.execute(sa.delete(FormulaRuntimeOutbox).where(
                        FormulaRuntimeOutbox.run_id == run_id
                    ))
                    await cleanup.execute(sa.delete(DraftRefreshSnapshot).where(
                        DraftRefreshSnapshot.refresh_id == run_id
                    ))
                    await cleanup.execute(sa.delete(DraftRefreshAudit).where(
                        DraftRefreshAudit.id == run_id
                    ))
                if hash_audit_id is not None:
                    await cleanup.execute(sa.delete(AuditLogEntry).where(
                        AuditLogEntry.id == hash_audit_id
                    ))
                await cleanup.execute(sa.delete(WpFormula).where(WpFormula.id == formula_id))
                if wp_id is not None:
                    await cleanup.execute(sa.delete(WorkingPaper).where(WorkingPaper.id == wp_id))
                if wp_index_id is not None:
                    await cleanup.execute(sa.delete(WpIndex).where(WpIndex.id == wp_index_id))
                if user_id is not None:
                    await cleanup.execute(sa.delete(User).where(User.id == user_id))
                if project_id is not None:
                    await cleanup.execute(sa.delete(Project).where(Project.id == project_id))
                await cleanup.commit()
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_all_or_nothing_rolls_back_business_value_snapshot_and_formula_state():
    url = _pg_url()
    connect_args = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(url, poolclass=NullPool, connect_args=connect_args)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    formula_id = uuid.uuid4()
    run_id = None
    sheet = f"_FMRUNTIME_ROLLBACK_{uuid.uuid4().hex}"
    user_id = project_id = wp_index_id = wp_id = None

    class _FailAfterWrite:
        def __init__(self, inner):
            self.inner = inner

        async def apply_many(self, mutations):
            await self.inner.apply_many(mutations)
            raise RuntimeError("injected_after_business_write")

    try:
        async with Session() as session:
            user_id, project_id, wp_index_id, wp_id = await _seed_case(
                session,
                formula_id=formula_id,
                sheet=sheet,
                cell="Z997",
                expression="999",
            )

        async with Session() as session:
            target = CanonicalFormulaTarget(
                domain="workpaper", project_id=project_id, year=2025,
                addr_id=f"{wp_id}/{sheet}/Z997",
                locator={"wp_id": str(wp_id), "storage_kind": "parsed_data",
                         "sheet_name": sheet, "cell_ref": "Z997"},
                wp_id=wp_id,
            )
            inner = WorkpaperMutationAdapter(session)
            prepared = await inner.prepare_many([target], {target.addr_id: Decimal("999")})
            mutation = FormulaMutation(
                target=prepared[0].target, before_value=prepared[0].before_value,
                after_value=prepared[0].after_value, expected_version=prepared[0].expected_version,
                source_formula_id=formula_id,
            )
            operator = await session.get(User, user_id)
            result = await DraftRefreshService().execute_refresh(
                session, project_id=project_id, year=2025, scopes=["workpaper:A"],
                mutations=[mutation], adapters={"workpaper": _FailAfterWrite(inner)},
                transaction_mode="all_or_nothing", operator=operator,
                formula_definition_revision=uuid.uuid4().hex,
            )
            assert result.status == "failed"
            run_id = result.run_id
            await session.commit()

        async with Session() as verify:
            paper = await verify.get(WorkingPaper, wp_id)
            formula = await verify.get(WpFormula, formula_id)
            snapshots = (await verify.execute(sa.select(DraftRefreshSnapshot).where(
                DraftRefreshSnapshot.refresh_id == run_id
            ))).scalars().all()
            outbox = (await verify.execute(sa.select(FormulaRuntimeOutbox).where(
                FormulaRuntimeOutbox.run_id == run_id
            ))).scalars().all()
            audit = await verify.get(DraftRefreshAudit, run_id)
            assert _cell_value(paper.parsed_data, sheet, "Z997") is None
            assert formula.last_computed_at is None
            assert formula.lifecycle_state == "saved"
            assert snapshots == []
            assert outbox == []
            assert audit is not None and audit.result_status == "failed"
            assert audit.affected_count == 0
    finally:
        try:
            async with Session() as cleanup:
                if run_id is not None:
                    await cleanup.execute(sa.delete(FormulaRuntimeOutbox).where(
                        FormulaRuntimeOutbox.run_id == run_id
                    ))
                    await cleanup.execute(sa.delete(DraftRefreshSnapshot).where(
                        DraftRefreshSnapshot.refresh_id == run_id
                    ))
                    await cleanup.execute(sa.delete(DraftRefreshAudit).where(
                        DraftRefreshAudit.id == run_id
                    ))
                await cleanup.execute(sa.delete(WpFormula).where(WpFormula.id == formula_id))
                if wp_id is not None:
                    await cleanup.execute(sa.delete(WorkingPaper).where(WorkingPaper.id == wp_id))
                if wp_index_id is not None:
                    await cleanup.execute(sa.delete(WpIndex).where(WpIndex.id == wp_index_id))
                if user_id is not None:
                    await cleanup.execute(sa.delete(User).where(User.id == user_id))
                if project_id is not None:
                    await cleanup.execute(sa.delete(Project).where(Project.id == project_id))
                await cleanup.commit()
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_human_edit_policy_and_public_rollback_restore_value_and_governance():
    """未确认跳过人工值；确认后可写；rollback 同时恢复值、marker 与公式状态。"""
    url = _pg_url()
    connect_args = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(url, poolclass=NullPool, connect_args=connect_args)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    formula_id = uuid.uuid4()
    sheet = f"_FMRUNTIME_POLICY_{uuid.uuid4().hex}"
    cell = "Z996"
    user_id = project_id = wp_index_id = wp_id = None
    skipped_run_id = applied_run_id = None
    hash_audit_ids: list[uuid.UUID] = []

    try:
        async with Session() as setup:
            user_id, project_id, wp_index_id, wp_id = await _seed_case(
                setup,
                formula_id=formula_id,
                sheet=sheet,
                cell=cell,
                expression="120 + 3",
            )
            paper = await setup.get(WorkingPaper, wp_id)
            paper.parsed_data = {
                "html_data": {sheet: {"cells": {cell: {"value": 7}}}},
            }
            unit_scope = f"workpaper:{wp_id}/{sheet}/{cell}"
            setup.add(DraftMarker(
                project_id=project_id,
                year=2025,
                unit_scope=unit_scope,
                state="human_edited",
                refresh_id=None,
            ))
            await setup.commit()

        async with Session() as preserve:
            operator = await preserve.get(User, user_id)
            skipped, _ = await DraftRefreshOrchestrator(preserve).generate(
                project_id=project_id,
                year=2025,
                operator=operator,
                scopes=["workpaper:A"],
                confirm_overwrite=False,
                transaction_mode="all_or_nothing",
            )
            assert skipped.status == "no_effect"
            assert skipped.skipped_count == 1
            skipped_run_id = skipped.run_id
            await preserve.commit()

        async with Session() as verify_preserved:
            paper = await verify_preserved.get(WorkingPaper, wp_id)
            formula = await verify_preserved.get(WpFormula, formula_id)
            marker = (await verify_preserved.execute(sa.select(DraftMarker).where(
                DraftMarker.project_id == project_id,
                DraftMarker.year == 2025,
                DraftMarker.unit_scope == unit_scope,
            ))).scalars().one()
            assert _cell_value(paper.parsed_data, sheet, cell) == 7
            assert marker.state == "human_edited" and marker.refresh_id is None
            assert formula.lifecycle_state == "saved" and formula.last_computed_at is None

        async with Session() as overwrite:
            operator = await overwrite.get(User, user_id)
            applied, _ = await DraftRefreshOrchestrator(overwrite).generate(
                project_id=project_id,
                year=2025,
                operator=operator,
                scopes=["workpaper:A"],
                confirm_overwrite=True,
                transaction_mode="all_or_nothing",
            )
            assert applied.status == "success", applied.failures
            assert applied.applied_count == 1
            applied_run_id = applied.run_id
            await overwrite.commit()

        async with Session() as verify_applied:
            paper = await verify_applied.get(WorkingPaper, wp_id)
            formula = await verify_applied.get(WpFormula, formula_id)
            marker = (await verify_applied.execute(sa.select(DraftMarker).where(
                DraftMarker.unit_scope == unit_scope,
            ))).scalars().one()
            assert _cell_value(paper.parsed_data, sheet, cell) == 123
            assert marker.state == "draft" and marker.refresh_id == applied_run_id
            assert formula.lifecycle_state == "succeeded" and formula.last_computed_at is not None

        async with Session() as rollback_session:
            operator = await rollback_session.get(User, user_id)
            rollback = await DraftRefreshService().rollback_refresh(
                rollback_session,
                run_id=applied_run_id,
                adapters={"workpaper": WorkpaperMutationAdapter(rollback_session)},
                operator=operator,
            )
            assert rollback.status == "rolled_back", rollback.conflicts
            assert rollback.restored_count >= 1
            await rollback_session.commit()

        async with Session() as verify_rollback:
            paper = await verify_rollback.get(WorkingPaper, wp_id)
            formula = await verify_rollback.get(WpFormula, formula_id)
            marker = (await verify_rollback.execute(sa.select(DraftMarker).where(
                DraftMarker.unit_scope == unit_scope,
            ))).scalars().one()
            audit = await verify_rollback.get(DraftRefreshAudit, applied_run_id)
            assert _cell_value(paper.parsed_data, sheet, cell) == 7
            assert marker.state == "human_edited" and marker.refresh_id is None
            assert formula.lifecycle_state == "saved" and formula.last_computed_at is None
            assert audit.result_status == "rolled_back"
            assert audit.detail["rollback"]["restored_business_count"] == 1

            logs = (await verify_rollback.execute(sa.select(AuditLogEntry).where(
                AuditLogEntry.object_type == "formula_runtime"
            ))).scalars().all()
            hash_audit_ids = [
                row.id for row in logs
                if (row.payload or {}).get("run_id") == str(applied_run_id)
            ]
    finally:
        try:
            async with Session() as cleanup:
                run_ids = [run_id for run_id in (skipped_run_id, applied_run_id) if run_id]
                if run_ids:
                    await cleanup.execute(sa.delete(FormulaRuntimeOutbox).where(
                        FormulaRuntimeOutbox.run_id.in_(run_ids)
                    ))
                    await cleanup.execute(sa.delete(DraftRefreshSnapshot).where(
                        DraftRefreshSnapshot.refresh_id.in_(run_ids)
                    ))
                    await cleanup.execute(sa.delete(DraftRefreshAudit).where(
                        DraftRefreshAudit.id.in_(run_ids)
                    ))
                if hash_audit_ids:
                    await cleanup.execute(sa.delete(AuditLogEntry).where(
                        AuditLogEntry.id.in_(hash_audit_ids)
                    ))
                if project_id is not None:
                    await cleanup.execute(sa.delete(DraftMarker).where(
                        DraftMarker.project_id == project_id
                    ))
                await cleanup.execute(sa.delete(WpFormula).where(WpFormula.id == formula_id))
                if wp_id is not None:
                    await cleanup.execute(sa.delete(WorkingPaper).where(WorkingPaper.id == wp_id))
                if wp_index_id is not None:
                    await cleanup.execute(sa.delete(WpIndex).where(WpIndex.id == wp_index_id))
                if user_id is not None:
                    await cleanup.execute(sa.delete(User).where(User.id == user_id))
                if project_id is not None:
                    await cleanup.execute(sa.delete(Project).where(Project.id == project_id))
                await cleanup.commit()
        finally:
            await engine.dispose()
