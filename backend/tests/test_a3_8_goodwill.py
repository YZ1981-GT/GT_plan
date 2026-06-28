"""A3-8 商誉减值测试 — 后端解析器 + 注册契约测试.

Spec: .kiro/specs/a3-8-goodwill-impairment/ Task 7
"""

import pytest


def test_parser_returns_skeleton_structure():
    """解析器返回 impairmentData/recoverableData 完整骨架."""
    from app.services.a3_8_goodwill_parser import parse_a3_8_goodwill

    d = parse_a3_8_goodwill()
    assert "impairmentData" in d
    assert "recoverableData" in d

    imp = d["impairmentData"]
    assert len(imp["impairment_rows"]) >= 1
    assert [r["asset_type"] for r in imp["allocation_rows"]] == ["流动资产", "固定资产", "无形资产", "商誉"]
    assert len(imp["guidance"]["impairment_reasons"]) == 9
    assert "Ke" in imp["guidance"]["wacc_params"]

    rec = d["recoverableData"]
    assert len(rec["dcf"]["cash_flows"]) == 5
    assert set(rec["wacc"].keys()) == {
        "tax_rate", "debt_d", "equity_e", "cost_debt_kd", "rf", "beta", "rm"
    }


def test_parser_graceful_on_missing_template(monkeypatch):
    """模板缺失时仍返回有效骨架不崩溃."""
    from app.services import a3_8_goodwill_parser

    monkeypatch.setattr(a3_8_goodwill_parser, "_find_template", lambda: None)
    d = a3_8_goodwill_parser.parse_a3_8_goodwill()
    assert d["impairmentData"]["impairment_rows"]
    assert d["recoverableData"]["dcf"]["cash_flows"] == [None] * 5


def test_registered_in_dispatch_and_valid_types():
    """componentType 注册于 RENDERER_DISPATCH 与 VALID_COMPONENT_TYPES."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert "a3-8-goodwill-impairment" in RENDERER_DISPATCH
    assert "a3-8-goodwill-impairment" in VALID_COMPONENT_TYPES


def test_overrides_mapping():
    """A3-8 / A3-8-1 在 overrides 中映射到专属组件."""
    import json
    from pathlib import Path

    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("A3-8") == "a3-8-goodwill-impairment"
    assert data.get("A3-8-1") == "a3-8-goodwill-impairment"


@pytest.mark.asyncio
async def test_render_merges_field_overrides():
    """render() 合并 field_overrides 中的用户录入 responses."""
    from unittest.mock import AsyncMock, MagicMock
    from app.routers.wp_render_strategies._a3_8_goodwill import render
    from app.routers.wp_render_strategies._context import RenderContext

    mock_wp = MagicMock()
    mock_cls = MagicMock()
    ctx = RenderContext(
        db=AsyncMock(),
        project_id="11111111-1111-1111-1111-111111111111",
        wp_id="22222222-2222-2222-2222-222222222222",
        wp_code="A3-8",
        working_paper=mock_wp,
        classification=mock_cls,
        component_type="a3-8-goodwill-impairment",
        sheet_html_data=None,
        sheet_schema=None,
        template_file_path=None,
        year=2025,
        business_category="C",
    )

    # mock FieldOverrideService.get_batch
    import app.services.field_override_service as fos_mod

    saved_rows = [{"id": "ag-1", "name": "资产组A", "carrying_a": 100.0,
                   "goodwill_b1": 20.0, "minority_b2": 0.0, "recoverable": 90.0,
                   "reason": "", "remark": ""}]

    class _FakeSvc:
        def __init__(self, db):
            pass

        async def get_batch(self, project_id, year, scope):
            return {"impairment_rows": {"value": saved_rows}}

    orig = fos_mod.FieldOverrideService
    fos_mod.FieldOverrideService = _FakeSvc
    try:
        result = await render(ctx)
    finally:
        fos_mod.FieldOverrideService = orig

    assert result["responses"]["impairment_rows"] == saved_rows
    # 骨架仍在
    assert "impairmentData" in result
    assert "recoverableData" in result
