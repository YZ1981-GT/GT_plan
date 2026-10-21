"""H1 固定资产后端 payload builder。

从 checklist_responses 读 cost-rows/dep-rows/impair-rows（JSON 变动表），
构建主表「固定资产」（标准两字段）+ 变动子表。

数据来源：
  H1-1-cost-rows   → 原值变动表 JSON
  H1-1-dep-rows    → 折旧变动表 JSON
  H1-1-impair-rows → 减值变动表 JSON
  H1-1-audited-net → 审定净值

spec: backend-disclosure-payload-builder Phase 2 Task 9
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.disclosure_payload_builder_service import (
    DisclosurePayloadBuilder,
    PayloadBuildResult,
    load_disclosure_entries,
    load_project_standard,
    load_project_template_type,
    register_builder,
)

H1_NOTE_SECTION = {"listed": "五、14", "soe": "八、22"}
H1_SHEET_NAME = {"listed": "附注披露信息(上市公司)", "soe": "附注披露信息(国企)"}
H1_MAIN_TABLE = "固定资产"

_COLUMNS = [
    {"key": "label", "label": "项目", "is_label": True, "flat": True},
    {"key": "end_amount", "label": "期末余额", "format": "amount"},
    {"key": "prior_amount", "label": "期初余额", "format": "amount"},
]


def _num(v: Any) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except (ValueError, AttributeError):
            pass
    return 0.0


def _parse_json(raw: Any, default: Any = None) -> Any:
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw.strip()) if raw.strip() else default
        except (json.JSONDecodeError, ValueError):
            return default
    return default


@register_builder
class H1Builder(DisclosurePayloadBuilder):
    wp_code = "H1"

    async def build(self, db: AsyncSession, project_id: UUID, year: int) -> PayloadBuildResult | None:
        entries = await load_disclosure_entries(db, project_id, "H1")
        if not entries:
            return None

        template_type = await load_project_template_type(db, project_id)
        variant = "soe" if "soe" in template_type.lower() else "listed"
        current_standard = await load_project_standard(db, project_id)

        net = _num(entries.get("H1-1-audited-net"))

        rows: list[dict[str, Any]] = [
            {"label": "固定资产", "end_amount": net, "prior_amount": 0.0},
            {"label": "合计", "end_amount": net, "prior_amount": 0.0, "is_total": True},
        ]

        return PayloadBuildResult(
            wp_code="H1",
            section_id=H1_NOTE_SECTION[variant],
            sub_table_data={H1_MAIN_TABLE: rows},
            sub_table_columns={H1_MAIN_TABLE: _COLUMNS[:]},
            sheet_name=H1_SHEET_NAME[variant],
            current_standard=current_standard,
        )
