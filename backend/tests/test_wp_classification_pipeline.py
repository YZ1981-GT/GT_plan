"""``/api/wp-classifications`` 复用 render 公共裁决核的行为特征测试。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers import wp_classification
from app.routers import wp_render_pipeline as pipeline
from app.services.wp_classification_service import (
    ClassificationNotFoundError,
    ClassificationResult,
)


def _classification(*, wp_code: str = "D2", sheet_name: str = "审定表D2-1") -> ClassificationResult:
    return ClassificationResult(
        wp_code=wp_code,
        sheet_name=sheet_name,
        class_code="F-审定表",
        class_="F类",
        scope="standalone",
        is_real_workpaper=True,
        delegated_module=None,
        render_schema_path=None,
        template_version_id=None,
    )


def _db_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalar_one.return_value = value
    return result


def _index(wp_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=wp_id,
        wp_name="应收账款",
        audit_cycle="D",
    )


def _working_paper(wp_index_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), wp_index_id=wp_index_id)


def _resolution(*items: ClassificationResult) -> pipeline.ClassificationResolution:
    return pipeline.ClassificationResolution(
        template_version_id=None,
        template_version=None,
        classifications=tuple(items),
        package_sheets=None,
        package_applied=False,
        winning_source="classification",
    )


@pytest.mark.asyncio
async def test_classifications_resolves_common_sources_and_derives_components() -> None:
    project_id = uuid.uuid4()
    wp_index = _index(uuid.uuid4())
    working_paper = _working_paper(wp_index.id)
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _db_result(wp_index),  # wp index
            _db_result(working_paper),  # working paper
        ]
    )
    classification = _classification()
    resolution = _resolution(classification)
    plan = pipeline.SheetPlan(
        classification=classification,
        component_type="audit-sheet",
        host_policy="html",
        override_hit=False,
        winning_source="class_code",
        candidate_sources=("class_code:F-审定表",),
        is_multi_sheet=False,
        renderer_available=True,
        whole_workbook_dedicated=False,
    )
    render_plan = pipeline.RenderPlan(
        sheets=(plan,),
        decisions=(),
        ordered_classifications=(classification,),
    )

    with (
        patch(
            "app.routers.wp_classification.resolve_common_classification_resolution",
            AsyncMock(return_value=resolution),
        ) as resolver,
        patch(
            "app.routers.wp_classification.plan_sheets",
            AsyncMock(return_value=render_plan),
        ) as planner,
        patch(
            "app.routers.wp_classification.derive_component_type",
            return_value="audit-sheet",
        ) as derive,
        patch(
            "app.routers.wp_classification.refresh_wp_code_overrides",
        ),
    ):
        response = await wp_classification.get_wp_classifications(
            wp_code="D2",
            project_id=project_id,
            template_version_id=None,
            db=db,
            current_user=None,
        )

    response_payload = response.model_dump()
    assert response_payload == {
        "wp_code": "D2",
        "project_id": str(project_id),
        "adjudication_core": "resolve_common_classification_sources",
        "classifications": [
            {
                "sheet_name": "审定表D2-1",
                "class_code": "F-审定表",
                "componentType": "audit-sheet",
                "scope": "standalone",
                "is_real_workpaper": True,
                "delegated_module": None,
                "has_override": False,
                "render_plan_componentType": "audit-sheet",
                "winning_source": "classification_derive",
                "divergence_reason": None,
            }
        ],
    }
    resolver.assert_awaited_once_with(
        db=db,
        wp_code="D2",
        project_id=project_id,
        template_version_id=None,
        wp_index=wp_index,
        working_paper=working_paper,
    )
    planner.assert_awaited_once()
    derive.assert_called_once_with(
        classification,
        ignore_wp_code_override=True,
    )


@pytest.mark.asyncio
async def test_classifications_reports_explicit_plan_divergence() -> None:
    project_id = uuid.uuid4()
    wp_index = _index(uuid.uuid4())
    working_paper = _working_paper(wp_index.id)
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[_db_result(wp_index), _db_result(working_paper)]
    )
    classification = _classification()
    resolution = _resolution(classification)
    plan = pipeline.SheetPlan(
        classification=classification,
        component_type="d2-accounts-receivable",
        host_policy="html",
        override_hit=True,
        winning_source="wp_override",
        candidate_sources=("class_code:F-审定表", "wp_override:d2-accounts-receivable"),
        is_multi_sheet=False,
        renderer_available=True,
        whole_workbook_dedicated=False,
    )
    render_plan = pipeline.RenderPlan(
        sheets=(plan,),
        decisions=(),
        ordered_classifications=(classification,),
    )

    with (
        patch(
            "app.routers.wp_classification.resolve_common_classification_resolution",
            AsyncMock(return_value=resolution),
        ),
        patch(
            "app.routers.wp_classification.plan_sheets",
            AsyncMock(return_value=render_plan),
        ),
        patch(
            "app.routers.wp_classification.derive_component_type",
            return_value="audit-sheet",
        ),
        patch("app.routers.wp_classification.refresh_wp_code_overrides"),
    ):
        response = await wp_classification.get_wp_classifications(
            wp_code="D2",
            project_id=project_id,
            template_version_id=None,
            db=db,
            current_user=None,
        )

    item = response.model_dump()["classifications"][0]
    assert item["componentType"] == "audit-sheet"
    assert item["render_plan_componentType"] == "d2-accounts-receivable"
    assert item["divergence_reason"] == (
        "classifications_api=audit-sheet;"
        "render_plan=d2-accounts-receivable;"
        "winning_source=wp_override;"
        "override_hit=true"
    )


@pytest.mark.asyncio
async def test_classifications_preserves_404_and_skip_degradation() -> None:
    project_id = uuid.uuid4()
    missing_wp_index = _index(uuid.uuid4())
    missing_working_paper = _working_paper(missing_wp_index.id)
    missing_db = AsyncMock()
    missing_db.execute = AsyncMock(
        side_effect=[_db_result(missing_wp_index), _db_result(missing_working_paper)]
    )

    with patch(
        "app.routers.wp_classification.resolve_common_classification_resolution",
        AsyncMock(return_value=_resolution()),
    ):
        with pytest.raises(
            wp_classification.HTTPException,
            match="No classification found",
        ) as exc_info:
            await wp_classification.get_wp_classifications(
                wp_code="MISSING",
                project_id=project_id,
                template_version_id=None,
                db=missing_db,
                current_user=None,
            )
    assert exc_info.value.status_code == 404

    degraded_wp_index = _index(uuid.uuid4())
    degraded_working_paper = _working_paper(degraded_wp_index.id)
    degraded_db = AsyncMock()
    degraded_db.execute = AsyncMock(
        side_effect=[_db_result(degraded_wp_index), _db_result(degraded_working_paper)]
    )
    classification = _classification()
    skip_plan = pipeline.SheetPlan(
        classification=classification,
        component_type="skip",
        host_policy="unresolved",
        override_hit=False,
        winning_source="skip_fallback",
        candidate_sources=("class_code:F-审定表",),
        is_multi_sheet=False,
        renderer_available=False,
        whole_workbook_dedicated=False,
        fallback_reason="classification_not_found",
    )
    with (
        patch(
            "app.routers.wp_classification.resolve_common_classification_resolution",
            AsyncMock(return_value=_resolution(classification)),
        ),
        patch(
            "app.routers.wp_classification.plan_sheets",
            AsyncMock(
                return_value=pipeline.RenderPlan(
                    sheets=(skip_plan,),
                    decisions=(),
                    ordered_classifications=(classification,),
                )
            ),
        ),
        patch(
            "app.routers.wp_classification.derive_component_type",
            side_effect=ClassificationNotFoundError("degraded"),
        ),
        patch("app.routers.wp_classification.refresh_wp_code_overrides"),
    ):
        response = await wp_classification.get_wp_classifications(
            wp_code="D2",
            project_id=project_id,
            template_version_id=None,
            db=degraded_db,
            current_user=None,
        )
    item = response.model_dump()["classifications"][0]
    assert item["componentType"] == "skip"
    assert item["divergence_reason"] == "classification_not_found"


def test_format_classification_plan_divergence_is_explicit() -> None:
    assert (
        pipeline.format_classification_plan_divergence(
            classification_component_type="audit-sheet",
            plan_component_type="audit-sheet",
        )
        is None
    )
    reason = pipeline.format_classification_plan_divergence(
        classification_component_type="audit-sheet",
        plan_component_type="onlyoffice-sheet",
        winning_source="manifest_host_policy",
        fallback_reason="manifest_onlyoffice_fallback",
    )
    assert "classifications_api=audit-sheet" in reason
    assert "render_plan=onlyoffice-sheet" in reason
    assert "winning_source=manifest_host_policy" in reason
