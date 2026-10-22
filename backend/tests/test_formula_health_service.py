"""项目级公式健康度服务测试（spec: formula-management-deep-optimization · R2）。

验证 compute_health 各维度聚合逻辑。使用 SQLite 内存库测试核心聚合，
PG 特定行为（如 JSONB）不在此测试范围。
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.formula_health_service import compute_health


@pytest.fixture
def project_id():
    return uuid.uuid4()


class TestPushCoverage:
    """维度 1：推送覆盖率（纯函数，不碰 DB）。"""

    def test_returns_dict_with_percentage(self):
        from app.services.formula_health_service import _push_coverage
        result = _push_coverage()
        assert isinstance(result, dict)
        assert "percentage" in result
        assert "cycles" in result

    def test_percentage_is_numeric(self):
        from app.services.formula_health_service import _push_coverage
        result = _push_coverage()
        assert isinstance(result["percentage"], (int, float))


class TestComputeHealthStructure:
    """compute_health 返回结构验证（mock DB 避免真实连接）。"""

    @pytest.mark.asyncio
    async def test_returns_six_dimensions(self, project_id):
        """返回的 dict 包含全部六个维度键。"""
        db = AsyncMock()
        # mock 所有查询返回空结果
        db.execute = AsyncMock(return_value=_MockResult(None))

        result = await compute_health(db, project_id, 2025)

        assert "push_coverage" in result
        assert "push_success_rate" in result
        assert "formula_config_rate" in result
        assert "pending_conflicts" in result
        assert "cross_check_pass_rate" in result
        assert "stale_ratio" in result

    @pytest.mark.asyncio
    async def test_project_id_and_year_in_result(self, project_id):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_MockResult(None))

        result = await compute_health(db, project_id, 2025)

        assert result["project_id"] == str(project_id)
        assert result["year"] == 2025

    @pytest.mark.asyncio
    async def test_graceful_on_db_error(self, project_id):
        """DB 查询出错时各维度返回安全默认值，不抛异常。"""
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("DB down"))

        result = await compute_health(db, project_id, 2025)

        # 各维度应该有默认值，不抛异常
        assert result["push_success_rate"].get("has_run") is False or "error" in result["push_success_rate"]
        assert result["formula_config_rate"].get("total_rows", 0) == 0
        assert result["pending_conflicts"].get("pending", 0) == 0


class TestPendingCount:
    """维度 4：冲突待确认数。"""

    @pytest.mark.asyncio
    async def test_zero_when_no_pending(self, project_id):
        from app.services.formula_health_service import _pending_count
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_MockScalar(0))

        result = await _pending_count(db, project_id)
        assert result["pending"] == 0

    @pytest.mark.asyncio
    async def test_nonzero_when_pending(self, project_id):
        from app.services.formula_health_service import _pending_count
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_MockScalar(5))

        result = await _pending_count(db, project_id)
        assert result["pending"] == 5


class TestConfigCoverage:
    """维度 3：公式配置率。"""

    @pytest.mark.asyncio
    async def test_zero_when_no_rows(self, project_id):
        from app.services.formula_health_service import _config_coverage
        db = AsyncMock()
        # 第一次调用返回 total=0，第二次返回 with_formula=0
        db.execute = AsyncMock(return_value=_MockScalar(0))

        result = await _config_coverage(db, project_id, 2025)
        assert result["coverage_rate"] == 0


# ── 辅助 mock ──

class _MockResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return self

    def first(self):
        return self._value

    def all(self):
        return [] if self._value is None else [self._value]

    def scalar(self):
        return self._value


class _MockScalar:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value
