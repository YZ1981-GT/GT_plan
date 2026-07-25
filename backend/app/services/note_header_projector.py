"""附注表头补齐器：legacy 单表 headers 为空时从行 _cell_meta 语义派生表头。

背景
----
历史生成/模板绑定合并路径产出的部分附注 ``table_data`` 出现 ``headers: []``
（空数组）但 ``rows`` 非空——每行携带 ``values`` 数组与 ``_cell_meta[colIdx].semantic``
列语义，却没有可渲染的表头。前端 ``el-table`` 按 ``headers`` 生成列，空表头 →
零列 → 表格坍缩为"只有一行"/空白（用户报的"附注表格只有一行"）。

本模块在 ``get_note_detail`` 读时（不写库）从行的 ``_cell_meta`` 语义派生表头，
使数据列可见；前端保存整表时派生表头随之落库，实现自愈。

纯函数、无 IO、读时执行。语义→中文标签复用 ``note_column_semantics`` 标准语义集，
避免两套映射漂移。

spec: 附注表格显示修复（headers 为空导致列坍缩）
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 标签列（首列）默认表头
_LABEL_HEADER = "项目"

# 标准语义 → 中文列标签。键取自 note_column_semantics.STANDARD_SEMANTICS，
# 值为审计披露表习惯用词（资产负债表类第二列惯用"上年年末余额"）。
_SEMANTIC_LABEL: dict[str, str] = {
    "closing_balance": "期末余额",
    "opening_balance": "期初余额",
    "prior_year_value": "上年年末余额",
    "current_year_increase": "本期增加",
    "current_year_decrease": "本期减少",
    "current_year_provision": "本期计提",
    "current_period_acquisition": "本期购置",
    "current_period_disposal": "本期处置",
    "current_period_writeoff": "本期核销",
    "current_period_recover": "本期收回",
    "original_value": "原值",
    "accumulated_depreciation": "累计折旧/摊销",
    "impairment_provision": "减值准备",
    "carrying_value": "账面价值",
    "provision_ratio": "计提比例",
    "cost": "成本",
    "fair_value": "公允价值",
    "category_subtotal": "小计",
    "aging_bucket_within_1y": "1年以内",
    "aging_bucket_1_2y": "1-2年",
    "aging_bucket_2_3y": "2-3年",
    "aging_bucket_3_5y": "3-5年",
    "aging_bucket_over_5y": "5年以上",
    # manual_text / formula_result 为文本/公式列，无固定语义标签 → 留空（列仍渲染）
}


def _value_len(row: Any) -> int:
    if isinstance(row, dict):
        vals = row.get("values")
        if isinstance(vals, list):
            return len(vals)
    return 0


def _semantic_for_col(rows: list, col_idx: int) -> str | None:
    """扫描所有行，返回该值列首个非空语义（跳过合计行更可靠但非必需）。"""
    key = str(col_idx)
    for r in rows:
        if not isinstance(r, dict):
            continue
        cm = r.get("_cell_meta")
        if not isinstance(cm, dict):
            continue
        meta = cm.get(key)
        if isinstance(meta, dict):
            sem = meta.get("semantic")
            if isinstance(sem, str) and sem:
                return sem
    return None


def derive_headers_for_legacy_table(table_data: Any) -> list[str] | None:
    """legacy 单表 ``headers`` 为空时，从行结构派生可渲染表头。

    仅在以下条件全部满足时派生（否则返回 ``None`` 表示不改动）：
      - ``table_data`` 是 dict
      - 未走多表投影（无 ``_tables``）
      - ``rows`` 是非空 list
      - ``headers`` 缺失或为空

    Returns:
        - ``None``：不适用（沿用原 headers）。
        - ``list[str]``：派生出的表头（首列 ``项目`` + 各值列语义标签，
          无语义的值列留空字符串，列仍渲染）。
    """
    if not isinstance(table_data, dict):
        return None
    if table_data.get("_tables"):
        return None  # 多表已投影，不处理
    rows = table_data.get("rows")
    if not isinstance(rows, list) or not rows:
        return None
    headers = table_data.get("headers")
    if isinstance(headers, list) and len(headers) > 0:
        return None  # 已有表头，不改动

    # 值列数：所有行 values 长度的最大值
    num_value_cols = max((_value_len(r) for r in rows), default=0)

    if num_value_cols == 0:
        # 无值列——仅标签列（如股份支付情况等文本清单表），给单列表头使行可见
        has_label = any(isinstance(r, dict) and ("label" in r) for r in rows)
        return [_LABEL_HEADER] if has_label else None

    derived = [_LABEL_HEADER]
    for i in range(num_value_cols):
        sem = _semantic_for_col(rows, i)
        derived.append(_SEMANTIC_LABEL.get(sem or "", ""))
    return derived


def project_headers(table_data: Any) -> dict | None:
    """读时投影：若需派生表头，返回带补齐 ``headers`` 的**新** dict（浅拷贝），
    否则返回 ``None`` 表示无需改动。纯函数，不修改入参。
    """
    derived = derive_headers_for_legacy_table(table_data)
    if derived is None:
        return None
    return {**table_data, "headers": derived}
