"""F2 存货后端 payload builder。

从 checklist_responses 读 6 个科目审定数（F2-1-tb-{科目码}），
构建主表「存货分类」（6 行数据 + 合计行，6 字段 end_gross/end_impairment/end_net/prior_*）。

spec: backend-disclosure-payload-builder Phase 2 Task 8
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

F2_NOTE_SECTION = {"listed": "五、9", "soe": "八、10"}
F2_SHEET_NAME = {"listed": "附注披露信息(上市公司)", "soe": "附注披露信息(国企)"}
F2_MAIN_TABLE = "存货分类"

# 存货分类行：科目码 → 行标签
_F2_ACCOUNT_ROWS = [
    ("1401", "原材料"),
    ("1402", "在产品"),
    ("1403", "库存商品"),
    ("1405", "委托加工物资"),
    ("1408", "周转材料"),
    ("1461", "合同履约成本"),
]

_COLUMNS = [
    {"key": "label", "label": "项目", "is_label": True, "flat": True},
    {"key": "end_gross", "label": "期末账面余额", "group": "期末数", "format": "amount"},
    {"key": "end_impairment", "label": "期末跌价准备", "group": "期末数", "format": "amount"},
    {"key": "end_net", "label": "期末账面价值", "group": "期末数", "format": "amount"},
    {"key": "prior_gross", "label": "期初账面余额", "group": "期初数", "format": "amount"},
    {"key": "prior_impairment", "label": "期初跌价准备", "group": "期初数", "format": "amount"},
    {"key": "prior_net", "label": "期初账面价值", "group": "期初数", "format": "amount"},
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
class F2Builder(DisclosurePayloadBuilder):
    wp_code = "F2"

    async def build(self, db: AsyncSession, project_id: UUID, year: int) -> PayloadBuildResult | None:
        entries = await load_disclosure_entries(db, project_id, "F2")
        if not entries:
            return None

        template_type = await load_project_template_type(db, project_id)
        variant = "soe" if "soe" in template_type.lower() else "listed"
        current_standard = await load_project_standard(db, project_id)

        rows: list[dict[str, Any]] = []
        for code, label in _F2_ACCOUNT_ROWS:
            val = _num(entries.get(f"F2-1-tb-{code}"))
            rows.append({
                "label": label,
                "end_gross": val,
                "end_impairment": 0.0,
                "end_net": val,
                "prior_gross": 0.0,
                "prior_impairment": 0.0,
                "prior_net": 0.0,
            })

        total = {
            "label": "合计",
            "is_total": True,
            **{k: sum(r[k] for r in rows) for k in
               ("end_gross", "end_impairment", "end_net", "prior_gross", "prior_impairment", "prior_net")},
        }
        rows.append(total)

        return PayloadBuildResult(
            wp_code="F2",
            section_id=F2_NOTE_SECTION[variant],
            sub_table_data={F2_MAIN_TABLE: rows},
            sub_table_columns={F2_MAIN_TABLE: _COLUMNS[:]},
            sheet_name=F2_SHEET_NAME[variant],
            current_standard=current_standard,
        )
