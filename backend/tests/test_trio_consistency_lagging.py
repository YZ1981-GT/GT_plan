"""三件套一致性可定位滞后类别 — deliverable-lineage-wiring-… Wave 4 Task 24 / 25.1

Property 23：三类绑定 hash 不一致时，返回结果能指出**哪一类**与多数不同。

改造前 `check_trio_consistency` 只返回 `consistent` + 一句 `message`，交付中心把它
拼进 warnings 显示成一行文字 ⇒ 审计师看不出该重新生成哪一类。本文件钉住：

- 有严格多数 ⇒ `lagging` 精确列出少数派、`majority_tb_hash` 非空
- **无严格多数**（三类各不相同 / 两类各一票）⇒ `ambiguous=True` 且 `lagging` 为空
  🔴 反向自检：此时若硬指一类，审计师会照着重新生成**错的**那一类
- 未全部生成（present < 2）⇒ 不判不一致（fail-open，避免刚开工就红）
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.phase13_models import (
    WordExportStatus,
    WordExportTask,
    WordExportTaskVersion,
)
from app.services.deliverable_snapshot_service import (
    STANDARD_TRIO,
    DeliverableSnapshotService,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

H1, H2, H3 = "1" * 64, "2" * 64, "3" * 64
YEAR = 2025


async def _mk_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            WordExportTask.metadata.create_all,
            tables=[WordExportTask.__table__, WordExportTaskVersion.__table__],
        )
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


def _check(hashes: dict[str, str | None]):
    """按给定绑定建三件套任务，跑一致性校验。"""

    async def _scenario(session):
        project_id = uuid.uuid4()
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for i, doc_type in enumerate(STANDARD_TRIO):
            h = hashes.get(doc_type)
            if h is _MISSING:
                continue
            session.add(
                WordExportTask(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    doc_type=doc_type,
                    status=WordExportStatus.generated.value,
                    created_by=uuid.uuid4(),
                    source_snapshot_refs={"tb_hash": h} if h else None,
                    updated_at=base + timedelta(minutes=i),
                )
            )
        await session.flush()
        return await DeliverableSnapshotService(session).check_trio_consistency(
            project_id, YEAR
        )

    return _run(_scenario)


class _Missing:
    def __repr__(self) -> str:  # pragma: no cover - 仅调试可读
        return "<未生成>"


_MISSING = _Missing()


def test_trio_labels_cover_all_three():
    """中文名表必须覆盖三件套全部 doc_type（否则消息里出现裸英文）。"""
    from app.services.deliverable_snapshot_service import _TRIO_LABEL

    for doc_type in STANDARD_TRIO:
        assert doc_type in _TRIO_LABEL, f"{doc_type} 缺中文名 ⇒ 滞后提示会显示裸英文"
        assert _TRIO_LABEL[doc_type].strip()


def test_all_same_hash_is_consistent():
    res = _check({d: H1 for d in STANDARD_TRIO})
    assert res.consistent is True
    assert res.lagging == []
    assert res.ambiguous is False
    assert res.majority_tb_hash == H1


@pytest.mark.parametrize("lagging_doc", list(STANDARD_TRIO))
def test_property_23_points_out_the_lagging_doc_type(lagging_doc):
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 23
    """两类绑定 H1、一类绑定 H2 ⇒ 精确指出那一类滞后。"""
    hashes = {d: (H2 if d == lagging_doc else H1) for d in STANDARD_TRIO}
    res = _check(hashes)

    assert res.consistent is False
    assert res.majority_tb_hash == H1
    assert res.lagging == [lagging_doc], f"未精确指出滞后类别，实得 {res.lagging}"
    assert res.ambiguous is False
    # 消息必须点名（中文），否则前端仍看不出该重新生成哪一类
    from app.services.deliverable_snapshot_service import _TRIO_LABEL

    assert _TRIO_LABEL[lagging_doc] in (res.message or "")


def test_three_way_disagreement_is_ambiguous_not_a_guess():
    """🔴 三类各不相同 ⇒ 不得指名，只标 ambiguous。

    反向自检：若实现改成「取任一 hash 当多数」，`lagging` 会非空 ——
    审计师会照着重新生成**错的**那一类，比不提示更坏。
    """
    res = _check({
        STANDARD_TRIO[0]: H1,
        STANDARD_TRIO[1]: H2,
        STANDARD_TRIO[2]: H3,
    })
    assert res.consistent is False
    assert res.ambiguous is True
    assert res.lagging == [], "无严格多数时凭空指名 = 误导"
    assert res.majority_tb_hash is None
    assert "无法判定" in (res.message or "")


def test_two_way_tie_is_ambiguous():
    """只有两类生成且各绑定不同 ⇒ 1:1 平票，同样不得指名。"""
    res = _check({
        STANDARD_TRIO[0]: H1,
        STANDARD_TRIO[1]: H2,
        STANDARD_TRIO[2]: _MISSING,
    })
    assert res.consistent is False
    assert res.ambiguous is True
    assert res.lagging == []


def test_fewer_than_two_present_does_not_flag_inconsistent():
    """只生成一类（或全未生成）⇒ 不判不一致（刚开工不该常亮红）。"""
    for hashes in (
        {STANDARD_TRIO[0]: H1, STANDARD_TRIO[1]: _MISSING, STANDARD_TRIO[2]: _MISSING},
        {d: _MISSING for d in STANDARD_TRIO},
        # 任务存在但无绑定（历史数据）同样不算「present」
        {d: None for d in STANDARD_TRIO},
    ):
        res = _check(hashes)
        assert res.consistent is True, hashes
        assert res.lagging == []
        assert res.ambiguous is False


def test_tb_hashes_exposes_all_three_for_column_view():
    """需求 11.3 的三列对照要求逐类下发绑定（未生成的也要有键，值为 None）。"""
    res = _check({
        STANDARD_TRIO[0]: H1,
        STANDARD_TRIO[1]: H2,
        STANDARD_TRIO[2]: _MISSING,
    })
    assert set(res.tb_hashes) == set(STANDARD_TRIO), (
        "缺键会让前端三列对照少一列 ⇒ 看不出哪一类尚未生成"
    )
    assert res.tb_hashes[STANDARD_TRIO[2]] is None


def test_completeness_result_carries_trio_fields():
    """契约：完整性结果与 schema 必须把这些字段带到前端。"""
    from dataclasses import fields as dc_fields

    from app.models.phase13_schemas import CompletenessResponse
    from app.services.completeness_service import CompletenessResult

    names = {f.name for f in dc_fields(CompletenessResult)}
    schema = set(CompletenessResponse.model_fields)
    for name in (
        "trio_tb_hashes",
        "trio_lagging",
        "trio_majority_tb_hash",
        "trio_ambiguous",
    ):
        assert name in names, f"CompletenessResult 缺 {name}"
        assert name in schema, f"CompletenessResponse 缺 {name} ⇒ 前端拿不到"
