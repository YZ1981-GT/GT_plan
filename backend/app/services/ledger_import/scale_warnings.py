"""F42 / design D30 — detect 阶段规模异常检测。

本模块在 detect 返回结果的基础上附加 ``scale_warnings`` 数组，作为 submit
阶段的强制确认依据（see ``routers/ledger_import_v2.py::submit_import``）。

两类警告：

- **EMPTY_LEDGER_WARNING**：``total_rows_estimate < 10``
  —— 数据量过少（空文件/误传），极可能是操作失误。
- **SUSPICIOUS_DATASET_SIZE**：相对同 project 历史 ``active`` 数据集 total
  的均值，比例 ``< 0.1`` 或 ``> 10`` —— 规模异常（同 project 从未见过这个
  数量级），可能是错选年度/误传其他客户的数据。

每个警告元素结构（对齐 design D30）：

    {
        "code": "EMPTY_LEDGER_WARNING" | "SUSPICIOUS_DATASET_SIZE",
        "severity": "warning",
        "message": "数据量过少（N 行）" | "规模异常：当前 N vs 历史均值 M (X.Y×)",
    }

设计决策：

1. 历史均值从 ``LedgerDataset.record_summary`` 的四张 Tb* 表行数累加得到
   （``tb_balance + tb_ledger + tb_aux_balance + tb_aux_ledger``），与
   ``total_rows_estimate`` 语义对齐（均为"四表总行数"）。
2. 若 project 没有 ``active`` 历史数据集（首次导入），``SUSPICIOUS`` 规则
   直接跳过——第一次导入无基线可比。
3. 本函数 **只返回警告列表**，不写 DB、不改 detection 对象，调用方负责
   把 warnings 拼进响应。
4. ``check_scale_warnings`` 是 async 以便在 FastAPI 路由内直接 await；但
   内部 SQL 只一次聚合查询，不会成为热点。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.dataset_models import DatasetStatus, LedgerDataset


# ---------------------------------------------------------------------------
# 常量（阈值集中在此，便于未来 config.py 覆盖）
# ---------------------------------------------------------------------------

EMPTY_ROW_THRESHOLD = 10
"""低于该行数直接视为 EMPTY_LEDGER_WARNING。"""

SUSPICIOUS_MIN_RATIO = 0.1
"""新数据集相对历史均值 < 此值 → SUSPICIOUS_DATASET_SIZE。"""

SUSPICIOUS_MAX_RATIO = 10.0
"""新数据集相对历史均值 > 此值 → SUSPICIOUS_DATASET_SIZE。"""


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------


async def check_scale_warnings(
    detection: Any,
    project_id: UUID,
    db: AsyncSession,
) -> list[dict]:
    """生成 detect 阶段的规模异常警告。

    Args:
        detection: ``LedgerDetectionResult`` 或任何含 ``total_rows_estimate``
            属性/键的对象。通常是 ``ledger_import_v2.detect_files`` 内部
            对 ``LedgerDetectionResult`` 做 ``model_dump`` 之前的快照，也可
            直接传 dict（``{"total_rows_estimate": N}``）。
        project_id: 当前项目 UUID，用于查历史均值。
        db: async session。

    Returns:
        list[dict]：0-2 条警告。空列表表示无规模问题。每条 dict 结构：
            ``{"code": str, "severity": "warning", "message": str}``
    """
    total_rows = _extract_total_rows(detection)
    warnings: list[dict] = []

    # 规则 1：零行/极少行
    if total_rows < EMPTY_ROW_THRESHOLD:
        warnings.append(
            {
                "code": "EMPTY_LEDGER_WARNING",
                "severity": "warning",
                "message": f"数据量过少（{total_rows} 行）",
            }
        )

    # 规则 2：相对历史均值异常（仅当 total_rows > 0 且项目有历史时才评估）
    if total_rows > 0:
        history_mean = await _compute_history_mean(db, project_id)
        if history_mean is not None and history_mean > 0:
            ratio = total_rows / history_mean
            if ratio < SUSPICIOUS_MIN_RATIO or ratio > SUSPICIOUS_MAX_RATIO:
                warnings.append(
                    {
                        "code": "SUSPICIOUS_DATASET_SIZE",
                        "severity": "warning",
                        "message": (
                            f"规模异常：当前 {total_rows} vs 历史均值 "
                            f"{int(history_mean)} ({ratio:.1f}×)"
                        ),
                    }
                )

    return warnings


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _extract_total_rows(detection: Any) -> int:
    """兼容 Pydantic model / dict 两种入参。

    - ``LedgerDetectionResult`` 本身没有 ``total_rows_estimate`` 字段，
      该字段是 router 层在 detect 响应中追加的；调用方通常传入一个已
      携带该字段的 dict 或包装对象。
    - 如果 detection 既没有属性也没有键，则回退为 0（触发 empty 警告
      是无害的保守策略）。
    """
    if isinstance(detection, dict):
        value = detection.get("total_rows_estimate", 0)
    else:
        value = getattr(detection, "total_rows_estimate", 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


async def _compute_history_mean(
    db: AsyncSession,
    project_id: UUID,
) -> float | None:
    """计算 project 历史 ``active`` 数据集的四表总行数均值。

    - 只统计 ``status == active`` 的数据集（不含 superseded / rolled_back，
      它们不代表"当前口径下的正常规模"）。
    - 每个数据集的 total 从 ``record_summary`` 的四表键累加；任一键缺失
      按 0 计（容错）；如果 ``record_summary`` 为空或整条数据集 total=0，
      该条不进入均值（避免把初始化/空数据集拉低均值）。
    - 如果 project 没有任何有效历史数据集，返回 ``None``（调用方跳过规则）。
    """
    stmt = select(LedgerDataset.record_summary).where(
        LedgerDataset.project_id == project_id,
        LedgerDataset.status == DatasetStatus.active,
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return None

    totals: list[int] = []
    for (summary,) in rows:
        if not summary:
            continue
        total = 0
        for key in ("tb_balance", "tb_ledger", "tb_aux_balance", "tb_aux_ledger"):
            value = summary.get(key) if isinstance(summary, dict) else None
            if isinstance(value, (int, float)):
                total += int(value)
        if total > 0:
            totals.append(total)

    if not totals:
        return None
    return sum(totals) / len(totals)


__all__ = [
    "check_scale_warnings",
    "EMPTY_ROW_THRESHOLD",
    "SUSPICIOUS_MIN_RATIO",
    "SUSPICIOUS_MAX_RATIO",
]
