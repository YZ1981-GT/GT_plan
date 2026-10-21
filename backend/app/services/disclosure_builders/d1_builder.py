"""D1 应收票据后端 payload builder。

D1 极简：主表行按票据种类（银行承兑/商业承兑），从 checklist_responses
只有 `D1-adj-tb-amount`（审定数）。主表行结构 6 字段（与 D1 主表规则一致）。

但 D1 的附注 sub_table_data 与 E1 不同——D1 的数据不是存在 checklist_responses
的独立 item_id 里，而是存在底稿的 parsed_data 中。checklist_responses 只有 1 条
`D1-adj-tb-amount`（审定合计）。

由于 D1 的子表数据（分类/坏账/变动等）需要从底稿的 parsed_data 解析，
而 spec 约束 C2 说「不从 working_paper.parsed_data 读」，
D1 builder 只构建主表（标准两字段）——与已有的 D1.note.main 主表规则一致。

spec: backend-disclosure-payload-builder Phase 2 Task 6
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

D1_NOTE_SECTION = {"listed": "五、4", "soe": "八、4"}
D1_SHEET_NAME = {"listed": "附注披露信息(上市公司)", "soe": "附注披露信息(国企)"}
D1_MAIN_TABLE = "应收票据"

_COLUMNS = [
    {"key": "label", "label": "票据种类", "is_label": True},
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
class D1Builder(DisclosurePayloadBuilder):
    wp_code = "D1"

    async def build(self, db: AsyncSession, project_id: UUID, year: int) -> PayloadBuildResult | None:
        entries = await load_disclosure_entries(db, project_id, "D1")
        if not entries:
            return None

        template_type = await load_project_template_type(db, project_id)
        variant = "soe" if "soe" in template_type.lower() else "listed"
        current_standard = await load_project_standard(db, project_id)

        total = _num(entries.get("D1-adj-tb-amount"))
        main_rows = [
            {"label": "银行承兑汇票", "end_amount": 0.0, "prior_amount": 0.0},
            {"label": "商业承兑汇票", "end_amount": total, "prior_amount": 0.0},
            {"label": "合计", "end_amount": total, "prior_amount": 0.0, "is_total": True},
        ]

        return PayloadBuildResult(
            wp_code="D1",
            section_id=D1_NOTE_SECTION[variant],
            sub_table_data={D1_MAIN_TABLE: main_rows},
            sub_table_columns={D1_MAIN_TABLE: _COLUMNS[:]},
            sheet_name=D1_SHEET_NAME[variant],
            current_standard=current_standard,
        )
