"""WpTemplateRegistryService — 从 PG wp_template_registry 表读取底稿模板树。

替代原有 JSON 文件读取方式，支持 version 递增 + X-Indicators-Schema-Version 联动。

Requirements: Req 4 (advanced-query-enhancements-p1p2)
"""
import logging
from typing import Any

from sqlalchemy import text, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class WpTemplateRegistryService:
    """底稿模板注册表服务，从 PG 读取替代 JSON 文件读取。"""

    async def load_tree(self, db: AsyncSession) -> list[dict[str, Any]]:
        """从 wp_template_registry 表加载全部主底稿记录。

        Returns:
            List of dicts with keys: wp_code, wp_name, cycle, account_codes, sheets,
            applicable_standard, version, source_origin
        """
        sql = text("""
            SELECT wp_code, wp_name, cycle, account_codes, sheets,
                   applicable_standard, version, source_origin
            FROM wp_template_registry
            ORDER BY cycle, wp_code
        """)
        result = await db.execute(sql)
        rows = result.fetchall()
        return [
            {
                "wp_code": r[0],
                "wp_name": r[1],
                "cycle": r[2],
                "account_codes": r[3] if r[3] else [],
                "sheets": r[4] if r[4] else [],
                "applicable_standard": r[5] if r[5] else [],
                "version": r[6],
                "source_origin": r[7],
            }
            for r in rows
        ]

    async def get_max_version(self, db: AsyncSession) -> int:
        """获取当前最大 version 值，用于 X-Indicators-Schema-Version 响应头。"""
        sql = text("SELECT COALESCE(MAX(version), 1) FROM wp_template_registry")
        result = await db.execute(sql)
        return result.scalar() or 1

    async def increment_version(self, db: AsyncSession, wp_code: str) -> int:
        """递增指定 wp_code 的 version 字段，返回新版本号。

        用于模板内容更新时触发前端缓存失效。
        """
        sql = text("""
            UPDATE wp_template_registry
            SET version = version + 1, updated_at = NOW()
            WHERE wp_code = :wp_code
            RETURNING version
        """)
        result = await db.execute(sql, {"wp_code": wp_code})
        row = result.fetchone()
        if row is None:
            logger.warning("increment_version: wp_code=%s not found in registry", wp_code)
            return 1
        await db.commit()
        return row[0]

    async def table_exists(self, db: AsyncSession) -> bool:
        """检查 wp_template_registry 表是否存在（用于降级判断）。"""
        sql = text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'wp_template_registry'
            )
        """)
        result = await db.execute(sql)
        return result.scalar() or False


# Module-level singleton
wp_template_registry_service = WpTemplateRegistryService()
