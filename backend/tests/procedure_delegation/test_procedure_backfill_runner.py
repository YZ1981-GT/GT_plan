# Feature: procedure-delegation-notification — Task 15 可恢复/可重复 backfill
"""ProcedureBackfillRunner PostgreSQL 集成测试。

Task 15 / 需求 7.6-7.9, 13.5 / Design C1/C2/C8 + Legacy State Mapping / Property P24：

- **保守状态映射（Req 7.6-7.8 / P24）**：复用 ``map_legacy_status`` 把 legacy
  ``parsed_data.procedure_status`` 保守映射到 task 的 applicability/workflow，写入
  ``migration_confidence`` / ``migration_detail``，未知/矛盾不猜测。
- **可恢复（interrupt-resume, Req 13.5）**：已 backfill（migration_confidence 非空）或已被人工
  推进的 task 不再重映射；中断后重跑只处理剩余未映射行。
- **可重复（repeat-backfill, Req 13.5）**：重复运行结果一致，第二次全部 skip、无副作用。
- **coverage/conflict/orphan 报告（Req 13.5）**：canonical trim key coverage、conflict 明细、
  无匹配定义的 legacy 行进 orphans。
- **底稿主编候选 report-only（Req）**：legacy ProcedureInstance.assigned_to 仅作底稿主编候选
  写报告，**不复制到每条程序**（task.assignee_staff_id 保持 NULL）；多个不同 assignee 记 conflict。
- **投影重建/核对（Req 7.9）**：backfill 末尾复用 projection.rebuild + diff_report。

数据库约束/并发/jsonb 投影在 PostgreSQL 验证，不以 sqlite 替代（memory 铁律）。
materialize 使用 PG-only ``ON CONFLICT ... WHERE`` + ``xmax``，故整体需要 PostgreSQL。

隔离策略：为每个测试生成唯一 sheet_key（``{wp_code}A::BF::{hex}``），使 legacy 行只映射到本测试
物化的 task，避免与真实 JSON 模板定义的 (sheet_key, program_no) 碰撞；cleanup 按 wp_index 删任务、
按 sheet_key 前缀删定义，保持 dev 库整洁。
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings as app_settings
from app.core.migration_runner import MigrationRunner
from app.services.procedure_backfill_runner import (
    ProcedureBackfillRunner,
    extract_legacy_has_assignee,
    extract_legacy_status,
    legacy_row_program_no,
)
from app.services.procedure_task_materialization_service import (
    ProcedureTaskMaterializationService,
)
from app.services.procedure_trim_service import build_row_key, build_scope_key

import app.models.procedure_models  # noqa: F401
import app.models.phase15_models  # noqa: F401
import app.models.core  # noqa: F401

_V105 = (
    Path(__file__).resolve().parent.parent.parent
    / "migrations"
    / "V105__procedure_row_tasks.sql"
)
_IS_PG = app_settings.DATABASE_URL.startswith("postgresql")


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


# ===========================================================================
# 纯函数单测（legacy value 探测，无需 DB）
# ===========================================================================
class TestLegacyValueExtractors:
    def test_extract_legacy_status_from_string(self):
        assert extract_legacy_status("in_progress") == "in_progress"

    def test_extract_legacy_status_from_dict(self):
        assert extract_legacy_status({"status": "filled"}) == "filled"
        assert extract_legacy_status({"workflow_status": "reviewed"}) == "reviewed"

    def test_extract_legacy_status_none(self):
        assert extract_legacy_status(None) is None
        assert extract_legacy_status({}) is None

    def test_extract_has_assignee(self):
        assert extract_legacy_has_assignee({"assignee_staff_id": "x"}) is True
        assert extract_legacy_has_assignee({"assigned_to": "y"}) is True
        assert extract_legacy_has_assignee({"status": "pending"}) is False
        assert extract_legacy_has_assignee("pending") is False

    def test_legacy_row_program_no_strips_prefix(self):
        assert legacy_row_program_no("row-3") == "3"
        assert legacy_row_program_no("index-2") == "2"
        assert legacy_row_program_no("7") == "7"


# ===========================================================================
# PostgreSQL 集成 fixture（复用 dev 库 project+wp_index+working_paper）
# ===========================================================================
async def _apply_v105(engine) -> None:
    sql = _V105.read_text(encoding="utf-8")
    statements = MigrationRunner._split_sql_statements(sql)
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.exec_driver_sql(stmt)


@pytest_asyncio.fixture
async def pg_engine():
    if not _IS_PG:
        pytest.skip("need PostgreSQL (backfill materialize/projection/rollback retention)")
    engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")
    await _apply_v105(engine)
    try:
        yield engine
    finally:
        await engine.dispose()


async def _pick_project_wp(factory):
    async with factory() as s:
        return (
            await s.execute(
                sa.text(
                    "SELECT wp.project_id, wp.wp_index_id, wp.id, wi.wp_code, "
                    "COALESCE(wi.audit_cycle, 'A') "
                    "FROM working_paper wp JOIN wp_index wi ON wi.id = wp.wp_index_id "
                    "WHERE wp.is_deleted = false AND wi.is_deleted = false "
                    "ORDER BY wp.id LIMIT 1"
                )
            )
        ).first()


async def _insert_definition(factory, wp_code: str, sheet_key: str, program_no: str) -> str:
    """插入匹配 wp_code 的定义（template_code base==wp_code；带唯一 sheet_key + program_no）。

    materialize 后 task.sheet_key==sheet_key、task.program_no==program_no。返回 definition_key。
    """
    definition_key = f"{sheet_key}::{program_no}::{uuid.uuid4().hex}"
    async with factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO procedure_row_definitions "
                "(definition_key, template_code, template_revision_hash, sheet_key, "
                " program_no, procedure_text) "
                "VALUES (:k, :tc, :h, :sk, :pn, :pt)"
            ),
            {
                "k": definition_key,
                "tc": f"{wp_code}A",  # base==wp_code，被 _definitions_for_wp_code 命中
                "h": "c" * 64,
                "sk": sheet_key,
                "pn": program_no,
                "pt": f"临时 backfill 程序 {program_no}",
            },
        )
        await s.commit()
    return definition_key


async def _set_wp_legacy_projection(factory, wp_id, sheet_key: str, rows: dict) -> dict:
    """设置 working_paper.parsed_data.procedure_status[sheet_key]，返回原始 parsed_data 供还原。"""
    async with factory() as s:
        parsed = (
            await s.execute(
                sa.text("SELECT parsed_data FROM working_paper WHERE id = :i"),
                {"i": wp_id},
            )
        ).scalar_one()
    original = parsed if isinstance(parsed, dict) else {}
    new_parsed = dict(original)
    ps = dict(new_parsed.get("procedure_status") or {})
    ps[sheet_key] = rows
    new_parsed["procedure_status"] = ps
    async with factory() as s:
        await s.execute(
            sa.text("UPDATE working_paper SET parsed_data = CAST(:p AS jsonb) WHERE id = :i"),
            {"p": _json(new_parsed), "i": wp_id},
        )
        await s.commit()
    return original


async def _restore_wp_parsed(factory, wp_id, original: dict) -> None:
    async with factory() as s:
        await s.execute(
            sa.text("UPDATE working_paper SET parsed_data = CAST(:p AS jsonb) WHERE id = :i"),
            {"p": _json(original), "i": wp_id},
        )
        await s.commit()


async def _cleanup(factory, wp_index_id, wp_code: str) -> None:
    """删本 wp_index 全部 task/history + base==wp_code 的定义（含真实导入），保持 dev 库整洁。"""
    async with factory() as s:
        await s.execute(
            sa.text(
                "DELETE FROM procedure_row_task_history WHERE task_id IN "
                "(SELECT id FROM procedure_row_tasks WHERE wp_index_id = :w)"
            ),
            {"w": wp_index_id},
        )
        await s.execute(
            sa.text("DELETE FROM procedure_row_tasks WHERE wp_index_id = :w"),
            {"w": wp_index_id},
        )
        await s.execute(
            sa.text("DELETE FROM procedure_row_definitions WHERE sheet_key LIKE :pfx"),
            {"pfx": f"{wp_code}A%"},
        )
        await s.commit()


async def _task_row(factory, definition_key: str):
    async with factory() as s:
        return (
            await s.execute(
                sa.text(
                    "SELECT id, workflow_status, applicability_status, migration_confidence, "
                    "assignee_staff_id, wp_id FROM procedure_row_tasks WHERE definition_key = :k"
                ),
                {"k": definition_key},
            )
        ).first()


async def _materialize_isolate_bind(
    factory, project_id, wp_index_id, wp_id, keep_keys: list[str]
) -> None:
    """materialize → 删除本 wp_index 除测试定义外的真实模板任务 → 只绑定测试任务。

    真实 JSON 模板定义会被 materialize 一并物化；测试隔离需只保留测试 task 被绑定到 wp，
    使 backfill 的状态映射/投影重建只作用于测试行（run() 内部会再物化真实任务但保持 unbound，
    不进入 wp_id-bound 的投影重建与状态映射）。
    """
    async with factory() as s:
        svc = ProcedureTaskMaterializationService(s)
        await svc.materialize(project_id, [wp_index_id])
        await s.commit()
    async with factory() as s:
        await s.execute(
            sa.text(
                "DELETE FROM procedure_row_tasks "
                "WHERE wp_index_id = :w AND definition_key <> ALL(:keep)"
            ),
            {"w": wp_index_id, "keep": list(keep_keys)},
        )
        await s.commit()
    async with factory() as s:
        svc = ProcedureTaskMaterializationService(s)
        await svc.bind_working_paper(project_id, wp_index_id, wp_id)
        await s.commit()


def _unique_sheet_key(wp_code: str) -> str:
    return f"{wp_code}A::BF::{uuid.uuid4().hex[:8]}"


# ===========================================================================
# P24 + Req 7.6-7.9 / 13.5：保守映射 + coverage/orphan 报告
# Validates: Requirements 7.6, 7.7, 7.8, 7.9, 13.5
# ===========================================================================
@pytest.mark.asyncio
class TestPgBackfillRunner:
    async def test_backfill_maps_legacy_status_and_reports_coverage(self, pg_engine):
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp(factory)
        if picked is None:
            pytest.skip("dev 库无 project+wp_index+working_paper 可复用")
        project_id, wp_index_id, wp_id, wp_code, cycle = picked
        sheet_key = _unique_sheet_key(wp_code)
        dk = await _insert_definition(factory, wp_code, sheet_key, "1")
        original = await _set_wp_legacy_projection(
            factory, wp_id, sheet_key,
            {"row-1": {"status": "in_progress", "assignee_staff_id": str(uuid.uuid4())}},
        )
        try:
            await _materialize_isolate_bind(factory, project_id, wp_index_id, wp_id, [dk])
            async with factory() as s:
                runner = ProcedureBackfillRunner(s)
                report = await runner.run(project_id, wp_index_ids=[wp_index_id])
            # in_progress + assignee → workflow=in_progress, confidence=conservative
            assert report.status_mapped >= 1
            row = await _task_row(factory, dk)
            assert row[1] == "in_progress"
            assert row[3] == "conservative"
            # coverage：canonical scope + row key 均出现（row key 用 base wp_code）
            assert build_scope_key(cycle, wp_code) in report.coverage_keys
            assert build_row_key(wp_code, sheet_key, dk) in report.coverage_keys
            # 投影已重建
            assert report.projection_rebuilt_wps >= 1
        finally:
            await _cleanup(factory, wp_index_id, wp_code)
            await _restore_wp_parsed(factory, wp_id, original)

    async def test_backfill_conflict_when_in_progress_without_assignee(self, pg_engine):
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp(factory)
        if picked is None:
            pytest.skip("dev 库无 project+wp_index+working_paper 可复用")
        project_id, wp_index_id, wp_id, wp_code, _cycle = picked
        sheet_key = _unique_sheet_key(wp_code)
        dk = await _insert_definition(factory, wp_code, sheet_key, "1")
        original = await _set_wp_legacy_projection(
            factory, wp_id, sheet_key, {"row-1": {"status": "in_progress"}},
        )
        try:
            await _materialize_isolate_bind(factory, project_id, wp_index_id, wp_id, [dk])
            async with factory() as s:
                runner = ProcedureBackfillRunner(s)
                report = await runner.run(project_id, wp_index_ids=[wp_index_id])
            # in_progress 缺 assignee → conflict（不猜测降级）
            assert len(report.conflicts) >= 1
            row = await _task_row(factory, dk)
            assert row[3] == "conflict"
        finally:
            await _cleanup(factory, wp_index_id, wp_code)
            await _restore_wp_parsed(factory, wp_id, original)

    async def test_backfill_orphan_when_no_matching_definition(self, pg_engine):
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp(factory)
        if picked is None:
            pytest.skip("dev 库无 project+wp_index+working_paper 可复用")
        project_id, wp_index_id, wp_id, wp_code, _cycle = picked
        sheet_key = _unique_sheet_key(wp_code)
        dk = await _insert_definition(factory, wp_code, sheet_key, "1")
        # legacy row-99 无匹配 definition（program_no=99 无对应 task）→ orphan
        original = await _set_wp_legacy_projection(
            factory, wp_id, sheet_key,
            {
                "row-1": {"status": "pending"},
                "row-99": {"status": "pending"},
            },
        )
        try:
            await _materialize_isolate_bind(factory, project_id, wp_index_id, wp_id, [dk])
            async with factory() as s:
                runner = ProcedureBackfillRunner(s)
                report = await runner.run(project_id, wp_index_ids=[wp_index_id])
            orphan_rows = [o["legacy_row_id"] for o in report.orphans]
            assert "row-99" in orphan_rows
        finally:
            await _cleanup(factory, wp_index_id, wp_code)
            await _restore_wp_parsed(factory, wp_id, original)

    async def test_backfill_repeatable_second_run_all_skipped(self, pg_engine):
        """可重复：第二次 backfill 全部 skip，task 状态不变、无重复映射（Req 13.5）。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp(factory)
        if picked is None:
            pytest.skip("dev 库无 project+wp_index+working_paper 可复用")
        project_id, wp_index_id, wp_id, wp_code, _cycle = picked
        sheet_key = _unique_sheet_key(wp_code)
        dk = await _insert_definition(factory, wp_code, sheet_key, "1")
        original = await _set_wp_legacy_projection(
            factory, wp_id, sheet_key, {"row-1": {"status": "filled"}},
        )
        try:
            await _materialize_isolate_bind(factory, project_id, wp_index_id, wp_id, [dk])
            async with factory() as s:
                runner = ProcedureBackfillRunner(s)
                r1 = await runner.run(project_id, wp_index_ids=[wp_index_id])
            assert r1.status_mapped >= 1
            first = await _task_row(factory, dk)
            assert first[1] == "submitted"  # filled → submitted

            # 第二次运行：全部已映射 → skip，状态不变
            async with factory() as s:
                runner = ProcedureBackfillRunner(s)
                r2 = await runner.run(project_id, wp_index_ids=[wp_index_id])
            assert r2.status_mapped == 0
            assert r2.status_skipped_non_default >= 1
            second = await _task_row(factory, dk)
            assert second[1] == first[1]  # workflow 不变
            assert second[3] == first[3]  # confidence 不变
        finally:
            await _cleanup(factory, wp_index_id, wp_code)
            await _restore_wp_parsed(factory, wp_id, original)

    async def test_backfill_interrupt_resume_only_maps_remaining(self, pg_engine):
        """可恢复：模拟中断（一行已映射一行未映射），重跑只映射剩余未映射行（Req 13.5）。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp(factory)
        if picked is None:
            pytest.skip("dev 库无 project+wp_index+working_paper 可复用")
        project_id, wp_index_id, wp_id, wp_code, _cycle = picked
        sheet_key = _unique_sheet_key(wp_code)
        dk1 = await _insert_definition(factory, wp_code, sheet_key, "1")
        dk2 = await _insert_definition(factory, wp_code, sheet_key, "2")
        original = await _set_wp_legacy_projection(
            factory, wp_id, sheet_key,
            {
                "row-1": {"status": "reviewed"},
                "row-2": {"status": "filled"},
            },
        )
        try:
            await _materialize_isolate_bind(
                factory, project_id, wp_index_id, wp_id, [dk1, dk2]
            )
            # 模拟“上次 backfill 已处理 row-1”：手动把 dk1 的 task 标记为已迁移。
            async with factory() as s:
                await s.execute(
                    sa.text(
                        "UPDATE procedure_row_tasks SET workflow_status='reviewed', "
                        "migration_confidence='conservative' WHERE definition_key=:k"
                    ),
                    {"k": dk1},
                )
                await s.commit()
            # 重跑：只映射未处理的 dk2（row-2 → submitted）
            async with factory() as s:
                runner = ProcedureBackfillRunner(s)
                report = await runner.run(project_id, wp_index_ids=[wp_index_id])
            assert report.status_mapped == 1  # 只 dk2 被映射
            assert report.status_skipped_non_default >= 1  # dk1 已迁移被跳过
            row2 = await _task_row(factory, dk2)
            assert row2[1] == "submitted"
            row1 = await _task_row(factory, dk1)
            assert row1[1] == "reviewed"  # 已处理行保持不变
        finally:
            await _cleanup(factory, wp_index_id, wp_code)
            await _restore_wp_parsed(factory, wp_id, original)

    async def test_legacy_assignment_is_primary_editor_candidate_only(self, pg_engine):
        """legacy ProcedureInstance.assigned_to 仅作底稿主编候选写报告，不复制到每条程序。

        核心断言（≥1 staff 即可）：候选进报告 + task.assignee_staff_id 保持 NULL（不复制）。
        当 dev 库存在 ≥2 不同 active staff 时，追加断言多 assignee → conflict=True。
        """
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp(factory)
        if picked is None:
            pytest.skip("dev 库无 project+wp_index+working_paper 可复用")
        project_id, wp_index_id, wp_id, wp_code, cycle = picked
        async with factory() as s:
            staff_ids = (
                await s.execute(
                    sa.text("SELECT id FROM staff_members WHERE is_deleted = false LIMIT 2")
                )
            ).scalars().all()
        if len(staff_ids) < 1:
            pytest.skip("dev 库无 active staff_members，无法测试主编候选")
        sheet_key = _unique_sheet_key(wp_code)
        dk = await _insert_definition(factory, wp_code, sheet_key, "1")
        # 每个不同 staff 各建一条粗裁实例（同 wp_code）；多 staff → conflict。
        # 用 ORM 插入以套用 sort_order/is_custom/execution_status 等 Python 默认。
        from app.models.procedure_models import ProcedureInstance

        pi_ids: list[uuid.UUID] = []
        async with factory() as s:
            for staff_id in staff_ids:
                pi_id = uuid.uuid4()
                pi_ids.append(pi_id)
                s.add(
                    ProcedureInstance(
                        id=pi_id,
                        project_id=project_id,
                        audit_cycle=cycle,
                        procedure_code=f"{wp_code}-backfill-test",
                        procedure_name="backfill 主编候选测试",
                        status="execute",
                        assigned_to=staff_id,
                        wp_code=wp_code,
                    )
                )
            await s.commit()
        try:
            await _materialize_isolate_bind(factory, project_id, wp_index_id, wp_id, [dk])
            async with factory() as s:
                runner = ProcedureBackfillRunner(s)
                report = await runner.run(project_id, wp_index_ids=[wp_index_id])
            cand = [c for c in report.primary_editor_candidates if c["wp_code"] == wp_code]
            assert cand, "应产出该 wp_code 的底稿主编候选"
            distinct = len(set(str(s) for s in staff_ids))
            assert len(cand[0]["candidate_staff_ids"]) == distinct
            # 多个不同 assigned_to → conflict；单一 → 非 conflict
            assert cand[0]["conflict"] is (distinct > 1)
            # 关键：assignment 不复制到每条程序，task.assignee_staff_id 保持 NULL
            row = await _task_row(factory, dk)
            assert row[4] is None
        finally:
            async with factory() as s:
                for pi_id in pi_ids:
                    await s.execute(
                        sa.text("DELETE FROM procedure_instances WHERE id = :i"),
                        {"i": pi_id},
                    )
                await s.commit()
            await _cleanup(factory, wp_index_id, wp_code)
