"""D-cycle 明细表四表库维度归集 —— 可复用聚合（D6-2）.

原 spec: .kiro/specs/d-cycle-tier-a-writeback-detail-seed/  (Requirements 4.3, 4.4 / 决策4)
迁移 spec: .kiro/specs/four-table-extraction-entry-completion/  (Task 4, Requirements 2.3~2.6, 3.1, 3.5, 5.3)

🔴 G-C 迁移（2026 four-table-extraction-entry-completion / Task 4）
------------------------------------------------------------------
本模块**原本内联一份裸 SQL**（`_AUX_QUERY`：`SELECT aux_name ... FROM tb_aux_balance
WHERE ... is_deleted=false GROUP BY aux_name`），带四表库四铁律违规（红基线 ①②③④）：
① 不走 `get_active_filter`（跨数据集双算）；② `GROUP BY aux_name` 未先锁单一
`aux_type`（同科目挂多维度双算）；③ 科目码硬编码 `'1141%'`；④ 把期初/期末余额全额
塞进账龄首段（`agePrior1y=prior` / `ageEnd1y=current` / `receivableWithin1y=current`，
伪造账龄分布）。

迁移后**删除裸 SQL**，统一走共享件：

  * 科目前缀经 `d_aux_import.resolve_d_cycle_gross_prefixes`（报表映射 BS-011 解析，
    兜底 1141 注明 source_ref，治理 ③）。
  * 归集经 `four_table.aux_aggregation.aggregate_aux_by_name_ex`
    （`get_active_filter` 治理 ①；`pick_aux_type` 治理 ②；前缀匹配）。
  * 账龄字段与派生列**留空/交前端 recalc**（治理 ④，Requirement 2.5/5.3；
    Property 4 只写录入列）。

本模块保留两层，供**两个消费者**（HTTP 端点 `d6_import_aux_balance` + P0-2 render
自动 seed `_seed_d6_detail_prefill`）复用同一归集，**不新造第 3/4 套四表库读取**：

  * `build_d6_detail_rows_from_aux(...)` —— **纯函数**（无 I/O）：把归集条目构建为
    D6-2 明细行 dict（只写录入列）。可无 DB 单测。
  * `aggregate_d6_detail_rows(db, project_id, year, ...)` —— **可复用入口**：
    经共享件 `aggregate_aux_by_name_ex` 归集后调纯函数。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, Sequence
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# D6-2 明细行上限（与 `_d6_import_export._ROW_LIMIT` 一致；此处独立定义避免端点↔服务循环 import）
DEFAULT_ROW_LIMIT = 500


def build_d6_detail_rows_from_aux(
    aux_entries: Iterable[Sequence],
    *,
    row_limit: int = DEFAULT_ROW_LIMIT,
    row_id_factory: Callable[[], str] | None = None,
) -> list[dict]:
    """纯函数：把 1141 归集结果构建为 D6-2 明细行 dict 列表（**只写录入列**）.

    🔴 迁移后只写录入列（Property 4，Requirement 3.3）：合同/客户名（业务键）+ 期初未审
    `priorUnadjusted`。账龄字段（agePrior*/ageEnd*/receivableWithin1y）与派生列
    （priorAudited/endUnadjusted/endAudited/debitAmount/creditAmount 等）**不再写**
    （治理红基线 ④伪造账龄 + Requirement 3.3 禁双写派生列），交前端 recalc / 人工填账龄。

    Args:
        aux_entries: 可迭代的归集条目，每项按位置解构，至少取 ``entry[0]`` 作 aux_name、
            ``entry[1]`` 作期初余额（兼容既有 `(aux_name, prior, current)` 三元组与
            `AuxEntry(aux_name, opening, debit, credit, closing)` 具名元组）。
        row_limit: 行数上限（超出截断）。
        row_id_factory: 生成 rowId 的工厂（默认 `uuid4`）；单测可注入确定性工厂。

    Returns:
        `list[dict]`，每行含录入列（`seqNo` 从 1 起）。无 I/O、可单测。
    """
    make_row_id = row_id_factory or (lambda: str(uuid4()))
    rows_data: list[dict] = []
    for idx, entry in enumerate(list(aux_entries)[:row_limit], 1):
        aux_name = entry[0]
        prior_bal = float(entry[1]) if len(entry) > 1 and entry[1] is not None else 0.0
        name = aux_name or ""
        rows_data.append(
            {
                "rowId": make_row_id(),
                "seqNo": idx,
                "contractName": name,
                "customerName": name,
                "priorUnadjusted": prior_bal,
            }
        )
    return rows_data


async def aggregate_d6_detail_rows(
    db: AsyncSession,
    project_id: str,
    year: int | None = None,
    *,
    row_limit: int = DEFAULT_ROW_LIMIT,
    row_id_factory: Callable[[], str] | None = None,
) -> list[dict]:
    """可复用入口（HTTP 端点 + P0-2 render 自动 seed 共用 / 不新造第 3 套四表库读取）.

    🔴 G-C 迁移后：经共享件 `aggregate_aux_by_name_ex` 归集（`get_active_filter`
    + `pick_aux_type` + 报表映射 BS-011 解析前缀，兜底 1141），再调纯函数构建 D6-2 行。
    无归集数据 / 异常 → 返回 `[]`（fail-open，异常由共享件记 ERROR）。

    Args:
        db: 传入的异步会话（不自建 engine/sessionmaker）。
        project_id: 项目 ID（str）。
        year: 审计年度（active dataset 过滤的必要维度）；None 时用 0（无 active dataset
            则降级 is_deleted 过滤，仍不裸 GROUP BY）。
        row_limit: 行数上限。
        row_id_factory: rowId 工厂（默认 uuid4）。
    """
    from app.services.d_cycle_extraction.d_aux_import import aggregate_d_cycle_aux

    agg = await aggregate_d_cycle_aux(db, str(project_id), int(year or 0), "D6")
    if not agg.entries:
        return []
    # AuxEntry(aux_name, opening, debit, credit, closing) —— 纯函数按位置取 name + opening
    return build_d6_detail_rows_from_aux(
        agg.entries, row_limit=row_limit, row_id_factory=row_id_factory
    )
