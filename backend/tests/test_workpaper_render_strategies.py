"""策略单元测试 — 7 个 render(ctx) 策略的正常路径 + 降级路径

覆盖策略：_b_index, _a_program, _audit_sheet, _checklist,
          _analytical_review, _c_note, _univer_grid

每个策略至少 2 个测试：
1. 正常路径 — render(ctx) 返回 dict 或 None
2. 降级路径 — sheet_html_data=None, sheet_schema=None, template_file_path=None 时不抛异常

Requirements: 3.1, 3.2, 3.3, 3.4
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.routers.wp_render_strategies._context import RenderContext


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_ctx(
    *,
    component_type: str = "audit-sheet",
    wp_code: str = "D1",
    sheet_name: str = "审定表D1-1",
    sheet_html_data: dict | None = None,
    sheet_schema: dict | None = None,
    template_file_path: str | None = "/fake/template.xlsx",
    year: int = 2025,
    business_category: str = "C",
    audit_cycle: str = "D",
) -> RenderContext:
    """构造一个用于测试的 RenderContext（所有外部依赖 mock）"""
    db = AsyncMock()
    # db.execute 返回空结果集
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_result.fetchone.return_value = None
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result

    working_paper = MagicMock()
    working_paper.id = uuid4()

    classification = MagicMock()
    classification.sheet_name = sheet_name
    classification.wp_code = wp_code
    classification.component_type = component_type

    return RenderContext(
        db=db,
        project_id=uuid4(),
        wp_id=uuid4(),
        wp_code=wp_code,
        working_paper=working_paper,
        classification=classification,
        component_type=component_type,
        sheet_html_data=sheet_html_data,
        sheet_schema=sheet_schema,
        template_file_path=template_file_path,
        year=year,
        business_category=business_category,
        classifications=[classification],
        audit_cycle=audit_cycle,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# _b_index 策略
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_b_index_render_normal_path():
    """B-Index 策略：无持久化数据时返回 dict"""
    ctx = _make_ctx(
        component_type="b-index",
        wp_code="D1",
        sheet_name="B-Index",
        sheet_html_data=None,
    )

    mock_prep_info = {
        "entity_name": "测试公司",
        "period_end": "2025-12-31",
        "preparer": "张三",
        "prep_date": "2025-01-01",
        "reviewer": "李四",
        "review_date": "2025-02-01",
        "index_no": "D1",
    }

    with (
        patch(
            "app.services.wp_preparation_info_service.build_preparation_info",
            new_callable=AsyncMock,
            return_value=mock_prep_info,
        ),
        patch(
            "app.services.wp_cycle_directory.build_cycle_workpapers",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.wp_classification_service.derive_component_type",
            return_value="audit-sheet",
        ),
    ):
        from app.routers.wp_render_strategies._b_index import render

        result = await render(ctx)

    assert result is None or isinstance(result, dict)
    if result is not None:
        assert "preparation_info" in result
        assert "navigation_rows" in result


@pytest.mark.asyncio
async def test_b_index_render_refresh_cycle_on_existing_navigation():
    """已有 navigation_rows 时仍注入 cycle_workpapers（修复历史持久化缺跨底稿目录）。"""
    ctx = _make_ctx(
        component_type="b-index",
        wp_code="G4",
        sheet_name="底稿目录",
        sheet_html_data={"navigation_rows": [{"seq": 1, "content": "审定表G4-1"}]},
        audit_cycle="G",
    )
    mock_cycle = [
        {"wp_code": "G4", "wp_name": "债权投资", "wp_id": str(ctx.wp_id), "status": "", "is_current": True},
        {"wp_code": "G1", "wp_name": "交易性金融资产", "wp_id": None, "status": "", "is_current": False},
    ]

    with patch(
        "app.services.wp_cycle_directory.build_cycle_workpapers",
        new_callable=AsyncMock,
        return_value=mock_cycle,
    ):
        from app.routers.wp_render_strategies._b_index import render

        result = await render(ctx)

    assert isinstance(result, dict)
    assert result.get("cycle_workpapers") == mock_cycle
    assert result.get("navigation_rows") == [{"seq": 1, "content": "审定表G4-1"}]


@pytest.mark.asyncio
async def test_b_index_render_degraded_path():
    """B-Index 策略：降级路径不抛异常"""
    ctx = _make_ctx(
        component_type="b-index",
        wp_code="D1",
        sheet_name="B-Index",
        sheet_html_data=None,
        sheet_schema=None,
        template_file_path=None,
    )

    with (
        patch(
            "app.services.wp_preparation_info_service.build_preparation_info",
            new_callable=AsyncMock,
            return_value={
                "entity_name": "",
                "period_end": "",
                "preparer": "",
                "prep_date": "",
                "reviewer": "",
                "review_date": "",
                "index_no": "",
            },
        ),
        patch(
            "app.services.wp_cycle_directory.build_cycle_workpapers",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.wp_classification_service.derive_component_type",
            return_value="audit-sheet",
        ),
    ):
        from app.routers.wp_render_strategies._b_index import render

        result = await render(ctx)

    assert result is None or isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# _a_program 策略
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_a_program_render_normal_path():
    """A-Program 策略：无持久化 programs 时从模板生成"""
    ctx = _make_ctx(
        component_type="a-program-console",
        wp_code="D1A",
        sheet_name="审计程序表D1A",
        sheet_html_data=None,
    )

    with patch(
        "app.services.wp_program_extract.extract_program_rows",
        return_value=[
            {"id": "row-1", "program_no": 1, "program_desc": "检查", "status": "pending"}
        ],
    ):
        from app.routers.wp_render_strategies._a_program import render

        result = await render(ctx)

    assert result is None or isinstance(result, dict)
    if result is not None:
        assert "programs" in result


@pytest.mark.asyncio
async def test_a_program_render_degraded_path():
    """A-Program 策略：降级路径（无模板文件+无DB匹配模板）不抛异常"""
    ctx = _make_ctx(
        component_type="a-program-console",
        wp_code="D1A",
        sheet_name="审计程序表D1A",
        sheet_html_data=None,
        sheet_schema=None,
        template_file_path=None,
    )

    with patch(
        "app.services.procedure_table_auto_service.get_template",
        return_value=None,
    ):
        from app.routers.wp_render_strategies._a_program import render

        result = await render(ctx)

    assert result is None or isinstance(result, dict)
    if result is not None:
        assert "programs" in result
        # 无模板匹配 + 无文件路径 → programs 为空列表
        assert result["programs"] == []


@pytest.mark.asyncio
async def test_a_program_existing_programs_returns_none():
    """A-Program 策略：已有持久化 programs 返回 None"""
    ctx = _make_ctx(
        component_type="a-program-console",
        wp_code="D1A",
        sheet_name="审计程序表D1A",
        sheet_html_data={"programs": [{"id": "row-1", "status": "done"}]},
    )

    from app.routers.wp_render_strategies._a_program import render

    result = await render(ctx)

    assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# _audit_sheet 策略
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_audit_sheet_render_normal_path():
    """Audit-Sheet 策略：正常路径返回含 audit_rows 和 tb_values 的 dict"""
    ctx = _make_ctx(
        component_type="audit-sheet",
        wp_code="D1-1",
        sheet_name="审定表D1-1",
        sheet_html_data=None,
    )

    mock_rows = [
        {"row_id": "row-1", "account_code": "1001", "account_name": "现金"}
    ]

    with (
        patch(
            "app.services.wp_audit_sheet_extract.extract_audit_rows_with_values_from_file",
            return_value=(mock_rows, None),
        ),
        patch(
            "app.services.wp_audit_sheet_extract.extract_audit_sections",
            return_value={"notes": "", "conclusion": "", "notes_label": "审计说明", "conclusion_label": "审计结论"},
        ),
        patch(
            "app.services.wp_audit_sheet_tb_service.fetch_audit_sheet_tb_values",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        from app.routers.wp_render_strategies._audit_sheet import render

        result = await render(ctx)

    assert isinstance(result, dict)
    assert "audit_rows" in result
    assert "tb_values" in result


@pytest.mark.asyncio
async def test_audit_sheet_render_degraded_path():
    """Audit-Sheet 策略：降级路径不抛异常"""
    ctx = _make_ctx(
        component_type="audit-sheet",
        wp_code="D1-1",
        sheet_name="审定表D1-1",
        sheet_html_data=None,
        sheet_schema=None,
        template_file_path=None,
    )

    with patch(
        "app.services.wp_audit_sheet_tb_service.fetch_audit_sheet_tb_values",
        new_callable=AsyncMock,
        return_value={},
    ):
        from app.routers.wp_render_strategies._audit_sheet import render

        result = await render(ctx)

    assert isinstance(result, dict)
    assert result["audit_rows"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# _checklist 策略
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_checklist_render_normal_path():
    """Checklist 策略：正常路径返回含 template 和 responses 的 dict"""
    ctx = _make_ctx(
        component_type="checklist-table",
        wp_code="A1-15",
        sheet_name="核对表A1-15",
        sheet_html_data=None,
    )

    mock_template = {"title": "独立性核对表", "items": []}

    with (
        patch(
            "app.services.checklist_xlsx_parser.is_xlsx_checklist",
            return_value=False,
        ),
        patch(
            "app.services.checklist_docx_parser.get_checklist_template",
            new_callable=AsyncMock,
            return_value=mock_template,
        ),
    ):
        from app.routers.wp_render_strategies._checklist import render

        result = await render(ctx)

    assert isinstance(result, dict)
    assert "template" in result
    assert "responses" in result


@pytest.mark.asyncio
async def test_checklist_render_degraded_path():
    """Checklist 策略：模板不存在时不抛异常"""
    ctx = _make_ctx(
        component_type="checklist-table",
        wp_code="A1-15",
        sheet_name="核对表A1-15",
        sheet_html_data=None,
        sheet_schema=None,
        template_file_path=None,
    )

    with (
        patch(
            "app.services.checklist_xlsx_parser.is_xlsx_checklist",
            return_value=False,
        ),
        patch(
            "app.services.checklist_docx_parser.get_checklist_template",
            new_callable=AsyncMock,
            side_effect=FileNotFoundError("not found"),
        ),
    ):
        from app.routers.wp_render_strategies._checklist import render

        result = await render(ctx)

    assert isinstance(result, dict)
    assert result["template"] is None
    assert result["responses"] == {}


# ═══════════════════════════════════════════════════════════════════════════════
# _analytical_review 策略
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_analytical_review_render_normal_path():
    """Analytical-Review 策略：正常路径返回含 analytical_review 的 dict"""
    ctx = _make_ctx(
        component_type="analytical-review",
        wp_code="A1-13",
        sheet_name="分析性复核A1-13",
        sheet_html_data=None,
    )

    mock_ar_data = {"ratios": [], "trends": []}

    with patch(
        "app.services.analytical_review_service.get_analytical_review_data",
        new_callable=AsyncMock,
        return_value=mock_ar_data,
    ):
        from app.routers.wp_render_strategies._analytical_review import render

        result = await render(ctx)

    assert isinstance(result, dict)
    assert "analytical_review" in result
    assert result["analytical_review"] == mock_ar_data


@pytest.mark.asyncio
async def test_analytical_review_render_degraded_path():
    """Analytical-Review 策略：数据获取异常时不抛异常"""
    ctx = _make_ctx(
        component_type="analytical-review",
        wp_code="A1-13",
        sheet_name="分析性复核A1-13",
        sheet_html_data=None,
        sheet_schema=None,
        template_file_path=None,
    )

    with patch(
        "app.services.analytical_review_service.get_analytical_review_data",
        new_callable=AsyncMock,
        side_effect=Exception("DB connection failed"),
    ):
        from app.routers.wp_render_strategies._analytical_review import render

        result = await render(ctx)

    assert isinstance(result, dict)
    assert result["analytical_review"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# _c_note 策略
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_c_note_render_normal_path():
    """C-Note 策略：无 schema 时从模板提取只读网格"""
    ctx = _make_ctx(
        component_type="c-note-table",
        wp_code="C1-1",
        sheet_name="附注C1-1",
        sheet_html_data=None,
        sheet_schema=None,
    )

    mock_grid = {
        "cells": {"A1": {"v": "标题"}},
        "merged_cells": [],
        "col_widths": {},
        "max_row": 10,
        "max_col": 5,
    }

    with patch(
        "app.services.wp_grid_extract.extract_grid",
        return_value=mock_grid,
    ):
        from app.routers.wp_render_strategies._c_note import render

        result = await render(ctx)

    assert result is None or isinstance(result, dict)
    if isinstance(result, dict):
        assert "cells" in result


@pytest.mark.asyncio
async def test_c_note_render_degraded_path():
    """C-Note 策略：降级路径（无模板无 schema）不抛异常"""
    ctx = _make_ctx(
        component_type="c-note-table",
        wp_code="C1-1",
        sheet_name="附注C1-1",
        sheet_html_data=None,
        sheet_schema=None,
        template_file_path=None,
    )

    from app.routers.wp_render_strategies._c_note import render

    result = await render(ctx)

    assert result is None or isinstance(result, dict)


@pytest.mark.asyncio
async def test_c_note_fixed_cells_substitution():
    """C-Note 策略：fixed_cells 占位符被编制信息替换"""
    ctx = _make_ctx(
        component_type="c-note-table",
        wp_code="C1-1",
        sheet_name="附注C1-1",
        sheet_html_data={"cells": {"A1": {"v": "数据"}}, "sub_tables": []},
        sheet_schema={
            "sub_tables": [{"name": "t1"}],
            "fixed_cells": {"A1": "${entity_name}", "B1": "${period_end}"},
        },
    )

    mock_prep = {
        "entity_name": "测试公司",
        "period_end": "2025-12-31",
        "preparer": "",
        "prep_date": "",
        "reviewer": "",
        "review_date": "",
        "index_no": "C1-1",
    }

    with patch(
        "app.services.wp_preparation_info_service.build_preparation_info",
        new_callable=AsyncMock,
        return_value=mock_prep,
    ):
        from app.routers.wp_render_strategies._c_note import render

        result = await render(ctx)

    # fixed_cells 替换写入 ctx.sheet_schema
    assert ctx.sheet_schema["fixed_cells"]["A1"] == "测试公司"
    assert ctx.sheet_schema["fixed_cells"]["B1"] == "2025-12-31"


# ═══════════════════════════════════════════════════════════════════════════════
# _univer_grid 策略
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_univer_grid_render_normal_path():
    """Univer-Grid 策略：正常路径从模板提取网格返回 dict"""
    ctx = _make_ctx(
        component_type="univer",
        wp_code="D1-2",
        sheet_name="明细表D1-2",
        sheet_html_data=None,
    )

    mock_grid = {
        "cells": {"A1": {"v": "项目"}},
        "merged_cells": [],
        "col_widths": {},
        "max_row": 20,
        "max_col": 8,
    }

    with patch(
        "app.services.wp_grid_extract.extract_grid",
        return_value=mock_grid,
    ):
        from app.routers.wp_render_strategies._univer_grid import render

        result = await render(ctx)

    assert isinstance(result, dict)
    assert "cells" in result
    assert result["cells"] == {"A1": {"v": "项目"}}


@pytest.mark.asyncio
async def test_univer_grid_render_degraded_path():
    """Univer-Grid 策略：降级路径不抛异常"""
    ctx = _make_ctx(
        component_type="univer",
        wp_code="D1-2",
        sheet_name="明细表D1-2",
        sheet_html_data=None,
        sheet_schema=None,
        template_file_path=None,
    )

    from app.routers.wp_render_strategies._univer_grid import render

    result = await render(ctx)

    assert isinstance(result, dict)
    assert result["cells"] == {}


@pytest.mark.asyncio
async def test_univer_grid_existing_cells_returns_none():
    """Univer-Grid 策略：已有网格数据返回 None"""
    ctx = _make_ctx(
        component_type="univer",
        wp_code="D1-2",
        sheet_name="明细表D1-2",
        sheet_html_data={"cells": {"A1": {"v": "已有数据"}}, "merged_cells": []},
    )

    from app.routers.wp_render_strategies._univer_grid import render

    result = await render(ctx)

    assert result is None
