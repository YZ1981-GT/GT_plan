"""合并工作底稿数据存储 API — 通用 JSON 存储，支持所有 16 张表的保存/加载"""

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/api/consol-worksheet-data", tags=["consolidation-worksheet-data"])


class WorksheetDataSave(BaseModel):
    """保存请求"""
    sheet_key: str  # info / cost / equity_inv / net_asset / equity_sim / elimination / capital / share_change_1 / ...
    data: dict  # 整张表的 JSON 数据


class WorksheetDataResponse(BaseModel):
    """响应"""
    project_id: str
    year: int
    sheet_key: str
    data: dict
    updated_at: str | None = None


# ─── 确保表存在 ──────────────────────────────────────────────────────────────
_table_created = False

async def ensure_table(db: AsyncSession):
    """首次调用时自动建表"""
    global _table_created
    if _table_created:
        return
    try:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS consol_worksheet_data (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id UUID NOT NULL,
                year INT NOT NULL,
                sheet_key VARCHAR(100) NOT NULL,
                data JSONB NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_by UUID,
                UNIQUE(project_id, year, sheet_key)
            )
        """))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_cwd_project_year ON consol_worksheet_data(project_id, year)"
        ))
        await db.commit()
        _table_created = True
    except Exception:
        await db.rollback()
        _table_created = True  # 表可能已存在，忽略错误


# ─── GET: 加载某张表的数据 ────────────────────────────────────────────────────
@router.get("/{project_id}/{year}/{sheet_key}", response_model=WorksheetDataResponse)
async def get_worksheet_data(
    project_id: str, year: int, sheet_key: str,
    db: AsyncSession = Depends(get_db),
):
    await ensure_table(db)
    result = await db.execute(
        text("SELECT data, updated_at FROM consol_worksheet_data WHERE project_id = :pid AND year = :y AND sheet_key = :sk"),
        {"pid": project_id, "y": year, "sk": sheet_key},
    )
    row = result.fetchone()
    if not row:
        return WorksheetDataResponse(
            project_id=project_id, year=year, sheet_key=sheet_key, data={},
        )
    return WorksheetDataResponse(
        project_id=project_id, year=year, sheet_key=sheet_key,
        data=row[0] if isinstance(row[0], dict) else {},
        updated_at=str(row[1]) if row[1] else None,
    )


# ─── PUT: 保存某张表的数据（upsert） ─────────────────────────────────────────
@router.put("/{project_id}/{year}/{sheet_key}", response_model=WorksheetDataResponse)
async def save_worksheet_data(
    project_id: str, year: int, sheet_key: str,
    body: WorksheetDataSave,
    db: AsyncSession = Depends(get_db),
):
    await ensure_table(db)
    now = datetime.utcnow()
    try:
        await db.execute(
            text("""
                INSERT INTO consol_worksheet_data (id, project_id, year, sheet_key, data, created_at, updated_at)
                VALUES (:id, :pid, :y, :sk, CAST(:data AS jsonb), :now, :now)
                ON CONFLICT (project_id, year, sheet_key)
                DO UPDATE SET data = CAST(:data AS jsonb), updated_at = :now
            """),
            {
                "id": str(uuid.uuid4()), "pid": project_id, "y": year,
                "sk": sheet_key, "data": json.dumps(body.data, ensure_ascii=False),
                "now": now,
            },
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Save failed: {str(e)}")
    return WorksheetDataResponse(
        project_id=project_id, year=year, sheet_key=sheet_key,
        data=body.data, updated_at=str(now),
    )


# ─── GET: 加载项目所有表的数据（批量） ────────────────────────────────────────
@router.get("/{project_id}/{year}", response_model=list[WorksheetDataResponse])
async def get_all_worksheet_data(
    project_id: str, year: int,
    db: AsyncSession = Depends(get_db),
):
    await ensure_table(db)
    result = await db.execute(
        text("SELECT sheet_key, data, updated_at FROM consol_worksheet_data WHERE project_id = :pid AND year = :y"),
        {"pid": project_id, "y": year},
    )
    rows = result.fetchall()
    return [
        WorksheetDataResponse(
            project_id=project_id, year=year, sheet_key=r[0],
            data=r[1] if isinstance(r[1], dict) else {},
            updated_at=str(r[2]) if r[2] else None,
        )
        for r in rows
    ]
