"""四表库共享件 —— `tb_aux_balance`（辅助余额表）按往来单位维度归集.

本模块把 F1 已跑通的 aux 归集通用部分提升为共享件（`_f1_import_export.pick_aux_type`
原为平台唯一正确实现，G7 已直接 import 它）。新循环（K1 是第一个消费者）一律复用，
禁止再抄一份归集逻辑。

🔴 三条四表库铁律（照 F1 实现，禁止照抄 D3/D5/D6/D7 的历史 aux 版本）：

⚠️ 旧注释曾写「历史版本 SQL 引用不存在的列 `period_type`/`balance`，运行必 500」——
   **该理由已过期、事实为假**（2026 实测：`tb_aux_balance` 真实存在 `aux_name` /
   `opening_balance` / `closing_balance` / `account_code` / `is_deleted`，无 `period_type` /
   无裸 `balance`；四家 SQL 只用前者，逐字在真库跑得通、返回真实行、不会 500，
   见 spec `four-table-extraction-entry-completion/evidence/task2-red-baseline-verification.md`）。
   历史版本**真实**的缺陷是：① 裸写 `is_deleted = false` 不走 `get_active_filter`（跨数据集
   双算，实测 2×）；② 直接 `GROUP BY aux_name` 未先锁单一 `aux_type`（同科目挂多维度时双算）；
   ③ 科目码硬编码（`'2203%'` 等）不从报表映射解析；④ 把余额全额塞进账龄首段（伪造账龄分布）。
   结论不变（勿照抄），只是理由改为上述真实缺陷。

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

import logging
from typing import Any, Iterable, Literal, NamedTuple, Sequence

import sqlalchemy as sa

logger = logging.getLogger(__name__)

#: `AuxAggregationResult.reason` 的固定枚举（design Error Handling 段权威六值）。
#: - ``ok``：正常取到 ≥1 行；
#: - ``no_prefixes``：报表映射未解析出任何科目前缀（禁静默用字面量）；
#: - ``no_aux_type``：命中科目但无任何可归集的 aux 维度候选；
#: - ``no_rows``：锁定 aux_type 后聚合出 0 行（真·无数据，**正常空**，不记 ERROR）；
#: - ``no_active_dataset``：预留（当前 `get_active_filter` 无 active 时降级 `is_deleted`，
#:   不在本层区分，保留于枚举供下游端点/未来扩展使用）；
#: - ``error``：内部抛异常并被 fail-open 吞掉（**必记一条 ERROR**，与 `no_rows` 不可混淆）。
AuxAggregationReason = Literal[
    "ok", "no_prefixes", "no_aux_type", "no_rows", "no_active_dataset", "error"
]

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


class AuxAggregationResult(NamedTuple):
    """`aggregate_aux_by_name_ex` 的结构化结果（带可辨别 `reason` 码）.

    fail-open 治理（Requirement 5.1 / 5.2）的核心载体：旧 `aggregate_aux_by_name`
    的三元组 fail-open 契约让"接线错误"伪装成"本项目无此数据"。本结构把 `reason`
    带回调用方，端点据此产出可辨别的中文提示；异常路径另记一条 ERROR 日志，
    使二者在日志上也可分辨（Property 6）。

    字段：
        entries: 归集结果行（无数据时为空 list）。
        aux_type: 锁定的单一 aux 维度（无候选时为 None）。
        total_units: ``len(entries)``。
        reason: 见 :data:`AuxAggregationReason`。
    """

    entries: list[AuxEntry]
    aux_type: str | None
    total_units: int
    reason: AuxAggregationReason


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


async def aggregate_aux_by_name_ex(
    db: Any,
    project_id: str,
    year: int,
    account_prefixes: Sequence[str],
) -> AuxAggregationResult:
    """按**单一 aux_type** 锁定维度后，按 ``aux_name`` 归集辅助余额（带 reason 码）.

    这是 `aggregate_aux_by_name` 的增强版：**保留 fail-open 的返回契约**（异常时
    退回空结果），但异常路径必须 ``logger.exception`` 记一条 ERROR（含
    ``project_id`` / ``year`` / ``account_prefixes``），并把可辨别的 `reason` 带回，
    使"接线错误"与"真无数据"在日志与提示上都可分辨（Requirement 5.1 / 5.2）。

    Args:
        db: `AsyncSession`。
        project_id: 项目 id（字符串）。
        year: 审计年度。
        account_prefixes: 科目原始码前缀集（如 ``['1221']``，来自
            `report_line_accounts` 解析结果的 `gross`，而非硬编码）。

    Returns:
        :class:`AuxAggregationResult`；`reason` 精确说明空结果的成因：
          - 无前缀 → ``no_prefixes``；
          - 无 aux 维度候选 → ``no_aux_type``；
          - 锁定维度后 0 行 → ``no_rows``（**正常空**，不记 ERROR）；
          - 内部异常 → ``error``（**记一条 ERROR**）；
          - 取到 ≥1 行 → ``ok``。

    失败不抛：任何异常都退回 ``([], None, 0, 'error')``（fail-open）。
    """
    from app.models.audit_platform_models import TbAuxBalance
    from app.services.dataset_query import get_active_filter

    prefixes = [str(p).strip() for p in (account_prefixes or []) if str(p or "").strip()]
    if not prefixes:
        return AuxAggregationResult([], None, 0, "no_prefixes")

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
            return AuxAggregationResult([], None, 0, "no_aux_type")

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
    except Exception:  # noqa: BLE001 — fail-open，但**必记 ERROR**（禁静默吞）
        # 🔴 与 `no_rows`（正常空）不可混淆：接线错误（列名拼错、传错 db 形态、
        #    单参 async 误用等）在这里被吞成空结果，若不记 ERROR 就会伪装成
        #    "本项目无此数据"。带上 project/year/前缀便于定位。
        logger.exception(
            "aggregate_aux_by_name_ex 取数异常（fail-open 退回空结果）"
            " project_id=%s year=%s account_prefixes=%s",
            project_id,
            year,
            prefixes,
        )
        try:
            await db.rollback()
        except Exception:
            pass
        return AuxAggregationResult([], None, 0, "error")

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
    if not entries:
        # 锁到了 aux_type 但聚合出 0 行（或全是空 aux_name）——真·无数据，正常空。
        return AuxAggregationResult([], aux_type, 0, "no_rows")
    return AuxAggregationResult(entries, aux_type, len(entries), "ok")


async def aggregate_aux_by_name(
    db: Any,
    project_id: str,
    year: int,
    account_prefixes: Sequence[str],
) -> tuple[list[AuxEntry], str | None, int]:
    """按**单一 aux_type** 锁定维度后，按 ``aux_name`` 归集辅助余额。

    🔴 **薄壳**：委托给 :func:`aggregate_aux_by_name_ex`，只丢弃 `reason` 后返回
    原三元组 ``(entries, aux_type, total_units)``——既有 4 个消费者
    （`_k1_import_export`、`row_name_alignment`、K1 测试的两处 monkeypatch 桩）
    **逐字节零改动**。新消费者应直接用 `_ex` 版消费 `reason`（Requirement 5.2）。

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
    异常时 `_ex` 已记 ERROR，本薄壳不重复记录。
    """
    result = await aggregate_aux_by_name_ex(db, project_id, year, account_prefixes)
    return result.entries, result.aux_type, result.total_units
