#!/usr/bin/env python
"""从真实数据库采集脱敏的 render-config wire golden（只读）。

采集器直接调用生产 ``_get_render_config_impl``，覆盖 HTML、OnlyOffice、函证、
程序表、redirect 与 multi-sheet 代表底稿。输出只包含字段路径、类型/nullability、
componentType、sheet 数和结构摘要；不保存客户正文、schema/html_data 值、用户信息或凭据。

用法::

    python backend/scripts/diagnose/capture_render_config_wire_golden.py --apply
    python backend/scripts/diagnose/capture_render_config_wire_golden.py --check
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.database import async_session  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.workpaper_models import WorkingPaper, WpIndex  # noqa: E402
from app.routers.wp_render_config import _get_render_config_impl  # noqa: E402
from app.schemas.render_config_contract import RenderConfigResponse  # noqa: E402

OUTPUT_PATH = (
    ROOT
    / "backend"
    / "tests"
    / "fixtures"
    / "platform_architecture"
    / "render_config_wire_golden.json"
)
SAMPLE_CODES = ("D2", "D2-6", "D0", "B15", "B50-1", "A14-4")
REQUIRED_COVERAGE = frozenset(
    {"html", "onlyoffice", "confirmation", "program", "redirect", "multi_sheet"}
)


def _runtime_type(value: Any) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) is int:
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return type(value).__name__


def _shape(value: Any) -> Any:
    """把全部标量替换为类型标签，只保留 JSON 结构。"""
    if isinstance(value, dict):
        return {key: _shape(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        unique: dict[str, Any] = {}
        for item in value:
            item_shape = _shape(item)
            canonical = json.dumps(item_shape, ensure_ascii=False, sort_keys=True)
            unique.setdefault(canonical, item_shape)
        return {"$array_items": [unique[key] for key in sorted(unique)]}
    return {"$type": _runtime_type(value)}


def _collect_paths(value: Any, path: str, observed: dict[str, set[str]]) -> None:
    observed[path].add(_runtime_type(value))
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            _collect_paths(child, child_path, observed)
    elif isinstance(value, list):
        for child in value:
            _collect_paths(child, f"{path}[]", observed)


def _categories(payload: dict[str, Any]) -> set[str]:
    sheets = payload.get("sheets") if isinstance(payload.get("sheets"), list) else []
    component_types = {
        str(sheet.get("componentType"))
        for sheet in sheets
        if isinstance(sheet, dict) and sheet.get("componentType")
    }
    categories: set[str] = set()
    if payload.get("redirect") is True:
        categories.add("redirect")
    if len(sheets) > 1:
        categories.add("multi_sheet")
    if "onlyoffice-sheet" in component_types or "onlyoffice" in component_types:
        categories.add("onlyoffice")
    if any(value.startswith("confirmation-") for value in component_types):
        categories.add("confirmation")
    if component_types & {"a-program-console", "procedure-table"}:
        categories.add("program")
    if any(
        value not in {"onlyoffice", "onlyoffice-sheet", "univer", "skip"}
        for value in component_types
    ):
        categories.add("html")
    return categories


async def _sample_payload(wp_code: str, user_id: Any) -> dict[str, Any]:
    async with async_session() as db:
        wp_id = (
            await db.execute(
                sa.select(WorkingPaper.id)
                .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
                .join(Project, Project.id == WorkingPaper.project_id)
                .where(
                    WpIndex.wp_code == wp_code,
                    WpIndex.is_deleted.is_(False),
                    WorkingPaper.is_deleted.is_(False),
                    Project.is_deleted.is_(False),
                )
                .order_by(WorkingPaper.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if wp_id is None:
            raise RuntimeError(f"真实库缺少代表底稿 wp_code={wp_code}")
        try:
            return await _get_render_config_impl(
                wp_id,
                None,
                db,
                SimpleNamespace(id=user_id),
            )
        finally:
            await db.rollback()


async def _find_live_onlyoffice_sample(
    user_id: Any,
    excluded_codes: set[str],
) -> tuple[str, dict[str, Any]] | None:
    """先按生产裁决条件缩小范围，再真跑候选，禁止构造 OnlyOffice fixture。"""
    from app.routers.wp_render_config import (
        _SHEET_CODE_RE,
        _WHOLE_WP_MULTISHEET_DEDICATED,
    )
    from app.services.account_package_registry_service import AccountPackageRegistryService
    from app.services.wp_classification_service import (
        _WP_CODE_OVERRIDE,
        refresh_wp_code_overrides,
    )

    refresh_wp_code_overrides()
    package_codes = {
        str(package.get("primary_wp_code"))
        for package in AccountPackageRegistryService().get_packages()
        if package.get("primary_wp_code")
    }
    async with async_session() as db:
        rows = (
            await db.execute(
                sa.text(
                    """
                    SELECT DISTINCT c.wp_code, c.sheet_name
                    FROM workpaper_sheet_classification c
                    WHERE c.class_code LIKE 'G-%'
                      AND EXISTS (
                        SELECT 1
                        FROM wp_index wi
                        JOIN working_paper wp ON wp.wp_index_id = wi.id
                        JOIN projects p ON p.id = wp.project_id
                        WHERE wi.wp_code = c.wp_code
                          AND wi.is_deleted = false
                          AND wp.is_deleted = false
                          AND p.is_deleted = false
                      )
                      AND (
                        SELECT COUNT(DISTINCT c2.sheet_name)
                        FROM workpaper_sheet_classification c2
                        WHERE c2.wp_code = c.wp_code
                      ) > 1
                    ORDER BY c.wp_code, c.sheet_name
                    """
                )
            )
        ).all()

    by_code: dict[str, list[str]] = defaultdict(list)
    for wp_code, sheet_name in rows:
        by_code[str(wp_code)].append(str(sheet_name))

    candidates: list[str] = []
    for wp_code, sheet_names in sorted(by_code.items()):
        if wp_code in excluded_codes or wp_code in package_codes:
            continue
        wp_override = _WP_CODE_OVERRIDE.get(wp_code)
        if wp_override in _WHOLE_WP_MULTISHEET_DEDICATED:
            continue
        has_unmapped_grid = False
        for sheet_name in sheet_names:
            match = _SHEET_CODE_RE.search(sheet_name)
            sheet_override = (
                (_WP_CODE_OVERRIDE.get(match.group(1)) if match else None)
                or _WP_CODE_OVERRIDE.get(sheet_name)
                or _WP_CODE_OVERRIDE.get(f"{wp_code}-{sheet_name}")
            )
            if not sheet_override:
                has_unmapped_grid = True
                break
        if has_unmapped_grid:
            candidates.append(wp_code)

    for wp_code in candidates:
        payload = await _sample_payload(wp_code, user_id)
        if "onlyoffice" in _categories(payload):
            return wp_code, payload
    return None


async def capture() -> dict[str, Any]:
    async with async_session() as db:
        user_id = (
            await db.execute(
                sa.select(User.id)
                .where(User.is_active.is_(True), User.is_deleted.is_(False))
                .order_by(User.id)
                .limit(1)
            )
        ).scalar_one_or_none()
    if user_id is None:
        raise RuntimeError("真实库没有可用于只读渲染的 active user")

    payloads = [(wp_code, await _sample_payload(wp_code, user_id)) for wp_code in SAMPLE_CODES]
    initial_coverage = set().union(*(_categories(payload) for _, payload in payloads))
    if "onlyoffice" not in initial_coverage:
        live_onlyoffice = await _find_live_onlyoffice_sample(
            user_id,
            {wp_code for wp_code, _ in payloads},
        )
        if live_onlyoffice is not None:
            payloads.append(live_onlyoffice)

    observed: dict[str, set[str]] = defaultdict(set)
    samples: list[dict[str, Any]] = []
    coverage: set[str] = set()
    for wp_code, payload in payloads:
        wire_payload = RenderConfigResponse.model_validate(payload).model_dump(
            by_alias=True,
            exclude_unset=True,
            mode="json",
        )
        if wire_payload != payload:
            removed = sorted(set(payload) - set(wire_payload))
            added = sorted(set(wire_payload) - set(payload))
            raise RuntimeError(
                "RenderConfigResponse round-trip 改变真实 payload: "
                f"wp_code={wp_code}, removed={removed}, added={added}"
            )
        _collect_paths(payload, "", observed)
        categories = _categories(payload)
        coverage.update(categories)
        sheets = payload.get("sheets") if isinstance(payload.get("sheets"), list) else []
        component_types = sorted(
            {
                str(sheet.get("componentType"))
                for sheet in sheets
                if isinstance(sheet, dict) and sheet.get("componentType")
            }
        )
        shape_bytes = json.dumps(
            _shape(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        samples.append(
            {
                "wp_code": wp_code,
                "categories": sorted(categories),
                "component_types": component_types,
                "sheet_count": len(sheets),
                "shape_sha256": hashlib.sha256(shape_bytes).hexdigest(),
                "top_level_fields": sorted(payload),
                "sheet_fields": sorted(
                    {
                        key
                        for sheet in sheets
                        if isinstance(sheet, dict)
                        for key in sheet
                    }
                ),
            }
        )

    missing = sorted(REQUIRED_COVERAGE - coverage)

    return {
        "schema_version": 1,
        "source": "live_database_production_render_path",
        "captured_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "sample_codes": [sample["wp_code"] for sample in samples],
        "coverage": sorted(coverage),
        "required_coverage": sorted(REQUIRED_COVERAGE),
        "coverage_complete": not missing,
        "missing_coverage": missing,
        "field_contract": {
            path or "$": {
                "types": sorted(types),
                "nullable": "null" in types,
            }
            for path, types in sorted(observed.items())
        },
        "samples": samples,
    }


def _stable_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.pop("captured_at_utc", None)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    captured = asyncio.run(capture())
    if args.apply:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(captured, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        status = "OK" if captured["coverage_complete"] else "PARTIAL"
        print(
            f"[{status}] captured {len(captured['samples'])} live render-config samples "
            f"with coverage={captured['coverage']}; "
            f"missing_coverage={captured['missing_coverage']}"
        )
        return 0

    try:
        expected = json.loads(args.output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[FAIL] cannot read golden: {exc}", file=sys.stderr)
        return 2
    if _stable_payload(expected) != _stable_payload(captured):
        print("[FAIL] live render-config shape drift", file=sys.stderr)
        return 1
    if not captured["coverage_complete"]:
        print(
            f"[PARTIAL] live render-config shape matches golden "
            f"({len(captured['samples'])} samples); "
            f"missing_coverage={captured['missing_coverage']}"
        )
        return 0
    print(
        f"[OK] live render-config shape matches golden "
        f"({len(captured['samples'])} samples)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
