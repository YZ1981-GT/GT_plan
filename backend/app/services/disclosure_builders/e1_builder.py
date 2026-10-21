"""E1 货币资金后端 payload builder。

从 checklist_responses 读审定数 + 受限明细 + 披露说明，
构建与前端 buildE1SyncPayload 逐字段一致的 sub_table_data。

数据来源（item_id 命名规律）：
  E1-adj-total-{科目码}          → 期末审定数（1001 库存现金 / 1002 银行存款 / 1012 其他货币资金）
  E1-adj-total-{科目码}-opening  → 期初数
  E1-disclosure-{variant}-restricted     → 受限明细 JSON 数组
  E1-disclosure-{variant}-note-{key}     → 披露说明文本

spec: backend-disclosure-payload-builder Phase 2 Task 5
"""
from __future__ import annotations

import json
import logging
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

logger = logging.getLogger(__name__)

# ── 常量（与前端 e1DisclosureScope.ts / e1NoteSectionMap.ts 逐字对齐） ────────

E1_NOTE_SECTION = {"listed": "五、1", "soe": "八、1"}
E1_DISCLOSURE_SHEET_NAME = {
    "listed": "附注披露信息(上市公司)",
    "soe": "附注披露信息(国企)",
}
E1_MAIN_TABLE = "货币资金"
E1_RESTRICTED_TABLE = "受限制的货币资金明细"
E1_NOTE_TOTAL_LABEL = "合计"

# 主表行定义（key / label(附注口径 noteLabel) / crossKey）
# 上市 8 行 / 国企 6 行——与前端 E1_MAIN_ROWS_LISTED / E1_MAIN_ROWS_SOE 逐字一致
_LISTED_ROWS: list[dict[str, Any]] = [
    {"key": "cash", "label": "库存现金", "crossKey": "E1-adj-total-1001"},
    {"key": "bank", "label": "银行存款", "crossKey": "E1-adj-total-1002"},
    {"key": "finance_co", "label": "存放财务公司款项", "crossKey": ""},
    {"key": "other_mf", "label": "其他货币资金", "crossKey": "E1-adj-total-1012"},
    {"key": "accrued", "label": "存款应计利息", "crossKey": ""},
    {"key": "digital", "label": "数字货币", "crossKey": ""},
    {"key": "total", "label": E1_NOTE_TOTAL_LABEL, "crossKey": "", "isTotal": True},
    {"key": "overseas", "label": "其中：存放在境外的款项总额", "crossKey": "", "isMemo": True},
]
_SOE_ROWS: list[dict[str, Any]] = [
    # 🔴 soe 首行附注口径是「库存现金」（noteLabel），底稿是「现金」
    {"key": "cash", "label": "库存现金", "crossKey": "E1-adj-total-1001"},
    {"key": "bank", "label": "银行存款", "crossKey": "E1-adj-total-1002"},
    {"key": "other_mf", "label": "其他货币资金", "crossKey": "E1-adj-total-1012"},
    {"key": "digital", "label": "数字货币", "crossKey": ""},
    {"key": "total", "label": E1_NOTE_TOTAL_LABEL, "crossKey": "", "isTotal": True},
    {"key": "overseas", "label": "其中：存放在境外的款项总额", "crossKey": "", "isMemo": True},
]

# 披露说明段（与前端 E1_NOTE_TEXTS_LISTED / E1_NOTE_TEXTS_SOE 的 key 对齐）
_LISTED_NOTE_KEYS = ["restricted", "interest"]
_SOE_NOTE_KEYS = ["restricted", "digital"]
_NOTE_TITLES = {
    "restricted": "受限及境外款项说明",
    "interest": "存款利息说明",
    "digital": "数字货币说明",
}

# 列定义（与前端 buildE1ListedColumns / buildE1SoeColumns 一致）
_MAIN_COLUMNS = [
    {"key": "label", "label": "项目", "is_label": True, "flat": True},
    {"key": "end_amount", "label": "期末余额", "format": "amount"},
    {"key": "prior_amount", "label": "期初余额", "format": "amount"},
]
_RESTRICTED_COLUMNS = [
    {"key": "label", "label": "项目", "is_label": True, "flat": True},
    {"key": "end_amount", "label": "期末余额", "format": "amount"},
    {"key": "prior_amount", "label": "期初余额", "format": "amount"},
]


def _num(v: Any) -> float:
    """安全数值转换——与前端 num() 语义一致。"""
    if isinstance(v, (int, float)) and not (isinstance(v, float) and (v != v)):  # noqa: PLR0124
        return float(v)
    if isinstance(v, str):
        v = v.strip()
        if v:
            try:
                return float(v)
            except ValueError:
                pass
    return 0.0


def _parse_json(raw: Any, default: Any = None) -> Any:
    """安全 JSON 解析。"""
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return default
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return default
    return default


