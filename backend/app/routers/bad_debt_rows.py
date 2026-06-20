"""坏账准备明细表 D2-3 嵌套子表 API 路由（bad_debt_rows）

对应 design.md「Components and Interfaces #5 Router」与 requirements Req 8。

前缀：/api/workpapers/{wp_id}/bad-debt-rows
路径参数 wp_id 同时接受 working_paper.id 与 wp_index_id：
  各端点入口调用 resolve_wp_index_id(db, wp_id) 归一为 wp_index_id 再传给 service。
  - 前端 GtBadDebtSheet 经 GtWpRenderer 传来的是 working_paper.id → 解析为 wp_index_id；
  - 直接调 API / 现有测试传 wp_index_id → 解析查不到 working_paper 时回退原值。

铁律：
- service 只 flush 不 commit；本 router 在写操作成功后统一 await db.commit()。
- 路由顺序：静态路径段端点（provision-methods/prefill/aje-suggestion/serialize/
  deserialize/parents）必须声明在 `/{row_id}` 通配端点之前，否则通配截获静态路径
  导致 422 UUID parse error。`/{parent_id}/children` 同理放在 `/{row_id}` 之前。
- 错误映射：
    DuplicateProvisionMethodError → 409
    OptimisticLockError           → 409
    HierarchyError                → 400
    RowNotFoundError              → 404
    deserialize 校验错误列表       → 422
    prefill no-op                 → 200

Requirements: 1.4, 8.2, 8.3, 8.5, 10.5
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.bad_debt_models import PROVISION_METHOD_LABELS, ProvisionMethod
from app.models.core import User
from app.schemas.bad_debt_schemas import (
    BadDebtTreeResponse,
    ChildRowResponse,
    CreateChildRowDTO,
    CreateParentRowDTO,
    ParentRowResponse,
    RowAmounts,
    UpdateRowDTO,
)
from app.services.bad_debt_aje_generator import AjeSuggestion, BadDebtAjeGenerator
from app.services.bad_debt_nested_table_service import (
    DuplicateProvisionMethodError,
    HierarchyError,
    NestedTableService,
    OptimisticLockError,
    RowNotFoundError,
    resolve_wp_index_id,
)
from app.services.bad_debt_prefill_service import BadDebtPrefillService, PrefillResult

router = APIRouter(
    prefix="/api/workpapers/{wp_id}/bad-debt-rows",
    tags=["bad-debt-rows"],
)


# ─── 辅助请求/响应模型 ───────────────────────────────────────────────────────


class ProvisionMethodItem(BaseModel):
    """枚举值 + 中文显示名。"""

    value: str
    label: str


class PrefillRequest(BaseModel):
    """预填请求体：project_id + year（也可经 query 传入）。"""

    project_id: UUID
    year: int


# ─────────────────────────────────────────────────────────────────────────────
# 静态路径端点（必须在 /{row_id} 通配之前声明）
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/provision-methods", response_model=list[ProvisionMethodItem])
async def list_provision_methods(
    wp_id: UUID,
    _user: User = Depends(get_current_user),
) -> list[ProvisionMethodItem]:
    """查可用坏账计提方法枚举列表及中文显示名（Req 1.4）。"""
    return [
        ProvisionMethodItem(value=m.value, label=PROVISION_METHOD_LABELS[m])
        for m in ProvisionMethod
    ]


@router.get("", response_model=BadDebtTreeResponse)
async def get_tree(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> BadDebtTreeResponse:
    """获取完整嵌套树（父行嵌套 children + Summary 合计）。"""
    wp_index_id = await resolve_wp_index_id(db, wp_id)
    return await NestedTableService(db).get_tree(wp_index_id)


@router.post("/parents", response_model=ParentRowResponse, status_code=status.HTTP_201_CREATED)
async def create_parent_row(
    wp_id: UUID,
    data: CreateParentRowDTO,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ParentRowResponse:
    """新增父行（计提类别）。同一底稿 provision_method 重复 → 409。"""
    wp_index_id = await resolve_wp_index_id(db, wp_id)
    svc = NestedTableService(db)
    try:
        result = await svc.create_parent_row(wp_index_id, data)
    except DuplicateProvisionMethodError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    return result


@router.post(
    "/{parent_id}/children",
    response_model=ChildRowResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_child_row(
    wp_id: UUID,
    parent_id: UUID,
    data: CreateChildRowDTO,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ChildRowResponse:
    """在指定父行下新增子行（明细行）。父行不存在 → 404。"""
    svc = NestedTableService(db)
    try:
        result = await svc.create_child_row(parent_id, data)
    except RowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except HierarchyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await db.commit()
    return result


@router.post("/prefill", response_model=PrefillResult)
async def prefill_summary(
    wp_id: UUID,
    body: PrefillRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PrefillResult:
    """从试算表科目 1231 预填 Summary 期初/期末未审数（no-op 时仍 200）。"""
    wp_index_id = await resolve_wp_index_id(db, wp_id)
    result = await BadDebtPrefillService(db).prefill_summary(
        wp_index_id, body.project_id, body.year
    )
    # 只读查询，无写操作；保持一致性 commit 无副作用
    await db.commit()
    return result


@router.get("/aje-suggestion", response_model=AjeSuggestion | None)
async def get_aje_suggestion(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AjeSuggestion | None:
    """获取坏账准备调整分录建议（零差额返回 null）。"""
    wp_index_id = await resolve_wp_index_id(db, wp_id)
    return await BadDebtAjeGenerator(db).generate_suggestion(wp_index_id)


@router.post("/serialize")
async def serialize_tree(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """导出完整嵌套结构为 JSON。"""
    wp_index_id = await resolve_wp_index_id(db, wp_id)
    return await NestedTableService(db).serialize(wp_index_id)


@router.post("/deserialize")
async def deserialize_tree(
    wp_id: UUID,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """从 JSON 恢复完整嵌套结构。校验失败 → 422（返回详细错误列表）。"""
    wp_index_id = await resolve_wp_index_id(db, wp_id)
    svc = NestedTableService(db)
    errors = await svc.deserialize(wp_index_id, payload)
    if errors:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "DESERIALIZE_VALIDATION_FAILED", "errors": errors},
        )
    await db.commit()
    return {"restored": True}


# ─────────────────────────────────────────────────────────────────────────────
# 导出模板 + 导出数据（spec bad-debt-sheet-enhancement Sprint 1）
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/export-template")
async def export_template(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """导出空模板 xlsx（坏账树结构 + 列标题，金额列留空供离线填写）。

    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
    """
    from fastapi.responses import StreamingResponse

    from app.services.bad_debt_export_service import BadDebtExportService

    wp_index_id = await resolve_wp_index_id(db, wp_id)
    svc = BadDebtExportService(db)
    buf = await svc.export_bytes(wp_index_id, template_only=True)
    filename = "bad_debt_template.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export-data")
async def export_data(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """导出含数据的完整坏账准备表 xlsx（父行汇总 + 子行明细 + 合计行）。

    Requirements: 2.1, 2.2, 2.3, 2.4
    """
    from fastapi.responses import StreamingResponse

    from app.services.bad_debt_export_service import BadDebtExportService

    wp_index_id = await resolve_wp_index_id(db, wp_id)
    svc = BadDebtExportService(db)
    buf = await svc.export_bytes(wp_index_id, template_only=False)
    filename = "bad_debt_data.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 导入解析 + 导入写入（spec bad-debt-sheet-enhancement Sprint 2）
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/import-parse")
async def import_parse(
    wp_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """上传 xlsx 文件，解析并与当前坏账树 row_label 行匹配。

    - 文件大小限制 10MB
    - 返回 ImportParseResult（匹配结果列表 + 统计）
    - 格式错误返回 422

    Requirements: 3.1, 3.2, 3.3, 3.8
    """
    from app.services.bad_debt_import_service import BadDebtImportService, ImportParseResult

    # 文件大小限制 10MB
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "FILE_TOO_LARGE",
                "detail": "文件大小超过 10MB 限制",
            },
        )

    wp_index_id = await resolve_wp_index_id(db, wp_id)
    svc = BadDebtImportService(db)
    result: ImportParseResult = await svc.parse_and_match(content, wp_index_id)

    if result.errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "IMPORT_PARSE_ERROR",
                "detail": "; ".join(result.errors),
                "errors": result.errors,
            },
        )

    return result


class ImportCommitRequest(BaseModel):
    """导入写入请求体。"""

    rows: list[dict] = Field(..., description="匹配结果行列表（来自 import-parse 响应）")


@router.post("/import-commit")
async def import_commit(
    wp_id: UUID,
    body: ImportCommitRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """将匹配到的行金额批量写入（仅 matched 行的非 None 值覆盖原值）。

    Requirements: 3.6, 5.3
    """
    from app.services.bad_debt_import_service import BadDebtImportService, ImportRowMatch

    wp_index_id = await resolve_wp_index_id(db, wp_id)

    # 解析请求体中的行数据为 ImportRowMatch 列表
    try:
        parsed_rows = [ImportRowMatch(**r) for r in body.rows]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "IMPORT_COMMIT_VALIDATION_ERROR",
                "detail": f"行数据格式错误: {exc}",
            },
        ) from exc

    svc = BadDebtImportService(db)
    updated_count = await svc.commit_matched_rows(wp_index_id, parsed_rows)
    await db.commit()
    return {"updated_count": updated_count}


# ─────────────────────────────────────────────────────────────────────────────
# 账龄段配置（spec bad-debt-sheet-enhancement Sprint 3）
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/aging-segments")
async def get_aging_segments(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """获取当前底稿的账龄段配置（不存在返回 null）。

    Requirements: 4.1, 4.7
    """
    from app.services.aging_segment_service import AgingSegmentService

    wp_index_id = await resolve_wp_index_id(db, wp_id)
    svc = AgingSegmentService(db)
    config = await svc.get_config(wp_index_id)
    if config is None:
        return None
    return config


@router.put("/aging-segments")
async def save_aging_segments(
    wp_id: UUID,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """保存账龄段配置 + 同步 CREDIT_RISK_AGING 子行。

    请求体：{"preset": "THREE_YEAR"|"FIVE_YEAR"|"CUSTOM", "segments": ["1年以内", ...]}
    校验失败返回 422（error_code: EMPTY_SEGMENT_NAME / DUPLICATE_SEGMENT_NAME）

    Requirements: 4.7, 4.10
    """
    from app.services.aging_segment_service import (
        AgingPreset,
        AgingSegmentConfig,
        AgingSegmentService,
    )

    # 解析请求体为 AgingSegmentConfig
    try:
        config = AgingSegmentConfig(
            preset=AgingPreset(body.get("preset", "CUSTOM")),
            segments=body.get("segments", []),
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "INVALID_AGING_CONFIG",
                "detail": f"配置格式错误: {exc}",
            },
        ) from exc

    # 段名校验
    svc = AgingSegmentService(db)
    errors = svc.validate_segments(config.segments)
    if errors:
        # 提取第一个错误的 error_code
        first_error = errors[0]
        error_code = first_error.split(":")[0] if ":" in first_error else first_error
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": error_code,
                "detail": "; ".join(errors),
                "errors": errors,
            },
        )

    wp_index_id = await resolve_wp_index_id(db, wp_id)
    await svc.save_config(wp_index_id, config)
    await db.commit()
    return {"saved": True}


@router.get("/aging-segments/has-amounts")
async def aging_segments_has_amounts(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """检查 CREDIT_RISK_AGING 子行是否有已填金额（用于前端保存前警告）。

    Requirements: 4.10
    """
    from app.services.aging_segment_service import AgingSegmentService

    wp_index_id = await resolve_wp_index_id(db, wp_id)
    svc = AgingSegmentService(db)
    has = await svc.check_has_amounts(wp_index_id)
    return {"has_amounts": has}


# ─────────────────────────────────────────────────────────────────────────────
# 通配 /{row_id} 端点（必须在静态路径之后声明）
# ─────────────────────────────────────────────────────────────────────────────


@router.put("/{row_id}", response_model=RowAmounts)
async def update_row(
    wp_id: UUID,
    row_id: UUID,
    data: UpdateRowDTO,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> RowAmounts:
    """更新单行金额/标签（乐观锁）。version 冲突 → 409；父行有子行编辑金额 → 400。"""
    svc = NestedTableService(db)
    try:
        result = await svc.update_row(row_id, data)
    except RowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OptimisticLockError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except HierarchyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await db.commit()
    return result


@router.delete("/{row_id}", status_code=status.HTTP_200_OK)
async def delete_row(
    wp_id: UUID,
    row_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """删除行。删父行级联删子行；拒删最后一个父行 → 400；行不存在 → 404。"""
    svc = NestedTableService(db)
    try:
        await svc.delete_row(row_id)
    except RowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except HierarchyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await db.commit()
    return {"deleted": str(row_id)}
