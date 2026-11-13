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


async def _seed_without_trace_sources(pg_tx, object_type: str, version_type: str):
    """一个【测试】项目 + 按 object_type 原值登记的附件 + 同一引用的 wp_cell 附件与版本链反例。"""
    project_id = await make_project(pg_tx, f"lineage_empty_{object_type}")
    attachment_id = await make_attachment(pg_tx, project_id)
    object_id = uuid.uuid4()
    expected_link = await insert_lineage(
        pg_tx, attachment_id=attachment_id, target_type=object_type, target_ref=str(object_id), project_id=project_id,
    )
    await insert_lineage(
        pg_tx, attachment_id=attachment_id, target_type="wp_cell", target_ref=str(object_id), project_id=project_id,
    )
    pg_tx.add(VersionLineStamp(
        project_id=project_id, object_type=version_type, object_id=object_id, version_no=1,
        trace_id=f"fh-task27-{object_type}",
    ))
    await pg_tx.flush()
    return project_id, str(object_id), expected_link


def _assert_exact_attachments(result, object_type: str, expected_link) -> None:
    assert {item["id"] for item in result["attachments"]} == {str(expected_link)}
    assert {item["target_type"] for item in result["attachments"]} == {object_type}


async def test_adjustment_has_no_trace_sources_but_keeps_exact_attachment_type(pg_tx):
    """adjustment 不委托 wp/version 溯源；附件仍按请求 object_type 原值查询。"""
    project_id, object_id, link = await _seed_without_trace_sources(pg_tx, "adjustment", "adjustment")
    result = await UnifiedLineageService(pg_tx).query_lineage(project_id, "adjustment", object_id, direction="both")
    assert result["upstream"] == []
    assert result["downstream"] == [], "adjustment 不得读取已存在的版本链反例"
    assert result["partial"] is False
    assert result["errors"] == []
    _assert_exact_attachments(result, "adjustment", link)
    UnifiedLineageResponse.model_validate(result)


async def test_tb_row_has_own_source_without_wp_trace_and_keeps_exact_attachment_type(pg_tx):
    """tb_row 不委托 wp/version 溯源，另有试算表行子源（spec voucher-workflow-linkage-lineage-closure R8.1）：

    - 项目没有审计年度：子源报 ``TB_LINEAGE_YEAR_REQUIRED``（partial），附件照常返回（R8.3）；
    - 给了年度、本年度试算表没有这个科目：子源返回空、不报 partial。
    """
    project_id, object_id, link = await _seed_without_trace_sources(pg_tx, "tb_row", "trial_balance")
    service = UnifiedLineageService(pg_tx)

    no_year = await service.query_lineage(project_id, "tb_row", object_id, direction="both")
    assert no_year["upstream"] == []
    assert no_year["downstream"] == [], "tb_row 不得读取已存在的版本链反例"
    assert no_year["partial"] is True
    assert [(e["source"], e["error_code"]) for e in no_year["errors"]] == [("tb_row", "TB_LINEAGE_YEAR_REQUIRED")]
    _assert_exact_attachments(no_year, "tb_row", link)
    UnifiedLineageResponse.model_validate(no_year)

    with_year = await service.query_lineage(project_id, "tb_row", object_id, direction="both", year=2025)
    assert with_year["upstream"] == []
    assert with_year["downstream"] == []
    assert with_year["partial"] is False
    assert with_year["errors"] == []
    _assert_exact_attachments(with_year, "tb_row", link)
    UnifiedLineageResponse.model_validate(with_year)


async def test_missing_note_mapping_is_normal_not_found_and_does_not_poison_attachment_source(pg_tx):
    """注册表无章节是可解释的空结果，不再因不存在的旧表使 UnifiedLineage partial。"""
    project_id = await make_project(pg_tx, "lineage_not_found")
    project = await pg_tx.get(Project, project_id)
    assert project is not None
    project.template_type = "soe"
    attachment_id = await make_attachment(pg_tx, project_id)
    section = "FH-T27-附注"
    link_id = await insert_lineage(
        pg_tx,
        attachment_id=attachment_id,
        target_type="note_section",
        target_ref=section,
        project_id=project_id,
    )
    await pg_tx.flush()

    result = await UnifiedLineageService(pg_tx).query_lineage(
        project_id, "note_cell", section, direction="upstream", year=2025,
    )

    assert result["partial"] is False
    assert result["errors"] == []
    assert result["upstream"] == []
    assert {item["id"] for item in result["attachments"]} == {str(link_id)}
    assert (await pg_tx.execute(text("SELECT 1"))).scalar_one() == 1
    UnifiedLineageResponse.model_validate(result)
