"""D-cycle 明细表四表库维度归集 —— 可复用聚合（Wave 0 / Task 1.3 块 C-2）.

spec: .kiro/specs/d-cycle-tier-a-writeback-detail-seed/  (Requirements 4.3, 4.4 / 决策4)

**背景（前置核实结论）**：D6-2 明细表的 `tb_aux_balance` 1402 客户/合同维度归集，
原本**仅内联于 HTTP handler** `_d6_import_export.py::d6_import_aux_balance`（原始 SQL
GROUP BY aux_name + 行构建循环），**无可复用后端函数**。按 R4.4 / 决策4（B）：
若归集仅存在于 HTTP handler，则**先抽取为纯函数（不改原端点行为）** 再供 P0-2 render
自动 seed（Wave 5 / Task 5.1）按名调用。

本模块提供两层（收敛铁律：复用同一 SQL，不新造第 3 套四表库读取）：

  * `build_d6_detail_rows_from_aux(...)` —— **纯函数**（无 I/O）：把 1402 归集结果
    （aux_name / 期初余额 / 期末余额）构建为 D6-2 行 dict（30 列）。可无 DB 单测。
  * `aggregate_d6_detail_rows(db, project_id, ...)` —— **可复用入口**（供 render 按名调用）：
    执行与原端点**逐字节相同**的 tb_aux_balance 1402 GROUP BY aux_name 查询后调纯函数。

原 HTTP 端点 `d6_import_aux_balance` 改为委托 `aggregate_d6_detail_rows` —— 端点行为
（查询口径、行 schema、merge/persist、返回结构）逐字节不变。

注意：**不 import 四表库 ORM**（TbAuxBalance 等），沿用原端点的原始 `sa.text` SQL，
满足契约守卫 G7（明细归集复用既有函数、不新造第 3 套四表库读取 / Property 9）。
"""
from __future__ import annotations

from typing import Callable, Iterable, Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

# D6-2 明细行上限（与 `_d6_import_export._ROW_LIMIT` 一致；此处独立定义避免端点↔服务循环 import）
DEFAULT_ROW_LIMIT = 500

# tb_aux_balance 科目 1402 按客户/合同维度（aux_name）归集期初/期末余额。
# 🔴 与原端点 `d6_import_aux_balance` 逐字节相同的 SQL（复用不新造）。
_AUX_QUERY = """
    SELECT aux_name,
           COALESCE(SUM(CASE WHEN period_type = 'opening' THEN balance ELSE 0 END), 0) AS prior_balance,
           COALESCE(SUM(CASE WHEN period_type = 'closing' THEN balance ELSE 0 END), 0) AS current_balance
    FROM tb_aux_balance
    WHERE project_id = :pid
      AND account_code = '1402'
      AND is_deleted = false
    GROUP BY aux_name
    ORDER BY aux_name
"""


def build_d6_detail_rows_from_aux(
    aux_entries: Iterable[Sequence],
    *,
    row_limit: int = DEFAULT_ROW_LIMIT,
    row_id_factory: Callable[[], str] | None = None,
) -> list[dict]:
    """纯函数：把 1402 归集结果构建为 D6-2 行 dict 列表（30 列，与原端点逐字节一致）.

    Args:
        aux_entries: 可迭代的归集条目，每项按位置解构为 `(aux_name, prior_balance, current_balance)`。
        row_limit: 行数上限（超出截断，与原端点 `aux_rows[:_ROW_LIMIT]` 一致）。
        row_id_factory: 生成 rowId 的工厂（默认 `uuid4`）；单测可注入确定性工厂以断言其余字段。

    Returns:
        `list[dict]`，每行含 D6-2 明细 30 个字段（`seqNo` 从 1 起）。无 I/O、可单测。
    """
    make_row_id = row_id_factory or (lambda: str(uuid4()))
    rows_data: list[dict] = []
    for idx, entry in enumerate(list(aux_entries)[:row_limit], 1):
        aux_name, prior_raw, current_raw = entry[0], entry[1], entry[2]
        prior_bal = float(prior_raw)
        current_bal = float(current_raw)
        name = aux_name or ""
        rows_data.append(
            {
                "rowId": make_row_id(),
                "seqNo": idx,
                "contractName": name,
                "contractType": "工程施工",
                "customerName": name,
                "companyCode": "",
                "relatedPartyType": "非关联方",
                "priorUnadjusted": prior_bal,
                "priorAje": 0,
                "priorRje": 0,
                "priorAudited": prior_bal,
                "agePrior1y": prior_bal,
                "agePrior1to2y": 0,
                "agePrior2to3y": 0,
                "agePrior3yAbove": 0,
                "debitAmount": 0,
                "creditAmount": 0,
                "endUnadjusted": current_bal,
                "endAje": 0,
                "endRje": 0,
                "endAudited": current_bal,
                "ageEnd1y": current_bal,
                "ageEnd1to2y": 0,
                "ageEnd2to3y": 0,
                "ageEnd3yAbove": 0,
                "receivableWithin1y": current_bal,
                "receivableAbove1y": 0,
                "isInConstructionPeriod": "否",
                "creditRiskGroup": "业务类型组合",
                "isConfirmed": "否",
                "postPeriodSettlement": 0,
            }
        )
    return rows_data


async def aggregate_d6_detail_rows(
    db: AsyncSession,
    project_id: str,
    *,
    row_limit: int = DEFAULT_ROW_LIMIT,
    row_id_factory: Callable[[], str] | None = None,
) -> list[dict]:
    """可复用入口（供 P0-2 render 自动 seed 按名调用 / Wave 5 Task 5.1）.

    执行与原端点 `d6_import_aux_balance` 逐字节相同的 tb_aux_balance 1402 GROUP BY aux_name
    查询，然后调 `build_d6_detail_rows_from_aux` 构建 D6-2 行。无归集数据 → 返回 `[]`。

    Args:
        db: 传入的异步会话（不自建 engine/sessionmaker，收敛）。
        project_id: 项目 ID（str）。
        row_limit: 行数上限。
        row_id_factory: rowId 工厂（默认 uuid4）。
    """
    result = await db.execute(sa.text(_AUX_QUERY), {"pid": str(project_id)})
    aux_rows = result.fetchall()
    if not aux_rows:
        return []
    entries = [
        (row.aux_name, row.prior_balance, row.current_balance) for row in aux_rows
    ]
    return build_d6_detail_rows_from_aux(
        entries, row_limit=row_limit, row_id_factory=row_id_factory
    )
