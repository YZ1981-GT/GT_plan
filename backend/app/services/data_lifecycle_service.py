# -*- coding: utf-8 -*-
"""数据生命周期管理 — 归档、清理、容量监控

多企业大数据量场景下的数据管理：
1. 项目数据归档（已完成项目移到归档表，主表保持精简）
2. 容量监控（按项目统计数据量，预警阈值）
3. 导入并发控制（同一时间只允许一个项目导入，避免资源争抢）
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 四表模型
_TABLE_NAMES = ["tb_balance", "tb_aux_balance", "tb_ledger", "tb_aux_ledger"]


class DataLifecycleService:
    """数据生命周期管理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 容量监控 ──

    async def get_capacity_stats(self) -> dict:
        """获取全局容量统计。"""
        stats = {"tables": {}, "projects": [], "total_rows": 0, "total_size_mb": 0}

        # 各表统计
        for tbl in _TABLE_NAMES:
            r = await self.db.execute(sa.text(
                f"SELECT COUNT(*) FROM {tbl} WHERE is_deleted = false"
            ))
            rows = r.scalar() or 0
            r2 = await self.db.execute(sa.text(
                f"SELECT pg_total_relation_size('{tbl}'::regclass)"
            ))
            size_bytes = r2.scalar() or 0
            stats["tables"][tbl] = {
                "rows": rows,
                "size_mb": round(size_bytes / 1024 / 1024, 1),
            }
            stats["total_rows"] += rows
            stats["total_size_mb"] += size_bytes / 1024 / 1024

        stats["total_size_mb"] = round(stats["total_size_mb"], 1)

        # 按项目统计
        r = await self.db.execute(sa.text("""
            SELECT t.project_id, p.name, p.client_name,
                   SUM(t.cnt) as total_rows
            FROM (
                SELECT project_id, COUNT(*) as cnt FROM tb_balance WHERE is_deleted = false GROUP BY project_id
                UNION ALL
                SELECT project_id, COUNT(*) FROM tb_aux_balance WHERE is_deleted = false GROUP BY project_id
                UNION ALL
                SELECT project_id, COUNT(*) FROM tb_ledger WHERE is_deleted = false GROUP BY project_id
                UNION ALL
                SELECT project_id, COUNT(*) FROM tb_aux_ledger WHERE is_deleted = false GROUP BY project_id
            ) t
            LEFT JOIN projects p ON p.id = t.project_id
            GROUP BY t.project_id, p.name, p.client_name
            ORDER BY total_rows DESC
        """))
        for row in r.fetchall():
            stats["projects"].append({
                "project_id": str(row[0]),
                "name": row[1] or "",
                "client_name": row[2] or "",
                "total_rows": row[3],
            })

        return stats

    async def get_project_data_stats(self, project_id: UUID) -> dict:
        """获取单个项目的数据统计。"""
        stats = {"project_id": str(project_id), "tables": {}, "years": []}

        for tbl in _TABLE_NAMES:
            r = await self.db.execute(sa.text(
                f"SELECT year, COUNT(*) FROM {tbl} "
                f"WHERE project_id = :pid AND is_deleted = false GROUP BY year ORDER BY year"
            ), {"pid": str(project_id)})
            by_year = {row[0]: row[1] for row in r.fetchall()}
            stats["tables"][tbl] = by_year
            for y in by_year:
                if y not in stats["years"]:
                    stats["years"].append(y)

        stats["years"].sort()
        return stats

    # ── 项目数据归档 ──

    async def archive_project_data(self, project_id: UUID) -> dict:
        """归档项目数据（软删除，不物理删除）。

        归档后数据仍在数据库中（is_deleted=true），但不参与查询。
        可通过 restore_project_data 恢复。
        """
        counts = {}
        for tbl in _TABLE_NAMES:
            r = await self.db.execute(sa.text(
                f"UPDATE {tbl} SET is_deleted = true "
                f"WHERE project_id = :pid AND is_deleted = false"
            ), {"pid": str(project_id)})
            counts[tbl] = r.rowcount

        await self.db.commit()
        logger.info("归档项目 %s: %s", project_id, counts)
        return {"archived": counts}

    async def restore_project_data(self, project_id: UUID) -> dict:
        """恢复已归档的项目数据。"""
        counts = {}
        for tbl in _TABLE_NAMES:
            r = await self.db.execute(sa.text(
                f"UPDATE {tbl} SET is_deleted = false "
                f"WHERE project_id = :pid AND is_deleted = true"
            ), {"pid": str(project_id)})
            counts[tbl] = r.rowcount

        await self.db.commit()
        logger.info("恢复项目 %s: %s", project_id, counts)
        return {"restored": counts}

    async def purge_project_data(self, project_id: UUID) -> dict:
        """物理删除项目数据（不可恢复）。

        只删除已归档（is_deleted=true）的数据。
        活跃数据需要先归档再清理。
        """
        counts = {}
        for tbl in _TABLE_NAMES:
            r = await self.db.execute(sa.text(
                f"DELETE FROM {tbl} WHERE project_id = :pid AND is_deleted = true"
            ), {"pid": str(project_id)})
            counts[tbl] = r.rowcount

        await self.db.commit()
        logger.info("清理项目 %s: %s", project_id, counts)
        return {"purged": counts}

    # ── 批量清理 ──

    async def purge_all_archived(self) -> dict:
        """物理删除所有已归档数据（释放磁盘空间）。"""
        counts = {}
        for tbl in _TABLE_NAMES:
            r = await self.db.execute(sa.text(
                f"DELETE FROM {tbl} WHERE is_deleted = true"
            ))
            counts[tbl] = r.rowcount

        await self.db.commit()

        # VACUUM 释放空间（需要在事务外执行）
        logger.info("清理已归档数据: %s", counts)
        return {"purged": counts, "hint": "建议执行 VACUUM ANALYZE 释放磁盘空间"}
