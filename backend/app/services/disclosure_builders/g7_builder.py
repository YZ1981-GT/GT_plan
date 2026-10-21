"""G7 长期股权投资后端 payload builder。

G7 的核心数据在 `G7-main-disclosure-soe-v2`（31KB JSON），内含 24 张子表。
后端 builder 解析这个 JSON 的 tables 字典，每张表的行转为标准 sub_table_data 格式。

主表从 `G7-1-tb-amount` 取审定数。子表从 disclosure JSON 的 `tables` 直接平移。

数据来源：
  G7-1-tb-amount               → 审定数
  G7-main-disclosure-soe-v2    → 前端构建的 24 表 JSON

spec: backend-disclosure-payload-builder Phase 2 Task 11 + 遗留修复 2
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

G7_NOTE_SECTION = {"listed": "五、18", "soe": "八、18"}
G7_SHEET_NAME = {"listed": "附注披露信息(上市公司)", "soe": "附注披露信息(国企)"}
G7_MAIN_TABLE = "长期股权投资"

_MAIN_COLUMNS = [
    {"key": "label", "label": "项目", "is_label": True, "flat": True},
    {"key": "end_amount", "label": "期末余额", "format": "amount"},
    {"key": "prior_amount", "label": "期初余额", "format": "amount"},
]

# disclosure JSON 中子表 key → 附注子表中文名映射
_TABLE_NAME_MAP = {
    "subsidiary-basic": "子公司基本信息",
    "control-below-half": "持股比例不超过半数但纳入合并范围的被投资方",
    "no-control-above-half": "持股比例超过半数但未纳入合并范围的被投资方",
    "minority-shareholders": "重要的少数股东情况",
    "minority-financials": "重要少数股东的主要财务信息",
    "former-subsidiary-basic": "本期不再纳入合并范围的原子公司基本信息",
    "former-subsidiary-position": "本期不再纳入合并范围的原子公司财务状况",
    "former-subsidiary-results": "本期不再纳入合并范围的原子公司经营成果",
    "newly-consolidated": "本期新纳入合并范围的子公司",
    "lte-classification": "长期股权投资分类",
    "lte-movement": "长期股权投资变动",
    "important-jv-fs": "重要合营企业财务状况",
    "important-jv-pl": "重要合营企业经营成果",
    "important-associate-fs": "重要联营企业财务状况",
    "important-associate-pl": "重要联营企业经营成果",
    "insignificant-aggregate": "不重要的合营企业和联营企业汇总",
    "unrecognized-losses": "未确认投资损失",
}


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


def _convert_table_rows(table_rows: list[dict]) -> list[dict[str, Any]]:
    """将 disclosure JSON 的 {id, label, values, kind} 行转为 sub_table_data 标准格式。"""
    out: list[dict[str, Any]] = []
    for r in table_rows:
        if not isinstance(r, dict):
            continue
        label = str(r.get("label") or "").strip()
        values = r.get("values", {})
        row: dict[str, Any] = {"label": label}
        # 把 values 字典展平到行
        if isinstance(values, dict):
            for k, v in values.items():
                if v is not None:
                    row[k] = _num(v) if isinstance(v, (int, float)) else v
        if r.get("kind") == "total":
            row["is_total"] = True
        out.append(row)
    return out


@register_builder
class G7Builder(DisclosurePayloadBuilder):
    wp_code = "G7"

    async def build(self, db: AsyncSession, project_id: UUID, year: int) -> PayloadBuildResult | None:
        entries = await load_disclosure_entries(db, project_id, "G7")
        if not entries:
            return None

        template_type = await load_project_template_type(db, project_id)
        variant = "soe" if "soe" in template_type.lower() else "listed"
        current_standard = await load_project_standard(db, project_id)

        total = _num(entries.get("G7-1-tb-amount"))

        sub: dict[str, Any] = {}
        cols: dict[str, list[dict]] = {}

        # 主表
        sub[G7_MAIN_TABLE] = [
            {"label": "长期股权投资", "end_amount": total, "prior_amount": 0.0},
            {"label": "合计", "end_amount": total, "prior_amount": 0.0, "is_total": True},
        ]
        cols[G7_MAIN_TABLE] = _MAIN_COLUMNS[:]

        # 子表：从 disclosure JSON 直接平移
        disc_key = f"G7-main-disclosure-{variant}-v2"
        disc_data = _parse_json(entries.get(disc_key), {})
        if isinstance(disc_data, dict):
            tables = disc_data.get("tables", {})
            if isinstance(tables, dict):
                for eng_key, table_rows in tables.items():
                    if not isinstance(table_rows, list) or not table_rows:
                        continue
                    cn_name = _TABLE_NAME_MAP.get(eng_key)
                    if not cn_name:
                        continue  # 未映射的跳过
                    converted = _convert_table_rows(table_rows)
                    if converted:
                        sub[cn_name] = converted

        return PayloadBuildResult(
            wp_code="G7",
            section_id=G7_NOTE_SECTION[variant],
            sub_table_data=sub,
            sub_table_columns=cols,
            sheet_name=G7_SHEET_NAME[variant],
            current_standard=current_standard,
        )
