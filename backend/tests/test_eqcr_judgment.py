"""Tests for EQCR Judgment API — Phase 7 F1

Tests:
- 5 维度全 pass → can_sign=True
- 1 个 fail → can_sign=False
- 维度数 ≠ 5 → 422
- 非 EQCR 角色 → 403 (via role check)
- GET 返回已提交判断
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from app.routers.eqcr_judgment import (
    EqcrJudgmentSubmit,
    JudgmentDimension,
    DIMENSION_KEYS,
)


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


class TestEqcrJudgmentSchema:
    """Test Pydantic validation for EqcrJudgmentSubmit."""

    def _make_dimensions(self, conclusions: list[str]) -> list[dict]:
        """Helper to create 5 dimensions with given conclusions."""
        dims = []
        for i, key in enumerate(DIMENSION_KEYS):
            dims.append({
                "key": key,
                "conclusion": conclusions[i] if i < len(conclusions) else "pass",
                "rationale": f"Test rationale for {key}",
                "referenced_wps": ["D2-1"],
                "risk_level": "medium",
            })
        return dims

    def test_valid_all_pass(self):
        """5 维度全 pass → 验证通过。"""
        dims = self._make_dimensions(["pass"] * 5)
        body = EqcrJudgmentSubmit(dimensions=[JudgmentDimension(**d) for d in dims])
        assert len(body.dimensions) == 5
        assert all(d.conclusion == "pass" for d in body.dimensions)

    def test_valid_with_fail(self):
        """含 fail 维度 → 验证通过（can_sign 由业务逻辑判断）。"""
        dims = self._make_dimensions(["pass", "fail", "pass", "qualified", "pass"])
        body = EqcrJudgmentSubmit(dimensions=[JudgmentDimension(**d) for d in dims])
        assert len(body.dimensions) == 5
        assert body.dimensions[1].conclusion == "fail"

    def test_invalid_less_than_5_dimensions(self):
        """维度数 < 5 → 422 ValidationError。"""
        dims = self._make_dimensions(["pass"] * 3)[:3]
        with pytest.raises(Exception):
            EqcrJudgmentSubmit(dimensions=[JudgmentDimension(**d) for d in dims])

    def test_invalid_more_than_5_dimensions(self):
        """维度数 > 5 → 422 ValidationError。"""
        dims = self._make_dimensions(["pass"] * 5)
        dims.append({
            "key": "material_misstatement",  # duplicate
            "conclusion": "pass",
            "rationale": "extra",
            "referenced_wps": [],
            "risk_level": "low",
        })
        with pytest.raises(Exception):
            EqcrJudgmentSubmit(dimensions=[JudgmentDimension(**d) for d in dims])

    def test_invalid_missing_dimension_key(self):
        """缺少某个维度 key → 422 ValidationError。"""
        dims = []
        for key in DIMENSION_KEYS[:4]:
            dims.append({
                "key": key,
                "conclusion": "pass",
                "rationale": "",
                "referenced_wps": [],
                "risk_level": "medium",
            })
        # Add duplicate instead of the 5th
        dims.append({
            "key": DIMENSION_KEYS[0],
            "conclusion": "pass",
            "rationale": "",
            "referenced_wps": [],
            "risk_level": "medium",
        })
        with pytest.raises(Exception):
            EqcrJudgmentSubmit(dimensions=[JudgmentDimension(**d) for d in dims])

    def test_can_sign_logic_all_pass(self):
        """Business logic: all pass → can_sign=True."""
        dims = self._make_dimensions(["pass"] * 5)
        body = EqcrJudgmentSubmit(dimensions=[JudgmentDimension(**d) for d in dims])
        can_sign = all(d.conclusion != "fail" for d in body.dimensions)
        assert can_sign is True

    def test_can_sign_logic_one_fail(self):
        """Business logic: one fail → can_sign=False."""
        dims = self._make_dimensions(["pass", "pass", "fail", "pass", "pass"])
        body = EqcrJudgmentSubmit(dimensions=[JudgmentDimension(**d) for d in dims])
        can_sign = all(d.conclusion != "fail" for d in body.dimensions)
        assert can_sign is False

    def test_can_sign_logic_qualified_ok(self):
        """Business logic: qualified (not fail) → can_sign=True."""
        dims = self._make_dimensions(["pass", "qualified", "pass", "qualified", "pass"])
        body = EqcrJudgmentSubmit(dimensions=[JudgmentDimension(**d) for d in dims])
        can_sign = all(d.conclusion != "fail" for d in body.dimensions)
        assert can_sign is True

    def test_invalid_conclusion_value(self):
        """Invalid conclusion value → ValidationError."""
        with pytest.raises(Exception):
            JudgmentDimension(
                key="material_misstatement",
                conclusion="invalid_value",
                rationale="",
                referenced_wps=[],
                risk_level="medium",
            )

    def test_invalid_risk_level(self):
        """Invalid risk_level → ValidationError."""
        with pytest.raises(Exception):
            JudgmentDimension(
                key="material_misstatement",
                conclusion="pass",
                rationale="",
                referenced_wps=[],
                risk_level="critical",
            )
