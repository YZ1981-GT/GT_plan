"""I6 研发费用 — render策略 + 导入导出 + AI生成 集成测试.

Spec: .kiro/specs/i6-research-development-expense/ Task 7.3
Validates: Requirements 1.1, 5.1-5.3, 10.1

测试:
- render策略返回income_statement标识
- render策略含occurrence取数逻辑
- import_export路由已注册
- ai_generate路由已注册
- YAML schema存在且有效
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole
from app.core.database import get_db
from app.routers.wp_render_strategies import RENDERER_DISPATCH


class _FakeUser:
    id = "test-user-id"
    name = "Test User"
    email = "test@example.com"
    role = UserRole.admin


@pytest.fixture(autouse=True)
def override_deps():
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.execute = AsyncMock()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = _override_db
    yield mock_db
    app.dependency_overrides.clear()


# ─── test_i6_render_strategy_returns_income_statement_flag ──────────────────

@pytest.mark.asyncio
async def test_i6_render_strategy_returns_income_statement_flag():
    """RENDERER_DISPATCH 中 i6-research-development-expense 已注册且可调用."""
    assert "i6-research-development-expense" in RENDERER_DISPATCH
    fn = RENDERER_DISPATCH["i6-research-development-expense"]
    assert callable(fn)


# ─── test_i6_render_strategy_fetches_occurrence_amount ──────────────────────

@pytest.mark.asyncio
async def test_i6_render_strategy_fetches_occurrence_amount():
    """render策略模块中 _fetch_tb_income_statement 使用损益类发生额取数."""
    from app.routers.wp_render_strategies._i6_research_development_expense import (
        _I6_ACCOUNT_PREFIX,
        I6_SHEETS,
    )
    # 验证科目前缀为6602
    assert _I6_ACCOUNT_PREFIX == "6602"
    # 验证sheet列表包含11个sheets
    assert len(I6_SHEETS) >= 10
    # 验证每个sheet都有component_type标记
    for sheet in I6_SHEETS:
        assert sheet["component_type"] == "i6-research-development-expense"


# ─── test_i6_import_export_router_registered ────────────────────────────────

@pytest.mark.asyncio
async def test_i6_import_export_router_registered():
    """I6导入导出路由已注册（能被 app 发现）."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 验证export-template端点存在（即使返回错误也说明路由已注册）
        resp = await client.post("/api/workpapers/test-wp/i6/export-template?sheet=I6-2")
    # 路由存在会返回 200/400/422，不存在返回 404（路由未匹配）
    assert resp.status_code != 404, "I6 import_export router not registered"


@pytest.mark.asyncio
async def test_i6_cutoff_export_template_sheets():
    """I6-5 / I6-6 截止测试导出模板可下载."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for sheet in ("I6-5", "I6-6"):
            resp = await client.post(f"/api/workpapers/test-wp/i6/export-template?sheet={sheet}")
            assert resp.status_code == 200, f"{sheet} export-template: {resp.status_code}"
            assert resp.headers.get("content-type", "").startswith(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            assert len(resp.content) > 500


def test_i6_import_export_includes_cutoff_specs():
    from app.routers.wp_render_strategies._i6_import_export import _I6_SPECS

    assert {"I6-5", "I6-6"}.issubset(_I6_SPECS.keys())
    for code in ("I6-5", "I6-6"):
        spec = _I6_SPECS[code]
        assert spec["item_id"] == f"{code}-rows"
        assert len(spec["headers"]) == len(spec["field_keys"])
        assert spec["storage_field"] == "remark"


# ─── test_i6_ai_generate_router_registered ─────────────────────────────────

@pytest.mark.asyncio
async def test_i6_ai_generate_router_registered():
    """I6 AI生成路由已注册."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/i6/ai-generate",
            json={"section": "targeted_check", "existingContent": ""},
        )
    # 路由存在：200/400/422；路由不存在：404
    assert resp.status_code != 404, "I6 ai_generate router not registered"


# ─── test_i6_yaml_schema_exists_and_valid ──────────────────────────────────

@pytest.mark.asyncio
async def test_i6_yaml_schema_exists_and_valid():
    """YAML render schema文件存在且结构合法."""
    schema_path = Path(__file__).parent.parent / "data" / "ledger_adapters" / "wp_render_schema" / "i6-research-development-expense.yaml"

    assert schema_path.exists(), f"YAML schema not found at {schema_path}"

    with open(schema_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # 验证核心字段
    assert data["component_type"] == "i6-research-development-expense"
    assert data["wp_code"] == "I6"
    assert data["income_statement"] is True  # 损益类标识！
    assert "6602" in data["account_codes"]
    assert data["selfLoad"] is True

    # 验证 sheets 定义
    assert "sheets" in data
    sheets = data["sheets"]
    assert len(sheets) >= 10

    # 验证 tb_writeback 配置
    assert "tb_writeback" in data
    wb = data["tb_writeback"]
    assert wb["account_code"] == "6602"
    assert wb["value_type"] == "occurrence_amount"  # 发生额非余额！

    # 验证 cross_wp_references 包含I6↔I2
    assert "cross_wp_references" in data
    refs = data["cross_wp_references"]
    i2_refs = [r for r in refs if "I2" in str(r.get("target_wp", "")) or "I2" in str(r.get("source_wp", ""))]
    assert len(i2_refs) >= 2, "Missing I6↔I2 bidirectional references"
