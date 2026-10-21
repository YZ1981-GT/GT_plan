"""K1 其他应收款后端 payload builder。

K1 的 checklist_responses 中有 `K1-note-{variant}-rows`（前端已构建好的附注行 JSON），
后端 builder 直接解析这个 JSON 构建 sub_table_data。

数据来源：
  K1-note-soe-rows / K1-note-listed-rows → 前端构建的附注行结构
  K1-1-audited-net / K1-1-audited-receivable / K1-1-audited-baddebt → 审定数

spec: backend-disclosure-payload-builder Phase 2 Task 12
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

K1_NOTE_SECTION = {"listed": "五、8", "soe": "八、42"}
K1_SHEET_NAME = {"listed": "附注披露信息(上市公司)", "soe": "附注披露信息(国企)"}
K1_MAIN_TABLE = "其他应收款"

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


def _extract_aging_rows(note_data: dict) -> list[dict[str, Any]]:
    """从 K1-note-{variant}-rows 解析账龄行。"""
    aging = note_data.get("agingRows", [])
    if not isinstance(aging, list):
        return []
    rows: list[dict[str, Any]] = []
    for r in aging:
        if not isinstance(r, dict):
            continue
        label = str(r.get("label", "")).strip()
        if not label:
            continue
        kind = r.get("kind", "data")
        row: dict[str, Any] = {
            "label": label,
            "end_amount": _num(r.get("endAmount")),
            "prior_amount": _num(r.get("priorAmount")),
        }
        if kind == "total":
            row["is_total"] = True
        rows.append(row)
    return rows


@register_builder
class K1Builder(DisclosurePayloadBuilder):
    wp_code = "K1"

    async def build(self, db: AsyncSession, project_id: UUID, year: int) -> PayloadBuildResult | None:
        entries = await load_disclosure_entries(db, project_id, "K1")
        if not entries:
            return None

        template_type = await load_project_template_type(db, project_id)
        variant = "soe" if "soe" in template_type.lower() else "listed"
        current_standard = await load_project_standard(db, project_id)

        # 优先从前端已构建的附注行 JSON 取数
        note_key = f"K1-note-{variant}-rows"
        note_data = _parse_json(entries.get(note_key), {})

        sub_table_data: dict[str, Any] = {}
        columns: dict[str, list[dict]] = {}

        if isinstance(note_data, dict) and note_data:
            # 账龄行
            aging_rows = _extract_aging_rows(note_data)
            if aging_rows:
                sub_table_data[K1_MAIN_TABLE] = aging_rows
                columns[K1_MAIN_TABLE] = _COLUMNS[:]
        else:
            # 兜底：从审定数构建简单主表
            net = _num(entries.get("K1-1-audited-net"))
            sub_table_data[K1_MAIN_TABLE] = [
                {"label": "其他应收款", "end_amount": net, "prior_amount": 0.0},
                {"label": "合计", "end_amount": net, "prior_amount": 0.0, "is_total": True},
            ]
            columns[K1_MAIN_TABLE] = _COLUMNS[:]

        if not sub_table_data:
            return None

        return PayloadBuildResult(
            wp_code="K1",
            section_id=K1_NOTE_SECTION[variant],
            sub_table_data=sub_table_data,
            sub_table_columns=columns,
            sheet_name=K1_SHEET_NAME[variant],
            current_standard=current_standard,
        )
