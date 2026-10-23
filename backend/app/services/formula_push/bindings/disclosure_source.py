"""从披露表取数的 binding 基类。

数据流：底稿披露表（前端 buildXSyncPayload 同步写入 disclosure_notes.table_data.sub_table_data）
       → 本基类的 note_rows() 从中读取行 → 转换为 _push_note 消费的标准格式。

核心原则：附注的数据唯一来源是披露表，不直接从 TB 取数。

所有 80 个 binding 的 note_rows() 最终都应委托给本基类的实现。
改造方式：在现有 binding 的 note_rows() 中优先走「从披露表取数」路径，
TB 直推降级为兜底（披露表无数据时告知用户去编制披露表）。

spec: note-data-from-disclosure-table Phase 2
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_push.note_writer import NOTE_FIELDS

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).resolve().parents[4] / "data" / "note_workpaper_sync_registry.json"


# ── 注册表（wp_code → 附注章节）────────────────────────────────────────────


@lru_cache(maxsize=1)
def _load_section_map() -> dict[str, dict[str, str]]:
    """wp_code → {listed: section, soe: section}。"""
    try:
        doc = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, dict[str, str]] = {}
    for e in doc.get("entries") or []:
        code = str(e.get("wp_code") or "").strip()
        if code:
            out[code] = {
                k: str(e.get(k) or "").strip()
                for k in ("listed", "soe")
                if str(e.get(k) or "").strip()
            }
    return out


def _section_for(wp_code: str, template_type: str) -> str | None:
    """按 wp_code + template_type 查目标附注章节号。"""
    entry = _load_section_map().get(wp_code)
    if not entry:
        return None
    # template_type 可能是 "soe"、"listed"、"soe_standalone"、"listed_standalone" 等
    variant = "soe" if "soe" in (template_type or "").lower() else "listed"
    return entry.get(variant)


# ── 从 disclosure_notes 读取 sub_table_data ─────────────────────────────────


async def load_disclosure_sub_table_data(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    wp_code: str,
    template_type: str,
) -> dict[str, list[dict]] | None:
    """读取该底稿对应附注章节的 sub_table_data（由前端同步写入）。

    返回 None 如果：附注不存在、未生成、或从未由前端同步过（_source 非 workpaper）。
    """
    from app.models.report_models import DisclosureNote

    section = _section_for(wp_code, template_type)
    if not section:
        return None

    note = (await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.note_section == section,
            DisclosureNote.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()

    if note is None:
        return None

    td = note.table_data
    if not isinstance(td, dict):
        return None

    sub = td.get("sub_table_data")
    if not isinstance(sub, dict) or not sub:
        return None

    # 检查是否有实际数据行
    has_data = any(
        isinstance(rows, list) and len(rows) > 0
        for rows in sub.values()
    )
    return sub if has_data else None


# ── 从 sub_table_data 构建 note_rows 标准输出 ───────────────────────────────


def note_rows_from_disclosure(
    sub_table_data: dict[str, list[dict]],
    table_name: str,
    wp_code: str,
    fields: tuple[str, ...] | None = None,
) -> list[dict]:
    """从披露表 sub_table_data 的指定子表构建 note_rows 标准输出。

    遍历 sub_table_data[table_name] 的每一行，按字段名映射：
    - 标准两字段（end_amount/prior_amount）：读 ending/end_amount + opening/prior_amount
    - D1 六字段（end_balance/...）：读对应名称

    返回格式与所有 binding 的 note_rows() 一致。
    """
    rows = sub_table_data.get(table_name)
    if not isinstance(rows, list) or not rows:
        return []

    # 确定要返回的字段
    if fields is None:
        fields = ("end_amount", "prior_amount")

    result: list[dict] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue

        label = str(row.get("label") or "").strip()
        is_total = bool(row.get("is_total"))

        out: dict[str, Any] = {
            "key": f"{wp_code}-disclosure-{table_name}-{i}",
            "label": label,
            "note_label": label,
            "is_total": is_total,
            "is_memo": False,
        }

        for field_name in fields:
            value_key, _period = NOTE_FIELDS.get(field_name, (field_name, "end"))

            # 从行中读取值——尝试多种键名（不同 payload builder 用不同的键）
            raw = _read_row_value(row, value_key, field_name)
            if raw is not None:
                try:
                    out[value_key] = float(raw)
                except (TypeError, ValueError):
                    out[value_key] = 0.0
                out[f"{value_key}_resolved"] = True
            else:
                out[value_key] = 0.0
                out[f"{value_key}_resolved"] = False

        result.append(out)

    return result


def _read_row_value(row: dict, value_key: str, field_name: str) -> Any:
    """从披露表行中读值。尝试多种键名兼容不同 payload builder 的命名。

    value_key 来自 NOTE_FIELDS（如 "ending"），field_name 来自规则（如 "end_amount"）。
    披露表行可能用 "end_amount"、"ending"、"end_balance" 等不同的键。
    """
    # 优先级：value_key（NOTE_FIELDS 映射值）→ field_name（规则声明）→ 常见别名
    for key in (value_key, field_name):
        v = row.get(key)
        if v is not None:
            return v

    # 兜底别名映射
    _ALIASES: dict[str, list[str]] = {
        "ending": ["end_amount", "end_balance", "end_gross", "end_net", "amount"],
        "opening": ["prior_amount", "prior_balance", "prior_gross", "prior_net", "opening_amount"],
        "end_balance": ["ending", "end_amount"],
        "end_provision": ["provision", "end_impairment"],
        "end_book_value": ["carrying_value", "end_net", "book_value"],
        "prior_balance": ["opening", "prior_amount"],
        "prior_provision": ["prior_impairment"],
        "prior_book_value": ["prior_net"],
    }
    for alias in _ALIASES.get(value_key, []):
        v = row.get(alias)
        if v is not None:
            return v

    # 最后尝试 values 数组（F3 格式）
    values = row.get("values")
    if isinstance(values, list) and values:
        # 只对标准两字段做位置映射
        if value_key == "ending" and len(values) >= 1:
            return values[0]
        if value_key == "opening" and len(values) >= 2:
            return values[1]

    return None


# ── 集成到现有 binding：mixin 方式 ───────────────────────────────────────────


class DisclosureSourceMixin:
    """混入现有 binding 类，提供「优先从披露表取数」的 note_rows 实现。

    用法：
    1. binding 的 load_sources() 中调用 self._load_disclosure_data() 缓存数据
    2. binding 的 note_rows() 中调用 self._note_rows_from_disclosure() 优先取数
       如果返回非空就使用，否则降级到原 TB 逻辑
    """

    _disclosure_sub_table_data: dict[str, list[dict]] | None = None

    async def _load_disclosure_data(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        wp_code: str,
        template_type: str,
    ) -> None:
        """在 load_sources 中调用：缓存披露表数据。"""
        self._disclosure_sub_table_data = await load_disclosure_sub_table_data(
            db, project_id, year, wp_code, template_type,
        )

    def _note_rows_from_disclosure(
        self,
        template_type: str,
        rule: Any,
    ) -> list[dict] | None:
        """从缓存的披露表数据构建 note_rows。

        返回 None 表示披露表无数据（调用方应降级到原逻辑或返回空）。
        """
        if self._disclosure_sub_table_data is None:
            return None

        wp_code = getattr(self, "wp_code", "")
        table_name = rule.target.resolve_table(template_type) or rule.target.table
        if not table_name:
            return None

        fields = rule.target.fields if rule.target.fields else ("end_amount", "prior_amount")
        rows = note_rows_from_disclosure(
            self._disclosure_sub_table_data,
            table_name,
            wp_code,
            fields=fields,
        )
        return rows if rows else None
