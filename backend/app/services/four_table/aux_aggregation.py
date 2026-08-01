"""四表库共享件 —— `tb_aux_balance`（辅助余额表）按往来单位维度归集.

本模块把 F1 已跑通的 aux 归集通用部分提升为共享件（`_f1_import_export.pick_aux_type`
原为平台唯一正确实现，G7 已直接 import 它）。新循环（K1 是第一个消费者）一律复用，
禁止再抄一份归集逻辑。

🔴 三条四表库铁律（照 F1 实现，D3/D5/D6/D7 的历史 aux 版本引用了不存在的列，勿照抄）：

1. **数据集版本**：经 `get_active_filter` 只取 active dataset（禁裸写 `is_deleted == False`）
   —— aux 数据按数据集版本冗余存储，实测同一余额可存在 2 份。
2. **aux 维度冗余**：同一科目同一余额会在多个 `aux_type`（如「客户」「成本中心」
   「保证金类别」）各存一份 —— 必须**先锁定单一 aux_type** 再按 `aux_name` 归集，
   直接 `GROUP BY aux_name` 会金额双算。
3. **前缀匹配**：账套里科目通常落在子科目（`1221.01` / `1221.12` …），故用前缀
   匹配而非精确等值。

spec: .kiro/specs/k1-extraction-chain-and-note-alignment/
"""

from __future__ import annotations

from typing import Any, Iterable, NamedTuple, Sequence

import sqlalchemy as sa

#: 往来单位维度优先关键词（命中则优先作为归集维度）
#: 与 `_f1_import_export._AUX_TYPE_PREFERRED_KEYWORDS` **逐字同源**（提升时原样搬迁）。
AUX_TYPE_PREFERRED_KEYWORDS = ("客户", "供应商", "往来", "单位", "个人", "职员", "员工")


class AuxEntry(NamedTuple):
    """按 ``aux_name`` 归集后的一条辅助余额。

    字段顺序刻意与 F1 的位置化元组 ``(aux_name, opening, debit, credit, closing)``
    一致 —— `build_f1_detail_rows_from_aux` 按位置解构，NamedTuple 可直接喂它。
    """

    aux_name: str
    opening: float
    debit: float
    credit: float
    closing: float


def pick_aux_type(
    candidates: Iterable[tuple[str, int, float]],
) -> str | None:
    """纯函数：从 ``(aux_type, 行数, 余额绝对值合计)`` 候选中挑唯一归集维度。

    优先含往来单位关键词的维度；其次余额合计更大者；再次行数更多者。
    无候选返回 ``None``。

    🔴 语义与提升前的 `_f1_import_export.pick_aux_type` **逐字一致**（F1 改为
    re-export 薄壳，G7 的 `from ._f1_import_export import pick_aux_type` 零改动）。
    守卫见 `backend/tests/four_table/test_aux_aggregation.py`。
    """
    items = [(str(t or ""), int(n or 0), float(amt or 0)) for t, n, amt in candidates]
    if not items:
        return None
    preferred = [
        it for it in items
        if any(kw in it[0] for kw in AUX_TYPE_PREFERRED_KEYWORDS)
    ]
    pool = preferred or items
    pool.sort(key=lambda it: (abs(it[2]), it[1], it[0]), reverse=True)
    return pool[0][0]


def _prefix_predicate(column: Any, prefixes: Sequence[str]) -> Any:
    """``account_code LIKE '{p}%'`` 的 OR 组合（空前缀集返回恒假）。"""
    clauses = [column.like(f"{p}%") for p in prefixes if str(p or "").strip()]
    if not clauses:
        return sa.false()
    return sa.or_(*clauses)


async def aggregate_aux_by_name(
    db: Any,
    project_id: str,
    year: int,
    account_prefixes: Sequence[str],
) -> tuple[list[AuxEntry], str | None, int]:
    """按**单一 aux_type** 锁定维度后，按 ``aux_name`` 归集辅助余额。

    Args:
        db: `AsyncSession`。
        project_id: 项目 id（字符串）。
        year: 审计年度。
        account_prefixes: 科目原始码前缀集（如 ``['1221']``，来自
            `report_line_accounts` 解析结果的 `gross`，而非硬编码）。

    Returns:
        ``(entries, aux_type, total_units)``；无数据时 ``([], None, 0)``。
        `total_units` == `len(entries)`（截断由调用方按 `row_limit` 处理）。

    失败不抛：任何异常都退回 ``([], None, 0)``（fail-open），由调用方决定提示。
    """
    from app.models.audit_platform_models import TbAuxBalance
    from app.services.dataset_query import get_active_filter

    prefixes = [str(p).strip() for p in (account_prefixes or []) if str(p or "").strip()]
    if not prefixes:
        return [], None, 0

    try:
        active_filter = await get_active_filter(
            db, TbAuxBalance.__table__, project_id, year
        )
        base_where = sa.and_(
            active_filter,
            _prefix_predicate(TbAuxBalance.account_code, prefixes),
        )

        # ① 先定维度（防 aux_type 冗余双算）
        type_rows = (
            await db.execute(
                sa.select(
                    TbAuxBalance.aux_type,
                    sa.func.count().label("n"),
                    sa.func.coalesce(
                        sa.func.sum(
                            sa.func.abs(sa.func.coalesce(TbAuxBalance.closing_balance, 0))
                        ),
                        0,
                    ).label("amt"),
                )
                .where(base_where)
                .group_by(TbAuxBalance.aux_type)
            )
        ).fetchall()
        aux_type = pick_aux_type([(r.aux_type, r.n, r.amt) for r in type_rows])
        if not aux_type:
            return [], None, 0

        # ② 锁定维度后按往来单位名称归集
        agg_rows = (
            await db.execute(
                sa.select(
                    TbAuxBalance.aux_name,
                    sa.func.coalesce(sa.func.sum(TbAuxBalance.opening_balance), 0).label("opening"),
                    sa.func.coalesce(sa.func.sum(TbAuxBalance.debit_amount), 0).label("debit"),
                    sa.func.coalesce(sa.func.sum(TbAuxBalance.credit_amount), 0).label("credit"),
                    sa.func.coalesce(sa.func.sum(TbAuxBalance.closing_balance), 0).label("closing"),
                )
                .where(sa.and_(base_where, TbAuxBalance.aux_type == aux_type))
                .group_by(TbAuxBalance.aux_name)
                .order_by(TbAuxBalance.aux_name)
            )
        ).fetchall()
    except Exception:  # noqa: BLE001 — fail-open，调用方按 entries 为空处理
        try:
            await db.rollback()
        except Exception:
            pass
        return [], None, 0

    entries = [
        AuxEntry(
            aux_name=str(r.aux_name or "").strip(),
            opening=float(r.opening or 0),
            debit=float(r.debit or 0),
            credit=float(r.credit or 0),
            closing=float(r.closing or 0),
        )
        for r in agg_rows
        if str(r.aux_name or "").strip()
    ]
    return entries, aux_type, len(entries)
