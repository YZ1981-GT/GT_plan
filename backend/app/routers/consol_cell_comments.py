"""单元格批注与复核标记 API — 支持所有模块的单元格级批注和复核状态持久化

TODO: 后续迭代时将 raw SQL text() 迁移到 ORM（ConsolCellComment 模型已就绪）

表结构：consol_cell_comments
  - project_id + year + module + sheet_key + row_idx + col_idx 唯一定位一个单元格
  - comment_type: 'comment' | 'review'
  - comment: 批注文本（review 类型可为空）
  - status: 复核状态 'reviewed' | 'pending' | 'rejected'
  - created_by / updated_at: 审计留痕

API:
  GET  /api/cell-comments/{project_id}/{year}/{module}           — 加载模块下所有批注/复核
  GET  /api/cell-comments/{project_id}/{year}/{module}/{sheet_key} — 加载某表的批注/复核
  PUT  /api/cell-comments/{project_id}/{year}                    — 保存单个批注/复核（upsert）
  DELETE /api/cell-comments/{project_id}/{year}/{comment_id}     — 删除单个批注
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User

router = APIRouter(prefix="/api/cell-comments", tags=["cell-comments"])


# ─── 请求/响应模型 ────────────────────────────────────────────────────────────

class CellCommentSave(BaseModel):
    module: str          # 'report' | 'trial_balance' | 'disclosure' | 'consol_report' | 'consol_tb' | 'consol_note'
    sheet_key: str       # 报表类型/附注section_id/底稿sheet_key
    row_idx: int
    col_idx: int
    comment_type: str    # 'comment' | 'review'
    comment: str = ''    # 批注文本
    status: str = ''     # 复核状态: 'reviewed' | 'pending' | 'rejected'
    row_name: str = ''   # 行名（显示用）
    col_name: str = ''   # 列名（显示用）


class CellCommentResponse(BaseModel):
    id: str
    project_id: str
    year: int
    module: str
    sheet_key: str
    row_idx: int
    col_idx: int
    comment_type: str
    comment: str
    status: str
    row_name: str
    col_name: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None





def _row_to_response(row, project_id: str, year: int) -> CellCommentResponse:
    return CellCommentResponse(
        id=str(row[0]),
        project_id=project_id,
        year=year,
        module=row[1],
        sheet_key=row[2],
        row_idx=row[3],
        col_idx=row[4],
        comment_type=row[5],
        comment=row[6] or '',
        status=row[7] or '',
        row_name=row[8] or '',
        col_name=row[9] or '',
        created_at=str(row[10]) if row[10] else None,
        updated_at=str(row[11]) if row[11] else None,
    )


# ─── GET: 加载模块下所有批注/复核 ─────────────────────────────────────────────
@router.get("/{project_id}/{year}/{module}", response_model=list[CellCommentResponse])
async def get_module_comments(
    project_id: UUID, year: int, module: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    result = await db.execute(
        text("""
            SELECT id, module, sheet_key, row_idx, col_idx, comment_type,
                   comment, status, row_name, col_name, created_at, updated_at
            FROM consol_cell_comments
            WHERE project_id = :pid AND year = :y AND module = :mod
            ORDER BY sheet_key, row_idx, col_idx
        """),
        {"pid": str(project_id), "y": year, "mod": module},
    )
    return [_row_to_response(r, str(project_id), year) for r in result.fetchall()]


# ─── GET: 加载某表的批注/复核 ─────────────────────────────────────────────────
@router.get("/{project_id}/{year}/{module}/{sheet_key}", response_model=list[CellCommentResponse])
async def get_sheet_comments(
    project_id: UUID, year: int, module: str, sheet_key: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    result = await db.execute(
        text("""
            SELECT id, module, sheet_key, row_idx, col_idx, comment_type,
                   comment, status, row_name, col_name, created_at, updated_at
            FROM consol_cell_comments
            WHERE project_id = :pid AND year = :y AND module = :mod AND sheet_key = :sk
            ORDER BY row_idx, col_idx
        """),
        {"pid": str(project_id), "y": year, "mod": module, "sk": sheet_key},
    )
    return [_row_to_response(r, str(project_id), year) for r in result.fetchall()]


# ─── PUT: 保存单个批注/复核（upsert） ─────────────────────────────────────────
@router.put("/{project_id}/{year}", response_model=CellCommentResponse)
async def save_cell_comment(
    project_id: UUID, year: int,
    body: CellCommentSave,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    now = datetime.now(timezone.utc)
    new_id = str(uuid.uuid4())
    try:
        await db.execute(
            text("""
                INSERT INTO consol_cell_comments
                    (id, project_id, year, module, sheet_key, row_idx, col_idx,
                     comment_type, comment, status, row_name, col_name, created_at, updated_at)
                VALUES
                    (:id, :pid, :y, :mod, :sk, :ri, :ci,
                     :ct, :comment, :status, :rn, :cn, :now, :now)
                ON CONFLICT (project_id, year, module, sheet_key, row_idx, col_idx, comment_type)
                DO UPDATE SET comment = :comment, status = :status,
                              row_name = :rn, col_name = :cn, updated_at = :now
            """),
            {
                "id": new_id, "pid": str(project_id), "y": year,
                "mod": body.module, "sk": body.sheet_key,
                "ri": body.row_idx, "ci": body.col_idx,
                "ct": body.comment_type, "comment": body.comment,
                "status": body.status, "rn": body.row_name, "cn": body.col_name,
                "now": now,
            },
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Save failed: {str(e)}")

    # 查询实际保存的记录（可能是 upsert 更新的旧 id）
    result = await db.execute(
        text("""
            SELECT id, module, sheet_key, row_idx, col_idx, comment_type,
                   comment, status, row_name, col_name, created_at, updated_at
            FROM consol_cell_comments
            WHERE project_id = :pid AND year = :y AND module = :mod
              AND sheet_key = :sk AND row_idx = :ri AND col_idx = :ci AND comment_type = :ct
        """),
        {"pid": str(project_id), "y": year, "mod": body.module, "sk": body.sheet_key,
         "ri": body.row_idx, "ci": body.col_idx, "ct": body.comment_type},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=500, detail={"message": "保存成功但回读失败", "message_en": "Save succeeded but read-back failed"})
    return _row_to_response(row, str(project_id), year)


# ─── DELETE: 删除单个批注 ─────────────────────────────────────────────────────
@router.delete("/{project_id}/{year}/{comment_id}")
async def delete_cell_comment(
    project_id: UUID, year: int, comment_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    try:
        result = await db.execute(
            text("DELETE FROM consol_cell_comments WHERE id = :cid AND project_id = :pid AND year = :y"),
            {"cid": comment_id, "pid": str(project_id), "y": year},
        )
        await db.commit()
        deleted = result.rowcount
        return {"ok": True, "deleted": deleted}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")
