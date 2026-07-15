# Feature: procedure-delegation-notification — Task 9 兼容投影与旧状态映射
"""ProcedureProjectionService 测试：Properties P22-P24 + PG jsonb_set 并发/重建。

Task 9 / 需求 7.1-7.9 / Design C8、D7：

- **P22（投影可重建且 task 优先）**：Requirements 7.1/7.2/7.3/7.9 —— overlay 纯函数 task 优先；
  legacy projection 冲突时 task 值获胜；rebuild 后投影与 task 一致（PG）。
- **P23（parsed_data 不同路径并发不丢）**：Requirements 7.4/7.5 —— 两事务并发更新不同
  sheet/definition 路径，jsonb_set 精确写 + 行锁序列化后两项均保留，不整列覆盖（PG）。
- **P24（旧状态保守映射）**：Requirements 7.6/7.7/7.8 —— 已知 legacy 状态严格映射到表；
  未知/矛盾只产生 conflict/confidence，不猜测更高状态。

投影并发/约束在 PostgreSQL 验证，不以 sqlite 替代；PBT 用项目 fast profile。
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings as app_settings
from app.core.migration_runner import MigrationRunner
from app.services.procedure_projection_service import (
    ProcedureProjectionService,
    map_legacy_status,
    overlay,
    task_projection_value,
)

_V105 = (
    Path(__file__).resolve().parent.parent.parent
    / "migrations"
    / "V105__procedure_row_tasks.sql"
)
_IS_PG = app_settings.DATABASE_URL.startswith("postgresql")


# ===========================================================================
# P24：旧状态保守映射（表驱动，纯函数）
# Validates: Requirements 7.6, 7.7, 7.8
# ===========================================================================
class TestP24LegacyMapping:
    def test_pending_with_assignee_is_assigned(self):
        r = map_legacy_status("pending", has_assignee=True)
        assert r["applicability"] == "execute" and r["workflow"] == "assigned"
        assert r["confidence"] == "conservative"

    def test_pending_without_assignee_is_unassigned(self):
        r = map_legacy_status("not_started", has_assignee=False)
        assert r["workflow"] == "unassigned" and r["confidence"] == "conservative"

    def test_in_progress_without_assignee_is_conflict(self):
        r = map_legacy_status("in_progress", has_assignee=False)
        assert r["workflow"] == "in_progress"
        assert r["confidence"] == "conflict"
        assert "conflict" in r["detail"]

    def test_in_progress_with_assignee_conservative(self):
        r = map_legacy_status("in_progress", has_assignee=True)
        assert r["workflow"] == "in_progress" and r["confidence"] == "conservative"

    def test_filled_completed_to_submitted(self):
        for s in ("filled", "completed"):
            r = map_legacy_status(s, has_assignee=True)
            assert r["workflow"] == "submitted" and r["confidence"] == "conservative"

    def test_reviewed_approved_to_reviewed(self):
        for s in ("reviewed", "approved"):
            r = map_legacy_status(s, has_assignee=True)
            assert r["workflow"] == "reviewed"

    def test_not_applicable_maps_cancelled(self):
        r = map_legacy_status("not_applicable", has_assignee=True)
        assert r["applicability"] == "not_applicable" and r["workflow"] == "cancelled"

    @given(bad=st.text(min_size=1).filter(lambda x: x.strip().lower() not in {
        "pending", "not_started", "in_progress", "filled", "completed",
        "reviewed", "approved", "not_applicable"}))
    @settings(max_examples=5, deadline=None)
    def test_unknown_never_guesses_higher_state(self, bad):
        """未知/矛盾状态：不猜测更高状态 → 落到最低 unassigned + conflict，保留原值。"""
        r = map_legacy_status(bad, has_assignee=True)
        assert r["workflow"] == "unassigned"
        assert r["confidence"] == "conflict"
        assert r["detail"].get("legacy_status") == bad


# ===========================================================================
# P22（纯函数侧）：overlay task 优先
# Validates: Requirements 7.1, 7.2, 7.3
# ===========================================================================
class TestP22OverlayPure:
    def _defs(self):
        return [
            {"sheet_key": "D2A", "definition_key": "D2A::D2A::aaa", "program_no": "1", "procedure_text": "p1"},
            {"sheet_key": "D2A", "definition_key": "D2A::D2A::bbb", "program_no": "2", "procedure_text": "p2"},
        ]

    def test_missing_task_marks_materialization_required(self):
        rows = overlay(self._defs(), tasks={}, legacy_projection={})
        assert all(r["task_id"] is None and r["materialization_required"] for r in rows)

    def test_task_present_overrides_legacy(self):
        defs = self._defs()
        task = {
            "id": uuid.uuid4(), "workflow_status": "in_progress",
            "applicability_status": "execute", "assignee_staff_id": uuid.uuid4(),
            "reviewer_staff_id": None, "assignment_version": 2, "lock_version": 5,
        }
        tasks = {("D2A", "D2A::D2A::aaa"): task}
        # legacy 说 reviewed，但 task 说 in_progress → task 获胜
        legacy = {"D2A": {"D2A::D2A::aaa": {"status": "reviewed"}}}
        rows = overlay(defs, tasks=tasks, legacy_projection=legacy)
        row_a = next(r for r in rows if r["definition_key"] == "D2A::D2A::aaa")
        assert row_a["materialization_required"] is False
        assert row_a["workflow_status"] == "in_progress"  # task 优先，不被 legacy reviewed 覆盖
        row_b = next(r for r in rows if r["definition_key"] == "D2A::D2A::bbb")
        assert row_b["materialization_required"] is True


# ===========================================================================
# PostgreSQL 集成：rebuild（P22）+ jsonb_set 并发不丢（P23）
# ===========================================================================
async def _apply_v105(engine) -> None:
    sql = _V105.read_text(encoding="utf-8")
    for stmt in MigrationRunner._split_sql_statements(sql):
        async with engine.begin() as conn:
            await conn.exec_driver_sql(stmt)


@pytest_asyncio.fixture
async def pg_engine():
    if not _IS_PG:
        pytest.skip("need PostgreSQL (projection integration)")
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


async def _pick_wp(factory):
    async with factory() as s:
        row = (
            await s.execute(
                sa.text(
                    "SELECT wp.project_id, wp.wp_index_id, wp.id, wi.wp_code, COALESCE(wi.audit_cycle,'A') "
                    "FROM working_paper wp JOIN wp_index wi ON wi.id=wp.wp_index_id "
                    "WHERE wp.is_deleted=false AND wi.is_deleted=false LIMIT 1"
                )
            )
        ).first()
    return row


async def _seed_task(factory, project_id, wp_index_id, wp_id, wp_code, cycle, sheet_key, *, workflow="assigned"):
    dk = f"{sheet_key}::{sheet_key}::{uuid.uuid4().hex[:12]}"
    tid = uuid.uuid4()
    async with factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO procedure_row_definitions "
                "(definition_key, template_code, template_revision_hash, sheet_key, procedure_text) "
                "VALUES (:k,:tc,:h,:sk,:pt)"
            ),
            {"k": dk, "tc": sheet_key, "h": "a" * 64, "sk": sheet_key, "pt": "程序文本"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO procedure_row_tasks "
                "(id, project_id, wp_index_id, wp_id, definition_key, sheet_key, wp_code, "
                " definition_revision_hash, audit_cycle_snapshot, applicability_status, workflow_status, "
                " assignment_version, lock_version) "
                "VALUES (:id,:pid,:wi,:wp,:dk,:sk,:wc,:h,:cy,'execute',:wf,1,1)"
            ),
            {"id": tid, "pid": project_id, "wi": wp_index_id, "wp": wp_id, "dk": dk,
             "sk": sheet_key, "wc": wp_code, "h": "a" * 64, "cy": cycle, "wf": workflow},
        )
        await s.commit()
    return dk, tid


async def _cleanup(factory, wp_id, dks, tids, saved_parsed):
    async with factory() as s:
        for tid in tids:
            await s.execute(sa.text("DELETE FROM procedure_row_tasks WHERE id=:id"), {"id": tid})
        for dk in dks:
            await s.execute(sa.text("DELETE FROM procedure_row_definitions WHERE definition_key=:k"), {"k": dk})
        # 还原 working_paper.parsed_data，避免污染 dev 数据
        await s.execute(
            sa.text("UPDATE working_paper SET parsed_data = CAST(:pd AS jsonb) WHERE id=:id"),
            {"pd": saved_parsed, "id": wp_id},
        )
        await s.commit()


async def _get_parsed(factory, wp_id):
    import json
    async with factory() as s:
        raw = (await s.execute(sa.text("SELECT parsed_data FROM working_paper WHERE id=:id"), {"id": wp_id})).scalar()
    if raw is None:
        return "null"
    return json.dumps(raw, ensure_ascii=False)


@pytest.mark.asyncio
class TestPgProjection:
    async def test_write_path_precise_and_rebuild(self, pg_engine):
        """P22：write_path 精确写单条 + rebuild 从 task 全量重建，投影与 task 一致。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_wp(factory)
        if picked is None:
            pytest.skip("dev 库无 project/wp_index/working_paper 可复用")
        project_id, wp_index_id, wp_id, wp_code, cycle = picked
        saved = await _get_parsed(factory, wp_id)
        dk, tid = await _seed_task(factory, project_id, wp_index_id, wp_id, wp_code, cycle, f"{wp_code}A")
        try:
            async with factory() as s:
                svc = ProcedureProjectionService(s)
                res = await svc.rebuild(wp_id)
                await s.commit()
            assert res["rows"] >= 1
            # diff_report 无 mismatch
            async with factory() as s:
                svc = ProcedureProjectionService(s)
                report = await svc.diff_report(wp_id)
            assert report["mismatches"] == []
        finally:
            await _cleanup(factory, wp_id, [dk], [tid], saved)

    async def test_concurrent_different_paths_no_loss(self, pg_engine):
        """P23：两事务并发写不同 (sheet, definition) 路径，最终两项都在，不整列覆盖。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_wp(factory)
        if picked is None:
            pytest.skip("dev 库无 project/wp_index/working_paper 可复用")
        project_id, wp_index_id, wp_id, wp_code, cycle = picked
        saved = await _get_parsed(factory, wp_id)
        # 预置一个已有路径，验证并发写不覆盖既有键
        sheet1 = f"{wp_code}A"
        sheet2 = f"{wp_code}B"
        dk1, tid1 = await _seed_task(factory, project_id, wp_index_id, wp_id, wp_code, cycle, sheet1)
        dk2, tid2 = await _seed_task(factory, project_id, wp_index_id, wp_id, wp_code, cycle, sheet2)
        try:
            async def w(sheet, dk, val):
                async with factory() as s:
                    svc = ProcedureProjectionService(s)
                    await svc.write_path(wp_id, sheet, dk, {"marker": val})
                    await s.commit()

            await asyncio.gather(
                w(sheet1, dk1, "one"),
                w(sheet2, dk2, "two"),
            )
            import json
            async with factory() as s:
                raw = (await s.execute(sa.text("SELECT parsed_data FROM working_paper WHERE id=:id"), {"id": wp_id})).scalar()
            ps = (raw or {}).get("procedure_status") or {}
            # 两条不同路径均保留
            assert ps.get(sheet1, {}).get(dk1, {}).get("marker") == "one"
            assert ps.get(sheet2, {}).get(dk2, {}).get("marker") == "two"
        finally:
            await _cleanup(factory, wp_id, [dk1, dk2], [tid1, tid2], saved)
