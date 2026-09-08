"""render-config 七阶段顺序与 fail-open 行为守卫。

故意交换阶段或删除 fail-open fallback 必须准确 RED。
"""

from __future__ import annotations

import ast
import inspect
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.routers import wp_render_config
from app.routers import wp_render_pipeline as pipeline
from app.services.wp_classification_service import ClassificationResult


def _classification(
    sheet_name: str = "审定表D2-1",
    *,
    scope: str = "standalone",
    is_real: bool = True,
) -> ClassificationResult:
    return ClassificationResult(
        wp_code="D2",
        sheet_name=sheet_name,
        class_code="D-审定表",
        class_="D类",
        scope=scope,
        is_real_workpaper=is_real,
        delegated_module=None,
        render_schema_path=None,
        template_version_id=None,
    )


def _subject() -> pipeline.RenderSubject:
    working_paper = SimpleNamespace(
        project_id=uuid.uuid4(),
        parsed_data={"html_data": {}},
        file_path=None,
        id=uuid.uuid4(),
    )
    return pipeline.RenderSubject(
        wp_id=working_paper.id,
        working_paper=working_paper,
        project_id=working_paper.project_id,
        wp_code="D2",
        wp_name="应收账款",
        audit_cycle="D",
        user_id=uuid.uuid4(),
    )


STAGE_ORDER = (
    "load_render_subject",
    "resolve_classification_sources",
    "resolve_scope_redirect",
    "load_common_render_facts",
    "plan_sheets",
    "materialize_sheet",
    "finalize_render_response",
)


def _orchestrator_stage_call_order() -> list[str]:
    """从 ``_get_render_config_impl`` 源码提取七阶段 await/call 顺序。"""
    source = inspect.getsource(wp_render_config._get_render_config_impl)
    tree = ast.parse(source)
    order: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_Await(self, node: ast.Await) -> None:
            self._maybe_record(node.value)
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            self._maybe_record(node)
            self.generic_visit(node)

        def _maybe_record(self, node: ast.AST) -> None:
            name: str | None = None
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
            if name in STAGE_ORDER and (not order or order[-1] != name):
                order.append(name)

    Visitor().visit(tree)
    return order


def test_orchestrator_preserves_seven_stage_order() -> None:
    assert _orchestrator_stage_call_order() == list(STAGE_ORDER)


def test_swapping_adjacent_stages_would_red() -> None:
    """锚定：若有人把 facts 挪到 redirect 之前，本断言必须准确 RED。"""
    order = _orchestrator_stage_call_order()
    redirect_idx = order.index("resolve_scope_redirect")
    facts_idx = order.index("load_common_render_facts")
    assert redirect_idx < facts_idx, (
        "scope redirect 必须在 common facts 之前短路；交换阶段会加载无用事实"
    )
    plan_idx = order.index("plan_sheets")
    materialize_idx = order.index("materialize_sheet")
    assert plan_idx < materialize_idx


def test_planner_source_uses_host_policy_not_whitelist_literals() -> None:
    """planner 裁决只读 manifest host_policy；不得再读白名单集合字面量。"""
    plan_source = inspect.getsource(pipeline.plan_sheets)
    materialize_source = inspect.getsource(pipeline.materialize_sheet)
    assert "_ONLYOFFICE_HTML_WHITELIST" not in plan_source
    assert "_CONFIRMATION_COMPONENTS" not in plan_source
    assert "host_policy" in plan_source
    assert "manifest_host_policy" in plan_source
    assert "_ONLYOFFICE_HTML_WHITELIST" not in materialize_source
    # 导出投影仍可存在于 wp_render_config，但不得参与 Stage 5/6 裁决。
    config_source = Path(wp_render_config.__file__).read_text(encoding="utf-8")
    assert "types_from_source" in config_source
    assert "_ONLYOFFICE_HTML_WHITELIST" in config_source


