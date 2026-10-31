"""UnifiedLineage 真 PG 合同：来源映射、空来源和子源 SAVEPOINT 隔离。

spec formula-hub-integrity-closure 任务 27；需求 9.1~9.3；ADR-FHIC-16。

只读真实项目的和平药房 D2；其余夹具均写入 ``pg_tx`` 内的【测试】项目，结束由外层事务回滚。
测试不 patch ``UnifiedLineageService`` 调用的任何 trace 函数。
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import select, text

from app.models.core import Project
from app.models.phase16_models import VersionLineStamp
from app.schemas.locate_target import LocateTargetSchema, trace_item_to_locate_target
from app.schemas.unified_lineage import UnifiedLineageResponse
from app.services.attachment_lineage_schema import clear_lineage_schema_cache
from app.services.unified_lineage_service import UnifiedLineageService
from app.services.wp_trace_service import trace_upstream
from tests.formula_hub._lineage_fixtures import insert_lineage, make_attachment, make_project

pytestmark = pytest.mark.pg_only


@pytest.fixture(autouse=True)
def _fresh_lineage_schema_cache():
    clear_lineage_schema_cache()
    yield
    clear_lineage_schema_cache()


async def _heping_project_id(session) -> uuid.UUID:
    rows = (await session.execute(
        select(Project.id, Project.name).where(
            Project.is_deleted == sa.false(),
            Project.name.ilike("%和平药房%"),
        ).order_by(Project.name, Project.id)
    )).all()
    assert len(rows) == 1, f"和平药房活项目应恰好 1 个，实得：{[(str(r.id), r.name) for r in rows]}"
    return rows[0].id


def _serialized(items) -> list[dict]:
    return [LocateTargetSchema.from_dataclass(trace_item_to_locate_target(item)).model_dump() for item in items]


async def test_heping_d2_upstream_equals_direct_trace_upstream(pg_tx):
    """wp_cell 必须传 ``source=workpaper`` 与去掉 ``!cell`` 后的 D2 标识。"""
    project_id = await _heping_project_id(pg_tx)
    direct = await trace_upstream(pg_tx, project_id, "workpaper", "D2")
    assert direct.items, "和平药房 D2 的直接上游为空，合同夹具会空转"

    result = await UnifiedLineageService(pg_tx).query_lineage(
        project_id, "wp_cell", "D2!B5", direction="upstream",
    )

    assert len(result["upstream"]) == len(direct.items)
    assert result["upstream"] == _serialized(direct.items)
    assert result["downstream"] == []
    assert result["partial"] is False
    assert result["errors"] == []
    UnifiedLineageResponse.model_validate(result)


async def test_tb_row_and_adjustment_have_no_trace_sources_but_keep_exact_attachment_type(pg_tx):
    """两类对象不委托 wp/version 溯源；附件仍按请求 object_type 原值查询。"""
    project_id = await make_project(pg_tx, "lineage_empty_sources")
    attachment_id = await make_attachment(pg_tx, project_id)
    cases = {
        "tb_row": (uuid.uuid4(), "trial_balance"),
        "adjustment": (uuid.uuid4(), "adjustment"),
    }
    expected_links: dict[str, uuid.UUID] = {}
    for object_type, (object_id, version_type) in cases.items():
        expected_links[object_type] = await insert_lineage(
            pg_tx,
            attachment_id=attachment_id,
            target_type=object_type,
            target_ref=str(object_id),
            project_id=project_id,
        )
        await insert_lineage(
            pg_tx,
            attachment_id=attachment_id,
            target_type="wp_cell",
            target_ref=str(object_id),
            project_id=project_id,
        )
        pg_tx.add(VersionLineStamp(
            project_id=project_id,
            object_type=version_type,
            object_id=object_id,
            version_no=1,
            trace_id=f"fh-task27-{object_type}",
        ))
    await pg_tx.flush()

    service = UnifiedLineageService(pg_tx)
    for object_type, (object_id, _version_type) in cases.items():
        result = await service.query_lineage(
            project_id, object_type, str(object_id), direction="both",
        )
        assert result["upstream"] == [], object_type
        assert result["downstream"] == [], f"{object_type} 不得读取已存在的版本链反例"
        assert result["partial"] is False, object_type
        assert result["errors"] == [], object_type
        assert {item["id"] for item in result["attachments"]} == {str(expected_links[object_type])}
        assert {item["target_type"] for item in result["attachments"]} == {object_type}
        UnifiedLineageResponse.model_validate(result)


async def test_missing_note_mapping_is_partial_and_does_not_poison_attachment_source(pg_tx):
    """缺失 note_wp_mapping 只让 report_trace 失败；保存点回滚后附件子源仍可查询。"""
    missing = (await pg_tx.execute(text("SELECT to_regclass('note_wp_mapping')"))).scalar_one()
    assert missing is None, "快照库意外存在 note_wp_mapping，无法验证指定失败场景"

    project_id = await make_project(pg_tx, "lineage_partial")
    attachment_id = await make_attachment(pg_tx, project_id)
    section = "FH-T27-附注"
    link_id = await insert_lineage(
        pg_tx,
        attachment_id=attachment_id,
        target_type="note_section",
        target_ref=section,
        project_id=project_id,
    )

    result = await UnifiedLineageService(pg_tx).query_lineage(
        project_id, "note_cell", section, direction="upstream", year=2025,
    )

    assert result["partial"] is True
    assert len(result["errors"]) == 1, result["errors"]
    error = result["errors"][0]
    assert error["source"] == "report_trace"
    assert error["error_code"] == "LINEAGE_SOURCE_FAILED"
    assert error["status"] == 500
    assert "附注报表溯源查询失败" in error["message"]
    assert {item["id"] for item in result["attachments"]} == {str(link_id)}
    assert (await pg_tx.execute(text("SELECT 1"))).scalar_one() == 1, "失败子源污染了后续事务"
    UnifiedLineageResponse.model_validate(result)
