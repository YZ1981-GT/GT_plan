"""准则切换端点 — 多准则状态统一（multi-standard-unification）

POST /api/projects/{project_id}/standard/preview  — 切换影响预览（只读，需求 5.1/5.3）
POST /api/projects/{project_id}/standard/convert   — 执行准则切换（用户确认后执行，需求 5.2）

Requirements: 5.1, 5.2, 5.3
Spec: multi-standard-unification

设计要点：
- 两个端点均需认证（``get_current_user``），不创建未认证端点。
- 预览端点完全只读：读当前准则 + 调 ``preview_conversion``（不写库），
  天然满足"用户取消则无变更"（需求 5.3）。
- 执行端点的关键顺序（见下方 convert 实现）：先 ``convert_workpapers``
  （内部跑前置条件检查，preconditions 不满足时在改动权威准则之前即抛错），
  再 ``set_standard`` 持久化统一准则源并发 STANDARD_CHANGED 事件。
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.standard_unification_service import StandardUnificationService
from app.services.wp_standard_conversion_service import (
    WorkpaperConversionPreconditionError,
    WpStandardConversionService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["standard-conversion"])


class StandardConversionRequest(BaseModel):
    """准则切换请求体。

    Attributes:
        new_standard: 目标结构化准则 ``{entity_type, scope, stage}``。
        year: 可选审计年度（用于 STANDARD_CHANGED 事件 payload）。
    """

    new_standard: dict  # {entity_type, scope, stage}
    year: int | None = None


@router.post("/{project_id}/standard/preview")
async def preview_standard_conversion(
    project_id: UUID,
    body: StandardConversionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """准则切换影响预览（只读，需求 5.1/5.3）。

    读取项目当前统一准则作为 ``old_standard``，对目标准则
    ``body.new_standard`` 计算切换将"归档 / 新建 / 保留"的底稿清单。

    本端点不做任何 DB 写入——预览不改变任何状态，故用户取消时天然无变更
    （需求 5.3）。

    Returns:
        ``{
            "old_standard": {...},
            "new_standard": {...},
            "workpapers": {to_archive, to_create, to_retain, counts},
        }``
    """
    std_svc = StandardUnificationService(db)
    wp_svc = WpStandardConversionService(db)

    try:
        old_standard = await std_svc.get_standard(project_id)
        preview = await wp_svc.preview_conversion(
            project_id, old_standard, body.new_standard
        )
    except ValueError as exc:
        # 业务异常（如项目不存在）→ 422
        raise HTTPException(status_code=422, detail=str(exc))

    # --- 附注影响预览（需求 5.1 完整覆盖）---
    notes_preview: dict | None = None
    target_entity_type = (body.new_standard or {}).get("entity_type")
    if body.year is not None and target_entity_type:
        # year 是附注转换预览的必要参数；缺失时跳过（附注转换需要年度维度）
        try:
            from app.services.note_conversion_service import NoteConversionService

            note_svc = NoteConversionService(db)
            note_result = await note_svc.preview_conversion(
                project_id, body.year, target_entity_type
            )
            notes_preview = note_result.to_dict() if hasattr(note_result, "to_dict") else note_result
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "preview_standard_conversion: 附注预览失败 project=%s: %s",
                project_id,
                exc,
            )
            notes_preview = None

    # --- 报表影响预览（需求 5.1 完整覆盖）---
    reports_preview: dict | None = None
    try:
        import sqlalchemy as sa

        from app.models.report_models import FinancialReport

        stale_query = sa.select(sa.func.count()).where(
            FinancialReport.project_id == project_id,
            FinancialReport.is_deleted == sa.false(),
        )
        stale_result = await db.execute(stale_query)
        stale_count = int(stale_result.scalar_one() or 0)
        reports_preview = {"stale_count": stale_count}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "preview_standard_conversion: 报表预览失败 project=%s: %s",
            project_id,
            exc,
        )
        reports_preview = None

    return {
        "old_standard": old_standard,
        "new_standard": body.new_standard,
        "workpapers": preview,
        "notes": notes_preview,
        "reports": reports_preview,
    }


@router.post("/{project_id}/standard/convert")
async def convert_standard(
    project_id: UUID,
    body: StandardConversionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行准则切换（用户确认后执行，需求 5.2）。

    执行步骤（顺序关键）：
    1. 读取当前统一准则作为 ``old_standard``。
    2. ``classify_workpapers`` 分类（共有 / 源独有 / 目标独有）。
    3. ``convert_workpapers`` 执行底稿切换 —— **先于** 准则写入。该方法内部
       会跑 ``check_preconditions``：若前置条件不满足（如存在未保存底稿、项目
       归档、有进行中任务），会在改动任何权威准则之前抛
       ``WorkpaperConversionPreconditionError``，从而保证准则源不被错误更新。
    4. ``set_standard`` 持久化统一准则源（写 ``applicable_standard_v2`` + 双写
       旧字段 + 发 STANDARD_CHANGED 事件，供附注/报表 handler 消费）。

    两个服务共用同一 ``db`` 会话。

    Returns:
        ``{
            "status": "completed",
            "old_standard": {...},
            "new_standard": {...},
            "workpapers": {retained, archived, created},
        }``
    """
    std_svc = StandardUnificationService(db)
    wp_svc = WpStandardConversionService(db)

    try:
        old_standard = await std_svc.get_standard(project_id)
        classification = await wp_svc.classify_workpapers(
            project_id, old_standard, body.new_standard
        )
        # 关键顺序：底稿切换（含前置条件检查）先执行；preconditions 不满足时
        # 在此抛错，权威准则不会被更新。
        result = await wp_svc.convert_workpapers(
            project_id,
            classification,
            body.new_standard,
            changed_by=current_user.id,
        )
        # 底稿切换通过后，再持久化统一准则源并发 STANDARD_CHANGED 事件。
        new_standard = await std_svc.set_standard(
            project_id,
            body.new_standard,
            changed_by=current_user.id,
            year=body.year,
        )
        # 统一 commit 策略：convert_workpapers 和 set_standard 都只 flush，
        # 由 router 在两者都成功后统一提交事务，保证原子性。
        await db.commit()
    except WorkpaperConversionPreconditionError as exc:
        # 前置条件不满足（未保存底稿 / 归档 / 进行中任务）→ 422
        raise HTTPException(status_code=422, detail=str(exc))
    except ValueError as exc:
        # 其他业务异常（如项目不存在）→ 422
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "convert_standard 失败: project=%s new_standard=%s",
            project_id,
            body.new_standard,
        )
        raise HTTPException(status_code=500, detail=f"准则切换失败: {exc}")

    return {
        "status": "completed",
        "old_standard": old_standard,
        "new_standard": new_standard,
        "workpapers": result,
    }
