"""E1-3 segment-based row extraction for E0 send list population.

Pure functions for splitting the E1-3 明细表 rows into segments
(银行/其他金融机构/其他货币资金) and filtering out summary rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field


@dataclass(frozen=True)
class E1_3Variant:
    sheet_name: str
    bank_col: str          # 开户银行
    holder_col: str        # 总账银行名称
    account_col: str       # 银行账号
    currency_col: str | None
    unaudited_col: str     # 期末余额（未审）
    audited_col: str       # 期末审定数
    statement_col: str     # 期末对账单余额
    restricted_amt_col: str
    restricted_reason_col: str
    rate_col: str | None


E1_3_CNY = E1_3Variant(
    sheet_name="银行存款及其他货币资金明细表(仅人民币)E1-3",
    bank_col="A", holder_col="B", account_col="C", currency_col=None,
    unaudited_col="H", audited_col="J", statement_col="K",
    restricted_amt_col="Q", restricted_reason_col="R", rate_col=None,
)

E1_3_FX = E1_3Variant(
    sheet_name="银行存款及其他货币资金明细表(人民币及外币)E1-3",
    bank_col="A", holder_col="B", account_col="C", currency_col="E",
    unaudited_col="M", audited_col="AA", statement_col="AD",
    restricted_amt_col="AJ", restricted_reason_col="AK", rate_col="AL",
)

SEGMENT_HEADS = ("银行：", "其他金融机构（存放财务公司款项）：", "其他货币资金：")

EXCLUDED_ROWS = (
    "存款本金小计",
    "存款应计利息小计",
    "银行存款小计",
    "财务公司存款小计",
    "其他货币资金小计",
    "合 计",
)

INTEREST_SECTION_HEAD = "（二）应计利息"


_SUBJECT_MAP: dict[str, str] = {
    "银行：": "1002 银行存款",
    "其他金融机构（存放财务公司款项）：": "1002 银行存款",
    "其他货币资金：": "1012 其他货币资金",
}


@dataclass(frozen=True)
class Segment:
    head: str               # segment head text
    account_subject: str    # "1002 银行存款" or "1012 其他货币资金"
    detail_rows: list[dict] = dc_field(default_factory=list)


def account_subject_of(segment_head: str) -> str:
    """Map segment head to account subject.

    银行： → "1002 银行存款"
    其他金融机构（存放财务公司款项）： → "1002 银行存款"
    其他货币资金： → "1012 其他货币资金"
    """
    result = _SUBJECT_MAP.get(segment_head)
    if result is None:
        raise ValueError(f"Unknown segment head: {segment_head!r}")
    return result


def split_segments(rows: list[dict], label_key: str = "A") -> list[Segment]:
    """Split rows into segments by SEGMENT_HEADS.

    Args:
        rows: list of dicts where keys are column letters (A, B, C...) and values are cell values.
        label_key: which key in the dict holds the row label (default "A" for column A).

    Returns list of Segment objects. Rules:
    - Identify segment boundaries by checking if row[label_key] matches any SEGMENT_HEADS
    - Within each segment, include only detail rows (exclude the head itself)
    - Exclude any row whose label is in EXCLUDED_ROWS
    - Exclude the entire "(二) 应计利息" section and everything after it
    - Empty/None labels within a segment ARE included (they are valid detail rows)
    """
    segments: list[Segment] = []
    current_head: str | None = None
    current_rows: list[dict] = []

    for row in rows:
        label = row.get(label_key)
        label_str = str(label).strip() if label is not None else ""

        # Stop processing at the interest section
        if label_str == INTEREST_SECTION_HEAD:
            break

        # Check if this row starts a new segment
        if label_str in SEGMENT_HEADS:
            # Save previous segment if any
            if current_head is not None:
                segments.append(Segment(
                    head=current_head,
                    account_subject=account_subject_of(current_head),
                    detail_rows=current_rows,
                ))
            current_head = label_str
            current_rows = []
            continue

        # If we're inside a segment, add the row (unless excluded)
        if current_head is not None:
            if label_str in EXCLUDED_ROWS:
                continue
            current_rows.append(row)

    # Save the last segment
    if current_head is not None:
        segments.append(Segment(
            head=current_head,
            account_subject=account_subject_of(current_head),
            detail_rows=current_rows,
        ))

    return segments
