"""版本链溯源展示（后端派生字段）— deliverable-lineage-wiring-… Wave 4 Task 23

覆盖 Property 22 的后端半边（前端半边在 `deliverableVersionList.spec.ts`）：
版本链必须下发**绑定快照 / stale 三态 / 实际编辑人 / 差异检测结论**，
否则前端只能拿 `created_by` 近似编辑人、拿不到 task 级绑定而无法判 stale。

🔴 `is_stale` 必须三态（True / False / None）：任一侧 tb_hash 缺失时返 None。
退化成布尔会让历史版本（无绑定）一律显示成「与上游一致」= 骗人。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.core import User
from app.models.phase13_models import (
    WordExportStatus,
    WordExportTask,
    WordExportTaskVersion,
)
from app.models.phase13_schemas import DeliverableVersionSchema
from app.services.deliverable_service import DeliverableService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_HASH_A = "a" * 64
_HASH_B = "b" * 64


async def _mk_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            WordExportTask.metadata.create_all,
            tables=[WordExportTask.__table__, WordExportTaskVersion.__table__],
        )
        await conn.run_sync(User.metadata.create_all, tables=[User.__table__])
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _run(scenario):
    async def _main():
        engine, factory = await _mk_session()
        try:
            async with factory() as session:
                return await scenario(session)
        finally:
            await engine.dispose()

    return asyncio.run(_main())


async def _seed(
    session,
    *,
    task_refs: dict | None,
    version_refs: dict | None,
    created_via: str = "onlyoffice_edit",
    with_editor: bool = True,
    drift_report: dict | None = None,
):
    # 🔴 `User` 的 NOT NULL 无默认列 = username / email / hashed_password / role
    #（列名是 `hashed_password` 不是 `password_hash`；漏了以 TypeError 在构造时炸）。
    creator = User(
        id=uuid.uuid4(),
        username="创建人",
        email="creator@example.com",
        hashed_password="x",
        role="staff",
    )
    editor = User(
        id=uuid.uuid4(),
        username="张三",
        email="editor@example.com",
        hashed_password="x",
        role="staff",
    )
    session.add_all([creator, editor])
    await session.flush()

    task = WordExportTask(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        doc_type="financial_report",
        status=WordExportStatus.generated.value,
        created_by=creator.id,
        source_snapshot_refs=task_refs,
    )
    session.add(task)
    await session.flush()

    version = WordExportTaskVersion(
        id=uuid.uuid4(),
        word_export_task_id=task.id,
        version_no=1,
        file_path="storage/deliverables/x_v1.xlsx",
        created_by=creator.id,
        created_via=created_via,
        source_snapshot_refs=version_refs,
        edited_by=editor.id if with_editor else None,
        edited_at=datetime.now(timezone.utc) if with_editor else None,
        drift_report=drift_report,
    )
    session.add(version)
    await session.flush()
    return task, version, creator, editor


@pytest.mark.parametrize(
    "task_refs,version_refs,expected",
    [
        ({"tb_hash": _HASH_A}, {"tb_hash": _HASH_A}, False),
        ({"tb_hash": _HASH_B}, {"tb_hash": _HASH_A}, True),
        ({"tb_hash": _HASH_A}, None, None),
        (None, {"tb_hash": _HASH_A}, None),
        (None, None, None),
        ({}, {}, None),
    ],
)
def test_property_22_is_stale_is_three_state(task_refs, version_refs, expected):
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 22
    async def _scenario(session):
        task, _v, _c, _e = await _seed(
            session, task_refs=task_refs, version_refs=version_refs
        )
        return await DeliverableService(session).get_version_chain_view(task.id)

    rows = _run(_scenario)
    assert len(rows) == 1
    assert rows[0]["is_stale"] is expected


def test_reverse_selfcheck_naive_bool_would_lie_on_missing_hash():
    """反向自检：朴素 `bound != task_hash` 在缺失侧会给出**确定性结论**。

    版本无绑定（历史数据）时 `None != 'aaa'` 为 True ⇒ 显示「上游已变更」；
    反过来两侧都缺时 `None != None` 为 False ⇒ 显示「与上游一致」。
    两者都是编造，故必须三态。
    """
    assert (None != _HASH_A) is True  # noqa: SIM201 — 刻意复现朴素判据
    assert (None != None) is False  # noqa: E711,SIM201


def test_editor_name_comes_from_edited_by_not_created_by():
    """编辑人只能来自 `edited_by`（V142 列）。

    🔴 OO 路径下 `created_by` 只是回调处理占位（NOT NULL 列无法表达"未知"），
    拿它当编辑人会让所有在线编辑版本都显示成交付物创建人。
    """

    async def _scenario(session):
        task, _v, creator, editor = await _seed(
            session, task_refs=None, version_refs=None, with_editor=True
        )
        rows = await DeliverableService(session).get_version_chain_view(task.id)
        return rows, creator, editor

    rows, creator, editor = _run(_scenario)
    assert rows[0]["edited_by"] == editor.id
    assert rows[0]["edited_by_name"] == "张三"
    assert rows[0]["edited_by_name"] != "创建人"
    assert rows[0]["created_by"] == creator.id


def test_editor_name_is_none_when_unknown():
    """解析不出编辑人时如实为 None，**不得**回退创建人名。"""

    async def _scenario(session):
        task, _v, _c, _e = await _seed(
            session, task_refs=None, version_refs=None, with_editor=False
        )
        return await DeliverableService(session).get_version_chain_view(task.id)

    rows = _run(_scenario)
    assert rows[0]["edited_by"] is None
    assert rows[0]["edited_by_name"] is None


@pytest.mark.parametrize(
    "drift,blocked",
    [
        (None, False),
        ({"diffs": []}, False),
        ({"diffs": [{"row_name": "应收账款", "sheet": "bs", "coord": "C12"}]}, True),
        ({"unavailable": "映射解析失败"}, True),
    ],
)
def test_drift_decision_goes_through_single_entry(drift, blocked):
    """`drift_blocked` 必须由 `should_block_confirm` 判定。

    反向自检语义：若前端/本方法自己写 `if drift_report:`，
    `{"diffs": []}`（已比对且一致）会被误判成有差异 ⇒ 配了映射的报表永远确认不了。
    """

    async def _scenario(session):
        task, _v, _c, _e = await _seed(
            session, task_refs=None, version_refs=None, drift_report=drift
        )
        return await DeliverableService(session).get_version_chain_view(task.id)

    rows = _run(_scenario)
    assert rows[0]["drift_blocked"] is blocked
    assert rows[0]["drift_report"] == drift
    if blocked:
        assert rows[0]["drift_reason"]
    else:
        assert rows[0]["drift_reason"] is None


def test_bound_tb_hash_is_exposed_for_short_display():
    async def _scenario(session):
        task, _v, _c, _e = await _seed(
            session, task_refs={"tb_hash": _HASH_A}, version_refs={"tb_hash": _HASH_A}
        )
        return await DeliverableService(session).get_version_chain_view(task.id)

    rows = _run(_scenario)
    assert rows[0]["bound_tb_hash"] == _HASH_A


def test_schema_accepts_view_rows():
    """视图字典必须能被 `DeliverableVersionSchema` 校验（路由直接 model_validate）。"""

    async def _scenario(session):
        task, _v, _c, _e = await _seed(
            session,
            task_refs={"tb_hash": _HASH_A},
            version_refs={"tb_hash": _HASH_B},
            drift_report={"diffs": []},
        )
        return await DeliverableService(session).get_version_chain_view(task.id)

    rows = _run(_scenario)
    dto = DeliverableVersionSchema.model_validate(rows[0])
    assert dto.is_stale is True
    assert dto.bound_tb_hash == _HASH_B
    assert dto.edited_by_name == "张三"
    assert dto.drift_blocked is False


def test_schema_has_lineage_fields():
    """契约：schema 字段集必须含本波次新增的展示字段（缺一即前端拿不到）。"""
    fields = set(DeliverableVersionSchema.model_fields)
    for name in (
        "edited_by",
        "edited_at",
        "edited_by_name",
        "bound_tb_hash",
        "is_stale",
        "drift_report",
        "drift_blocked",
        "drift_reason",
    ):
        assert name in fields, f"DeliverableVersionSchema 缺 {name}"


def test_router_uses_view_not_raw_orm():
    """源码级：版本链端点必须走 view，否则派生字段全部为默认值（静默丢失）。"""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1] / "app" / "routers" / "deliverable.py"
    ).read_text(encoding="utf-8")
    i = src.index("async def get_version_chain")
    j = src.index("async def compare_versions")
    body = src[i:j]
    assert "get_version_chain_view" in body, "端点仍返回裸 ORM ⇒ 溯源字段全丢"
