"""D3.2 S-checklist 四集合与跨语言 item identity parity 守卫。"""

from __future__ import annotations

import json
from pathlib import Path

from app.routers.wp_render_config import _ONLYOFFICE_HTML_WHITELIST
from app.routers.wp_render_strategies import RENDERER_DISPATCH
from app.routers.wp_render_strategies._s_checklist_sheets import S_CHECKLIST_ITEM_IDS
from app.services.wp_classification_service import VALID_COMPONENT_TYPES
from scripts.check.workpaper_component_manifest import parse_registry_component_types

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ITEM_MAP = (
    ROOT.parent
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "s-checklist"
    / "sChecklistItemIds.ts"
)
OVERRIDES_PATH = ROOT / "app" / "data" / "wp_code_overrides.json"

CANONICAL_S_CHECKLIST_TYPES = frozenset(
    {
        "s1-regulation-record",
        "s8-adjudication",
        "s9-adjudication",
        "s9-internal-control",
        "s9-legal-regulations",
        "s9-program-description",
        "s10-adjudication",
        "s10-internal-control",
        "s10-environmental-regulations",
        "s17-nonrecurring-detail",
        "s17-reconciliation",
        "s17-tax-impact",
    }
)


def _load_frontend_item_map() -> dict[str, str | None]:
    """读取简单 TS object，不执行前端代码，也不依赖具体引号风格。"""
    source = FRONTEND_ITEM_MAP.read_text(encoding="utf-8")
    marker = "export const sChecklistItemIds ="
    marker_start = source.index(marker)
    object_start = source.index("{", marker_start)
    object_end = source.index("} as const", object_start)
    payload: dict[str, str | None] = {}
    for raw_line in source[object_start + 1 : object_end].splitlines():
        line = raw_line.strip().rstrip(",")
        if not line:
            continue
        raw_key, separator, raw_value = line.partition(":")
        assert separator == ":", f"无法解析 item map 行: {raw_line!r}"
        key = raw_key.strip()
        assert len(key) >= 2 and key[0] == key[-1] and key[0] in {"'", '"'}
        value = raw_value.strip()
        if value == "null":
            parsed_value = None
        else:
            assert len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}
            parsed_value = value[1:-1]
        payload[key[1:-1]] = parsed_value
    return payload


def test_all_four_s_checklist_type_sets_are_exactly_the_canonical_twelve() -> None:
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    frontend_registry = set(parse_registry_component_types())
    observed = {
        "frontend registry": frontend_registry & CANONICAL_S_CHECKLIST_TYPES,
        "overrides": {
            value for value in overrides.values() if value in CANONICAL_S_CHECKLIST_TYPES
        },
        "backend valid": VALID_COMPONENT_TYPES & CANONICAL_S_CHECKLIST_TYPES,
        "backend whitelist": _ONLYOFFICE_HTML_WHITELIST & CANONICAL_S_CHECKLIST_TYPES,
        "RENDERER_DISPATCH": set(RENDERER_DISPATCH) & CANONICAL_S_CHECKLIST_TYPES,
    }

    for source, component_types in observed.items():
        assert component_types == CANONICAL_S_CHECKLIST_TYPES, (
            f"{source} 与 12-type canonical set 不一致: "
            f"missing={sorted(CANONICAL_S_CHECKLIST_TYPES - component_types)}, "
            f"unexpected={sorted(component_types - CANONICAL_S_CHECKLIST_TYPES)}"
        )

    # 不是分别“都包含 12 个”就算通过：四个后端来源和前端 registry
    # 的 S-checklist 投影必须逐值相等，防止某一来源漏换/错换后由交集掩盖。
    assert (
        observed["frontend registry"]
        == observed["overrides"]
        == observed["backend valid"]
        == observed["backend whitelist"]
        == observed["RENDERER_DISPATCH"]
    )


def test_backend_and_frontend_s_checklist_item_maps_match_exactly() -> None:
    frontend_item_map = _load_frontend_item_map()

    assert set(S_CHECKLIST_ITEM_IDS) == CANONICAL_S_CHECKLIST_TYPES
    assert set(frontend_item_map) == CANONICAL_S_CHECKLIST_TYPES
    assert frontend_item_map == S_CHECKLIST_ITEM_IDS
