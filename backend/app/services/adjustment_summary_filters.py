"""调整汇总统计的 where 条件构造（从 ``adjustment_service`` 抽出）。

🔴 为什么单独成文件：``adjustment_service.py`` 已达文件行数门上界
（whitelist 基线 958 + 5%），新增逻辑一律抽伴生模块，不抬白名单基线。

口径与列表端点一致：``allowed_codes`` 为 ``None`` 表示不限（admin / partner /
主管角色）；空集合表示受限且未分配任何含调整科目的循环 ⇒ 什么都不该看到。
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa


def summary_filters(
    adj: Any,
    project_id: UUID,
    year: int,
    allowed_codes: set[str] | None,
) -> list[Any]:
    """汇总统计的公共 where 条件（与调整列表端点同口径）。

    Args:
        adj: ``Adjustment.__table__``（取 ``.c`` 列）。
        project_id / year: 项目与年度。
        allowed_codes: 受限成员的可见科目集合；``None`` = 不限。
    """
    conds: list[Any] = [
        adj.c.project_id == project_id,
        adj.c.year == year,
        adj.c.is_deleted == sa.false(),
    ]
    if allowed_codes is not None:
        # 空集合 ⇒ 什么都不该看到（受限且未分配任何含调整科目的循环）
        conds.append(adj.c.account_code.in_(sorted(allowed_codes) or ["__none__"]))
    return conds
