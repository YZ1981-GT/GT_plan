"""属性测试 — wp-traceability-panel Task 5.1

**Validates: Requirements 1.1, 1.2, 3.2**

Property 1: 统一端点返回的 upstream/downstream 是现有 3 个 trace service 结果的超集
Property 2: 附件关联后，lineage 查询能返回该附件
Property 3: 图谱节点点击触发 locateCell 且参数正确
"""

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.schemas.locate_target import LocateTarget, LocateTargetSchema
from app.services.unified_lineage_service import UnifiedLineageService
from app.services.wp_trace_service import TraceItem, TraceResult


# ─── Strategies ──────────────────────────────────────────────────────────────

wp_code_st = st.from_regex(r"[A-N]\d{1,2}(-\d{1,2})?", fullmatch=True)
sheet_name_st = st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N")))
cell_ref_st = st.from_regex(r"[A-Z]{1,2}\d{1,4}", fullmatch=True)
object_type_st = st.sampled_from(["wp_cell", "report_row", "note_cell", "tb_row", "adjustment"])
direction_st = st.sampled_from(["both", "upstream", "downstream"])


def _mock_db() -> AsyncMock:
    @asynccontextmanager
    async def _savepoint():
        yield

    db = AsyncMock()
    db.begin_nested = MagicMock(side_effect=_savepoint)
    db.execute = AsyncMock(return_value=MagicMock(fetchall=lambda: []))
    return db


# ─── Property 1: 统一端点超集 ────────────────────────────────────────────────


class TestProperty1UnifiedEndpointSuperset:
    """Property 1: 统一端点返回的 upstream/downstream 是现有 trace service 结果的超集。

    **Validates: Requirements 1.1, 1.2**
    """

    @settings(max_examples=15, deadline=None)
    @given(
        wp_code=wp_code_st,
        direction=direction_st,
    )
    @pytest.mark.asyncio
    async def test_upstream_contains_wp_trace_results(self, wp_code: str, direction: str):
        """统一端点 upstream 包含 wp_trace_service 的所有结果。"""
        project_id = uuid.uuid4()
        mock_db = _mock_db()

        # 构造 wp_trace 返回的 items
        trace_items = [
            TraceItem(wp_code=f"A{i}", sheet=f"Sheet{i}", cell=f"B{i}", value=i * 100)
            for i in range(1, 4)
        ]
        mock_result = TraceResult(source="wp", identifier=wp_code, direction="upstream", items=trace_items)

        svc = UnifiedLineageService(mock_db)

        with patch("app.services.unified_lineage_service.trace_upstream", return_value=mock_result), \
             patch("app.services.unified_lineage_service.trace_downstream", return_value=MagicMock(items=[])), \
             patch("app.services.unified_lineage_service.version_line_service") as mock_vl:
            mock_vl.query_lineage = AsyncMock(return_value=[])

            result = await svc.query_lineage(
                project_id=project_id,
                object_type="wp_cell",
                object_id=wp_code,
                direction=direction,
            )

        if direction in ("both", "upstream"):
            # 所有 wp_trace items 的 wp_code 必须出现在 upstream 中
            upstream_codes = {t["wp_code"] for t in result["upstream"]}
            for item in trace_items:
                assert item.wp_code in upstream_codes, (
                    f"wp_trace item {item.wp_code} 未出现在统一端点 upstream 中"
                )

    @settings(max_examples=15, deadline=None)
    @given(
        wp_code=wp_code_st,
    )
    @pytest.mark.asyncio
    async def test_downstream_contains_wp_trace_results(self, wp_code: str):
        """统一端点 downstream 包含 wp_trace_service 的所有结果。"""
        project_id = uuid.uuid4()
        mock_db = _mock_db()

        trace_items = [
            TraceItem(wp_code=f"K{i}", sheet=f"汇总{i}", cell=f"C{i}", value=i * 50)
            for i in range(1, 3)
        ]
        mock_result = TraceResult(source="wp", identifier=wp_code, direction="downstream", items=trace_items)

        svc = UnifiedLineageService(mock_db)

        with patch("app.services.unified_lineage_service.trace_upstream", return_value=MagicMock(items=[])), \
             patch("app.services.unified_lineage_service.trace_downstream", return_value=mock_result), \
             patch("app.services.unified_lineage_service.version_line_service") as mock_vl:
            mock_vl.query_lineage = AsyncMock(return_value=[])

            result = await svc.query_lineage(
                project_id=project_id,
                object_type="wp_cell",
                object_id=wp_code,
                direction="both",
            )

        downstream_codes = {t["wp_code"] for t in result["downstream"]}
        for item in trace_items:
            assert item.wp_code in downstream_codes


# ─── Property 2: 附件关联可查 ────────────────────────────────────────────────


