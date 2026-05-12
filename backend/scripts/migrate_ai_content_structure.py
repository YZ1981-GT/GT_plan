"""迁移脚本：清洗 parsed_data.ai_content 老数据

R3 需求 11: 历史写入的 ai_content 可能缺少新字段（confirmed_by, confirmed_at,
confirm_action, revised_content, type, source_model 等），本脚本补齐。

运行方式：
    python -m scripts.migrate_ai_content_structure

逻辑：
1. 扫描所有 working_papers 中 parsed_data 含 ai_content 的记录
2. 对 ai_content 列表中每个条目：
   - 补 confirmed_by=null（如果缺失）
   - 补 confirmed_at=null（如果缺失）
   - 补 confirm_action=null（如果缺失）
   - 补 revised_content=null（如果缺失）
   - 补 type="ai_generated"（如果缺失）
   - 补 source_model="unknown"（如果缺失）
   - 补 id=uuid（如果缺失）
   - 补 generated_at=null（如果缺失）
   - 补 confidence=0.0（如果缺失）
   - 补 target_cell=null（如果缺失）
   - 补 target_field=null（如果缺失）
   - 补 source_prompt_version="v1.0"（如果缺失）
3. 仅在有变更时 UPDATE
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 新结构必须包含的字段及其默认值
_REQUIRED_FIELDS: dict[str, Any] = {
    "id": None,  # 特殊处理：生成 uuid
    "type": "ai_generated",
    "source_model": "unknown",
    "source_prompt_version": "v1.0",
    "generated_at": None,
    "confidence": 0.0,
    "content": "",
    "target_cell": None,
    "target_field": None,
    "confirmed_by": None,
    "confirmed_at": None,
    "confirm_action": None,
    "revised_content": None,
}


def normalize_ai_content_item(item: dict) -> tuple[dict, bool]:
    """规范化单个 ai_content 条目，返回 (规范化后的条目, 是否有变更)。"""
    changed = False
    result = dict(item)

    for field, default in _REQUIRED_FIELDS.items():
        if field not in result:
            if field == "id":
                result["id"] = str(uuid.uuid4())
            else:
                result[field] = default
            changed = True

    # 如果有旧的 status 字段但没有 confirm_action，做映射
    if "status" in result and result.get("confirm_action") is None:
        status_map = {
            "accepted": "accept",
            "modified": "revise",
            "rejected": "reject",
            "pending": None,
        }
        old_status = result.get("status", "")
        mapped_action = status_map.get(old_status)
        if mapped_action is not None:
            result["confirm_action"] = mapped_action
            changed = True

    # 如果有旧的 cell_ref 但没有 target_cell，做映射
    if "cell_ref" in result and result.get("target_cell") is None:
        result["target_cell"] = result["cell_ref"]
        changed = True

    return result, changed


def normalize_ai_content_list(ai_content: list) -> tuple[list, bool]:
    """规范化整个 ai_content 列表。"""
    any_changed = False
    normalized = []
    for item in ai_content:
        if not isinstance(item, dict):
            continue
        norm_item, changed = normalize_ai_content_item(item)
        normalized.append(norm_item)
        if changed:
            any_changed = True
    return normalized, any_changed


async def migrate(db_url: str | None = None) -> dict[str, int]:
    """执行迁移，返回统计信息。"""
    if db_url is None:
        from app.core.config import settings
        db_url = settings.DATABASE_URL

    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    stats = {"scanned": 0, "updated": 0, "items_normalized": 0}

    async with async_session() as session:
        # 查询所有有 parsed_data 的底稿
        stmt = sa.text("""
            SELECT id, parsed_data FROM working_papers
            WHERE parsed_data IS NOT NULL
              AND (is_deleted = false OR is_deleted IS NULL)
        """)
        result = await session.execute(stmt)
        rows = result.fetchall()

        for row in rows:
            wp_id, parsed_data = row
            if not isinstance(parsed_data, dict):
                continue

            ai_content = parsed_data.get("ai_content")
            if not ai_content:
                continue
            if not isinstance(ai_content, list):
                # 如果 ai_content 是 dict（旧格式），跳过或包装
                continue

            stats["scanned"] += 1
            normalized, changed = normalize_ai_content_list(ai_content)

            if changed:
                parsed_data["ai_content"] = normalized
                update_stmt = sa.text("""
                    UPDATE working_papers
                    SET parsed_data = :pd
                    WHERE id = :wp_id
                """)
                await session.execute(
                    update_stmt,
                    {"pd": sa.type_coerce(parsed_data, sa.JSON), "wp_id": str(wp_id)},
                )
                stats["updated"] += 1
                stats["items_normalized"] += len(normalized)

        await session.commit()

    await engine.dispose()
    logger.info(
        "Migration complete: scanned=%d, updated=%d, items_normalized=%d",
        stats["scanned"],
        stats["updated"],
        stats["items_normalized"],
    )
    return stats


if __name__ == "__main__":
    asyncio.run(migrate())
