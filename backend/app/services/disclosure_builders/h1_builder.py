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


def _num_or_none(v: Any) -> float | None:
    """数值或 ``None``（缺失 / 空串 / 不是数）—— 用于「读不到不写」的取值。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and v.strip():
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


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

        # 审定净值由公式推送按审定表三段行清单算出（原值 − 累计折旧 − 减值准备）；行清单没存时推送写空。
        # 空 ≠ 0：原先 _num('') 当 0 写进附注主表（spec formula-fetch-followup-defect-closure R6.3）
        net = _num_or_none(entries.get("H1-1-audited-net"))
        if net is None:
            return None

        template_type = await load_project_template_type(db, project_id)
        variant = "soe" if "soe" in template_type.lower() else "listed"
        current_standard = await load_project_standard(db, project_id)

        # 底稿不存期初净值 ⇒ 期初留空（原先写 0.0，把「没有」写成了「为零」）
        rows: list[dict[str, Any]] = [
            {"label": "固定资产", "end_amount": net, "prior_amount": None},
            {"label": "合计", "end_amount": net, "prior_amount": None, "is_total": True},
        ]

        return PayloadBuildResult(
            wp_code="H1",
            section_id=H1_NOTE_SECTION[variant],
            sub_table_data={H1_MAIN_TABLE: rows},
            sub_table_columns={H1_MAIN_TABLE: _COLUMNS[:]},
            sheet_name=H1_SHEET_NAME[variant],
            current_standard=current_standard,
        )