class TestProperty2AttachmentLinkQueryable:
    """Property 2: 附件关联后，lineage 查询能返回该附件。

    **Validates: Requirements 3.2**

    附件子源已收口到 ``AttachmentTraceService.for_object``（底稿读 EvidenceLink / 整稿关联 / reference，输出域读
    AttachmentLineage，多条查询）；原用例模拟「一条 fetchall 查询」并在本模块打补丁检查迁移就绪，对新实现不再成立
    （子源报错 ⇒ 附件为空，如 ``wp_cell`` / ``'0'``）。各来源的真实 SQL 由
    ``tests/attachment_platform_closure/test_attachment_trace_service.py``（SQLite 真库）覆盖；本属性只验统一层：
    任意对象类型与标识下，附件子源给出的附件原样出现在结果里，且按原参数调用、不标 partial。
    """

    @settings(max_examples=15, deadline=None)
    @given(
        object_type=st.sampled_from(["wp_cell", "report_row", "note_cell", "tb_row", "adjustment"]),
        object_id=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "P"))),
    )
    @pytest.mark.asyncio
    async def test_linked_attachment_appears_in_lineage(self, object_type: str, object_id: str):
        """关联的附件必须出现在 lineage 查询的 attachments 中。"""
        project_id = uuid.uuid4()
        attachment = {"id": str(uuid.uuid4()), "attachment_id": str(uuid.uuid4()), "target_type": object_type,
                      "target_ref": object_id, "file_name": "evidence.pdf", "file_type": "pdf",
                      "created_at": None, "source": "attachment_lineage"}
        calls: list[tuple] = []

        async def fake_for_object(self, pid, otype, oid):
            calls.append((pid, otype, oid))
            return [attachment]

        svc = UnifiedLineageService(_mock_db())
        with patch("app.services.unified_lineage_service.trace_upstream", return_value=MagicMock(items=[])), \
             patch("app.services.unified_lineage_service.trace_downstream", return_value=MagicMock(items=[])), \
             patch("app.services.unified_lineage_service.version_line_service") as mock_vl, \
             patch("app.services.unified_lineage_service.tb_row_upstream", new=AsyncMock(return_value=[])), \
             patch("app.services.unified_lineage_service.ReportTraceService") as mock_rts, \
             patch("app.services.attachment_trace_service.AttachmentTraceService.for_object", new=fake_for_object):
            mock_vl.query_lineage = AsyncMock(return_value=[])
            mock_rts.return_value.trace_section = AsyncMock(return_value={"note_data": None})
            result = await svc.query_lineage(
                project_id=project_id, object_type=object_type, object_id=object_id, direction="both",
            )

        assert result["attachments"] == [attachment]
        assert calls == [(project_id, object_type, object_id)]
        assert not any(e["source"] == "attachments" for e in result["errors"]), result["errors"]


# ─── Property 3: 节点跳转参数正确 ────────────────────────────────────────────


class TestProperty3NodeLocateParamsCorrect:
    """Property 3: 图谱节点点击触发 locateCell 且参数正确。

    **Validates: Requirements 1.2**
    """

    @settings(max_examples=15, deadline=None)
    @given(
        wp_code=wp_code_st,
        sheet_name=st.one_of(st.none(), sheet_name_st),
        cell_ref=st.one_of(st.none(), cell_ref_st),
    )
    def test_locate_target_schema_preserves_fields(
        self, wp_code: str, sheet_name: str | None, cell_ref: str | None
    ):
        """LocateTarget → LocateTargetSchema 转换保留所有字段。"""
        target = LocateTarget(
            wp_code=wp_code,
            sheet_name=sheet_name,
            cell_ref=cell_ref,
        )
        schema = LocateTargetSchema.from_dataclass(target)

        assert schema.wp_code == wp_code
        assert schema.sheet_name == sheet_name
        assert schema.cell_ref == cell_ref

    @settings(max_examples=15, deadline=None)
    @given(
        wp_code=wp_code_st,
        sheet=st.one_of(st.none(), sheet_name_st),
        cell=st.one_of(st.none(), cell_ref_st),
        value=st.one_of(st.none(), st.integers(min_value=0, max_value=999999)),
    )
    def test_trace_item_to_locate_target_preserves_coordinates(
        self, wp_code: str, sheet: str | None, cell: str | None, value: int | None
    ):
        """TraceItem → LocateTarget 转换保留定位坐标。"""
        from app.schemas.locate_target import trace_item_to_locate_target

        item = TraceItem(wp_code=wp_code, sheet=sheet, cell=cell, value=value)
        target = trace_item_to_locate_target(item)

        assert target.wp_code == wp_code
        assert target.sheet_name == sheet
        assert target.cell_ref == cell
        if value is not None:
            assert target.value == str(value)
        else:
            assert target.value is None
