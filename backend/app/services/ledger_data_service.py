"""账表数据管理服务 — 查询 / 删除 / 增量追加。

职责：
- summarize_ledger_data: 按 project+year+table 聚合行数 + 期间分布
- delete_ledger_data: 按维度删除已导入数据（year/table/period_range）
- detect_new_periods: 增量追加前检测期间差异（file vs existing）
- incremental_append: 增量追加序时账（避免覆盖已有月份）

设计原则：
- 纯 service 层，不依赖 FastAPI
- 余额表（tb_balance/tb_aux_balance）按 year 全量管理
- 序时账（tb_ledger/tb_aux_ledger）按 year + accounting_period 管理
- 所有操作生成 audit log（方便回溯）
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 支持的账表（四表）
LEDGER_TABLES: list[str] = [
    "tb_balance",
    "tb_ledger",
    "tb_aux_balance",
    "tb_aux_ledger",
]

# 按年度全量管理（不含 period 概念）
BALANCE_TABLES: frozenset[str] = frozenset({"tb_balance", "tb_aux_balance"})

# 按 period 分期管理
LEDGER_TABLES_PERIODIC: frozenset[str] = frozenset({"tb_ledger", "tb_aux_ledger"})


async def summarize_ledger_data(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: Optional[int] = None,
) -> dict[str, Any]:
    """查询项目已导入数据的概览。

    优先从 ledger_datasets.record_summary 读取预计算行数（O(1)），
    避免对千万级大表做实时 COUNT。
    """
    result: dict[str, Any] = {"project_id": str(project_id), "tables": {}}

    # 从 active dataset 的 record_summary 获取行数（瞬时查询）
    year_filter = "AND year = :year" if year is not None else ""
    ds_sql = f"""
        SELECT year, record_summary
        FROM ledger_datasets
        WHERE project_id = :pid AND status = 'active' {year_filter}
        ORDER BY year
    """
    params: dict[str, Any] = {"pid": str(project_id)}
    if year is not None:
        params["year"] = year

    try:
        ds_rows = await db.execute(sa.text(ds_sql), params)
        datasets = ds_rows.fetchall()
    except Exception as exc:
        logger.warning("summarize from datasets failed: %s", exc)
        datasets = []

    # 汇总各年度各表行数
    # record_summary key 映射: balance_rows→tb_balance, ledger_rows→tb_ledger 等
    _KEY_MAP = {
        "tb_balance": "balance_rows",
        "tb_ledger": "ledger_rows",
        "tb_aux_balance": "aux_balance_rows",
        "tb_aux_ledger": "aux_ledger_rows",
    }
    for table in LEDGER_TABLES:
        table_data: dict[str, Any] = {"total": 0, "years": {}}
        for ds_row in datasets:
            y = int(ds_row[0])
            summary = ds_row[1] or {}
            if not isinstance(summary, dict):
                continue
            # 尝试两种 key 格式（新格式 balance_rows / 旧格式 tb_balance）
            cnt = summary.get(_KEY_MAP.get(table, table), 0) or summary.get(table, 0)
            if cnt and int(cnt) > 0:
                table_data["total"] += int(cnt)
                table_data["years"][y] = {"total": int(cnt)}
        result["tables"][table] = table_data

    # 序时账补充 period 分布（只查 active 数据，用索引）
    for table in LEDGER_TABLES_PERIODIC:
        table_info = result["tables"].get(table, {})
        if table_info.get("total", 0) == 0:
            continue
        for y in list(table_info.get("years", {}).keys()):
            try:
                period_sql = f"""
                    SELECT
                        EXTRACT(MONTH FROM voucher_date)::int AS period,
                        COUNT(*) AS cnt
                    FROM {table}
                    WHERE project_id = :pid AND year = :yr AND is_deleted = false
                    GROUP BY period
                    ORDER BY period
                """
                prows = await db.execute(sa.text(period_sql), {"pid": str(project_id), "yr": y})
                periods: dict[int, int] = {}
                for prow in prows.all():
                    if prow[0] is not None:
                        periods[int(prow[0])] = int(prow[1])
                table_info["years"][y]["periods"] = periods
            except Exception:
                pass  # period 查询失败不阻断

    return result


async def delete_ledger_data(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    tables: Optional[list[str]] = None,
    periods: Optional[list[int]] = None,
    hard_delete: bool = False,
) -> dict[str, int]:
    """删除账表数据（按年度 + 可选期间/表）。

    S7-10: 默认软删除（is_deleted=true 标记），支持恢复；
    `hard_delete=True` 才真正 DELETE（不可恢复）。

    Args:
        project_id: 项目 UUID
        year: 必填，删除目标年度
        tables: 可选，指定要删除的表（默认全部 4 张）
        periods: 可选，指定要删除的月份（仅对 ledger/aux_ledger 生效；
                 若指定则只删这些月份，未指定则删整个年度）
        hard_delete: 是否硬删（默认 False 即软删，进回收站可恢复）

    Returns:
        {"tb_balance": 1822, "tb_ledger": 5000, ...} 各表影响行数

    注意：
    - 余额表（tb_balance/tb_aux_balance）不支持 period 过滤，periods 参数对它们无效
    - 软删除用 UPDATE is_deleted=true，保留可恢复能力
    - 返回的行数可用于生成审计日志
    """
    if not tables:
        tables = LEDGER_TABLES
    else:
        invalid = set(tables) - set(LEDGER_TABLES)
        if invalid:
            raise ValueError(f"不支持的表: {invalid}")

    deleted: dict[str, int] = {}

    for table in tables:
        use_period_filter = (
            periods is not None
            and len(periods) > 0
            and table in LEDGER_TABLES_PERIODIC
        )

        if hard_delete:
            verb = "DELETE FROM"
            set_clause = ""
        else:
            verb = "UPDATE"
            set_clause = "SET is_deleted = true"

        if use_period_filter:
            if hard_delete:
                sql = f"""
                    DELETE FROM {table}
                    WHERE project_id = :pid AND year = :year
                      AND EXTRACT(MONTH FROM voucher_date)::int = ANY(:periods)
                """
            else:
                sql = f"""
                    UPDATE {table} {set_clause}
                    WHERE project_id = :pid AND year = :year
                      AND EXTRACT(MONTH FROM voucher_date)::int = ANY(:periods)
                      AND is_deleted = false
                """
            params = {
                "pid": str(project_id),
                "year": year,
                "periods": periods,
            }
        else:
            if hard_delete:
                sql = f"DELETE FROM {table} WHERE project_id = :pid AND year = :year"
            else:
                sql = (
                    f"UPDATE {table} {set_clause} "
                    f"WHERE project_id = :pid AND year = :year AND is_deleted = false"
                )
            params = {"pid": str(project_id), "year": year}

        try:
            result = await db.execute(sa.text(sql), params)
            deleted[table] = result.rowcount or 0
            logger.info(
                "%s %d rows from %s (project=%s year=%d periods=%s)",
                "hard-deleted" if hard_delete else "soft-deleted",
                deleted[table], table, project_id, year, periods,
            )
        except Exception:
            logger.exception("delete %s failed", table)
            deleted[table] = -1  # sentinel for error
            raise

    await db.commit()
    return deleted


async def restore_ledger_data(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    tables: Optional[list[str]] = None,
    periods: Optional[list[int]] = None,
) -> dict[str, int]:
    """S7-10: 从回收站恢复软删除的数据（is_deleted=false）。

    参数语义同 delete_ledger_data（只不过反向操作）。
    硬删除的数据无法恢复，此函数只对软删有效。
    """
    if not tables:
        tables = LEDGER_TABLES
    else:
        invalid = set(tables) - set(LEDGER_TABLES)
        if invalid:
            raise ValueError(f"不支持的表: {invalid}")

    restored: dict[str, int] = {}

    for table in tables:
        use_period_filter = (
            periods is not None
            and len(periods) > 0
            and table in LEDGER_TABLES_PERIODIC
        )

        if use_period_filter:
            sql = f"""
                UPDATE {table} SET is_deleted = false
                WHERE project_id = :pid AND year = :year
                  AND EXTRACT(MONTH FROM voucher_date)::int = ANY(:periods)
                  AND is_deleted = true
            """
            params = {"pid": str(project_id), "year": year, "periods": periods}
        else:
            sql = (
                f"UPDATE {table} SET is_deleted = false "
                f"WHERE project_id = :pid AND year = :year AND is_deleted = true"
            )
            params = {"pid": str(project_id), "year": year}

        try:
            result = await db.execute(sa.text(sql), params)
            restored[table] = result.rowcount or 0
            logger.info(
                "restored %d rows in %s (project=%s year=%d periods=%s)",
                restored[table], table, project_id, year, periods,
            )
        except Exception:
            logger.exception("restore %s failed", table)
            restored[table] = -1
            raise

    await db.commit()
    return restored


async def list_trash(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: Optional[int] = None,
) -> dict[str, Any]:
    """S7-10: 列出回收站中的数据（is_deleted=true）。

    Returns:
        {
            "tb_balance": {"total": 1822, "years": {2024: 1822}},
            "tb_ledger": {"total": 10000, "years": {...}},
            ...
        }
    """
    result: dict[str, Any] = {}

    year_filter = "AND year = :year" if year is not None else ""

    for table in LEDGER_TABLES:
        count_sql = f"""
            SELECT year, COUNT(*) AS cnt
            FROM {table}
            WHERE project_id = :pid AND is_deleted = true {year_filter}
            GROUP BY year
            ORDER BY year DESC
        """
        params: dict[str, Any] = {"pid": str(project_id)}
        if year is not None:
            params["year"] = year

        try:
            rows = (await db.execute(sa.text(count_sql), params)).all()
        except Exception as exc:
            logger.warning("list_trash %s failed: %s", table, exc)
            result[table] = {"total": 0, "years": {}, "error": str(exc)}
            continue

        total = 0
        years: dict[int, int] = {}
        for row in rows:
            y, cnt = int(row[0]), int(row[1])
            years[y] = cnt
            total += cnt

        result[table] = {"total": total, "years": years}

    return result


async def detect_existing_periods(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
) -> set[int]:
    """查询项目某年度序时账已存在的月份集合（基于 voucher_date）。"""
    sql = """
        SELECT DISTINCT EXTRACT(MONTH FROM l.voucher_date)::int AS period
        FROM tb_ledger l
        WHERE l.project_id = :pid AND l.year = :year AND l.voucher_date IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM ledger_datasets d
            WHERE d.id = l.dataset_id AND d.status = 'active'
          )
    """
    rows = await db.execute(
        sa.text(sql), {"pid": str(project_id), "year": year}
    )
    return {int(r[0]) for r in rows.all() if r[0] is not None}


def compute_incremental_diff(
    existing_periods: set[int],
    file_periods: set[int],
) -> dict[str, list[int]]:
    """计算增量导入的期间差异。

    Returns:
        {
            "new": [12],           # 新增月份（文件有但库里没有）
            "overlap": [11],       # 重叠月份（文件有且库里也有，需 force 或跳过）
            "only_existing": [10], # 库里有但文件没有（不影响，不返回操作建议）
        }
    """
    return {
        "new": sorted(file_periods - existing_periods),
        "overlap": sorted(file_periods & existing_periods),
        "only_existing": sorted(existing_periods - file_periods),
    }


__all__ = [
    "LEDGER_TABLES",
    "BALANCE_TABLES",
    "LEDGER_TABLES_PERIODIC",
    "summarize_ledger_data",
    "delete_ledger_data",
    "restore_ledger_data",
    "list_trash",
    "detect_existing_periods",
    "compute_incremental_diff",
    "apply_incremental",
]



async def apply_incremental(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    file_periods: list[int],
    overlap_strategy: str = "skip",
) -> dict[str, Any]:
    """S6-15: 增量追加序时账 — 按期间 diff 执行清理。

    只做"清理将要被新导入覆盖的期间"，不做实际的文件解析和写入
    （那部分由 _execute_v2 管线负责）。调用顺序：

        1. 前端选好文件 → 调 `/detect` 获取 file_periods
        2. 前端调用本函数 → 返回 plan（需删的期间 + 行数预估）
        3. 前端确认后 → 调 `/submit` 触发正常导入（走 _execute_v2）
        4. 正常导入对 staged dataset activate 后，旧数据自动被标记 superseded

    Args:
        project_id: 项目 UUID
        year: 目标年度
        file_periods: 新导入文件包含的期间（月份列表，1-12）
        overlap_strategy: 重叠月份策略
            - "skip": 跳过重叠月份（保留旧数据，只补新月份）
            - "overwrite": 覆盖重叠月份（删除旧的，导入新的）

    Returns:
        {
            "diff": {new: [...], overlap: [...], only_existing: [...]},
            "action": {
                "periods_to_delete": [11, 12],  # 将要删除的期间
                "rows_preview": {tb_ledger: N, tb_aux_ledger: M},
            },
            "executed": bool,  # 是否执行了删除（仅 overwrite 策略真执行）
        }
    """
    if overlap_strategy not in ("skip", "overwrite"):
        raise ValueError(f"overlap_strategy must be skip|overwrite, got {overlap_strategy}")

    # 1. 获取现有期间
    existing = await detect_existing_periods(db, project_id=project_id, year=year)

    # 2. 计算 diff
    file_set = set(file_periods)
    diff = compute_incremental_diff(existing, file_set)

    # 3. 决定哪些期间需要删除
    if overlap_strategy == "overwrite":
        # 覆盖策略：删除重叠月份 + 新月份（新月份本来就不存在，删除无害）
        periods_to_delete = sorted(set(diff["overlap"]) | set(diff["new"]))
    else:
        # 跳过策略：只删除新月份（通常这里是空集，除非有脏数据）
        periods_to_delete = diff["new"]

    # 4. 预估行数
    rows_preview: dict[str, int] = {}
    for tbl in LEDGER_TABLES_PERIODIC:
        if periods_to_delete:
            sql = f"""
                SELECT COUNT(*) FROM {tbl}
                WHERE project_id = :pid AND year = :year
                  AND EXTRACT(MONTH FROM voucher_date)::int = ANY(:periods)
            """
            r = await db.execute(
                sa.text(sql),
                {"pid": str(project_id), "year": year, "periods": periods_to_delete},
            )
            rows_preview[tbl] = int(r.scalar() or 0)
        else:
            rows_preview[tbl] = 0

    result: dict[str, Any] = {
        "diff": diff,
        "action": {
            "overlap_strategy": overlap_strategy,
            "periods_to_delete": periods_to_delete,
            "rows_preview": rows_preview,
        },
        "executed": False,
    }

    # 5. 仅 overwrite 策略真实执行删除（清理旧数据）
    if overlap_strategy == "overwrite" and periods_to_delete:
        deleted = await delete_ledger_data(
            db,
            project_id=project_id,
            year=year,
            tables=list(LEDGER_TABLES_PERIODIC),
            periods=periods_to_delete,
        )
        result["executed"] = True
        result["action"]["rows_deleted"] = deleted
        logger.info(
            "incremental overwrite: project=%s year=%d periods=%s deleted=%s",
            project_id, year, periods_to_delete, deleted,
        )

    return result
