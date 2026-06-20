# Feature: workpaper-module-health-pass2
"""Property-Based Tests — 底稿模块健康度二期

6 个 PBT 属性测试（Property 2~7），使用 hypothesis 库验证系统不变量。

Properties:
  P2: 策略函数返回类型约束
  P3: 策略函数优雅降级
  P4: Override 映射值合法性
  P5: Override JSON 热重载正确性（简化版）
  P6: 所有 Resolver 均有 docstring
  P7: Router 注册完整性
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import pkgutil
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._context import RenderContext


# ─── Helpers ──────────────────────────────────────────────────────────────────

# 7 策略模块路径
_STRATEGY_MODULES = [
    "app.routers.wp_render_strategies._b_index",
    "app.routers.wp_render_strategies._a_program",
    "app.routers.wp_render_strategies._audit_sheet",
    "app.routers.wp_render_strategies._checklist",
    "app.routers.wp_render_strategies._analytical_review",
    "app.routers.wp_render_strategies._c_note",
    "app.routers.wp_render_strategies._univer_grid",
]


def _make_ctx(
    *,
    sheet_html_data: dict | None = None,
    sheet_schema: dict | None = None,
    template_file_path: str | None = "/fake/template.xlsx",
) -> RenderContext:
    """构造一个用于测试的 RenderContext（所有外部依赖 mock）"""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_result.fetchone.return_value = None
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
    db.execute.return_value = mock_result

    working_paper = MagicMock()
    working_paper.id = uuid4()

    classification = MagicMock()
    classification.sheet_name = "审定表D1-1"
    classification.wp_code = "D1"
    classification.component_type = "audit-sheet"

    return RenderContext(
        db=db,
        project_id=uuid4(),
        wp_id=uuid4(),
        wp_code="D1",
        working_paper=working_paper,
        classification=classification,
        component_type="audit-sheet",
        sheet_html_data=sheet_html_data,
        sheet_schema=sheet_schema,
        template_file_path=template_file_path,
        year=2025,
        business_category="C",
        classifications=[classification],
        audit_cycle="D",
    )


def _run_render_with_patches(strategy_module: str, ctx: RenderContext):
    """在 mock 环境中运行策略 render 函数并返回结果。"""
    mod = importlib.import_module(strategy_module)
    render_fn = mod.render

    mock_prep_info = {
        "entity_name": "",
        "period_end": "",
        "preparer": "",
        "prep_date": "",
        "reviewer": "",
        "review_date": "",
        "index_no": "",
    }

    patchers = [
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
        patch(
            "app.services.wp_program_extract.extract_program_rows",
            return_value=[],
        ),
        patch(
            "app.services.wp_audit_sheet_extract.extract_audit_rows_with_values_from_file",
            return_value=([], None),
        ),
        patch(
            "app.services.wp_audit_sheet_extract.extract_audit_sections",
            return_value={"notes": "", "conclusion": "", "notes_label": "", "conclusion_label": ""},
        ),
        patch(
            "app.services.wp_audit_sheet_tb_service.fetch_audit_sheet_tb_values",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "app.services.checklist_xlsx_parser.is_xlsx_checklist",
            return_value=False,
        ),
        patch(
            "app.services.checklist_docx_parser.get_checklist_template",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.analytical_review_service.get_analytical_review_data",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.wp_grid_extract.extract_grid",
            return_value={"cells": {}, "merged_cells": [], "col_widths": {}, "max_row": 0, "max_col": 0},
        ),
        patch(
            "app.services.procedure_table_auto_service.get_template",
            return_value=None,
        ),
    ]

    for p in patchers:
        p.start()
    try:
        result = asyncio.run(render_fn(ctx))
    finally:
        for p in patchers:
            p.stop()

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Property 2: 策略函数返回类型约束
# ═══════════════════════════════════════════════════════════════════════════════


@given(strategy_module=st.sampled_from(_STRATEGY_MODULES))
@settings(max_examples=100)
def test_p2_strategy_render_returns_dict_or_none(strategy_module: str):
    """Property 2: 策略函数返回类型约束

    对 7 个策略的 render(ctx)，使用 mock RenderContext（db 返回空数据），
    验证返回 dict | None。

    Validates: Requirements 3.3, 3.4
    """
    ctx = _make_ctx(
        sheet_html_data=None,
        sheet_schema=None,
        template_file_path="/fake/template.xlsx",
    )

    result = _run_render_with_patches(strategy_module, ctx)

    assert result is None or isinstance(result, dict), (
        f"策略 {strategy_module} 返回了非法类型: {type(result)}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Property 3: 策略函数优雅降级
# ═══════════════════════════════════════════════════════════════════════════════


@given(strategy_module=st.sampled_from(_STRATEGY_MODULES))
@settings(max_examples=100)
def test_p3_strategy_render_graceful_degradation(strategy_module: str):
    """Property 3: 策略函数优雅降级

    对 7 个策略的 render(ctx)，RenderContext 中
    sheet_html_data=None, sheet_schema=None, template_file_path=None，
    验证不抛异常，返回 dict | None。

    Validates: Requirements 3.4
    """
    ctx = _make_ctx(
        sheet_html_data=None,
        sheet_schema=None,
        template_file_path=None,
    )

    result = _run_render_with_patches(strategy_module, ctx)

    assert result is None or isinstance(result, dict), (
        f"策略 {strategy_module} 降级路径返回了非法类型: {type(result)}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Property 4: Override 映射值合法性
# ═══════════════════════════════════════════════════════════════════════════════

# 在模块级加载 override keys 避免 hypothesis 内部重复加载
from app.services.wp_classification_service import (  # noqa: E402
    VALID_COMPONENT_TYPES as _VALID_COMPONENT_TYPES,
    _WP_CODE_OVERRIDE as _OVERRIDE_MAP,
)

_OVERRIDE_KEYS = list(_OVERRIDE_MAP.keys())


@given(wp_code=st.sampled_from(_OVERRIDE_KEYS))
@settings(max_examples=100)
def test_p4_override_values_in_valid_component_types(wp_code: str):
    """Property 4: Override 映射值合法性

    用 st.sampled_from(list(_WP_CODE_OVERRIDE.keys())) 遍历验证
    每个 value ∈ VALID_COMPONENT_TYPES。

    Validates: Requirements 4.1, 6.2
    """
    component_type = _OVERRIDE_MAP[wp_code]
    assert component_type in _VALID_COMPONENT_TYPES, (
        f"wp_code={wp_code!r} 映射到 {component_type!r}，"
        f"不在 VALID_COMPONENT_TYPES 中"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Property 5: Override JSON 热重载正确性（简化版）
# ═══════════════════════════════════════════════════════════════════════════════


@given(data=st.data())
@settings(max_examples=100)
def test_p5_override_loader_returns_valid_dict(data):
    """Property 5: Override JSON 热重载正确性（简化版）

    验证 load_wp_code_overrides() 返回的 dict 非空且所有 value 都是 str。

    Validates: Requirements 6.4
    """
    from app.services.wp_code_override_loader import load_wp_code_overrides

    result = load_wp_code_overrides()

    assert isinstance(result, dict), "load_wp_code_overrides() 应返回 dict"
    assert len(result) > 0, "load_wp_code_overrides() 不应返回空 dict"

    # 随机采样一个 key 验证类型
    sampled_key = data.draw(st.sampled_from(list(result.keys())))
    assert isinstance(sampled_key, str), f"key {sampled_key!r} 不是 str"
    assert isinstance(result[sampled_key], str), (
        f"value（key={sampled_key!r}）不是 str: {result[sampled_key]!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Property 6: 所有 Resolver 均有 docstring
# ═══════════════════════════════════════════════════════════════════════════════

from app.services.auto_data_resolvers import (  # noqa: E402
    _REGISTRY as _RESOLVER_REGISTRY,
    get_registered_sources as _get_registered_sources,
)

_RESOLVER_NAMES = _get_registered_sources()


@given(resolver_name=st.sampled_from(_RESOLVER_NAMES))
@settings(max_examples=100)
def test_p6_all_resolvers_have_docstring(resolver_name: str):
    """Property 6: 所有 Resolver 均有 docstring

    用 st.sampled_from(get_registered_sources()) 验证
    _REGISTRY[name].__doc__ 非空。

    Validates: Requirements 7.1, 7.4
    """
    fn = _RESOLVER_REGISTRY[resolver_name]
    assert fn.__doc__ and fn.__doc__.strip(), (
        f"resolver {resolver_name!r} 缺少 docstring"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Property 7: Router 注册完整性
# ═══════════════════════════════════════════════════════════════════════════════


def _discover_router_modules() -> list[str]:
    """扫描 app/routers/ 下所有含 router = APIRouter( 的非私有模块。"""
    from app.router_registry import _ROUTER_PATTERN

    routers_pkg = importlib.import_module("app.routers")
    discovered: list[str] = []

    for module_info in pkgutil.walk_packages(
        routers_pkg.__path__, prefix="app.routers."
    ):
        if module_info.ispkg:
            continue
        module_name = module_info.name
        parts = module_name.split(".")
        leaf = parts[-1]
        if leaf.startswith("_") and leaf != "__init__":
            continue
        try:
            mod = importlib.import_module(module_name)
            source_file = inspect.getfile(mod)
            with open(source_file, "r", encoding="utf-8") as f:
                source = f.read()
            if _ROUTER_PATTERN.search(source):
                discovered.append(module_name)
        except Exception:
            continue

    return discovered


# 模块级发现 + 注册信息缓存（避免每次 hypothesis 迭代重新扫描和创建 app）
_discovered_router_modules = _discover_router_modules()


def _get_registered_modules() -> set[str]:
    """创建 FastAPI app 并注册所有路由，返回已注册模块集合。"""
    from fastapi import FastAPI

    from app.router_registry import register_all_routers

    app = FastAPI()
    register_all_routers(app)

    registered: set[str] = set()
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is not None:
            registered.add(endpoint.__module__)
    return registered


# 模块级缓存已注册模块集合
_registered_modules = _get_registered_modules()


@given(module_name=st.sampled_from(_discovered_router_modules))
@settings(max_examples=100)
def test_p7_router_registration_completeness(module_name: str):
    """Property 7: Router 注册完整性

    用 st.sampled_from(discovered_router_modules) 验证每个 module 已注册。

    Validates: Requirements 8.1, 8.2, 8.4, 8.5
    """
    from app.router_registry import _EXCLUDED_ROUTERS

    # 跳过排除列表中的模块
    if module_name in _EXCLUDED_ROUTERS:
        return

    assert module_name in _registered_modules, (
        f"模块 {module_name!r} 含 router = APIRouter 定义，"
        f"但未在 register_all_routers 中注册"
    )
