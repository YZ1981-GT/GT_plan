"""render-config 响应外壳、路由绑定与真实 golden 契约。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from pydantic import ValidationError

from app.routers.wp_render_config import router
from app.schemas.render_config_contract import (
    RenderConfigResponse,
    SheetRenderConfig,
)
from scripts.check.check_render_config_wire_contract import (
    DEFAULT_FRONTEND_PATH,
    backend_contract,
    check_contract,
    frontend_contract,
)

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = (
    ROOT
    / "backend"
    / "tests"
    / "fixtures"
    / "platform_architecture"
    / "render_config_wire_golden.json"
)
UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
#: 只在 ``share_html_data=1`` 时出现的字段（golden 抓的是不带参数的生产路径，不会出现）。
#: spec platform-perf-hotspots R1
PARAM_GATED_ROOT_FIELDS = frozenset({"shared_html_data"})
PARAM_GATED_SHEET_FIELDS = frozenset({"html_data_ref"})


def _dump(payload: dict) -> dict:
    return RenderConfigResponse.model_validate(payload).model_dump(
        by_alias=True,
        exclude_unset=True,
        mode="json",
    )


def _base_payload() -> dict:
    return {
        "wp_id": "wp-id",
        "wp_code": "D2",
        "project_id": "project-id",
        "scope": "standalone",
        "is_real_workpaper": True,
        "template_version": None,
        "sheets": [],
    }


def test_render_config_route_binds_strict_response_model() -> None:
    route = next(
        item
        for item in router.routes
        if isinstance(item, APIRoute) and item.path.endswith("/{wp_id}/render-config")
    )

    assert route.response_model is RenderConfigResponse
    assert route.response_model_exclude_unset is True


@pytest.mark.parametrize(
    "branch_payload",
    [
        {
            "audit_year": 2026,
            "applicable_standards": ["CAS"],
            "fill_results": {},
            "guidance": None,
            "sheets": [
                {
                    "sheet_name": "审定表",
                    "sheet_code": "D2-1",
                    "sheet_code_reason": "explicit_code",
                    "whole_workbook": False,
                    "componentType": "audit-sheet",
                    "schema": None,
                    "html_data": None,
                    "cross_refs": [{"wp_code": "B50", "cell": None}],
                    "sheet_type": None,
                    "field_sources": None,
                }
            ],
        },
        {
            "is_real_workpaper": False,
            "redirect": True,
            "delegated_module": "materiality",
            "target_path": "/materiality",
        },
        {
            "audit_year": 2026,
            "applicable_standards": [],
            "fill_results": {},
            "guidance": {"schema_version": 1},
            "sign_status": "draft",
            "permissions": {"edit": True},
            "sheets": [
                {
                    "sheet_name": "报告",
                    "sheet_code": None,
                    "sheet_code_reason": "whole_workbook",
                    "whole_workbook": True,
                    "componentType": "word-template",
                    "schema": None,
                    "html_data": {},
                    "cross_refs": [],
                }
            ],
        },
        {
            "audit_year": 2026,
            "applicable_standards": [],
            "fill_results": {},
            "guidance": None,
            "shared_html_data": {"h1": {"project_context": {"year": 2026}, "rows": []}},
            "sheets": [
                {
                    "sheet_name": name,
                    "componentType": "d2-accounts-receivable",
                    "schema": None,
                    "html_data": {"sheet_name": name},
                    "html_data_ref": "h1",
                    "cross_refs": [],
                }
                for name in ("审定表D2-1", "明细表D2-2")
            ],
        },
    ],
    ids=["normal-nullability", "redirect", "word-template", "shared-html-data"],
)
def test_render_config_branches_round_trip_without_field_loss(
    branch_payload: dict,
) -> None:
    payload = {**_base_payload(), **branch_payload}

    assert _dump(payload) == payload


def test_response_shell_rejects_unknown_root_and_sheet_fields() -> None:
    with pytest.raises(ValidationError, match="unexpected_root"):
        RenderConfigResponse.model_validate(
            {**_base_payload(), "unexpected_root": "must-fail"}
        )

    with pytest.raises(ValidationError, match="unexpected_sheet"):
        SheetRenderConfig.model_validate(
            {
                "sheet_name": "审定表",
                "componentType": "audit-sheet",
                "unexpected_sheet": "must-fail",
            }
        )


def test_live_golden_outer_fields_equal_model_plus_declared_reserved_fields() -> None:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    root_runtime_fields = {
        field
        for sample in golden["samples"]
        for field in sample["top_level_fields"]
    }
    sheet_runtime_fields = {
        field for sample in golden["samples"] for field in sample["sheet_fields"]
    }
    root_model_fields = {
        field.serialization_alias or field.alias or name
        for name, field in RenderConfigResponse.model_fields.items()
    }
    sheet_model_fields = {
        field.serialization_alias or field.alias or name
        for name, field in SheetRenderConfig.model_fields.items()
    }

    # word-template 分支字段：真实样本未命中，但模型与前端生命周期清单必须同时登记。
    # （not_applicable 自 golden 于 33b3b67fd 重抓后已在真实样本中出现，且已由 GtWpRenderer
    #   消费为顶层适用性覆盖层，前端登记为 active，不是 reserved。）
    model_only = root_model_fields - root_runtime_fields
    assert PARAM_GATED_ROOT_FIELDS <= model_only, "按参数出现的字段不得出现在不带参数的 golden 里"
    assert model_only - PARAM_GATED_ROOT_FIELDS == {
        "permissions",
        "sign_status",
        "business_category",
        "applicable_when",
    }
    frontend_src = DEFAULT_FRONTEND_PATH.read_text(encoding="utf-8")
    for field in sorted((model_only - PARAM_GATED_ROOT_FIELDS) | {"guidance", "scope"}):
        assert f"  {field}: 'reserved'" in frontend_src, (
            f"模型/运行时未消费字段 {field} 必须在 RENDER_CONFIG_FIELD_STATUS 登记为 reserved"
        )
    for field in sorted(PARAM_GATED_ROOT_FIELDS | {"decision_trace", "not_applicable"}):
        assert f"  {field}: 'active'" in frontend_src, (
            f"{field} 已有前端消费方（decision_trace → WpDecisionTracePanel，"
            f"not_applicable → GtWpRenderer，shared_html_data → expandSharedHtmlData），必须登记为 active"
        )
    assert root_runtime_fields - root_model_fields == set()
    assert not (PARAM_GATED_SHEET_FIELDS & sheet_runtime_fields)
    assert sheet_model_fields - PARAM_GATED_SHEET_FIELDS == sheet_runtime_fields


def test_known_nullability_quartet_is_aligned_bidirectionally() -> None:
    """schema / html_data / template_version / cross_refs.cell 前后端可空性必须一致。"""
    keys = {
        "SheetRenderConfigWire.schema",
        "SheetRenderConfigWire.html_data",
        "RenderConfigWire.template_version",
        "CrossRefWire.cell",
    }
    backend = {key: shape for key, shape in backend_contract().items() if key in keys}
    frontend = {key: shape for key, shape in frontend_contract().items() if key in keys}
    assert set(backend) == keys
    for key, shape in backend.items():
        assert shape.nullable is True, key
        assert frontend[key] == shape, key


def test_live_golden_is_redacted_and_has_complete_required_coverage() -> None:
    raw = GOLDEN_PATH.read_text(encoding="utf-8")
    golden = json.loads(raw)

    assert golden["source"] == "live_database_production_render_path"
    assert UUID_RE.search(raw) is None
    assert golden["coverage_complete"] is True
    assert golden["missing_coverage"] == []
    assert set(golden["coverage"]) == set(golden["required_coverage"])


def test_backend_and_frontend_wire_contract_have_zero_bidirectional_diff() -> None:
    diff = check_contract()

    assert diff.ok, diff.describe()
    assert diff.missing_in_frontend == ()
    assert diff.missing_in_backend == ()
    assert diff.mismatched == ()


@pytest.mark.parametrize(
    ("old", "new", "expected_bucket", "expected_path"),
    [
        (
            "  cell: string | null\n",
            "  cell: string\n",
            "mismatched",
            "CrossRefWire.cell",
        ),
        (
            "  guidance?: Record<string, any> | null\n",
            "",
            "missing_in_frontend",
            "RenderConfigWire.guidance",
        ),
        (
            "  decision_trace?: RenderDecisionWire[]\n",
            "  decision_trace?: RenderDecisionWire[]\n  rogue?: string\n",
            "missing_in_backend",
            "RenderConfigWire.rogue",
        ),
    ],
    ids=["remove-null", "remove-field", "add-field"],
)
def test_bidirectional_checker_mutations_turn_red(
    tmp_path: Path,
    old: str,
    new: str,
    expected_bucket: str,
    expected_path: str,
) -> None:
    source = DEFAULT_FRONTEND_PATH.read_text(encoding="utf-8")
    assert source.count(old) == 1
    mutated_path = tmp_path / "renderConfig.ts"
    mutated_path.write_text(source.replace(old, new, 1), encoding="utf-8")

    diff = check_contract(mutated_path)

    assert diff.ok is False
    assert any(expected_path in item for item in getattr(diff, expected_bucket))
