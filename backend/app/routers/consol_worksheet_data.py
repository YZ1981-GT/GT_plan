"""合并工作底稿数据存储 API — 通用 JSON 存储，支持所有 16 张表的保存/加载"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.consol_worksheet_data_models import ConsolWorksheetData
from app.models.core import User
from app.services.g7_consol_linkage_service import (
    G7LinkageConfigError,
    G7LinkageConflictError,
    import_g7_linkage,
    load_linkage_stale_state,
    preview_g7_linkage,
)

router = APIRouter(prefix="/api/consol-worksheet-data", tags=["consolidation-worksheet-data"])


class WorksheetDataSave(BaseModel):
    """保存请求。"""
    sheet_key: str  # info / cost / equity_inv / net_asset / equity_sim / elimination / share_change_1 / ...
    data: dict | list
    # 传入时启用可靠的整数 CAS；省略时保持旧人工整表 PUT 的兼容 upsert 语义。
    expected_version: int | None = Field(default=None, ge=0)


class WorksheetDataResponse(BaseModel):
    """响应。"""
    project_id: str
    year: int
    sheet_key: str
    content: dict | list
    version: int = 0
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


@router.get("/g7-linkage/{project_id}/{year}/stale")
async def get_g7_linkage_stale(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """G7 联动 stale 只读薄端点（Task 6.1）。

    仅委托既有 :func:`load_linkage_stale_state`，不含任何映射/计算逻辑，供
    ConsolWorksheetTabs / GtG7LongTermEquityMain 两侧常驻提示消费。
    """
    return await load_linkage_stale_state(db, project_id, year)


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


# ─── worksheet response helpers ───────────────────────────────────────────────
def _worksheet_content(value: object) -> dict | list:
    """保留数据库中的 JSON 对象/数组形状；损坏的 ORM 值由调用方显式报错。"""
    if isinstance(value, (dict, list)):
        return value
    raise ValueError("工作底稿 JSON 不是对象或数组")


def _worksheet_response(row: ConsolWorksheetData | None, *, project_id: UUID, year: int, sheet_key: str) -> WorksheetDataResponse:
    if row is None:
        return WorksheetDataResponse(
            project_id=str(project_id),
            year=year,
            sheet_key=sheet_key,
            content={},
            version=0,
        )
    try:
        content = _worksheet_content(row.data)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return WorksheetDataResponse(
        project_id=str(project_id),
        year=year,
        sheet_key=sheet_key,
        content=content,
        version=int(row.version or 0),
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


# ─── GET: 加载某张表的数据 ────────────────────────────────────────────────────
@router.get("/{project_id}/{year}/{sheet_key}", response_model=WorksheetDataResponse)
async def get_worksheet_data(
    project_id: UUID, year: int, sheet_key: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    row = (
        await db.execute(
            select(ConsolWorksheetData).where(
                ConsolWorksheetData.project_id == project_id,
                ConsolWorksheetData.year == year,
                ConsolWorksheetData.sheet_key == sheet_key,
            )
        )
    ).scalar_one_or_none()
    return _worksheet_response(
        row, project_id=project_id, year=year, sheet_key=sheet_key
    )


# ─── PUT: 保存某张表的数据（兼容整表 upsert + 可选 CAS） ───────────────────────
@router.put("/{project_id}/{year}/{sheet_key}", response_model=WorksheetDataResponse)
async def save_worksheet_data(
    project_id: UUID, year: int, sheet_key: str,
    body: WorksheetDataSave,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    if body.sheet_key != sheet_key:
        raise HTTPException(status_code=422, detail="请求体 sheet_key 与路径不一致")

    now = datetime.now(timezone.utc)
    try:
        row = (
            await db.execute(
                select(ConsolWorksheetData).where(
                    ConsolWorksheetData.project_id == project_id,
                    ConsolWorksheetData.year == year,
                    ConsolWorksheetData.sheet_key == sheet_key,
                )
            )
        ).scalar_one_or_none()

        if row is None:
            # 空表的逻辑版本为 0；expected_version=0 允许首次 CAS 创建。
            if body.expected_version not in (None, 0):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "worksheet_version_conflict",
                        "message": "工作底稿尚不存在，期望版本必须为 0",
                        "expected_version": body.expected_version,
                        "actual_version": None,
                    },
                )
            row = ConsolWorksheetData(
                project_id=project_id,
                year=year,
                sheet_key=sheet_key,
                data=body.data,
                version=0,
                created_at=now,
                updated_at=now,
                created_by=getattr(user, "id", None),
            )
            db.add(row)
            await db.flush()
        else:
            current_version = int(row.version or 0)
            if (
                body.expected_version is not None
                and current_version != body.expected_version
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "worksheet_version_conflict",
                        "message": "工作底稿已被其他操作修改，请重新加载后再保存",
                        "expected_version": body.expected_version,
                        "actual_version": current_version,
                    },
                )

            # Runtime/CAS 写入必须把版本条件放在 UPDATE 中，避免先读后写覆盖并发用户值。
            conditions = [ConsolWorksheetData.id == row.id]
            if body.expected_version is not None:
                conditions.append(ConsolWorksheetData.version == body.expected_version)
            result = await db.execute(
                update(ConsolWorksheetData)
                .where(*conditions)
                .values(data=body.data, updated_at=now, version=current_version + 1)
            )
            if result.rowcount != 1:
                actual = (
                    await db.execute(
                        select(ConsolWorksheetData.version).where(
                            ConsolWorksheetData.id == row.id
                        )
                    )
                ).scalar_one_or_none()
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "worksheet_version_conflict",
                        "message": "工作底稿已被其他操作修改，请重新加载后再保存",
                        "expected_version": body.expected_version,
                        "actual_version": int(actual) if actual is not None else None,
                    },
                )
            row.data = body.data
            row.version = current_version + 1
            row.updated_at = now

        await db.commit()
        await db.refresh(row)
        return _worksheet_response(
            row, project_id=project_id, year=year, sheet_key=sheet_key
        )
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"工作底稿保存失败：{exc}") from exc


# ─── GET: 加载项目所有表的数据（批量） ────────────────────────────────────────
@router.get("/{project_id}/{year}", response_model=list[WorksheetDataResponse])
async def get_all_worksheet_data(
    project_id: UUID, year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    rows = (
        await db.execute(
            select(ConsolWorksheetData)
            .where(
                ConsolWorksheetData.project_id == project_id,
                ConsolWorksheetData.year == year,
            )
            .order_by(ConsolWorksheetData.sheet_key)
        )
    ).scalars().all()
    return [
        _worksheet_response(
            row, project_id=project_id, year=year, sheet_key=row.sheet_key
        )
        for row in rows
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

    row = (
        await db.execute(
            select(
                ConsolWorksheetData.data,
                ConsolWorksheetData.updated_at,
                ConsolWorksheetData.version,
            )
            .where(
                ConsolWorksheetData.project_id == project_id,
                ConsolWorksheetData.year == prior_year,
                ConsolWorksheetData.sheet_key == prior_key,
            )
        )
    ).first()
    if not row:
        return {
            "found": False,
            "message": f"未找到 {prior_year} 年度的期末数据（{prior_key}）",
            "content": {},
            "version": 0,
        }
    try:
        content = _worksheet_content(row[0])
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "found": True,
        "source_year": prior_year,
        "source_key": prior_key,
        "content": content,
        "version": int(row[2] or 0),
        "updated_at": row[1].isoformat() if row[1] else None,
    }
