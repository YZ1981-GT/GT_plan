"""render-config 七阶段拆分的行为级特征测试。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.routers import wp_render_pipeline as pipeline
from app.services.wp_classification_service import ClassificationResult


def _classification(
    sheet_name: str = "审定表D2-1",
    *,
    scope: str = "standalone",
    is_real: bool = True,
    delegated_module: str | None = None,
) -> ClassificationResult:
    return ClassificationResult(
        wp_code="D2",
        sheet_name=sheet_name,
        class_code="D-审定表",
        class_="D类",
        scope=scope,
        is_real_workpaper=is_real,
        delegated_module=delegated_module,
        render_schema_path=None,
        template_version_id=None,
    )


def _subject() -> pipeline.RenderSubject:
    working_paper = SimpleNamespace(
        project_id=uuid.uuid4(),
        parsed_data={"html_data": {"审定表D2-1": {"seed": 1}}},
        file_path=None,
    )
    return pipeline.RenderSubject(
        wp_id=uuid.uuid4(),
        working_paper=working_paper,
        project_id=working_paper.project_id,
        wp_code="D2",
        wp_name="应收账款",
        audit_cycle="D",
        user_id=uuid.uuid4(),
    )


def _db_result(*, first=None, scalar=None, all_rows=None) -> MagicMock:
    result = MagicMock()
    result.first.return_value = first
    result.scalar.return_value = scalar
    result.scalars.return_value.first.return_value = first
    result.scalars.return_value.all.return_value = all_rows or []
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("results", "expected_detail", "expected_calls"),
    [
        ([_db_result(first=None)], "底稿不存在", 1),
        (
            [
                _db_result(first=SimpleNamespace(project_id=uuid.uuid4())),
                _db_result(scalar=True),
            ],
            "项目已删除",
            2,
        ),
        (
            [
                _db_result(
                    first=SimpleNamespace(
                        project_id=uuid.uuid4(),
                        wp_index_id=uuid.uuid4(),
                    )
                ),
                _db_result(scalar=False),
                _db_result(first=None),
            ],
            "底稿索引不存在",
            3,
        ),
    ],
    ids=["workpaper", "deleted-project", "wp-index"],
)
async def test_load_render_subject_preserves_404_order(
    results: list[MagicMock],
    expected_detail: str,
    expected_calls: int,
) -> None:
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=results)

    with pytest.raises(HTTPException) as exc_info:
        await pipeline.load_render_subject(
            wp_id=uuid.uuid4(),
            db=db,
            current_user=SimpleNamespace(id=uuid.uuid4()),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == expected_detail
    assert db.execute.await_count == expected_calls


@pytest.mark.asyncio
async def test_load_render_subject_snapshots_values_before_later_rollbacks() -> None:
    wp_id = uuid.uuid4()
    project_id = uuid.uuid4()
    user_id = uuid.uuid4()
    wp = SimpleNamespace(project_id=project_id, wp_index_id=uuid.uuid4())
    wp_index = SimpleNamespace(
        wp_code="D2",
        wp_name="应收账款",
        audit_cycle="D",
    )
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _db_result(first=wp),
            _db_result(scalar=False),
            _db_result(first=wp_index),
        ]
    )

    subject = await pipeline.load_render_subject(
        wp_id=wp_id,
        db=db,
        current_user=SimpleNamespace(id=user_id),
    )

    assert subject.wp_id == wp_id
    assert subject.project_id == project_id
    assert subject.wp_code == "D2"
    assert subject.audit_cycle == "D"
    assert subject.user_id == user_id


@pytest.mark.asyncio
async def test_template_version_http_exception_falls_back_but_other_errors_propagate() -> None:
    subject = _subject()
    db = AsyncMock()
    version_service = MagicMock()
    version_service.get_current_version = AsyncMock(
        side_effect=HTTPException(status_code=404, detail="missing")
    )
    classification_service = MagicMock()
    classification_service.get_classification = AsyncMock(return_value=[_classification()])

    resolution = await pipeline.resolve_classification_sources(
        subject=subject,
        db=db,
        template_version_service_factory=lambda _: version_service,
        classification_service_factory=lambda _: classification_service,
        maybe_custom_resolver=AsyncMock(side_effect=lambda *args: args[4]),
        package_resolver=AsyncMock(return_value=None),
    )
    assert resolution.template_version is None
    assert resolution.template_version_id is None

    version_service.get_current_version.side_effect = RuntimeError("must-propagate")
    with pytest.raises(RuntimeError, match="must-propagate"):
        await pipeline.resolve_classification_sources(
            subject=subject,
            db=db,
            template_version_service_factory=lambda _: version_service,
            classification_service_factory=lambda _: classification_service,
            maybe_custom_resolver=AsyncMock(side_effect=lambda *args: args[4]),
            package_resolver=AsyncMock(return_value=None),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("package_mode", ["truthy", "empty", "error"])
async def test_package_resolution_preserves_override_and_fallback_semantics(
    package_mode: str,
) -> None:
    subject = _subject()
    base = _classification("基础分类D2-1")
    package = _classification("工作包分类D2-1")
    db = AsyncMock()
    version_service = MagicMock()
    version_service.get_current_version = AsyncMock(
        return_value=SimpleNamespace(version="v1", id=uuid.uuid4())
    )
    classification_service = MagicMock()
    classification_service.get_classification = AsyncMock(return_value=[base])
    if package_mode == "truthy":
        package_resolver = AsyncMock(return_value=[package])
    elif package_mode == "empty":
        package_resolver = AsyncMock(return_value=[])
    else:
        package_resolver = AsyncMock(side_effect=RuntimeError("package-broken"))

    resolution = await pipeline.resolve_classification_sources(
        subject=subject,
        db=db,
        template_version_service_factory=lambda _: version_service,
        classification_service_factory=lambda _: classification_service,
        maybe_custom_resolver=AsyncMock(side_effect=lambda *args: args[4]),
        package_resolver=package_resolver,
    )

    if package_mode == "truthy":
        assert resolution.classifications == (package,)
        assert resolution.package_applied is True
        assert resolution.winning_source == "account_package"
    else:
        assert resolution.classifications == (base,)
        assert resolution.package_applied is False
        assert resolution.winning_source == "classification"
    if package_mode == "empty":
        assert resolution.package_sheets == ()
        db.rollback.assert_not_awaited()
    elif package_mode == "error":
        assert resolution.package_sheets is None
        assert resolution.fallback_reason == "package_resolver_error:RuntimeError"
        db.rollback.assert_awaited_once()


@pytest.mark.parametrize(
    ("scope", "override", "expected_module", "expected_target"),
    [
        ("consolidated", "redirect-materiality", "consolidation_hub", None),
        ("parent_only", None, "package_hub", None),
        ("standalone", "redirect-materiality", "materiality", "/materiality"),
    ],
)
def test_scope_redirect_priority_is_stable(
    scope: str,
    override: str | None,
    expected_module: str,
    expected_target: str | None,
) -> None:
    subject = _subject()
    classification = _classification(
        scope=scope,
        delegated_module="package_hub" if scope == "parent_only" else None,
    )
    resolution = pipeline.ClassificationResolution(
        template_version_id=None,
        template_version="v1",
        classifications=(classification,),
        package_sheets=None,
        package_applied=False,
        winning_source="classification",
    )

    result = pipeline.resolve_scope_redirect(
        subject=subject,
        resolution=resolution,
        overrides={subject.wp_code: override} if override else {},
    )

    assert result.redirect_applied is True
    assert result.delegated_module == expected_module
    assert result.target_path == expected_target


@pytest.mark.asyncio
async def test_redirect_short_circuits_before_common_facts_and_renderers() -> None:
    from app.routers import wp_render_config

    subject = _subject()
    resolution = pipeline.ClassificationResolution(
        template_version_id=None,
        template_version="v1",
        classifications=(_classification(scope="consolidated"),),
        package_sheets=None,
        package_applied=False,
        winning_source="classification",
    )
    scope = pipeline.ScopeResolution(
        scope="consolidated",
        is_real_workpaper=True,
        redirect_applied=True,
        delegated_module="consolidation_hub",
    )
    order: list[str] = []

    async def load_subject(**_kwargs):
        order.append("subject")
        return subject

    async def resolve_sources(**_kwargs):
        order.append("classification")
        return resolution

    def resolve_redirect(**_kwargs):
        order.append("scope")
        return scope

    common = AsyncMock(side_effect=AssertionError("redirect 后不得加载 common facts"))
    with (
        patch.object(pipeline, "load_render_subject", side_effect=load_subject),
        patch.object(
            pipeline,
            "resolve_classification_sources",
            side_effect=resolve_sources,
        ),
        patch.object(pipeline, "resolve_scope_redirect", side_effect=resolve_redirect),
        patch.object(pipeline, "load_common_render_facts", common),
        patch(
            "app.services.wp_classification_service.refresh_wp_code_overrides"
        ),
    ):
        response = await wp_render_config._get_render_config_impl(
            subject.wp_id,
            None,
            AsyncMock(),
            SimpleNamespace(id=subject.user_id),
        )

    assert order == ["subject", "classification", "scope"]
    common.assert_not_awaited()
    assert response == {
        "wp_id": str(subject.wp_id),
        "wp_code": "D2",
        "project_id": str(subject.project_id),
        "scope": "consolidated",
        "template_version": "v1",
        "sheets": [],
        "is_real_workpaper": True,
        "redirect": True,
        "delegated_module": "consolidation_hub",
    }


@pytest.mark.asyncio
async def test_common_facts_keep_first_year_query_and_cross_ref_shape() -> None:
    subject = _subject()
    cross_ref = SimpleNamespace(target_wp_code="B50", cell_reference=None)
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _db_result(all_rows=[cross_ref]),
            _db_result(first=(2025, "E")),
        ]
    )
    template_resolver = MagicMock(return_value="template.xlsx")

    facts = await pipeline.load_common_render_facts(
        subject=subject,
        db=db,
        template_path_resolver=template_resolver,
    )

    assert facts.html_data_all == {"审定表D2-1": {"seed": 1}}
    assert [item.model_dump() for item in facts.cross_ref_items] == [
        {"wp_code": "B50", "cell": None}
    ]
    assert facts.project_year == 2025
    assert facts.business_category == "E"
    assert facts.template_path == "template.xlsx"
    assert db.execute.await_count == 2
    db.rollback.assert_not_awaited()


def _sheet_plan(
    classification: ClassificationResult,
    *,
    component_type: str,
    host_policy: str = "html",
    is_multi_sheet: bool = True,
    renderer_available: bool = False,
    whole_dedicated: bool = False,
    g_shortcut: bool = False,
) -> pipeline.SheetPlan:
    return pipeline.SheetPlan(
        classification=classification,
        component_type=component_type,
        host_policy=host_policy,
        override_hit=False,
        winning_source="test",
        candidate_sources=("test",),
        is_multi_sheet=is_multi_sheet,
        renderer_available=renderer_available,
        whole_workbook_dedicated=whole_dedicated,
        g_onlyoffice_shortcut=g_shortcut,
    )


def _resolution(*items: ClassificationResult) -> pipeline.ClassificationResolution:
    return pipeline.ClassificationResolution(
        template_version_id=None,
        template_version="v1",
        classifications=tuple(items),
        package_sheets=None,
        package_applied=False,
        winning_source="classification",
    )


def _facts(html_data: dict, template_path: str | None = None) -> pipeline.CommonRenderFacts:
    return pipeline.CommonRenderFacts(
        html_data_all=html_data,
        cross_ref_items=(),
        project_year=2025,
        business_category="C",
        template_path=template_path,
    )


@pytest.mark.asyncio
async def test_plan_keeps_g_shortcut_before_force_component() -> None:
    subject = _subject()
    g_sheet = _classification("测算表G1-1")
    g_sheet.class_code = "G-OnlyOffice"
    regular = _classification("程序表D2A")
    regular.class_code = "A-程序表"
    resolution = _resolution(g_sheet, regular)

    plan = await pipeline.plan_sheets(
        subject=subject,
        resolution=resolution,
        facts=_facts({}),
        requested_sheet_name=None,
        force_component_type="a-program-console",
        overrides={},
        template_order_loader=lambda _path: {},
    )

    by_name = {item.classification.sheet_name: item for item in plan.sheets}
    assert by_name["测算表G1-1"].component_type == "onlyoffice-sheet"
    assert by_name["测算表G1-1"].g_onlyoffice_shortcut is True
    assert by_name["测算表G1-1"].force_applied is False
    assert by_name["程序表D2A"].component_type == "a-program-console"
    assert by_name["程序表D2A"].force_applied is True


@pytest.mark.asyncio
async def test_materialize_memo_caches_none_by_key_without_second_renderer_call() -> None:
    subject = _subject()
    first = _classification("Sheet-1")
    second = _classification("Sheet-2")
    plans = (
        _sheet_plan(
            first,
            component_type="a-program-console",
            renderer_available=True,
            whole_dedicated=True,
        ),
        _sheet_plan(
            second,
            component_type="a-program-console",
            renderer_available=True,
            whole_dedicated=True,
        ),
    )
    render_plan = pipeline.RenderPlan(
        sheets=plans,
        decisions=(),
        ordered_classifications=(first, second),
    )
    state = pipeline.MaterializationState(sheets=[], dedicated_render_memo={})
    renderer = AsyncMock(return_value=None)
    schema_service = MagicMock()
    schema_service.load_schema.side_effect = FileNotFoundError
    db = AsyncMock()

    for item in plans:
        await pipeline.materialize_sheet(
            plan=item,
            render_plan=render_plan,
            state=state,
            subject=subject,
            resolution=_resolution(first, second),
            facts=_facts({"Sheet-1": {"seed": 1}, "Sheet-2": {"seed": 2}}),
            db=db,
            schema_service=schema_service,
            renderer_dispatch={"a-program-console": renderer},
        )

    assert renderer.await_count == 1
    assert state.dedicated_render_memo == {"a-program-console": None}
    assert [sheet["html_data"] for sheet in state.sheets] == [
        {"seed": 1},
        {"seed": 2},
    ]


@pytest.mark.asyncio
async def test_renderer_exception_rolls_back_and_never_enters_grid_fallback() -> None:
    subject = _subject()
    classification = _classification("程序表D2A")
    plan = _sheet_plan(
        classification,
        component_type="a-program-console",
        renderer_available=True,
    )
    render_plan = pipeline.RenderPlan(
        sheets=(plan,),
        decisions=(),
        ordered_classifications=(classification,),
    )
    state = pipeline.MaterializationState(sheets=[], dedicated_render_memo={})
    schema_service = MagicMock()
    schema_service.load_schema.side_effect = FileNotFoundError
    db = AsyncMock()
    renderer = AsyncMock(side_effect=RuntimeError("renderer-broken"))

    with patch("app.services.wp_grid_extract.extract_grid") as extract_grid:
        await pipeline.materialize_sheet(
            plan=plan,
            render_plan=render_plan,
            state=state,
            subject=subject,
            resolution=_resolution(classification),
            facts=_facts({}, template_path="template.xlsx"),
            db=db,
            schema_service=schema_service,
            renderer_dispatch={"a-program-console": renderer},
        )

    renderer.assert_awaited_once()
    db.rollback.assert_awaited_once()
    extract_grid.assert_not_called()
    assert len(state.sheets) == 1
    assert state.sheets[0]["html_data"] is None


@pytest.mark.asyncio
async def test_confirmation_injectors_remain_three_independent_fail_open_steps() -> None:
    subject = _subject()
    classification = _classification("函证结果汇总表D0-1")
    plan = _sheet_plan(
        classification,
        component_type="confirmation-summary",
        host_policy="confirmation",
    )
    render_plan = pipeline.RenderPlan(
        sheets=(plan,),
        decisions=(),
        ordered_classifications=(classification,),
    )
    state = pipeline.MaterializationState(sheets=[], dedicated_render_memo={})
    schema_service = MagicMock()
    schema_service.load_schema.side_effect = FileNotFoundError
    population = AsyncMock(side_effect=RuntimeError("population"))
    h0 = AsyncMock(side_effect=RuntimeError("h0"))
    l0 = AsyncMock()

    with (
        patch.object(pipeline, "_inject_confirmation_population", population),
        patch.object(pipeline, "_inject_h0_book_amounts", h0),
        patch.object(pipeline, "_inject_l0_book_amounts", l0),
    ):
        await pipeline.materialize_sheet(
            plan=plan,
            render_plan=render_plan,
            state=state,
            subject=subject,
            resolution=_resolution(classification),
            facts=_facts({"函证结果汇总表D0-1": {"rows": []}}),
            db=AsyncMock(),
            schema_service=schema_service,
            renderer_dispatch={},
        )

    population.assert_awaited_once()
    h0.assert_awaited_once()
    l0.assert_awaited_once()
    assert len(state.sheets) == 1


@pytest.mark.asyncio
async def test_finalize_preserves_collapse_auto_sign_standards_identity_guidance_order() -> None:
    subject = _subject()
    classification = _classification("报告A16-1")
    sheet_plan = _sheet_plan(
        classification,
        component_type="word-template",
        is_multi_sheet=True,
    )
    render_plan = pipeline.RenderPlan(
        sheets=(sheet_plan,),
        decisions=(
            pipeline.RenderDecision(
                sheet_key="报告A16-1",
                chosen_component_type="word-template",
                candidate_sources=("test",),
                winning_source="test",
                override_hit=False,
                redirect_applied=False,
            ),
        ),
        ordered_classifications=(classification,),
    )
    scope = pipeline.ScopeResolution(
        scope="standalone",
        is_real_workpaper=True,
        redirect_applied=False,
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_db_result(first=(2025,)))
    order: list[str] = []

    async def auto_fill(**kwargs):
        order.append("auto-fill")
        assert list(kwargs["schema"]["sheets"]) == ["报告A16-1"]
        return {"ok": True}

    field_service = MagicMock()

    async def get_sign(**_kwargs):
        order.append("sign")
        return "draft"

    field_service.get = AsyncMock(side_effect=get_sign)
    standard_service = MagicMock()

    async def get_standard(_project_id):
        order.append("standards-load")
        return {"entity_type": "listed"}

    standard_service.get_standard = AsyncMock(side_effect=get_standard)

    def derive(_raw):
        order.append("standards-derive")
        return ["CAS"]

    def inject(_sheets, _standards):
        order.append("standards-inject")
        return 1

    def annotate(sheets):
        order.append("identity")
        for sheet in sheets:
            sheet["sheet_code"] = "A16-1"
            sheet["sheet_code_reason"] = "embedded_code"
            sheet["whole_workbook"] = False
        return sheets

    def guidance(_wp_code):
        order.append("guidance")
        return None

    with (
        patch(
            "app.services.field_override_service.FieldOverrideService",
            return_value=field_service,
        ),
        patch(
            "app.services.standard_unification_service.StandardUnificationService",
            return_value=standard_service,
        ),
        patch(
            "app.services.standard_unification_service.derive_applicable_standards",
            side_effect=derive,
        ),
        patch(
            "app.routers.wp_render_config_helpers.inject_applicable_standards",
            side_effect=inject,
        ),
    ):
        response = await pipeline.finalize_render_response(
            subject=subject,
            resolution=_resolution(classification),
            scope=scope,
            facts=_facts({}, template_path=None),
            render_plan=render_plan,
            materialized_sheets=[
                {
                    "sheet_name": "报告A16-1",
                    "componentType": "word-template",
                    "schema": {"fields": []},
                    "html_data": {"legacy": True},
                    "cross_refs": [],
                },
                {
                    "sheet_name": "冗余页",
                    "componentType": "word-template",
                    "schema": {"fields": []},
                    "html_data": {"legacy": True},
                    "cross_refs": [],
                },
            ],
            parent_component_type="word-template",
            self_contained_types={"word-template"},
            db=db,
            auto_fill_resolver=auto_fill,
            annotate_sheets=annotate,
            guidance_loader=guidance,
        )

    assert order == [
        "auto-fill",
        "sign",
        "standards-load",
        "standards-derive",
        "standards-inject",
        "identity",
        "guidance",
    ]
    assert len(response["sheets"]) == 1
    assert response["sheets"][0]["html_data"] == {}
    assert response["decision_trace"][0]["chosen_component_type"] == "word-template"
    assert response["permissions"] == {"edit": True}


@pytest.mark.asyncio
async def test_finalize_identity_is_fail_fast_and_prevents_guidance() -> None:
    subject = _subject()
    classification = _classification()
    plan = _sheet_plan(classification, component_type="audit-sheet", is_multi_sheet=False)
    render_plan = pipeline.RenderPlan(
        sheets=(plan,),
        decisions=(),
        ordered_classifications=(classification,),
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_db_result(first=(None,)))
    guidance = MagicMock()

    with patch(
        "app.services.standard_unification_service.StandardUnificationService"
    ) as standard_service:
        standard_service.return_value.get_standard = AsyncMock(
            side_effect=RuntimeError("standards-fail-open")
        )
        with pytest.raises(ValueError, match="identity-conflict"):
            await pipeline.finalize_render_response(
                subject=subject,
                resolution=_resolution(classification),
                scope=pipeline.ScopeResolution(
                    scope="standalone",
                    is_real_workpaper=True,
                    redirect_applied=False,
                ),
                facts=_facts({}),
                render_plan=render_plan,
                materialized_sheets=[
                    {
                        "sheet_name": classification.sheet_name,
                        "componentType": "audit-sheet",
                        "schema": None,
                        "html_data": None,
                        "cross_refs": [],
                    }
                ],
                parent_component_type=None,
                self_contained_types=set(),
                db=db,
                auto_fill_resolver=AsyncMock(return_value={}),
                annotate_sheets=MagicMock(
                    side_effect=ValueError("identity-conflict")
                ),
                guidance_loader=guidance,
            )

    guidance.assert_not_called()
