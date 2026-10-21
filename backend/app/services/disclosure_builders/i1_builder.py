"""I1 无形资产后端 payload builder。

从 checklist_responses 读 5 个数值（I1-1-tb-cost/amort/impair + I1-1-audited-net/receivable），
构建主表「无形资产」（标准两字段 end_amount/prior_amount）。

spec: backend-disclosure-payload-builder Phase 2 Task 10
"""
from __future__ import annotations

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

I1_NOTE_SECTION = {"listed": "五、17", "soe": "八、27"}
I1_SHEET_NAME = {"listed": "附注披露信息(上市公司)", "soe": "附注披露信息(国企)"}
I1_MAIN_TABLE = "无形资产"

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


@register_builder
class I1Builder(DisclosurePayloadBuilder):
    wp_code = "I1"

    async def build(self, db: AsyncSession, project_id: UUID, year: int) -> PayloadBuildResult | None:
        entries = await load_disclosure_entries(db, project_id, "I1")
        if not entries:
            return None

        template_type = await load_project_template_type(db, project_id)
        variant = "soe" if "soe" in template_type.lower() else "listed"
        current_standard = await load_project_standard(db, project_id)

        net = _num(entries.get("I1-1-audited-net"))
        cost = _num(entries.get("I1-1-tb-cost"))
        amort = _num(entries.get("I1-1-tb-amort"))
        impair = _num(entries.get("I1-1-tb-impair"))

        # 主表：审定净值 = 期末，无期初数据（checklist_responses 不存 opening）
        rows: list[dict[str, Any]] = [
            {"label": "无形资产", "end_amount": net, "prior_amount": 0.0},
            {"label": "合计", "end_amount": net, "prior_amount": 0.0, "is_total": True},
        ]

        return PayloadBuildResult(
            wp_code="I1",
            section_id=I1_NOTE_SECTION[variant],
            sub_table_data={I1_MAIN_TABLE: rows},
            sub_table_columns={I1_MAIN_TABLE: _COLUMNS[:]},
            sheet_name=I1_SHEET_NAME[variant],
            current_standard=current_standard,
        )
