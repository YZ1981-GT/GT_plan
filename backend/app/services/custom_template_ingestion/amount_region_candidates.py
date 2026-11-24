"""
逐 amount region 候选推导（2026-11-24 平台技术债清偿）。

从 `semantic_preflight._scan_sheet` 的逐列统计（数值格数 / 表头文本 /
首个数值行）推导「金额/数值 region 候选」，写入 preflight 报告的
``amountRegionCandidates`` —— 逐 region 确认 UI 的唯一候选来源。

职责边界：扫描器只给候选（列位置 + 表头 + 数值格数），**单位 / kind 语义
由用户在向导里逐 region 裁决**（前端 ``buildRegionsFromDecisions`` 与后端
``_validate_authority_manifest`` 同口径）—— scanner 不猜单位。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AmountRegionCandidate:
    """单列金额 region 候选（preflight 报告产出，供逐 region 确认 UI 消费）。

    只描述「这里有一列数值、表头是什么」—— 单位 / divisor / kind 语义由用户
    在向导里逐 region 裁决，scanner 不猜单位。
    """

    stable_id: str
    column_letter: str
    header: str
    numeric_cells: int
    first_numeric_row: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "stableId": self.stable_id,
            "columnLetter": self.column_letter,
            "header": self.header,
            "numericCells": self.numeric_cells,
            "firstNumericRow": self.first_numeric_row,
        }


def derive_amount_region_candidates(
    *,
    col_numeric: dict[int, int],
    col_first_text: dict[int, int | str] | dict[int, str],
    col_first_numeric_row: dict[int, int],
    non_empty: int,
) -> list[AmountRegionCandidate]:
    """从逐列统计推导「金额/数值 region 候选」。

    金额列形态 = ①首 3 行有文本表头 ②该列数值格数 ≥ 2 ③数值格数占该 sheet
    非空格的 5% 以上（阈值宽松，宁可多列候选让用户裁决，不静默漏列）。
    产出的 stable_id 规则：``region-{列字母小写}-{数值格数}`` —— 同一结构
    重跑稳定（幂等）；列字母随结构变化，正是「结构漂移要重新确认」的语义。
    """
    if non_empty <= 0:
        return []
    try:
        from openpyxl.utils import get_column_letter

        get_letter = get_column_letter
    except Exception:  # noqa: BLE001 — openpyxl 已是必需依赖，防御性兜底
        get_letter = lambda idx: chr(64 + idx) if 1 <= idx <= 26 else f"col{idx}"  # noqa: E731

    out: list[AmountRegionCandidate] = []
    threshold = max(2, int(non_empty * 0.05))
    for col in sorted(col_numeric):
        numeric_cells = col_numeric[col]
        if numeric_cells < threshold:
            continue
        header = col_first_text.get(col, "")
        letter = get_letter(col)
        out.append(AmountRegionCandidate(
            stable_id=f"region-{letter.lower()}-{numeric_cells}",
            column_letter=letter,
            header=header or f"第 {letter} 列",
            numeric_cells=numeric_cells,
            first_numeric_row=col_first_numeric_row.get(col, 0),
        ))
    return out
