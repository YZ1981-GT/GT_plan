"""章节状态落库接线测试 — deliverable-lineage-wiring-and-writeback-closure Task 4.1

覆盖：
- Property 3：`snapshot_on_confirm` 后 section_code 集合 == kept_codes，
  且每行 anchor_name == anchor_name(section_code)
- additive kwarg 三态：不传 ⇒ 三列保持 None（与引入前逐字节等价）；传 ⇒ 落库；
  二次 upsert 不传 ⇒ **保留原值**（不把已有锚点抹成 None）
- `persist_note_export_section_states` fail-open（异常只 warning，返回 0）
- 反向自检：不调用该函数则表恒空（这正是历史假绿的根因 —— 只测 snapshot_on_confirm
  本身永远发现不了「没人调用它」）
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import sqlalchemy as sa
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.audit_platform_models import DeliverableSectionState
from app.services.deliverable_section_state_service import (
    DeliverableSectionStateService,
    persist_note_export_section_states,
)
from app.services.note_word_exporter import NoteExportMeta
from app.services.section_anchor_utils import anchor_name

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

ALL_CODES = ["八、1", "八、2", "五、1", "八、22"]


async def _session():
    # compute_source_snapshot_hash 会读 disclosure_notes + trial_balance，
    # 三张表都要建，否则「落库失败」会被 fail-open 吞成 0（假绿）。
    from app.models.audit_platform_models import TrialBalance
    from app.models.report_models import DisclosureNote

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            DeliverableSectionState.metadata.create_all,
            tables=[
                DeliverableSectionState.__table__,
                TrialBalance.__table__,
                DisclosureNote.__table__,
            ],
        )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _rows(session, task_id) -> list[DeliverableSectionState]:
    res = await session.execute(
        sa.select(DeliverableSectionState).where(
            DeliverableSectionState.word_export_task_id == task_id
        )
    )
    return list(res.scalars().all())


def _run(coro_factory):
    async def _main():
        engine, factory = await _session()
        try:
            async with factory() as session:
                return await coro_factory(session)
        finally:
            await engine.dispose()

    return asyncio.run(_main())


# ─── Property 3 ──────────────────────────────────────────────────────────────


@given(kept=st.lists(st.sampled_from(ALL_CODES), min_size=1, max_size=4, unique=True))
@settings(max_examples=5, deadline=None)
def test_property_3_states_match_kept_codes_with_anchors(kept):
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 3
    task_id = uuid.uuid4()
    project_id = uuid.uuid4()
    meta = NoteExportMeta(
        kept_codes=list(kept),
        anchor_map={c: anchor_name(c) for c in kept},
        rendered_block_hashes={c: f"{i:064d}" for i, c in enumerate(kept)},
    )

    async def _scenario(session):
        n = await persist_note_export_section_states(
            session,
            word_export_task_id=task_id,
            project_id=project_id,
            year=2025,
            meta=meta,
            version_no=3,
        )
        rows = await _rows(session, task_id)
        return n, rows

    n, rows = _run(_scenario)

    assert n == len(kept)
    assert {r.section_code for r in rows} == set(kept)
    for r in rows:
        assert r.anchor_name == anchor_name(r.section_code)
        assert r.version_no == 3
        assert r.rendered_block_hash == meta.rendered_block_hashes[r.section_code]
        assert r.is_stale is False
        assert r.source_snapshot_hash and len(r.source_snapshot_hash) == 64


# ─── additive kwarg 三态 ─────────────────────────────────────────────────────


def test_without_kwargs_three_columns_stay_none():
    """不传三个 additive kwarg ⇒ 三列均为 None（与引入前逐字节等价）。"""
    task_id = uuid.uuid4()

    async def _scenario(session):
        svc = DeliverableSectionStateService(session)
        await svc.snapshot_on_confirm(task_id, uuid.uuid4(), 2025, ["八、1"])
        return await _rows(session, task_id)

    rows = _run(_scenario)
    assert len(rows) == 1
    assert rows[0].anchor_name is None
    assert rows[0].version_no is None
    assert rows[0].rendered_block_hash is None


def test_second_upsert_without_kwargs_preserves_existing_values():
    """二次 upsert 不传 kwarg ⇒ **保留**已有锚点/哈希，不抹成 None。

    反向自检意义：若实现写成无条件赋值，重新生成一次就把锚点抹掉 →
    溯源面板与刷新立刻失效，而单测若只跑首次 upsert 是发现不了的。
    """
    task_id = uuid.uuid4()

    async def _scenario(session):
        svc = DeliverableSectionStateService(session)
        await svc.snapshot_on_confirm(
            task_id,
            uuid.uuid4(),
            2025,
            ["八、1"],
            anchor_map={"八、1": "sec_八_1"},
            version_no=1,
            rendered_block_hashes={"八、1": "a" * 64},
        )
        await svc.snapshot_on_confirm(task_id, uuid.uuid4(), 2025, ["八、1"])
        return await _rows(session, task_id)

    rows = _run(_scenario)
    assert rows[0].anchor_name == "sec_八_1"
    assert rows[0].version_no == 1
    assert rows[0].rendered_block_hash == "a" * 64


def test_upsert_updates_anchor_when_provided_again():
    task_id = uuid.uuid4()

    async def _scenario(session):
        svc = DeliverableSectionStateService(session)
        await svc.snapshot_on_confirm(
            task_id, uuid.uuid4(), 2025, ["八、1"],
            anchor_map={"八、1": "sec_old"}, version_no=1,
            rendered_block_hashes={"八、1": "a" * 64},
        )
        await svc.snapshot_on_confirm(
            task_id, uuid.uuid4(), 2025, ["八、1"],
            anchor_map={"八、1": "sec_八_1"}, version_no=2,
            rendered_block_hashes={"八、1": "b" * 64},
        )
        return await _rows(session, task_id)

    rows = _run(_scenario)
    assert len(rows) == 1, "唯一约束 (task, section_code) 下不应产生第二行"
    assert rows[0].anchor_name == "sec_八_1"
    assert rows[0].version_no == 2
    assert rows[0].rendered_block_hash == "b" * 64


# ─── get_section_states 返回键集契约 ────────────────────────────────────────


# 这是 `/section-states` 端点、溯源面板与刷新链路的唯一读出口。
# 少返一个键 ⇒ 前端/验收脚本静默读到 undefined（列在 DB 里有值也白搭），
# 而只测「写进去了」的用例永远发现不了 —— Task 11 真实链路验收正是被这一处卡住。
_SECTION_STATE_KEYS = {
    "section_code",
    "source_snapshot_hash",
    "is_stale",
    "last_writeback_baseline_hash",
    "anchor_name",
    "version_no",
    "rendered_block_hash",
}


def test_get_section_states_returns_full_key_set_with_values():
    """读出口必须返回全部持久化列，且值与写入一致。"""
    task_id = uuid.uuid4()

    async def _scenario(session):
        svc = DeliverableSectionStateService(session)
        await svc.snapshot_on_confirm(
            task_id,
            uuid.uuid4(),
            2025,
            ["八、1"],
            anchor_map={"八、1": "sec_八_1"},
            version_no=7,
            rendered_block_hashes={"八、1": "c" * 64},
        )
        return await svc.get_section_states(task_id)

    states = _run(_scenario)

    assert len(states) == 1
    assert set(states[0]) == _SECTION_STATE_KEYS, (
        "get_section_states 返回键集与持久化列不一致 —— "
        "新增列必须同时补进返回 dict，否则下游静默读到 undefined"
    )
    assert states[0]["rendered_block_hash"] == "c" * 64
    assert states[0]["anchor_name"] == "sec_八_1"
    assert states[0]["version_no"] == 7


def test_reverse_selfcheck_missing_key_would_be_undefined_downstream():
    """反向自检：钉死「DB 有值 ≠ 读出口有值」这两件事互相独立。

    模拟旧实现（返回 dict 少 rendered_block_hash）后，下游 `.get()` 得 None ——
    与「该列压根没写进 DB」完全同形、无法区分。故上一条断言不可删。
    """
    row_like = {"section_code": "八、1", "rendered_block_hash": "c" * 64}
    legacy_projection = {k: v for k, v in row_like.items() if k != "rendered_block_hash"}

    assert row_like.get("rendered_block_hash") == "c" * 64
    assert legacy_projection.get("rendered_block_hash") is None


# ─── fail-open 与空 meta ─────────────────────────────────────────────────────


def test_empty_meta_persists_nothing():
    """programmatic 模式 meta 为空壳 ⇒ 不落库、不报错（返回 0）。"""
    task_id = uuid.uuid4()

    async def _scenario(session):
        n = await persist_note_export_section_states(
            session,
            word_export_task_id=task_id,
            project_id=uuid.uuid4(),
            year=2025,
            meta=NoteExportMeta(),
        )
        return n, await _rows(session, task_id)

    n, rows = _run(_scenario)
    assert n == 0
    assert rows == []


@pytest.mark.asyncio
async def test_persist_is_fail_open_on_db_error():
    """DB 异常只 warning + 返回 0，绝不向上抛（需求 1.6：不阻断已生成的交付件）。"""

    class _BoomSession:
        async def execute(self, *a, **kw):
            raise RuntimeError("boom")

        def add(self, obj):  # pragma: no cover
            raise RuntimeError("boom")

        async def flush(self):  # pragma: no cover
            raise RuntimeError("boom")

    n = await persist_note_export_section_states(
        _BoomSession(),
        word_export_task_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        year=2025,
        meta=NoteExportMeta(kept_codes=["八、1"], anchor_map={"八、1": "sec_八_1"}),
    )
    assert n == 0


# ─── 反向自检：不接线则表恒空 ────────────────────────────────────────────────


def test_reverse_selfcheck_no_wiring_means_empty_table():
    """不调用落库函数 ⇒ 表恒空。

    这正是历史缺陷的机理：`snapshot_on_confirm` 实现正确、28 条属性测试全绿，
    但全仓无生产调用方 ⇒ 表恒空 ⇒ `/section-states` 返空 ⇒ 回填恒返回全空。
    故「导出路径是否真的调用了落库」必须由 Task 2.1/11 的路径级/真实链路测试保证，
    单测 snapshot_on_confirm 本身**永远发现不了**。
    """
    task_id = uuid.uuid4()

    async def _scenario(session):
        return await _rows(session, task_id)

    assert _run(_scenario) == []