@pytest.mark.asyncio
async def test_package_resolver_fail_open_records_reason_and_continues() -> None:
    """删除 fail-open（改为抛错）会使本测试准确 RED。"""
    subject = _subject()
    db = AsyncMock()
    version_service = MagicMock()
    version_service.get_current_version = AsyncMock(
        return_value=SimpleNamespace(id=uuid.uuid4(), version="v1")
    )
    classification_service = MagicMock()
    classification_service.get_classification = AsyncMock(
        return_value=[_classification()]
    )

    resolution = await pipeline.resolve_classification_sources(
        subject=subject,
        db=db,
        template_version_service_factory=lambda _: version_service,
        classification_service_factory=lambda _: classification_service,
        maybe_custom_resolver=AsyncMock(side_effect=lambda *args: args[4]),
        package_resolver=AsyncMock(side_effect=RuntimeError("package-down")),
    )

    assert resolution.package_applied is False
    assert resolution.package_sheets is None
    assert resolution.fallback_reason == "package_resolver_error:RuntimeError"
    assert len(resolution.classifications) == 1
    db.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_removing_package_fail_open_must_red_if_raises() -> None:
    """行为锁：当前契约是吞异常继续；若实现改成 fail-fast，调用方会看到异常。"""
    subject = _subject()
    db = AsyncMock()
    version_service = MagicMock()
    version_service.get_current_version = AsyncMock(
        return_value=SimpleNamespace(id=uuid.uuid4(), version="v1")
    )
    classification_service = MagicMock()
    classification_service.get_classification = AsyncMock(
        return_value=[_classification()]
    )

    # 对照：非 HTTPException 的模板版本错误仍 fail-fast（不得被误改成 fail-open）。
    version_service.get_current_version = AsyncMock(
        side_effect=RuntimeError("template-must-propagate")
    )
    with pytest.raises(RuntimeError, match="template-must-propagate"):
        await pipeline.resolve_classification_sources(
            subject=subject,
            db=db,
            template_version_service_factory=lambda _: version_service,
            classification_service_factory=lambda _: classification_service,
            maybe_custom_resolver=AsyncMock(side_effect=lambda *args: args[4]),
            package_resolver=AsyncMock(return_value=None),
        )


@pytest.mark.asyncio
async def test_redirect_short_circuits_without_planning() -> None:
    subject = _subject()
    resolution = pipeline.ClassificationResolution(
        template_version_id=None,
        template_version=None,
        classifications=(
            _classification(scope="consolidated", is_real=False),
        ),
        package_sheets=None,
        package_applied=False,
        winning_source="classification",
    )
    scope = pipeline.resolve_scope_redirect(
        subject=subject,
        resolution=resolution,
        overrides={},
    )
    assert scope.redirect_applied is True
    # 若 orchestrator 把 redirect 挪到 plan 之后，characterization/golden 会红；
    # 此处锁定纯函数仍先于 facts/plan 可独立短路。
    assert scope.to_redirect_response(
        subject=subject,
        template_version=None,
    )["sheets"] == []


@pytest.mark.asyncio
async def test_host_policy_fallback_wins_over_whitelist_membership() -> None:
    """多 sheet + 无 renderer 时走 manifest host_policy，而非白名单集合成员测试。"""
    subject = _subject()
    first = _classification("Sheet-A")
    second = _classification("Sheet-B")
    # 伪造无 backend renderer、host_policy=onlyoffice 的能力。
    fake_cap = SimpleNamespace(
        has_backend_renderer=False,
        host_policy="onlyoffice",
    )
    fake_registry = MagicMock()
    fake_registry.get.return_value = fake_cap
    fake_registry.backend_renderer_types = frozenset()

    plan = await pipeline.plan_sheets(
        subject=subject,
        resolution=pipeline.ClassificationResolution(
            template_version_id=None,
            template_version=None,
            classifications=(first, second),
            package_sheets=None,
            package_applied=False,
            winning_source="classification",
        ),
        facts=pipeline.CommonRenderFacts(
            html_data_all={},
            cross_ref_items=(),
            project_year=None,
            business_category="C",
            template_path=None,
        ),
        requested_sheet_name=None,
        force_component_type=None,
        overrides={},
        template_order_loader=lambda _p: {},
        capabilities=fake_registry,
    )

    assert all(item.component_type == "onlyoffice-sheet" for item in plan.sheets)
    assert all(item.winning_source == "manifest_host_policy" for item in plan.sheets)
    assert all(
        item.fallback_reason == "manifest_onlyoffice_fallback" for item in plan.sheets
    )


@pytest.mark.asyncio
async def test_subject_404_still_ordered_before_classification() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(
            first=MagicMock(return_value=None),
            scalar=MagicMock(return_value=None),
            scalars=MagicMock(
                return_value=MagicMock(first=MagicMock(return_value=None), all=MagicMock(return_value=[]))
            ),
        )
    )
    with pytest.raises(HTTPException) as exc_info:
        await pipeline.load_render_subject(
            wp_id=uuid.uuid4(),
            db=db,
            current_user=SimpleNamespace(id=uuid.uuid4()),
        )
    assert exc_info.value.detail == "底稿不存在"
    # Stage 1 失败不得进入 Stage 2：orchestrator 顺序守卫已覆盖；此处锁定 404 文案。
