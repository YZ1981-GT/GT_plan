"""核对表填写响应 CRUD 端点

GET /api/workpapers/{wp_id}/checklist-responses — 获取已填写数据
PUT /api/workpapers/{wp_id}/checklist-responses — 批量保存（单次提交整章节）

章节适用性: 使用特殊 item_id 前缀 TOC-S01, TOC-S02 等存储章节级 applicable(Y/N)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers/{wp_id}/checklist-responses",
    tags=["checklist-responses"],
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ChecklistResponseItem(BaseModel):
    """单条核对表响应"""
    item_id: str
    conclusion: Optional[str] = None  # 'Y'/'N'/'NA'/null
    remark: Optional[str] = None
    wp_ref: Optional[str] = None


class ChecklistResponseOut(BaseModel):
    """返回给前端的响应"""
    id: uuid.UUID
    item_id: str
    conclusion: Optional[str] = None
    remark: Optional[str] = None
    wp_ref: Optional[str] = None
    updated_by: Optional[uuid.UUID] = None
    updated_at: Optional[str] = None


class BatchSaveRequest(BaseModel):
    """批量保存请求体"""
    project_id: uuid.UUID
    items: list[ChecklistResponseItem]


# ---------------------------------------------------------------------------
# GET — 获取该底稿所有填写数据
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ChecklistResponseOut])
async def get_checklist_responses(
    wp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定底稿的所有核对表填写响应（含章节适用性）"""
    result = await db.execute(
        text("""
            SELECT id, item_id, conclusion, remark, wp_ref, updated_by, updated_at
            FROM checklist_responses
            WHERE wp_id = :wp_id
            ORDER BY item_id
        """),
        {"wp_id": str(wp_id)},
    )
    rows = result.fetchall()
    return [
        ChecklistResponseOut(
            id=row.id,
            item_id=row.item_id,
            conclusion=row.conclusion,
            remark=row.remark,
            wp_ref=row.wp_ref,
            updated_by=row.updated_by,
            updated_at=row.updated_at.isoformat() if row.updated_at else None,
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# PUT — 批量保存（UPSERT 整章节）
# ---------------------------------------------------------------------------


@router.put("", response_model=list[ChecklistResponseOut])
async def batch_save_checklist_responses(
    wp_id: uuid.UUID,
    body: BatchSaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量保存核对表填写数据（UPSERT by wp_id + item_id）

    支持条目级填写和章节适用性（item_id 前缀 TOC-S01 等）。
    """
    if not body.items:
        return []

    now = datetime.now(timezone.utc)

    # UPSERT: INSERT ... ON CONFLICT (wp_id, item_id) DO UPDATE
    upsert_sql = text("""
        INSERT INTO checklist_responses (project_id, wp_id, item_id, conclusion, remark, wp_ref, updated_by, created_at, updated_at)
        VALUES (:project_id, :wp_id, :item_id, :conclusion, :remark, :wp_ref, :updated_by, :now, :now)
        ON CONFLICT (wp_id, item_id) DO UPDATE SET
            conclusion = EXCLUDED.conclusion,
            remark = EXCLUDED.remark,
            wp_ref = EXCLUDED.wp_ref,
            updated_by = EXCLUDED.updated_by,
            updated_at = EXCLUDED.updated_at
        RETURNING id, item_id, conclusion, remark, wp_ref, updated_by, updated_at
    """)

    try:
        results = await _do_batch_save(db, wp_id, body, current_user, upsert_sql, now)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("checklist_responses batch_save 未预期异常: wp_id=%s error=%s", wp_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"保存异常: {type(e).__name__}: {str(e)[:200]}")

    await db.commit()
    return results


async def _do_batch_save(db, wp_id, body, current_user, upsert_sql, now):
    """实际执行批量保存逻辑（从主函数抽出以支持全局 try/except）。"""

    # UPSERT: INSERT ... ON CONFLICT (wp_id, item_id) DO UPDATE
    upsert_sql = text("""
        INSERT INTO checklist_responses (project_id, wp_id, item_id, conclusion, remark, wp_ref, updated_by, created_at, updated_at)
        VALUES (:project_id, :wp_id, :item_id, :conclusion, :remark, :wp_ref, :updated_by, :now, :now)
        ON CONFLICT (wp_id, item_id) DO UPDATE SET
            conclusion = EXCLUDED.conclusion,
            remark = EXCLUDED.remark,
            wp_ref = EXCLUDED.wp_ref,
            updated_by = EXCLUDED.updated_by,
            updated_at = EXCLUDED.updated_at
        RETURNING id, item_id, conclusion, remark, wp_ref, updated_by, updated_at
    """)

    results = []
    for item in body.items:
        # Validate conclusion value
        if item.conclusion is not None:
            # TOC-前缀 = 章节适用性，用 Y/N
            if item.item_id.startswith("TOC-"):
                if item.conclusion not in ("Y", "N"):
                    raise HTTPException(
                        status_code=422,
                        detail=f"章节适用性 conclusion 值必须为 'Y'/'N' 或 null，收到: '{item.conclusion}'",
                    )
            else:
                allowed = ("Y", "X/I", "X/W", "N/A")
                if item.item_id.endswith("-sign-status"):
                    allowed = ("pending", "sent", "signed")
                elif item.item_id.startswith(("A17-1-ch", "A18-2")):
                    allowed = ("Y", "N", "done", "pending")
                elif item.item_id.endswith("-sign") and item.item_id.startswith(("A21-", "A22-", "A23-", "A24-", "A25-")):
                    allowed = ("pass", "reject")
                elif item.item_id.endswith("-record") and item.item_id.startswith(("A21-", "A22-", "A23-", "A24-", "A25-")):
                    allowed = ("done",)
                elif "-chk-" in item.item_id and item.item_id.startswith(("A21-", "A22-", "A23-", "A24-", "A25-")):
                    allowed = ("Y", "N", "NA")
                if item.conclusion not in allowed:
                    raise HTTPException(
                        status_code=422,
                        detail=f"conclusion 值无效，收到: '{item.conclusion}'",
                    )

        try:
            row = await db.execute(
                upsert_sql,
                {
                    "project_id": str(body.project_id),
                    "wp_id": str(wp_id),
                    "item_id": item.item_id,
                    "conclusion": item.conclusion,
                    "remark": item.remark,
                    "wp_ref": item.wp_ref,
                    "updated_by": str(current_user.id),
                    "now": now,
                },
            )
        except Exception as e:
            logger.error(
                "checklist_responses UPSERT 失败 wp_id=%s item_id=%s: %s",
                wp_id, item.item_id, e,
            )
            raise HTTPException(status_code=500, detail=f"保存失败: {item.item_id}: {str(e)[:200]}")
        r = row.fetchone()
        results.append(
            ChecklistResponseOut(
                id=r.id,
                item_id=r.item_id,
                conclusion=r.conclusion,
                remark=r.remark,
                wp_ref=r.wp_ref,
                updated_by=r.updated_by,
                updated_at=r.updated_at.isoformat() if r.updated_at else None,
            )
        )

    await db.commit()
    return results
