"""报表定义行的两个数据源（spec formula-hub-integrity-closure 任务 18 第一段 B；需求 6.1、6.3）。

``test_report_seed_attribution_rows`` / ``test_report_total_row_range_guard`` / ``test_report_row_ref_order_guard`` 共用：

- :func:`seed_definitions`：种子 ``backend/data/report_config_seed.json`` → ``{准则: [DefRow]}``（与
  ``ReportConfigService.load_seed_data`` 一样按 utf-8-sig 读）；
- :func:`db_definitions`：库内未删 ``report_config`` 行 → ``{准则: [DefRow]}``；``project:{项目}`` 行按 :func:`overlay` 叠加到
  该项目的准则行上（同表同行次覆盖公式、结构取准则行；独有行追加），键仍是 ``project:{项目}``。快照库现有 ``project:`` 行 0。
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from tests.formula_hub._pg_harness import SNAPSHOT_PREFIX, pg_required

SEED = Path(__file__).resolve().parents[2] / "data" / "report_config_seed.json"
PROJECT_PREFIX = "project:"


async def require_snapshot(db: Any, purpose: str) -> None:
    """只连快照库（库名 ``fh_snap_`` 开头）：别的库 —— ``GT_REQUIRE_PG=1`` 时失败，否则跳过。"""
    name = (await db.execute(text("SELECT current_database()"))).scalar_one()
    if not name.startswith(SNAPSHOT_PREFIX):
        reason = f"{purpose}只连快照库（{SNAPSHOT_PREFIX}*），当前库 {name}"
        if pg_required():
            pytest.fail(reason, pytrace=False)
        pytest.skip(reason)


@dataclass(frozen=True)
class DefRow:
    report_type: str
    row_code: str
    row_number: int
    row_name: str
    is_total_row: bool
    formula: str | None


def seed_blocks(path: Path = SEED) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def seed_definitions(path: Path = SEED) -> dict[str, list[DefRow]]:
    out: dict[str, list[DefRow]] = {}
    for block in seed_blocks(path):
        rows = out.setdefault(block["applicable_standard"], [])
        rows.extend(DefRow(block["report_type"], r["row_code"], int(r["row_number"]), r.get("row_name") or "",
                           r.get("is_total_row") is True, r.get("formula")) for r in block["rows"])
    return out


def overlay(base: list[DefRow], own: list[DefRow]) -> list[DefRow]:
    """准则行 ⊕ 本项目行：同表同行次只换公式（结构取准则行），本项目独有的行追加。"""
    own_by_key = {(r.report_type, r.row_code): r for r in own}
    merged = [replace(r, formula=own_by_key[(r.report_type, r.row_code)].formula)
              if (r.report_type, r.row_code) in own_by_key else r for r in base]
    base_keys = {(r.report_type, r.row_code) for r in base}
    return [*merged, *(r for r in own if (r.report_type, r.row_code) not in base_keys)]


async def db_definitions(db: Any) -> dict[str, list[DefRow]]:
    from app.services.report_config_service import ReportConfigService

    raw = (await db.execute(text(
        "SELECT applicable_standard, report_type::text, row_code, row_number, row_name, is_total_row, formula "
        "FROM report_config WHERE is_deleted = false"))).all()
    base: dict[str, list[DefRow]] = {}
    own: dict[str, list[DefRow]] = {}
    for std, rt, code, number, name, total, formula in raw:
        target = own if (std or "").startswith(PROJECT_PREFIX) else base
        target.setdefault(std, []).append(DefRow(rt, code, int(number or 0), name or "", total is True, formula))
    out = dict(base)
    for std, rows in own.items():
        standard = await ReportConfigService.resolve_applicable_standard(db, uuid.UUID(std[len(PROJECT_PREFIX):]))
        out[std] = overlay(base.get(standard, []), rows)
    return out
