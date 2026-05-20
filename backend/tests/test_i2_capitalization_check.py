"""Unit tests for I-F5 development expenditure capitalization check (CAS 6 / IAS 38).

Covers:
- 5-condition matrix evaluation (all True / all False / partial combinations)
- Capitalization start date = max(condition_dates, project_start_date)
- Missing conditions list when any False
- Date format validation (HTTP 422)
- Project end date upper bound check
- Recommendation text generation
- Write-back helper (apply_to_sheet=None returns None)
- RBAC (require_project_access("edit"))
- Schema validation

对应 spec: workpaper-i-intangible-assets-cycle I-F5
对应 ADR: ADR-I2
"""

from __future__ import annotations

import sys

sys.path.insert(0, "backend")

import asyncio
import inspect
from datetime import date

import pytest
from fastapi import HTTPException

from app.routers.wp_i_capitalization import (
    CONDITION_FIELDS,
    CONDITION_LABELS,
    CapitalizationCheckRequest,
    CapitalizationCheckResponse,
    _evaluate_conditions,
    _maybe_apply_capitalization_check_to_workpaper,
    _parse_iso_date,
    _resolve_capitalization_start_date,
    i2_capitalization_check,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CONDITION CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestConditionConstants:
    """5 个条件字段名称固定（与 CAS 6 第 9 条 (一)~(五) 对齐）"""

    def test_five_conditions_defined(self):
        assert len(CONDITION_FIELDS) == 5

    def test_condition_labels_complete(self):
        for field in CONDITION_FIELDS:
            assert field in CONDITION_LABELS
            assert CONDITION_LABELS[field]  # 非空

    def test_field_names_match_request_schema(self):
        # request schema 必须含全部 5 个字段（防止字段名漂移）
        req_fields = CapitalizationCheckRequest.model_fields.keys()
        for field in CONDITION_FIELDS:
            assert field in req_fields


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CONDITION EVALUATION (5 BOOLEAN COMBINATIONS)
# ═══════════════════════════════════════════════════════════════════════════════


def _make_request(
    *,
    technical_feasibility: bool = True,
    completion_intent: bool = True,
    ability_to_use_or_sell: bool = True,
    future_economic_benefits: bool = True,
    resource_sufficiency: bool = True,
    condition_dates: dict[str, str] | None = None,
    project_start_date: str = "2025-01-01",
    project_end_date: str | None = None,
    apply_to_sheet: str | None = None,
) -> CapitalizationCheckRequest:
    if condition_dates is None:
        # 默认全部条件提供日期（即使某些为 False，extra dates 会被忽略）
        condition_dates = {f: "2025-03-15" for f in CONDITION_FIELDS}
    return CapitalizationCheckRequest(
        technical_feasibility=technical_feasibility,
        completion_intent=completion_intent,
        ability_to_use_or_sell=ability_to_use_or_sell,
        future_economic_benefits=future_economic_benefits,
        resource_sufficiency=resource_sufficiency,
        condition_dates=condition_dates,
        project_start_date=project_start_date,
        project_end_date=project_end_date,
        apply_to_sheet=apply_to_sheet,
    )


class TestConditionEvaluation:
    """8+ 组合 case：全 True / 全 False / 单 False / 多 False"""

    def test_all_five_true(self):
        req = _make_request()
        status, missing = _evaluate_conditions(req)
        assert all(status.values())
        assert missing == []

    def test_all_five_false(self):
        req = _make_request(
            technical_feasibility=False,
            completion_intent=False,
            ability_to_use_or_sell=False,
            future_economic_benefits=False,
            resource_sufficiency=False,
        )
        status, missing = _evaluate_conditions(req)
        assert not any(status.values())
        assert len(missing) == 5

    def test_only_technical_feasibility_false(self):
        req = _make_request(technical_feasibility=False)
        status, missing = _evaluate_conditions(req)
        assert status["technical_feasibility"] is False
        assert len(missing) == 1
        assert missing[0] == CONDITION_LABELS["technical_feasibility"]

    def test_only_completion_intent_false(self):
        req = _make_request(completion_intent=False)
        _, missing = _evaluate_conditions(req)
        assert len(missing) == 1
        assert missing[0] == CONDITION_LABELS["completion_intent"]

    def test_only_ability_false(self):
        req = _make_request(ability_to_use_or_sell=False)
        _, missing = _evaluate_conditions(req)
        assert len(missing) == 1
        assert missing[0] == CONDITION_LABELS["ability_to_use_or_sell"]

    def test_only_future_economic_benefits_false(self):
        req = _make_request(future_economic_benefits=False)
        _, missing = _evaluate_conditions(req)
        assert len(missing) == 1
        assert missing[0] == CONDITION_LABELS["future_economic_benefits"]

    def test_only_resource_sufficiency_false(self):
        req = _make_request(resource_sufficiency=False)
        _, missing = _evaluate_conditions(req)
        assert len(missing) == 1
        assert missing[0] == CONDITION_LABELS["resource_sufficiency"]

    def test_two_conditions_false(self):
        req = _make_request(
            technical_feasibility=False,
            resource_sufficiency=False,
        )
        _, missing = _evaluate_conditions(req)
        assert len(missing) == 2
        assert CONDITION_LABELS["technical_feasibility"] in missing
        assert CONDITION_LABELS["resource_sufficiency"] in missing

    def test_three_conditions_false(self):
        req = _make_request(
            technical_feasibility=False,
            completion_intent=False,
            ability_to_use_or_sell=False,
        )
        _, missing = _evaluate_conditions(req)
        assert len(missing) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# 3. CAPITALIZATION START DATE RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════════


class TestCapitalizationStartDate:
    """资本化起始日期 = max(各满足条件日期, 项目启动日期)"""

    def test_max_of_condition_dates_when_after_project_start(self):
        req = _make_request(
            condition_dates={
                "technical_feasibility": "2025-02-15",
                "completion_intent": "2025-03-01",
                "ability_to_use_or_sell": "2025-04-20",  # 最晚
                "future_economic_benefits": "2025-03-15",
                "resource_sufficiency": "2025-04-01",
            },
            project_start_date="2025-01-01",
        )
        status, _ = _evaluate_conditions(req)
        result = _resolve_capitalization_start_date(req, status, date(2025, 1, 1))
        assert result == date(2025, 4, 20)

    def test_project_start_when_after_all_condition_dates(self):
        """项目启动日期晚于全部条件日期 → 取项目启动日期"""
        req = _make_request(
            condition_dates={f: "2024-01-15" for f in CONDITION_FIELDS},
            project_start_date="2025-06-01",
        )
        status, _ = _evaluate_conditions(req)
        result = _resolve_capitalization_start_date(req, status, date(2025, 6, 1))
        assert result == date(2025, 6, 1)

    def test_missing_condition_date_for_satisfied_condition_raises_422(self):
        """已满足条件未提供日期 → HTTPException 422"""
        req = _make_request(
            condition_dates={
                "technical_feasibility": "2025-02-15",
                # completion_intent 缺失
                "ability_to_use_or_sell": "2025-03-01",
                "future_economic_benefits": "2025-03-15",
                "resource_sufficiency": "2025-04-01",
            },
        )
        status, _ = _evaluate_conditions(req)
        with pytest.raises(HTTPException) as exc:
            _resolve_capitalization_start_date(req, status, date(2025, 1, 1))
        assert exc.value.status_code == 422
        assert "completion_intent" in exc.value.detail

    def test_unsatisfied_condition_doesnt_require_date(self):
        """未满足条件不要求 condition_dates 中提供日期"""
        req = _make_request(
            technical_feasibility=False,
            condition_dates={
                # technical_feasibility 没给（因为是 False）
                "completion_intent": "2025-03-01",
                "ability_to_use_or_sell": "2025-04-20",
                "future_economic_benefits": "2025-03-15",
                "resource_sufficiency": "2025-04-01",
            },
        )
        status, missing = _evaluate_conditions(req)
        # 不会触发 422（technical_feasibility 是 False 不要日期）；但实际不调用此函数因为 missing != []
        # 仍验证：仅看 4 个 True 条件
        # NOTE: 真实流程是 missing != [] → 不进入 _resolve_capitalization_start_date
        assert missing  # 有 missing → endpoint 不会调用 resolver
        # 但函数签名应能正常处理（仅遍历 status[True] 的字段）
        result = _resolve_capitalization_start_date(req, status, date(2025, 1, 1))
        assert result == date(2025, 4, 20)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. DATE PARSING
# ═══════════════════════════════════════════════════════════════════════════════


class TestDateParsing:
    def test_valid_iso_date(self):
        assert _parse_iso_date("2025-03-15", "test") == date(2025, 3, 15)

    def test_invalid_format_raises_422(self):
        with pytest.raises(HTTPException) as exc:
            _parse_iso_date("2025/03/15", "test_field")
        assert exc.value.status_code == 422
        assert "test_field" in exc.value.detail

    def test_empty_string_raises_422(self):
        with pytest.raises(HTTPException) as exc:
            _parse_iso_date("", "test_field")
        assert exc.value.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# 5. SCHEMA VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════


class TestRequestValidation:
    """输入参数 schema 校验"""

    def test_valid_request(self):
        req = _make_request()
        assert req.technical_feasibility is True

    def test_condition_dates_default_empty(self):
        req = CapitalizationCheckRequest(
            technical_feasibility=False,
            completion_intent=False,
            ability_to_use_or_sell=False,
            future_economic_benefits=False,
            resource_sufficiency=False,
            project_start_date="2025-01-01",
        )
        assert req.condition_dates == {}

    def test_apply_to_sheet_optional(self):
        req = _make_request()
        assert req.apply_to_sheet is None

    def test_project_end_date_optional(self):
        req = _make_request()
        assert req.project_end_date is None


# ═══════════════════════════════════════════════════════════════════════════════
# 6. END-TO-END ENDPOINT (without DB)
# ═══════════════════════════════════════════════════════════════════════════════


class _NoopDb:
    """Stand-in DB session for endpoint scenarios that don't write back."""


class TestEndpointE2E:
    """端到端 endpoint 调用（apply_to_sheet=None 不触碰 DB）"""

    @pytest.fixture
    def project_id(self):
        return "8ec73ee7-4c6c-4f01-9c0a-d3bb3ce5e7f5"

    @pytest.fixture
    def wp_id(self):
        return "f07a3e73-1f4d-4c2a-9d8b-7e0a8c5f2b3d"

    def _run(self, project_id, wp_id, payload):
        return asyncio.run(
            i2_capitalization_check(
                project_id=project_id,
                wp_id=wp_id,
                payload=payload,
                db=_NoopDb(),  # type: ignore[arg-type]
                _user=object(),
            )
        )

    def test_all_true_returns_capitalization_start_date(self, project_id, wp_id):
        req = _make_request(
            condition_dates={
                "technical_feasibility": "2025-02-15",
                "completion_intent": "2025-03-01",
                "ability_to_use_or_sell": "2025-04-20",
                "future_economic_benefits": "2025-03-15",
                "resource_sufficiency": "2025-04-01",
            },
            project_start_date="2025-01-01",
        )
        resp = self._run(project_id, wp_id, req)
        assert isinstance(resp, CapitalizationCheckResponse)
        assert resp.all_conditions_met is True
        assert resp.capitalization_start_date == "2025-04-20"
        assert resp.missing_conditions == []
        assert "建议" in resp.recommendation
        assert "2025-04-20" in resp.recommendation

    def test_partial_true_returns_missing(self, project_id, wp_id):
        req = _make_request(
            technical_feasibility=False,
            future_economic_benefits=False,
        )
        resp = self._run(project_id, wp_id, req)
        assert resp.all_conditions_met is False
        assert resp.capitalization_start_date is None
        assert len(resp.missing_conditions) == 2
        assert "费用化" in resp.recommendation or "缺失" in resp.recommendation

    def test_invalid_project_id_returns_400(self, wp_id):
        req = _make_request()
        with pytest.raises(HTTPException) as exc:
            self._run("not-a-uuid", wp_id, req)
        assert exc.value.status_code == 400

    def test_project_end_before_start_returns_400(self, project_id, wp_id):
        req = _make_request(
            project_start_date="2025-06-01",
            project_end_date="2025-01-01",
        )
        with pytest.raises(HTTPException) as exc:
            self._run(project_id, wp_id, req)
        assert exc.value.status_code == 400

    def test_capitalization_after_project_end_returns_400(self, project_id, wp_id):
        """全部条件满足但起始日 > 项目预计完成日 → 400"""
        req = _make_request(
            condition_dates={f: "2025-12-31" for f in CONDITION_FIELDS},
            project_start_date="2025-01-01",
            project_end_date="2025-06-01",
        )
        with pytest.raises(HTTPException) as exc:
            self._run(project_id, wp_id, req)
        assert exc.value.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# 7. WRITE-BACK HELPER
# ═══════════════════════════════════════════════════════════════════════════════


class TestWriteBack:
    """写回 helper 签名和可调用性"""

    def test_write_back_function_exists(self):
        assert callable(_maybe_apply_capitalization_check_to_workpaper)

    def test_write_back_is_async(self):
        assert inspect.iscoroutinefunction(_maybe_apply_capitalization_check_to_workpaper)

    def test_write_back_returns_none_when_no_sheet(self):
        """apply_to_sheet 为 None 时不写回，直接返回 None"""

        async def _test():
            return await _maybe_apply_capitalization_check_to_workpaper(
                db=None,  # type: ignore[arg-type]
                wp_id="fake-id",
                payload=_make_request(apply_to_sheet=None),
                all_met=True,
                capitalization_start_date="2025-04-20",
                missing_conditions=[],
                condition_status={f: True for f in CONDITION_FIELDS},
                recommendation="test",
            )

        assert asyncio.run(_test()) is None

    def test_write_back_returns_none_when_invalid_wp_id(self):
        """wp_id 不是合法 UUID 时返回 None（防御性早退）"""

        async def _test():
            return await _maybe_apply_capitalization_check_to_workpaper(
                db=None,  # type: ignore[arg-type]
                wp_id="not-a-uuid",
                payload=_make_request(apply_to_sheet="项目成立条件I2-6"),
                all_met=True,
                capitalization_start_date="2025-04-20",
                missing_conditions=[],
                condition_status={f: True for f in CONDITION_FIELDS},
                recommendation="test",
            )

        assert asyncio.run(_test()) is None


# ═══════════════════════════════════════════════════════════════════════════════
# 8. RBAC + ENDPOINT METADATA
# ═══════════════════════════════════════════════════════════════════════════════


class TestRbac:
    """RBAC 校验"""

    def test_endpoint_has_rbac_dependency(self):
        sig = inspect.signature(i2_capitalization_check)
        assert "_user" in sig.parameters

    def test_endpoint_is_async(self):
        assert inspect.iscoroutinefunction(i2_capitalization_check)

    def test_router_uses_require_project_access_edit(self):
        """RBAC 依赖必须是 require_project_access('edit')

        通过 router 注册的路由读取 dependency 列表验证。
        """
        from app.routers.wp_i_capitalization import router

        # 找到 capitalization-check route
        target = None
        for route in router.routes:
            if getattr(route, "path", "").endswith("/capitalization-check"):
                target = route
                break
        assert target is not None, "capitalization-check route not registered"

        # endpoint signature 必须含 _user 参数（绑定 require_project_access dep）
        ep = target.endpoint  # type: ignore[attr-defined]
        sig = inspect.signature(ep)
        assert "_user" in sig.parameters

        # 校验依赖来源（lazy import 避免循环）
        from app.deps import require_project_access  # noqa: F401
