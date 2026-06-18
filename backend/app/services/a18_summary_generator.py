"""a18_summary_generator — A18-1 审计小结生成

从 A17-1 章节内容 + 审计意见 + KAM 生成审计小结框架。
依赖 A17-core 已完成（A17-1 章节数据存在）。

设计（见 a18 requirements）：
- 读取 A17-1 关键章节（ch01 范围/ch08 报表分析/ch12 KAM/ch14 审计结论）
- 组装为审计小结结构化摘要
- 写入 A18-1 对应 docx 模板的预填字段（或返回给前端弹窗展示）
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# A17-1 用于生成小结的关键章节
_KEY_CHAPTERS = [
    ("A17-1-ch01", "审计业务约定范围"),
    ("A17-1-ch06", "重大错报风险应对"),
    ("A17-1-ch08", "已审报表分析"),
    ("A17-1-ch12", "关键审计事项"),
    ("A17-1-ch14", "审计结论"),
]


async def generate_audit_summary(
    db: AsyncSession, project_id: UUID
) -> dict:
    """从 A17-1 章节数据生成审计小结框架。

    Returns:
        {
            "summary_sections": [{"title": str, "content": str}, ...],
            "source": "A17-1",
            "completeness": float (0~1, 已填章节占比),
        }
    """
    # 查找 A17-1 对应的 wp_id
    wp_result = await db.execute(
        text(
            "SELECT wi.id FROM wp_index wi "
            "WHERE wi.project_id = :pid AND wi.wp_code = 'A17-1' "
            "LIMIT 1"
        ),
        {"pid": str(project_id)},
    )
    wp_id = wp_result.scalar_one_or_none()
    if not wp_id:
        logger.info("A18-1 生成：未找到 A17-1 底稿 (project=%s)", project_id)
        return {"summary_sections": [], "source": "A17-1", "completeness": 0.0}

    # 加载关键章节内容
    chapter_ids = [ch[0] for ch in _KEY_CHAPTERS]
    placeholders = ", ".join(f":id_{i}" for i in range(len(chapter_ids)))
    params = {"wp_id": str(wp_id)}
    params.update({f"id_{i}": cid for i, cid in enumerate(chapter_ids)})
    result = await db.execute(
        text(
            f"SELECT item_id, remark FROM checklist_responses "
            f"WHERE wp_id = :wp_id AND item_id IN ({placeholders})"
        ),
        params,
    )
    rows = {r["item_id"]: r["remark"] for r in result.mappings().all()}

    sections: list[dict] = []
    filled = 0
    for ch_id, ch_title in _KEY_CHAPTERS:
        content = rows.get(ch_id, "")
        if content and content.strip():
            filled += 1
        sections.append({"title": ch_title, "content": content or ""})

    completeness = filled / len(_KEY_CHAPTERS) if _KEY_CHAPTERS else 0.0

    return {
        "summary_sections": sections,
        "source": "A17-1",
        "completeness": completeness,
    }
