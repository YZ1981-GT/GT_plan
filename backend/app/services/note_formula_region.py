"""附注公式 ``REGION('区域名', '列 id', agg=…)``：同表动态区域聚合（Sprint A.3.1）。

按 ``file_size_whitelist.txt`` 登记的拆分方向从 ``note_formula_generator.py`` 原样抽出（2026-11-04，该文件
超行数门）；那边以原名导入，既有引用不变。``exec_with_region`` 里的 TB / REPORT 等单引用仍由生成器的
``_resolve_single_cross_ref`` 解析（调用时导入，避免导入期循环）。
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.services.note_formula_provenance import as_decimal as _as_decimal


_REGION_AGG_FUNCS = {
    "sum": lambda xs: sum(xs, Decimal("0")),
    "count": lambda xs: Decimal(len(xs)),
    "max": lambda xs: max(xs) if xs else None,
    "min": lambda xs: min(xs) if xs else None,
    "avg": lambda xs: (sum(xs, Decimal("0")) / Decimal(len(xs))) if xs else None,
}


def resolve_region_token(
    token: str,
    table_data: dict | None,
) -> Decimal | None:
    """解析 REGION('region_name','col_id', agg='sum'|'count'|'max'|'min'|'avg') token.

    引用同表内的动态区域 ``_dynamic_regions[name=region_name]`` 在指定 col_id
    的聚合值（仅 axis=row 区域 + row_type=dynamic_data 行参与聚合）。

    Args:
        token: 形如 "REGION('客户','col_amount_end', agg='sum')"
        table_data: 含 _dynamic_regions / _columns_meta / rows 的 dict

    Returns:
        聚合值（Decimal），无匹配 region / col / 数据时返 None；
        agg='count' 始终返非负 Decimal（无数据返 Decimal("0")）。

    支持 agg：sum / count / max / min / avg；默认 sum。

    无效输入（None / 非字符串 / 解析失败 / 缺 region / 缺 col_id）→ 返 None。
    """
    import re

    if not token or not isinstance(token, str):
        return None
    if not isinstance(table_data, dict):
        return None

    s = token.strip()
    # REGION('name','col', agg='sum')   或   REGION('name','col')
    m = re.fullmatch(
        r"\s*REGION\("
        r"\s*'([^']+)'\s*,"
        r"\s*'([^']+)'"
        r"(?:\s*,\s*agg\s*=\s*['\"]([^'\"]+)['\"]\s*)?"
        r"\)\s*",
        s,
    )
    if not m:
        return None

    region_name = m.group(1)
    col_id = m.group(2)
    agg_raw = (m.group(3) or "sum").strip().lower()
    agg = _REGION_AGG_FUNCS.get(agg_raw)
    if agg is None:
        return None

    # 1. 找到匹配 region（axis=row）
    regions = table_data.get("_dynamic_regions") or []
    target_region = None
    for r in regions:
        if not isinstance(r, dict):
            continue
        if r.get("axis") != "row":
            continue
        if r.get("name") == region_name:
            target_region = r
            break
    if target_region is None:
        return None

    start_idx = target_region.get("start_idx")
    end_idx = target_region.get("end_idx")
    if not isinstance(start_idx, int) or not isinstance(end_idx, int):
        return None
    if end_idx < start_idx:
        return None

    # 2. 找到 col_id 在 _columns_meta 中的位置
    columns_meta = table_data.get("_columns_meta") or []
    col_pos: int | None = None
    for idx, col in enumerate(columns_meta):
        if isinstance(col, dict) and col.get("id") == col_id:
            col_pos = idx
            break
    if col_pos is None:
        return None

    # 3. 在 [start_idx, end_idx] 范围内迭代 dynamic_data 行
    rows = table_data.get("rows") or []
    if not isinstance(rows, list):
        return None

    nums: list[Decimal] = []
    for i in range(start_idx, min(end_idx + 1, len(rows))):
        r = rows[i]
        if not isinstance(r, dict):
            continue
        if r.get("row_type") != "dynamic_data":
            continue
        vals = r.get("values")
        if not isinstance(vals, list) or col_pos >= len(vals):
            continue
        v = vals[col_pos]
        if v is None:
            continue
        value = _as_decimal(v)
        if value is not None:
            nums.append(value)

    if agg_raw == "count":
        # count 始终返非负数；无数据返 Decimal("0")
        return Decimal(len(nums))

    if not nums:
        return None

    try:
        result = agg(nums)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return result if result is not None else None


def exec_with_region(
    expression: Any,
    cross_data: dict[str, Any],
    table_data: dict | None,
) -> Decimal | None:
    """REGION-aware 表达式解析：直接迭代 +/- 组合的 REGION + 其他跨表 token.

    支持组合：``REGION('A','col_x') + TB('1001','期末') - REGION('B','col_y')``

    Args:
        expression: 含 REGION + 其他 token 的表达式
        cross_data: 跨表数据（TB / WP / REPORT / NOTE / PRIOR / AGING）
        table_data: 同表内 _dynamic_regions / _columns_meta / rows

    Returns:
        - 数值（所有 token 解析成功）
        - None（任一 token 解析失败 / 表达式不合法）
    """
    import re

    from app.services.note_formula_generator import _resolve_single_cross_ref

    if expression is None or not isinstance(expression, str):
        return None
    s = expression.strip()
    if not s:
        return None

    # 整体单 REGION 直接走 resolver（避免 +/- 拆分）
    region_pattern = re.compile(
        r"REGION\(\s*'[^']+'\s*,\s*'[^']+'(?:\s*,\s*agg\s*=\s*['\"][^'\"]+['\"])?\s*\)"
    )
    if region_pattern.fullmatch(s):
        return resolve_region_token(s, table_data)

    # 表达式由 +/- 拼接的 token 组成（REGION / TB / REPORT / WP / NOTE / PRIOR / AGING）
    token_pattern = re.compile(
        r"([+-]?)\s*("
        r"REGION\(\s*'[^']+'\s*,\s*'[^']+'(?:\s*,\s*agg\s*=\s*['\"][^'\"]+['\"])?\s*\)"
        r"|"
        r"(?:TB|REPORT|WP|NOTE|PRIOR|AGING)\([^)]*\)"
        r")"
    )
    matches = token_pattern.findall(s)
    if not matches:
        return None

    # 校验整体由这些 token + +/- 组成（不能混入未识别字符）
    rebuilt = "".join(f"{sign or '+'}{token}" for sign, token in matches)
    s_no_space = re.sub(r"\s+", "", s)
    rec_no_space = re.sub(r"\s+", "", rebuilt)
    if rec_no_space.lstrip("+") != s_no_space.lstrip("+"):
        return None

    total = Decimal("0")
    for sign, token in matches:
        if token.startswith("REGION("):
            val = resolve_region_token(token, table_data)
        else:
            val = _resolve_single_cross_ref(token, cross_data)
        if val is None:
            return None
        total += -val if sign == "-" else val
    return total
