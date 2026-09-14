"""E0-3 上游取数：E1-3 → E0-3 段语义取数（transient prefill）

纯函数 + DB 查询封装。render 期调用，结果挂 `_prefill`（不落库）。
任一环异常 fail-open：返回 None，不阻断 render。

Design 判断 3：金额口径可切换三态，默认未审期末。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

import sqlalchemy as sa

from .e1_3_segments import (
    E1_3_CNY,
    E1_3_FX,
    E1_3Variant,
    SEGMENT_HEADS,
    account_subject_of,
    split_segments,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def build_e03_prefill(
    db: "AsyncSession",
    project_id: UUID,
    year: int | None,
) -> dict | None:
    """E1-3 → E0-3 取数。

    返回 transient prefill dict（挂在 html_data._prefill）或 None（宁缺勿造）。
    """
    try:
        # 1. 找 E1 的 wp_id（同项目同年）
        wp_id = await _find_e1_wp_id(db, project_id, year)
        if wp_id is None:
            logger.debug("E0-3 prefill: 项目无 E1 底稿")
            return None

        # 2. 尝试两版 E1-3，优先人民币及外币版（列更全）
        for variant in (E1_3_FX, E1_3_CNY):
            sheet_data = await _load_e1_sheet(db, wp_id, variant.sheet_name)
            if sheet_data and _has_rows(sheet_data):
                rows = _extract_prefill_rows(sheet_data, variant)
                if rows:
                    return {
                        "variant": variant.sheet_name,
                        "source_caliber_note": (
                            "源模板 E0-3.K 原公式指向 E1-3.K「期末对账单余额」"
                        ),
                        "rows": rows,
                    }

        logger.debug("E0-3 prefill: E1-3 两版都无明细行数据")
        return None

    except Exception:
        logger.warning("E0-3 prefill 取数异常，fail-open", exc_info=True)
        return None


def _extract_prefill_rows(sheet_data: dict, variant: E1_3Variant) -> list[dict]:
    """从 E1-3 sheet 数据中提取明细行并按段切分。"""
    # E1-3 的行数据可能在 responses_snapshot 或直接在 rows 里
    # 实际 E1 render 策略把行数据放在 checklist_responses（前端自取）
    # 但也可能在 html_data 的 detail_rows / e1_3_rows 等键
    raw_rows = _get_detail_rows(sheet_data)
    if not raw_rows:
        return []

    # 切段
    segments = split_segments(raw_rows, label_key=variant.bank_col)

    prefill_rows: list[dict] = []
    for seg in segments:
        subject = seg.account_subject
        for row in seg.detail_rows:
            bank_name = row.get(variant.bank_col)
            if not bank_name or not str(bank_name).strip():
                continue  # 跳过空行

            prefill_row: dict = {
                "bank_name": str(bank_name).strip(),
                "account_holder": _get_str(row, variant.holder_col),
                "bank_account": _get_str(row, variant.account_col),
                "currency": _get_str(row, variant.currency_col) if variant.currency_col else None,
                "interest_rate": _get_num(row, variant.rate_col) if variant.rate_col else None,
                "account_subject": subject,
                "amount_unaudited": _get_num(row, variant.unaudited_col),
                "amount_audited": _get_num(row, variant.audited_col),
                "amount_statement": _get_num(row, variant.statement_col),
                "restricted_amount": _get_num(row, variant.restricted_amt_col),
                "restricted_reason": _get_str(row, variant.restricted_reason_col),
                "_segment": seg.head,
            }
            prefill_rows.append(prefill_row)

    return prefill_rows


def _has_rows(sheet_data: dict) -> bool:
    """判断 sheet 数据是否有明细行。"""
    if not isinstance(sheet_data, dict):
        return False
    # 多种可能的行存储位置
    for key in ("rows", "detail_rows", "e1_3_rows", "responses_snapshot"):
        v = sheet_data.get(key)
        if isinstance(v, list) and len(v) > 0:
            return True
        if isinstance(v, dict) and v:
            return True
    return False


def _get_detail_rows(sheet_data: dict) -> list[dict]:
    """从各种可能的存储形态中提取行列表。"""
    # 直接行列表
    for key in ("rows", "detail_rows", "e1_3_rows"):
        v = sheet_data.get(key)
        if isinstance(v, list) and v:
            return v

    # responses_snapshot 形态（E1 常用：{item_id: value}）
    snap = sheet_data.get("responses_snapshot")
    if isinstance(snap, dict):
        # 查找 E1-3 明细行键
        for k, v in snap.items():
            if "E1-3" in k and isinstance(v, list):
                return v

    return []


def _get_str(row: dict, key: str | None) -> str | None:
    if not key:
        return None
    v = row.get(key)
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _get_num(row: dict, key: str | None) -> float | None:
    if not key:
        return None
    v = row.get(key)
    if v is None or v == "":
        return None
    try:
        n = float(str(v).replace(",", ""))
        return n if n == n else None  # NaN check
    except (ValueError, TypeError):
        return None


async def _find_e1_wp_id(db: "AsyncSession", project_id: UUID, year: int | None) -> UUID | None:
    """找同项目的 E1 底稿 ID。"""
    query = sa.text("""
        SELECT wp.id
        FROM working_paper wp
        JOIN wp_index wi ON wi.id = wp.wp_index_id
        WHERE wp.project_id = :pid
          AND wi.wp_code = 'E1'
          AND wp.is_deleted = false
        LIMIT 1
    """)
    result = await db.execute(query, {"pid": str(project_id)})
    row = result.first()
    return UUID(str(row[0])) if row else None


async def _load_e1_sheet(db: "AsyncSession", wp_id: UUID, sheet_name: str) -> dict | None:
    """读取 E1 底稿的 parsed_data.html_data[sheet_name]。"""
    query = sa.text("""
        SELECT parsed_data->'html_data'->:sheet_name AS sheet_data
        FROM working_paper
        WHERE id = :wp_id
    """)
    result = await db.execute(query, {"wp_id": str(wp_id), "sheet_name": sheet_name})
    row = result.first()
    if not row or row[0] is None:
        return None
    return row[0] if isinstance(row[0], dict) else None
