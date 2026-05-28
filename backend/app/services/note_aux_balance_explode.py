"""Sprint A.2.3 — aux_balance 行 explode.

按辅助账码（aux_code）把 TbAuxBalance 行展开成动态行数据，喂给
``dynamic_region_engine.expand_dynamic_rows`` 的 ctx['aux_data'] 桶。

与 `note_source_resolvers.resolve_aux_balance` 的区别：
- resolve_aux_balance：按 (account_codes, aux_type) **求和** → 单个标量
- explode_aux_balance：按 (account_codes, aux_type) **每个 aux_code 一行** → 列表

设计原则：
- async 函数 — 实时查 PG（与 resolve_aux_balance 一致风格）
- 永不抛异常 — 缺 db / project_id / year / account_codes → 返回 []
- 输出兼容 ``dynamic_region_engine._make_dynamic_data_row``：
  ``[{"label": str, "values": {col_id: Decimal}, "aux_code": str}, ...]``
- top_n + exclude_zero 过滤辅助审计师做「前 5 名客户」展示
- 排序按 |closing_balance| 降序，同金额按 aux_code 字母序兜底（确定性）

binding 字段
-----------
- account_codes: list[str]   必填 — 辅助账所挂科目
- aux_type:      str          可选 — 过滤辅助类型（如 customer / supplier）
- field_map:     dict          可选 — col_id → TbAuxBalance.field 字段名映射，
                                默认 {"col_amount_end": "closing_balance",
                                       "col_amount_start": "opening_balance"}
- top_n:         int           可选 — 按 |closing_balance| 降序取前 N 行
- exclude_zero:  bool          可选 — 跳过 closing_balance 为 0 的辅助账
                                （默认 True）
- order_field:   str           可选 — 排序字段（默认 closing_balance）

ctx 字段
--------
- db:           AsyncSession  必填
- project_id:   UUID          必填
- year:         int           必填

Validates: Requirements R1.1 / R1.2 + Sprint A.2.3
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import sqlalchemy as sa

logger = logging.getLogger(__name__)


_DEFAULT_FIELD_MAP: dict[str, str] = {
    "col_amount_end": "closing_balance",
    "col_amount_start": "opening_balance",
}


def _safe_account_codes(binding: dict[str, Any]) -> list[str]:
    codes = binding.get("account_codes")
    if not isinstance(codes, list):
        return []
    return [c for c in codes if isinstance(c, str) and c]


def _coerce_decimal(x: Any) -> Decimal | None:
    """安全转 Decimal；None / 非数 → None."""
    if x is None:
        return None
    if isinstance(x, Decimal):
        return x
    if isinstance(x, bool):
        return None
    if isinstance(x, int | float):
        try:
            return Decimal(str(x))
        except Exception:
            return None
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return None
        try:
            return Decimal(s)
        except Exception:
            return None
    return None


def _build_field_map(binding: dict[str, Any]) -> dict[str, str]:
    """合并默认与 binding 提供的 field_map（binding 优先）."""
    raw = binding.get("field_map")
    if isinstance(raw, dict) and raw:
        out: dict[str, str] = {}
        for col_id, field in raw.items():
            if isinstance(col_id, str) and isinstance(field, str) and field:
                out[col_id] = field
        if out:
            return out
    return dict(_DEFAULT_FIELD_MAP)


def _row_value(row: Any, field: str) -> Decimal | None:
    """从 ORM 行 / SimpleNamespace / dict 上读取字段."""
    if row is None:
        return None
    if isinstance(row, dict):
        return _coerce_decimal(row.get(field))
    return _coerce_decimal(getattr(row, field, None))


def _row_str(row: Any, field: str) -> str | None:
    """读取字符串字段，去空白后返回；空 → None."""
    if row is None:
        return None
    raw = row.get(field) if isinstance(row, dict) else getattr(row, field, None)
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    return s or None


def _aggregate_rows(rows: list[Any], fields: set[str]) -> dict[str, dict[str, Any]]:
    """按 aux_code 合并多行（同 aux_code 不同月份/分录 → sum）.

    返回 {aux_code: {"aux_name": str | None, fields: {field_name: Decimal}}}
    """
    bucket: dict[str, dict[str, Any]] = {}
    for r in rows:
        aux_code = _row_str(r, "aux_code")
        if not aux_code:
            continue  # 没 aux_code 没法 explode 成「一个客户一行」
        slot = bucket.setdefault(
            aux_code,
            {"aux_name": None, "fields": {f: Decimal("0") for f in fields}},
        )
        # aux_name：取首次非空
        if slot["aux_name"] is None:
            name = _row_str(r, "aux_name")
            if name:
                slot["aux_name"] = name
        for f in fields:
            v = _row_value(r, f)
            if v is not None:
                slot["fields"][f] = slot["fields"][f] + v
    return bucket


async def explode_aux_balance(
    binding: dict[str, Any],
    ctx: dict[str, Any],
) -> list[dict[str, Any]]:
    """按辅助账码 explode 为行级数据.

    Returns
    -------
    list[dict] — 每个 aux_code 一行：
        [{"label": aux_name, "values": {col_id: Decimal | None}, "aux_code": str}, ...]

    缺 db / project_id / year / account_codes → 返回 []。
    """
    db = ctx.get("db")
    if db is None:
        return []
    project_id = ctx.get("project_id")
    year = ctx.get("year")
    if project_id is None or year is None:
        return []

    codes = _safe_account_codes(binding)
    if not codes:
        return []

    field_map = _build_field_map(binding)
    fields_needed: set[str] = set(field_map.values())

    try:
        from app.models.audit_platform_models import TbAuxBalance
    except Exception as err:  # pragma: no cover - import 失败极少出现
        logger.warning("aux_balance_explode: import TbAuxBalance failed: %s", err)
        return []

    where = [
        TbAuxBalance.project_id == project_id,
        TbAuxBalance.year == year,
        TbAuxBalance.is_deleted == sa.false(),
        TbAuxBalance.account_code.in_(codes),
    ]
    aux_type = binding.get("aux_type")
    if isinstance(aux_type, str) and aux_type:
        where.append(TbAuxBalance.aux_type == aux_type)

    try:
        result = await db.execute(sa.select(TbAuxBalance).where(*where))
        # SQLAlchemy 2.x: scalars().all() 拿 ORM list；测试场景注入 list 也行
        if hasattr(result, "scalars"):
            rows = list(result.scalars().all())
        else:
            rows = list(result.all() or [])
    except Exception as err:
        logger.warning("aux_balance_explode query failed: %s", err)
        return []

    if not rows:
        return []

    bucket = _aggregate_rows(rows, fields_needed)

    exclude_zero = bool(binding.get("exclude_zero", True))
    order_field = binding.get("order_field") or "closing_balance"
    if order_field not in fields_needed:
        # 兜底：order_field 不在 field_map 中 → 用首个 field
        order_field = next(iter(fields_needed), "closing_balance")

    exploded: list[dict[str, Any]] = []
    for aux_code, slot in bucket.items():
        order_val = slot["fields"].get(order_field) or Decimal("0")
        if exclude_zero and order_val == Decimal("0"):
            # closing 为 0 但 opening 非 0 时，不视为「空辅助账」 — 仅以 order_field 过滤
            # 但若所有 fields 都是 0，确认无数据 → 跳过
            if all(v == Decimal("0") for v in slot["fields"].values()):
                continue
            # 仅 order_field 为 0 但其他字段有值 → 保留
        values: dict[str, Decimal | None] = {}
        for col_id, field in field_map.items():
            values[col_id] = slot["fields"].get(field)
        label = slot["aux_name"] or aux_code
        exploded.append(
            {
                "label": label,
                "values": values,
                "aux_code": aux_code,
            }
        )

    # 排序：按 |order_field| 降序；并列时按 aux_code 字典序升序确定性
    def _sort_key(item: dict[str, Any]) -> tuple:
        v = item["values"].get(_ORDER_COL_FOR_FIELD(field_map, order_field))
        magnitude = abs(v) if isinstance(v, Decimal) else Decimal("0")
        return (-magnitude, item["aux_code"])

    exploded.sort(key=_sort_key)

    top_n = binding.get("top_n")
    if isinstance(top_n, int) and top_n > 0:
        exploded = exploded[:top_n]

    return exploded


def _ORDER_COL_FOR_FIELD(field_map: dict[str, str], field: str) -> str:
    """从 field_map 反查 col_id（首个映射到 field 的 col_id）."""
    for col_id, f in field_map.items():
        if f == field:
            return col_id
    return next(iter(field_map.keys()), "col_amount_end")


__all__ = ["explode_aux_balance"]
