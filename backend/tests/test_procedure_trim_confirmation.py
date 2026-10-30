"""粗裁确认当前态投影（spec trim-generation-plan-followup-optimizations R3）。

SQLite 真 ORM + 真实 ProcedureTrimService preview / apply：
- apply 成功（含 applied=0 的保存）在同一事务按 scope 循环写投影；细裁行请求不写；同 request_id 重试不重复写；
- apply 失败（版本变化 409 / 投影写入失败）整笔回滚：凭证不消费、程序行不变、投影不变；
- 投影与提交先后无关：同一组已消费凭证按任意顺序写入，结果都等于 ``(consumed_at, id)`` 最大者、保存次数 = 凭证数；
- 损坏的旧 JSON、操作人显示名降级、校验器能抓住篡改；读确认状态不扫描预览凭证历史。
真实 PostgreSQL 的回填 / 并发 / 查询计划见 ``test_procedure_trim_confirmation_pg.py``。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401
from app.models.base import Base, ProjectStatus, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.procedure_models import (  # noqa: E402
    ProcedureInstance,
    ProcedureOperationPreview,
    ProcedureTrimCycleConfirmation,
)
from app.models.staff_models import StaffMember  # noqa: E402
from app.services import procedure_generation_plan as gp  # noqa: E402
from app.services import procedure_trim_confirmation as tc  # noqa: E402
from app.services.procedure_trim_service import ProcedureTrimService  # noqa: E402

pytestmark = pytest.mark.asyncio
T0 = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
async def world():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(sa.text(
            "CREATE TABLE checklist_responses (id TEXT PRIMARY KEY, project_id TEXT, wp_id TEXT NOT NULL, "
            "item_id TEXT, updated_by TEXT)"
        ))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    project = Project(id=uuid.uuid4(), name="【测试】粗裁确认投影", client_name="【测试】粗裁确认投影",
                      status=ProjectStatus.execution, template_type="soe", report_scope="standalone", audit_year=2025)
    user = User(id=uuid.uuid4(), username="u_manager", email="m@example.com", hashed_password="x",
                role=UserRole.manager)
    async with factory() as s:
        s.add_all([project, user])
        await s.flush()
        s.add(StaffMember(user_id=user.id, name="王经理"))
        for i, (cycle, code) in enumerate((("D", "D2-5"), ("D", "D3"), ("A", "A1"))):
            s.add(ProcedureInstance(project_id=project.id, audit_cycle=cycle, procedure_code=code,
                                    procedure_name=code, status="execute", wp_code=code, sort_order=i * 10))
        await s.commit()
    yield {"engine": engine, "factory": factory, "pid": project.id, "user": user.id}
    await engine.dispose()


def _scope(cycle: str, code: str, status: str = "not_applicable", reason: str | None = "本期无此业务") -> dict:
    entry = {"kind": "scope", "cycle": cycle, "wp_index_code": code, "target_status": status}
    if status != "execute" and reason:
        entry["skip_reason"] = reason
    return entry


_ROW_ONLY = [{"kind": "row", "template_code": "D2-5", "sheet_key": "程序表",
              "definition_key": "D2-5::程序表::no-such-row", "target_applicability": "execute"}]


async def _preview(w, entries) -> uuid.UUID:
    async with w["factory"]() as s:
        pv = await ProcedureTrimService(s).preview_scheme(w["pid"], actor_user_id=w["user"], entries=entries)
        await s.commit()
    return uuid.UUID(pv["preview_id"])


async def _apply(w, entries, *, preview_id: uuid.UUID | None = None, request_id: str | None = None) -> dict:
    preview_id = preview_id or await _preview(w, entries)
    async with w["factory"]() as s:
        res = await ProcedureTrimService(s).apply_scheme(
            w["pid"], actor_user_id=w["user"], preview_id=preview_id,
            request_id=request_id or uuid.uuid4().hex, entries=entries)
        await s.commit()
    return res


async def _projection(w) -> dict[str, ProcedureTrimCycleConfirmation]:
    async with w["factory"]() as s:
        rows = (await s.execute(sa.select(ProcedureTrimCycleConfirmation).where(
            ProcedureTrimCycleConfirmation.project_id == w["pid"]))).scalars().all()
    return {r.audit_cycle: r for r in rows}


async def _preview_row(w, preview_id: uuid.UUID) -> ProcedureOperationPreview:
    async with w["factory"]() as s:
        return await s.get(ProcedureOperationPreview, preview_id)


def _aware(at: datetime) -> datetime:
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


async def _assert_verified(w) -> None:
    async with w["factory"]() as s:
        report = await tc.verify_projection(s, w["pid"])
    assert report.ok, report


# ── 写入：成功 / no-op / 细裁行 / 幂等重试 ────────────────────────────────


async def test_apply_writes_projection_per_scope_cycle_including_noop_and_skips_row_only(world):
    entries = [_scope("D", "D2-5"), _scope("A", "A1", "execute")]
    first_preview = await _preview(world, entries)
    first = await _apply(world, entries, preview_id=first_preview, request_id="req-first")
    assert first["applied"] == 1
    proj = await _projection(world)
    assert sorted(proj) == ["A", "D"]
    stored = await _preview_row(world, first_preview)
    groups = tc.scope_entries_by_cycle(stored.request_payload_snapshot["entries"])
    for cycle, row in proj.items():
        assert (row.source_preview_id, row.confirmed_by, row.request_id, row.revision_no) == (
            first_preview, world["user"], "req-first", 1)
        assert _aware(row.confirmed_at) == _aware(stored.consumed_at)
        assert row.cycle_revision_hash == tc.cycle_revision_hash(groups[cycle])
    assert proj["D"].cycle_revision_hash != proj["A"].cycle_revision_hash

    # 同样的决定再保存一次：没有任何程序行变化（applied=0）也算一次确认
    second_preview = await _preview(world, entries)
    second = await _apply(world, entries, preview_id=second_preview, request_id="req-second")
    assert second["applied"] == 0
    proj = await _projection(world)
    assert {c: (r.source_preview_id, r.request_id, r.revision_no) for c, r in proj.items()} == {
        "D": (second_preview, "req-second", 2), "A": (second_preview, "req-second", 2)}

    # 同一凭证同一 request_id 重试：走幂等分支返回旧结果，投影不再 +1
    replay = await _apply(world, entries, preview_id=second_preview, request_id="req-second")
    assert replay == second
    assert {c: r.revision_no for c, r in (await _projection(world)).items()} == {"D": 2, "A": 2}

    # 只有细裁行的请求：凭证照常消费，粗裁确认不变
    row_preview = await _preview(world, _ROW_ONLY)
    await _apply(world, _ROW_ONLY, preview_id=row_preview)
    assert (await _preview_row(world, row_preview)).consumed_at is not None
    assert {c: (r.source_preview_id, r.revision_no) for c, r in (await _projection(world)).items()} == {
        "D": (second_preview, 2), "A": (second_preview, 2)}
    await _assert_verified(world)


async def test_failed_apply_rolls_back_projection_with_the_domain_change(world):
    entries = [_scope("D", "D2-5")]
    stale = await _preview(world, entries)
    await _apply(world, entries)
    before = {c: (r.source_preview_id, r.revision_no) for c, r in (await _projection(world)).items()}
    async with world["factory"]() as s:
        with pytest.raises(HTTPException) as ei:
            await ProcedureTrimService(s).apply_scheme(
                world["pid"], actor_user_id=world["user"], preview_id=stale,
                request_id="req-stale", entries=entries)
        assert ei.value.status_code == 409
        await s.rollback()
    assert {c: (r.source_preview_id, r.revision_no) for c, r in (await _projection(world)).items()} == before
    assert (await _preview_row(world, stale)).consumed_at is None


async def test_projection_write_failure_aborts_the_whole_apply(world):
    """投影写不进去（表缺失：在被测函数的下一层 —— 数据库 —— 注入故障）⇒ 整笔 apply 回滚。"""
    entries = [_scope("D", "D3")]
    preview_id = await _preview(world, entries)
    async with world["engine"].begin() as conn:
        await conn.execute(sa.text("DROP TABLE procedure_trim_cycle_confirmations"))
    async with world["factory"]() as s:
        with pytest.raises(sa.exc.OperationalError):
            await ProcedureTrimService(s).apply_scheme(
                world["pid"], actor_user_id=world["user"], preview_id=preview_id,
                request_id="req-broken", entries=entries)
        await s.rollback()
    async with world["factory"]() as s:
        row = (await s.execute(sa.select(ProcedureInstance).where(
            ProcedureInstance.project_id == world["pid"], ProcedureInstance.procedure_code == "D3"))).scalar_one()
        preview = await s.get(ProcedureOperationPreview, preview_id)
    assert row.status == "execute", "程序行变更必须随投影写入失败一起回滚"
    assert preview.consumed_at is None and preview.consumed_request_id is None


async def test_record_confirmations_requires_a_consumed_trim_preview(world):
    async with world["factory"]() as s:
        for operation, consumed_at in (("trim", None), ("delegate", T0)):
            with pytest.raises(ValueError):
                await tc.record_confirmations(s, _transient(world, operation=operation, consumed_at=consumed_at))


# ── 与提交先后无关 / 同一时间平局 ─────────────────────────────────────────


def _transient(w, *, consumed_at, entries=None, operation: str = "trim", preview_id: uuid.UUID | None = None,
               actor: uuid.UUID | None = None, project_id: uuid.UUID | None = None,
               request_id: str | None = "req") -> ProcedureOperationPreview:
    return ProcedureOperationPreview(
        id=preview_id or uuid.uuid4(), actor_user_id=actor or w["user"], project_id=project_id or w["pid"],
        operation=operation, request_hash="a" * 64, membership_snapshot_hash="b" * 64,
        request_payload_snapshot={"operation": operation, "entries": entries or [_scope("D", "D3")]},
        expires_at=T0, consumed_at=consumed_at, consumed_request_id=request_id,
    )


async def test_projection_is_order_independent_and_breaks_ties_by_preview_id(world):
    """三份凭证（较早 1 份 + 同一最新时间 2 份）按三种提交顺序写入：结果都等于 (时间, 凭证 id) 最大者。"""
    other_actor = uuid.uuid4()
    late = T0 + timedelta(hours=1)
    results = []
    for n, order in enumerate(((0, 1, 2), (2, 1, 0), (1, 2, 0))):
        project_id, base = uuid.uuid4(), (n + 1) * 100  # 凭证只属于一个项目：每轮换一组 id，保持相对大小
        previews = [
            _transient(world, consumed_at=T0, preview_id=uuid.UUID(int=base + 9), request_id="old",
                       project_id=project_id),
            _transient(world, consumed_at=late, preview_id=uuid.UUID(int=base + 1), request_id="new-low",
                       project_id=project_id),
            _transient(world, consumed_at=late, preview_id=uuid.UUID(int=base + 2), request_id="new-high",
                       actor=other_actor, project_id=project_id),
        ]
        async with world["factory"]() as s:
            for i in order:
                await tc.record_confirmations(s, previews[i])
            await s.commit()
            row = (await s.execute(sa.select(ProcedureTrimCycleConfirmation).where(
                ProcedureTrimCycleConfirmation.project_id == project_id))).scalar_one()
        results.append((row.source_preview_id.int - base, row.confirmed_by, row.request_id, row.revision_no,
                        _aware(row.confirmed_at)))
        expected = tc.expected_projection([tc.ConsumedPreview(
            p.id, project_id, p.actor_user_id, p.consumed_at, p.consumed_request_id, p.request_payload_snapshot)
            for p in previews])[(project_id, "D")]
        assert (expected.source_preview_id.int - base, expected.revision_no) == (2, 3), "校验器与写入同一规则"
    assert results == [(2, other_actor, "new-high", 3, late)] * 3


# ── 损坏的旧 JSON / 指纹 ───────────────────────────────────────────────────


async def test_scope_grouping_and_hash_tolerate_corrupted_legacy_json():
    junk = [
        123, "scope", None, ["kind", "scope"],
        {"kind": "row", "cycle": "D"},
        {"kind": "scope", "cycle": 5, "wp_index_code": "D1"},
        {"kind": "scope", "cycle": "   ", "wp_index_code": "D1"},
        {"kind": "scope", "cycle": "TOOLONGCYCLE", "wp_index_code": "D1"},
        {"kind": "scope", "cycle": " d ", "wp_index_code": "D3", "target_status": "execute"},
        {"kind": "scope", "cycle": "D", "wp_index_code": 7, "target_status": None, "skip_reason": {"x": 1}},
    ]
    groups = tc.scope_entries_by_cycle(junk)
    assert list(groups) == ["D"] and len(groups["D"]) == 2
    assert tc.snapshot_entries({"entries": {"not": "a list"}}) == []
    assert tc.snapshot_entries("not a dict") == []
    assert tc.cycle_revision_hash(groups["D"]) == tc.cycle_revision_hash(list(reversed(groups["D"])))
    a = [_scope("D", "D2", reason="原因甲"), _scope("D", "D3", "execute")]
    b = [_scope("D", "D2", reason="原因乙"), _scope("D", "D3", "execute")]
    assert tc.cycle_revision_hash(a) != tc.cycle_revision_hash(b), "理由变化也是一次不同的决定"
    # 指纹算法与 V218 回填 SQL 同步（PG 用例逐字节对拍）；改算法必须同时改迁移
    assert tc.cycle_revision_hash([_scope("D", "D2", reason='带"引号"\\与\n换行'), _scope("D", "D1", "execute")]) == (
        "52c684344ba02bc2ab05fd73abc162dfcc8a713270baf6294c7a3e3c12a842d0"
    )


# ── 读取：显示名降级 / 不扫描凭证历史 ──────────────────────────────────────


async def test_display_name_falls_back_from_staff_to_username_to_none(world):
    named, plain, ghost = world["user"], uuid.uuid4(), uuid.uuid4()
    async with world["factory"]() as s:
        s.add(User(id=plain, username="u_plain", email="p@example.com", hashed_password="x", role=UserRole.auditor))
        await s.flush()
        s.add_all([StaffMember(user_id=plain, name="已离职", is_deleted=True),
                   StaffMember(user_id=named, name="王经理（新档案）",
                               created_at=datetime(2030, 1, 1, tzinfo=timezone.utc))])
        for cycle, actor in (("D", named), ("A", plain), ("Z", ghost)):
            await tc.record_confirmations(s, _transient(world, consumed_at=T0, actor=actor,
                                                         entries=[_scope(cycle, f"{cycle}1")]))
        await s.commit()
        out = await gp.load_cycle_confirmations(s, world["pid"])
    assert {c: v["confirmed_by"] for c, v in out.items()} == {"D": "王经理", "A": "u_plain", "Z": None}
    assert out["D"]["confirmed_at"].startswith("2026-10-01T08:00:00")


async def test_confirmation_reads_never_scan_preview_history(world):
    await _apply(world, [_scope("D", "D2-5")])
    statements: list[str] = []

    def _capture(_conn, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(world["engine"].sync_engine, "before_cursor_execute", _capture)
    try:
        async with world["factory"]() as s:
            confirmations = await gp.build_scope_confirmations(s, world["pid"])
    finally:
        event.remove(world["engine"].sync_engine, "before_cursor_execute", _capture)
    assert {c["cycle"]: c["trim_state"] for c in confirmations["cycles"]}["D"] == "confirmed"
    assert any("procedure_trim_cycle_confirmations" in st for st in statements)
    assert not [st for st in statements if "procedure_operation_previews" in st], "正常请求不得扫描凭证 JSON 历史"


# ── 校验器 ────────────────────────────────────────────────────────────────


async def test_verifier_catches_tampered_missing_and_unexpected_rows(world):
    await _apply(world, [_scope("D", "D2-5"), _scope("A", "A1", "execute")])
    await _assert_verified(world)
    async with world["factory"]() as s:
        await s.execute(sa.update(ProcedureTrimCycleConfirmation).where(
            ProcedureTrimCycleConfirmation.audit_cycle == "D").values(confirmed_by=uuid.uuid4()))
        await s.execute(sa.delete(ProcedureTrimCycleConfirmation).where(
            ProcedureTrimCycleConfirmation.audit_cycle == "A"))
        await tc.record_confirmations(s, _transient(world, consumed_at=T0, entries=[_scope("Z", "Z1")]))
        report = await tc.verify_projection(s, world["pid"])
        await s.rollback()
    assert not report.ok
    assert report.missing == [(world["pid"], "A")]
    assert report.unexpected == [(world["pid"], "Z")]
    assert [m[:2] for m in report.field_mismatches] == [(world["pid"], "D")]
    assert "confirmed_by" in report.field_mismatches[0][2]
    assert sorted(m[1] for m in report.legacy_mismatches) == ["A", "D", "Z"]
