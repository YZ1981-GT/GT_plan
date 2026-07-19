"""合并工作底稿数据存储 API — 通用 JSON 存储，支持所有 16 张表的保存/加载"""

import json
import uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.services.g7_consol_linkage_service import (
    G7LinkageConfigError,
    G7LinkageConflictError,
    import_g7_linkage,
    preview_g7_linkage,
)

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
    content: dict
    updated_at: str | None = None


class G7LinkageDiffSelection(BaseModel):
    sheet_key: str
    identity: str
    field: str


class G7LinkageImportRequest(BaseModel):
    """G7 联动确认请求；名称映射由用户在预览界面确认。"""

    company_mappings: dict[str, str] = Field(default_factory=dict)
    sheet_keys: list[str] = Field(
        default_factory=lambda: ["info", "cost", "equity_inv"]
    )
    overwrite: bool = False
    expected_versions: dict[str, str] = Field(default_factory=dict)
    # None=整表填空合并；传列表则仅写入勾选字段（可为空列表）
    selected_diffs: list[G7LinkageDiffSelection] | None = None
    apply_suggestion_ids: list[str] = Field(default_factory=list)


@router.get("/g7-linkage/{project_id}/{year}/preview")
async def get_g7_linkage_preview(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """预览 G7→合并工作底稿映射，不产生写入。"""
    try:
        return await preview_g7_linkage(db, project_id, year)
    except G7LinkageConfigError as exc:
        raise HTTPException(status_code=422, detail={"code": "g7_config", "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/g7-linkage/{project_id}/{year}/import")
async def apply_g7_linkage_import(
    project_id: UUID,
    year: int,
    body: G7LinkageImportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    """确认导入 G7 基础数据；默认只填空值，不覆盖合并侧已有值。"""
    try:
        return await import_g7_linkage(
            db,
            project_id,
            year,
            explicit_mappings=body.company_mappings,
            sheet_keys=body.sheet_keys,
            overwrite=body.overwrite,
            expected_versions=body.expected_versions or None,
            selected_diffs=(
                [item.model_dump() for item in body.selected_diffs]
                if body.selected_diffs is not None
                else None
            ),
            apply_suggestion_ids=body.apply_suggestion_ids or None,
        )
    except G7LinkageConflictError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "g7_stale",
                "message": str(exc),
                "stale_keys": exc.stale_keys,
            },
        ) from exc
    except G7LinkageConfigError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=422,
            detail={"code": "g7_config", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"G7 linkage import failed: {exc}") from exc


# ─── GET: 加载某张表的数据 ────────────────────────────────────────────────────
@router.get("/{project_id}/{year}/{sheet_key}", response_model=WorksheetDataResponse)
async def get_worksheet_data(
    project_id: UUID, year: int, sheet_key: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    result = await db.execute(
        text("SELECT data, updated_at FROM consol_worksheet_data WHERE project_id = :pid AND year = :y AND sheet_key = :sk"),
        {"pid": str(project_id), "y": year, "sk": sheet_key},
    )
    row = result.fetchone()
    if not row:
        return WorksheetDataResponse(
            project_id=str(project_id), year=year, sheet_key=sheet_key, content={},
        )
    return WorksheetDataResponse(
        project_id=str(project_id), year=year, sheet_key=sheet_key,
        content=row[0] if isinstance(row[0], dict) else {},
        updated_at=str(row[1]) if row[1] else None,
    )


# ─── PUT: 保存某张表的数据（upsert） ─────────────────────────────────────────
@router.put("/{project_id}/{year}/{sheet_key}", response_model=WorksheetDataResponse)
async def save_worksheet_data(
    project_id: UUID, year: int, sheet_key: str,
    body: WorksheetDataSave,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    now = datetime.now(timezone.utc)
    try:
        await db.execute(
            text("""
                INSERT INTO consol_worksheet_data (id, project_id, year, sheet_key, data, created_at, updated_at)
                VALUES (:id, :pid, :y, :sk, CAST(:data AS jsonb), :now, :now)
                ON CONFLICT (project_id, year, sheet_key)
                DO UPDATE SET data = CAST(:data AS jsonb), updated_at = :now
            """),
            {
                "id": str(uuid.uuid4()), "pid": str(project_id), "y": year,
                "sk": sheet_key, "data": json.dumps(body.data, ensure_ascii=False),
                "now": now,
            },
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Save failed: {str(e)}")
    return WorksheetDataResponse(
        project_id=str(project_id), year=year, sheet_key=sheet_key,
        content=body.data, updated_at=str(now),
    )


# ─── GET: 加载项目所有表的数据（批量） ────────────────────────────────────────
@router.get("/{project_id}/{year}", response_model=list[WorksheetDataResponse])
async def get_all_worksheet_data(
    project_id: UUID, year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    result = await db.execute(
        text("SELECT sheet_key, data, updated_at FROM consol_worksheet_data WHERE project_id = :pid AND year = :y"),
        {"pid": str(project_id), "y": year},
    )
    rows = result.fetchall()
    return [
        WorksheetDataResponse(
            project_id=str(project_id), year=year, sheet_key=r[0],
            content=r[1] if isinstance(r[1], dict) else {},
            updated_at=str(r[2]) if r[2] else None,
        )
        for r in rows
    ]


# ─── GET: 提取上年数（从上一年度的期末试算平衡表作为本年期初） ─────────────────
@router.get("/{project_id}/{year}/prior-year/{sheet_key}")
async def get_prior_year_data(
    project_id: UUID, year: int, sheet_key: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """提取上年数：从 year-1 的期末数据中提取，作为本年期初

    例如：请求 /proj/2025/prior-year/consol_tb_balance_sheet_opening
    → 查找 year=2024, sheet_key=consol_tb_balance_sheet_closing 的数据
    """
    # 将 opening 替换为 closing，查上一年度的期末数据
    prior_year = year - 1
    prior_key = sheet_key.replace('_opening', '_closing')

    result = await db.execute(
        text("SELECT data, updated_at FROM consol_worksheet_data WHERE project_id = :pid AND year = :y AND sheet_key = :sk"),
        {"pid": str(project_id), "y": prior_year, "sk": prior_key},
    )
    row = result.fetchone()
    if not row:
        return {
            "found": False,
            "message": f"未找到 {prior_year} 年度的期末数据（{prior_key}）",
            "content": {},
        }
    return {
        "found": True,
        "source_year": prior_year,
        "source_key": prior_key,
        "content": row[0] if isinstance(row[0], dict) else {},
        "updated_at": str(row[1]) if row[1] else None,
    }
