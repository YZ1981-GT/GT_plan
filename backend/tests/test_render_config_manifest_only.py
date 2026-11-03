"""render-config 只算清册（spec platform-perf-hotspots R3）。

guidance 调 ``_get_render_config_impl(..., manifest_only=True)``：不跑渲染器、不加载 schema、
不查 cross_ref / 项目年度 / 模板类型，循环后不做取数 / 签字 / 准则 / 静态指引；
页签清册（顺序 + 身份字段 + componentType）与完整渲染逐项相同。
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.routers.wp_render_strategies as strategies
import app.services.wp_classification_service as wcs
from app.routers import wp_render_config as rc
from app.services.wp_classification_service import ClassificationResult

WP_CODE = "ZZ9"
COMPONENT = "zz9-probe-renderer"
IDENTITY_KEYS = ("sheet_name", "sheet_code", "sheet_code_reason", "whole_workbook", "componentType")


def _cls(name: str, class_code: str) -> ClassificationResult:
    return ClassificationResult(
        wp_code=WP_CODE, sheet_name=name, class_code=class_code, class_="探针",
        scope="standalone", is_real_workpaper=True, delegated_module=None,
        render_schema_path=None, template_version_id=None,
    )


def _result(*, first=None, scalar=None) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.first.return_value = first
    result.scalars.return_value.all.return_value = []
    result.scalar.return_value = scalar
    result.first.return_value = None
    result.scalar_one_or_none.return_value = None
    return result


def _db(working_paper, wp_index) -> AsyncMock:
    fixed = [_result(first=working_paper), _result(scalar=False), _result(first=wp_index)]

    async def _execute(*_args, **_kwargs):
        return fixed.pop(0) if fixed else _result()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_execute)
    return db


@pytest.fixture()
def harness(monkeypatch: pytest.MonkeyPatch):
    calls = {"render": 0, "schema": 0}

    async def renderer(ctx):
        calls["render"] += 1
        return {"sheet_name": ctx.classification.sheet_name, "rows": [1]}

    def load_schema(**_kwargs):
        calls["schema"] += 1
        raise FileNotFoundError

    classifications = [
        _cls("审定表ZZ9-1", "Z-审定表"),       # 未知 class_code ⇒ 回落 wp_code override ⇒ 探针渲染器
        _cls("明细表ZZ9-2", "Z-明细表"),
        _cls("说明页ZZ9-3", "H-说明"),          # h-static-doc：无渲染器 ⇒ 只看渲染器是否存在的改写
        _cls("占位页ZZ9-4", "I-占位"),          # skip 也没有渲染器 ⇒ 多页册里同样被改写成 onlyoffice-sheet
    ]
    monkeypatch.setattr(wcs, "refresh_wp_code_overrides", lambda: None)
    monkeypatch.setitem(wcs._WP_CODE_OVERRIDE, WP_CODE, COMPONENT)
    monkeypatch.setattr(strategies, "RENDERER_DISPATCH", {COMPONENT: renderer})
    monkeypatch.setattr(rc, "WpTemplateVersionService", lambda _db: SimpleNamespace(
        get_current_version=AsyncMock(return_value=SimpleNamespace(version="v-probe", id=None))))
    monkeypatch.setattr(rc, "WpClassificationService", lambda _db: SimpleNamespace(
        get_classification=AsyncMock(return_value=list(classifications))))
    monkeypatch.setattr(rc, "_maybe_custom_classifications",
                        AsyncMock(side_effect=lambda _db, _pid, _code, _name, classes, _wp: classes))
    monkeypatch.setattr(rc, "resolve_package_sheets", AsyncMock(return_value=None))
    monkeypatch.setattr(rc, "_resolve_template_path", lambda _wp, _code: None)
    monkeypatch.setattr(rc._schema_service, "load_schema", load_schema)
    monkeypatch.setattr(rc, "_resolve_auto_fill_values", AsyncMock(return_value={}))

    working_paper = SimpleNamespace(
        id=uuid.uuid4(), project_id=uuid.uuid4(), wp_index_id=uuid.uuid4(),
        parsed_data={"html_data": {}}, file_path=None,
    )
    wp_index = SimpleNamespace(wp_code=WP_CODE, wp_name="探针底稿", audit_cycle="Z")
    return SimpleNamespace(calls=calls, working_paper=working_paper, wp_index=wp_index,
                           user=SimpleNamespace(id=uuid.uuid4()))


def _identity(response: dict) -> list[tuple]:
    return [tuple(sheet.get(key) for key in IDENTITY_KEYS) for sheet in response["sheets"]]


async def _run(harness, *, manifest_only: bool):
    harness.calls.update(render=0, schema=0)
    db = _db(harness.working_paper, harness.wp_index)
    kwargs = {"manifest_only": True} if manifest_only else {}
    response = await rc._get_render_config_impl(uuid.uuid4(), None, db, harness.user, **kwargs)
    return response, dict(harness.calls), db.execute.await_count


def _expected_component_types() -> list[str]:
    no_renderer = lambda ct: ct if ct in rc._ONLYOFFICE_HTML_WHITELIST else "onlyoffice-sheet"  # noqa: E731
    return [COMPONENT, COMPONENT, no_renderer("h-static-doc"), no_renderer("skip")]


async def test_full_render_runs_renderers_so_the_comparison_is_not_vacuous(harness) -> None:
    full, calls, executes = await _run(harness, manifest_only=False)
    assert calls == {"render": 2, "schema": 4}
    assert executes > 3
    assert [s["componentType"] for s in full["sheets"]] == _expected_component_types()
    assert full["sheets"][0]["html_data"] == {"sheet_name": "审定表ZZ9-1", "rows": [1]}


async def test_manifest_only_matches_full_manifest_without_renderers_or_queries(harness) -> None:
    full, _, _ = await _run(harness, manifest_only=False)
    manifest, calls, executes = await _run(harness, manifest_only=True)

    assert _identity(manifest) == _identity(full)
    # 「无渲染器且不在白名单 ⇒ onlyoffice-sheet」只看渲染器是否存在，清册模式照样生效
    assert [s["componentType"] for s in manifest["sheets"]] == _expected_component_types()
    assert manifest["template_version"] == full["template_version"] == "v-probe"
    assert calls == {"render": 0, "schema": 0}
    # 只剩底稿 / 项目删除标记 / 底稿索引三条（cross_ref、年度、模板类型、取数年度都不查）
    assert executes == 3
    assert set(manifest) == {"wp_id", "wp_code", "project_id", "scope", "template_version",
                             "sheets", "is_real_workpaper"}