@register_builder
class E1Builder(DisclosurePayloadBuilder):
    """E1 货币资金：主表 + 受限明细 + 披露说明。"""
    wp_code = "E1"

    async def build(
        self, db: AsyncSession, project_id: UUID, year: int,
    ) -> PayloadBuildResult | None:
        entries = await load_disclosure_entries(db, project_id, "E1")
        if not entries:
            return None

        template_type = await load_project_template_type(db, project_id)
        variant = "soe" if "soe" in template_type.lower() else "listed"
        current_standard = await load_project_standard(db, project_id)

        # ── 主表 ───────────────────────────────────────────────────────
        row_defs = _SOE_ROWS if variant == "soe" else _LISTED_ROWS
        main_rows: list[dict[str, Any]] = []
        for rd in row_defs:
            cross_key = rd["crossKey"]
            end_val = _num(entries.get(cross_key)) if cross_key else 0.0
            prior_key = f"{cross_key}-opening" if cross_key else ""
            prior_val = _num(entries.get(prior_key)) if prior_key else 0.0

            row: dict[str, Any] = {
                "label": rd["label"],
                "end_amount": end_val,
                "prior_amount": prior_val,
            }
            if rd.get("isTotal"):
                row["is_total"] = True
                # 合计 = 非合计非备注行之和
                row["end_amount"] = sum(
                    r["end_amount"] for r in main_rows
                    if not r.get("is_total") and not r.get("is_memo")
                )
                row["prior_amount"] = sum(
                    r["prior_amount"] for r in main_rows
                    if not r.get("is_total") and not r.get("is_memo")
                )
            if rd.get("isMemo"):
                row["is_memo"] = True
            main_rows.append(row)

        sub_table_data: dict[str, Any] = {E1_MAIN_TABLE: main_rows}
        columns: dict[str, list[dict]] = {E1_MAIN_TABLE: _MAIN_COLUMNS[:]}

        # ── 受限明细 ──────────────────────────────────────────────────
        restricted_key = f"E1-disclosure-{variant}-restricted"
        restricted_raw_str = entries.get(restricted_key)
        removed_table_keys: list[str] = []

        if restricted_raw_str is not None:
            restricted_raw = _parse_json(restricted_raw_str, [])
            if isinstance(restricted_raw, list) and restricted_raw:
                restricted_rows: list[dict[str, Any]] = []
                end_total = 0.0
                open_total = 0.0
                for item in restricted_raw:
                    if not isinstance(item, dict):
                        continue
                    label = str(item.get("item") or item.get("label") or "").strip()
                    end_amt = _num(item.get("endingAmount") or item.get("end_amount"))
                    open_amt = _num(item.get("openingAmount") or item.get("prior_amount"))
                    restricted_rows.append({
                        "label": label,
                        "end_amount": end_amt,
                        "prior_amount": open_amt,
                    })
                    end_total += end_amt
                    open_total += open_amt
                restricted_rows.append({
                    "label": E1_NOTE_TOTAL_LABEL,
                    "end_amount": end_total,
                    "prior_amount": open_total,
                    "is_total": True,
                })
                sub_table_data[E1_RESTRICTED_TABLE] = restricted_rows
                columns[E1_RESTRICTED_TABLE] = _RESTRICTED_COLUMNS[:]
            elif isinstance(restricted_raw, list):
                # 空数组 = 管这张表但当前为空 → _removed_table_keys
                removed_table_keys.append(E1_RESTRICTED_TABLE)
        # else: key 不存在 = 不管这张表 → 不进 removed

        if removed_table_keys:
            sub_table_data["_removed_table_keys"] = removed_table_keys

        # ── 披露说明 ──────────────────────────────────────────────────
        note_keys = _SOE_NOTE_KEYS if variant == "soe" else _LISTED_NOTE_KEYS
        note_texts: list[dict[str, str]] = []
        for nk in note_keys:
            item_key = f"E1-disclosure-{variant}-note-{nk}"
            text_val = str(entries.get(item_key) or "").strip()
            if text_val:
                note_texts.append({
                    "section": nk,
                    "title": _NOTE_TITLES.get(nk, nk),
                    "text": text_val,
                })
        # 旧版单一说明框兜底
        if not note_texts:
            legacy_key = f"E1-disclosure-{variant}-note"
            legacy_text = str(entries.get(legacy_key) or "").strip()
            if legacy_text:
                note_texts.append({
                    "section": "restricted",
                    "title": _NOTE_TITLES["restricted"],
                    "text": legacy_text,
                })

        if note_texts:
            sub_table_data["_note_texts"] = note_texts

        return PayloadBuildResult(
            wp_code="E1",
            section_id=E1_NOTE_SECTION[variant],
            sub_table_data=sub_table_data,
            sub_table_columns=columns,
            sheet_name=E1_DISCLOSURE_SHEET_NAME[variant],
            current_standard=current_standard,
        )
