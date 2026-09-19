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

import json
import logging
from functools import lru_cache
from pathlib import Path
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


def _template_path(source_template: str | None) -> Path | None:
    """按变体返回附注模板文件路径（listed / soe，其它/缺省 → None 不查模板）。"""
    variant = (source_template or "").strip().lower()
    if variant not in ("listed", "soe"):
        return None
    return Path(__file__).resolve().parents[2] / "data" / f"note_template_{variant}.json"


@lru_cache(maxsize=4)
def _template_header_index(source_template: str) -> dict[tuple[str, int], list[str]]:
    """``(section_number, table_index) -> headers`` 索引（模板为权威表头真源）。

    读盘失败/结构异常 → 返回空 dict（fail-open，调用方回退语义派生）。
    """
    path = _template_path(source_template)
    if path is None or not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        index: dict[tuple[str, int], list[str]] = {}
        for sec in data.get("sections") or []:
            if not isinstance(sec, dict):
                continue
            num = str(sec.get("section_number") or "").strip()
            if not num:
                continue
            for i, tbl in enumerate(sec.get("tables") or []):
                if not isinstance(tbl, dict):
                    continue
                headers = tbl.get("headers")
                if isinstance(headers, list) and headers:
                    index[(num, i)] = [str(h) for h in headers]
        return index
    except Exception:  # pragma: no cover - fail-open
        logger.warning(
            "note_header_projector: load template headers failed variant=%s",
            source_template, exc_info=True,
        )
        return {}


def template_headers_for(
    section_number: str | None,
    source_template: str | None,
    *,
    table_index: int = 0,
    num_value_cols: int | None = None,
) -> list[str] | None:
    """取模板中该表的权威表头。

    仅在**列数匹配**（``len(headers) == num_value_cols + 1``，含标签列）时返回，
    否则返回 ``None``——防止把列数不同的模板表头硬套到存量表上造成列错位。
    ``num_value_cols`` 为 ``None`` 时不做列数校验（调用方自行保证）。
    """
    if not section_number or not source_template:
        return None
    headers = _template_header_index(source_template).get((str(section_number).strip(), table_index))
    if not headers:
        return None
    if num_value_cols is not None and len(headers) != num_value_cols + 1:
        return None
    return list(headers)


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


def derive_headers_for_legacy_table(
    table_data: Any,
    *,
    section_number: str | None = None,
    source_template: str | None = None,
    table_index: int = 0,
) -> list[str] | None:
    """legacy 单表 ``headers`` 为空时，补齐可渲染表头。

    优先级：
      1. **附注模板表头**（权威真源，列数匹配才套用）——语义派生无法区分
         资产负债类"上年年末余额"与损益类"上期发生额"，且 ``manual_text`` /
         ``formula_result`` 列无语义标签会产出空表头（用户报"表头行是空的、
         内容也不对"），故模板优先。
      2. 行 ``_cell_meta`` 语义派生（模板缺失/列数不匹配时的兜底）。

    仅在以下条件全部满足时补齐（否则返回 ``None`` 表示不改动）：
      - ``table_data`` 是 dict
      - 未走多表投影（无 ``_tables``）
      - ``rows`` 是非空 list
      - ``headers`` 缺失或为空

    Returns:
        - ``None``：不适用（沿用原 headers）。
        - ``list[str]``：表头（模板原样，或首列 ``项目`` + 各值列语义标签，
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

    from_template = template_headers_for(
        section_number, source_template,
        table_index=table_index, num_value_cols=num_value_cols,
    )
    if from_template:
        return from_template

    if num_value_cols == 0:
        # 无值列——仅标签列（如股份支付情况等文本清单表），给单列表头使行可见
        has_label = any(isinstance(r, dict) and ("label" in r) for r in rows)
        return [_LABEL_HEADER] if has_label else None

    derived = [_LABEL_HEADER]
    for i in range(num_value_cols):
        sem = _semantic_for_col(rows, i)
        derived.append(_SEMANTIC_LABEL.get(sem or "", ""))
    return derived


def project_headers(
    table_data: Any,
    *,
    section_number: str | None = None,
    source_template: str | None = None,
    table_index: int = 0,
) -> dict | None:
    """读时投影：若需补齐表头，返回带 ``headers`` 的**新** dict（浅拷贝），
    否则返回 ``None`` 表示无需改动。纯函数，不修改入参。

    传入 ``section_number`` + ``source_template`` 时优先取模板权威表头；
    不传（向后兼容旧调用）则仅走语义派生。
    """
    derived = derive_headers_for_legacy_table(
        table_data,
        section_number=section_number,
        source_template=source_template,
        table_index=table_index,
    )
    if derived is None:
        return None
    return {**table_data, "headers": derived}
