"""模板复制 API 路由

POST /api/projects/{project_id}/workpapers/template-copy
  → CopyResult | list[CopyResult]

参数:
- source_wp_id: 单底稿复制源 ID
- source_project_id + audit_cycle: 批量复制整个循环
- overwrite: 是否覆盖目标已有同 wp_code 底稿

设计原则：
- router 层统一 commit（service 只 flush）
- 单底稿复制返回 CopyResult，批量返回 list[CopyResult]

Requirements: 7.1, 7.4, 7.5
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user, require_project_access
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers",
    tags=["wp-template-copy"],
)


# ─── Request Schema ───────────────────────────────────────────────────────────


class TemplateCopyRequest(BaseModel):
    """模板复制请求体"""

    source_wp_id: Optional[UUID] = Field(
        None, description="单底稿复制：源底稿 ID"
    )
    source_project_id: Optional[UUID] = Field(
        None, description="批量复制：源项目 ID"
    )
    audit_cycle: Optional[str] = Field(
        None, description="批量复制：审计循环代号"
    )
    overwrite: bool = Field(
        False, description="是否覆盖目标项目已有同 wp_code 底稿"
    )


# ─── 模板复制端点 ─────────────────────────────────────────────────────────────


@router.post("/template-copy")
async def template_copy(
    project_id: UUID,
    body: TemplateCopyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """跨项目模板复制

    两种模式：
    1. 单底稿复制：指定 source_wp_id
    2. 批量复制：指定 source_project_id + audit_cycle（复制整个循环）

    复制后：状态 draft、清除复核状态、清除业务数据保留结构。
    """
    from app.models.workpaper_models import WorkingPaper, WpIndex
    from app.services.procedure_scope_retention import TrimScopeUnavailable, load_trimmed_scope
    from app.services.wp_export.template_copier import TemplateCopier

    copier = TemplateCopier()
    try:
        trim_scope = await load_trimmed_scope(db, project_id)
    except TrimScopeUnavailable as e:
        raise HTTPException(status_code=503, detail=e.http_detail())

    # 获取目标项目已有 wp_code 集合
    existing_result = await db.execute(
        sa.select(WpIndex.wp_code)
        .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    existing_codes = {row[0] for row in existing_result.all() if row[0]}

    # ─── 模式 1: 单底稿复制 ──────────────────────────────────────────────
    if body.source_wp_id:
        source_wp_data = await _load_source_wp(db, body.source_wp_id)
        # 来源须对当前用户可见（与底稿列表同一可见性口径）；看不见与不存在同一句，不泄露存在性
        if source_wp_data is None or not await _source_visible(
            db, current_user, source_wp_data["project_id"], [source_wp_data["wp_index_id"]],
        ):
            raise HTTPException(status_code=404, detail="源底稿不存在")
        await _reset_target_context(db, current_user, project_id)

        result = copier.copy_single(
            source_wp=source_wp_data,
            target_project_id=project_id,
            overwrite=body.overwrite,
            existing_codes=existing_codes,
        )

        await _apply_retention(db, project_id, [result], trim_scope)
        # 持久化目标底稿记录
        jobs = []
        if result.status == "copied" and getattr(result, "target_record", None):
            jobs.append(await _persist_copy_result(db, result, project_id))

        await _materialize_and_commit(db, project_id, jobs)
        return _result_payload(result)

    # ─── 模式 2: 批量复制整个循环 ────────────────────────────────────────
    if body.source_project_id and body.audit_cycle:
        not_found = HTTPException(
            status_code=404,
            detail=f"源项目循环 {body.audit_cycle} 下无可复制底稿",
        )
        try:
            await assert_project_permission(db, current_user, body.source_project_id, "readonly")
        except HTTPException as exc:
            if exc.status_code == 403:  # 不是来源项目成员：与「没有可复制底稿」同一句
                raise not_found from exc
            raise
        source_wps = await _load_source_cycle(
            db, body.source_project_id, body.audit_cycle
        )
        if not source_wps:
            raise not_found
        visible = await _visible_index_ids(db, current_user, body.source_project_id)
        hidden = [w for w in source_wps if w["wp_index_id"] not in visible]
        source_wps = [w for w in source_wps if w["wp_index_id"] in visible]
        if not source_wps:
            raise not_found
        await _reset_target_context(db, current_user, project_id)

        results = copier.copy_cycle(
            source_workpapers=source_wps,
            target_project_id=project_id,
            audit_cycle=body.audit_cycle,
            overwrite=body.overwrite,
            existing_codes=existing_codes,
        )

        await _apply_retention(db, project_id, results, trim_scope)
        # 持久化所有复制成功的记录
        jobs = []
        for r in results:
            if r.status == "copied" and getattr(r, "target_record", None):
                jobs.append(await _persist_copy_result(db, r, project_id))

        await _materialize_and_commit(db, project_id, jobs)
        payload = [_result_payload(r) for r in results]
        payload += [
            {"source_wp_code": w["wp_code"], "target_wp_id": None, "status": "skipped",
             "message": "无权查看该底稿（未委派给你），未复制"}
            for w in hidden
        ]
        return payload

    # 参数不完整
    raise HTTPException(
        status_code=422,
        detail="请提供 source_wp_id（单底稿）或 source_project_id + audit_cycle（批量）",
    )


# ─── Private Helpers ──────────────────────────────────────────────────────────


def _result_payload(result) -> dict:
    """``CopyResult`` 是 dataclass（没有 ``model_dump``）：原先在 commit 之后调 ``model_dump`` ⇒ 复制已落库、
    接口却 500。``target_record`` 是附加属性，不进响应。"""
    return {
        "source_wp_code": result.source_wp_code,
        "target_wp_id": str(result.target_wp_id) if result.target_wp_id else None,
        "status": result.status,
        "message": result.message,
    }


async def _apply_retention(db: AsyncSession, project_id: UUID, results: list, trim_scope) -> None:
    """复制前按保留范围拦截：已裁 / 在回收站 / 目标已有同码（覆盖未实现，原先撞唯一索引 500）⇒ 跳过。"""
    from app.services.procedure_scope_retention import wp_index_states
    from app.services.wp_export.template_copier import EXISTING_CODE_SKIP_MESSAGE

    copied = [r for r in results if r.status == "copied"]
    states = await wp_index_states(db, project_id, [r.source_wp_code for r in copied])
    for r in copied:
        code = r.source_wp_code
        if trim_scope.is_trimmed(code):
            reason = "该编码已在程序裁剪中标为不执行，未复制"
        elif states.get(code) is True:
            reason = "该编码的底稿在回收站中，请先从回收站恢复，未复制"
        elif states.get(code) is False:
            reason = EXISTING_CODE_SKIP_MESSAGE
        else:
            continue
        r.status, r.message, r.target_wp_id = "skipped", reason, None


async def _load_source_wp(db: AsyncSession, wp_id: UUID) -> dict | None:
    """加载源底稿数据，返回 TemplateCopier 需要的 dict 格式。"""
    from app.models.workpaper_models import WorkingPaper, WpIndex

    result = await db.execute(
        sa.select(WorkingPaper, WpIndex)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.id == wp_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    row = result.first()
    if not row:
        return None

    wp, idx = row
    return {
        "wp_code": idx.wp_code,
        "wp_name": idx.wp_name or "",
        "audit_cycle": idx.audit_cycle or "",
        "status": wp.status,
        "review_status": wp.review_status.value if wp.review_status else "not_submitted",
        "is_deleted": False,
        "file_format": "xlsx",
        "data": wp.parsed_data or {},
        "schema": None,
        "wp_id": wp.id,
        "project_id": wp.project_id,
        "wp_index_id": idx.id,
    }


async def _visible_index_ids(db: AsyncSession, user: User, project_id: UUID) -> frozenset[UUID]:
    """当前用户在来源项目里可见的 wp_index（与底稿列表 / 看板同一口径；纯读、不写拒绝记录）。"""
    from app.services.wp_visibility import VisibilityRoleClassifier
    from app.services.wp_visibility.visibility_query import VisibilityQueryService

    context = await VisibilityRoleClassifier(db).classify(user, project_id)
    return await VisibilityQueryService(db).visible_wp_index_ids(context)


async def _source_visible(db: AsyncSession, user: User, project_id: UUID, wp_index_ids: list[UUID]) -> bool:
    visible = await _visible_index_ids(db, user, project_id)
    return all(i in visible for i in wp_index_ids)


async def _reset_target_context(db: AsyncSession, user: User, project_id: UUID) -> None:
    """来源项目的判定会把 RLS 上下文设成来源项目；写目标项目前设回（同时复核目标 edit 级）。"""
    await assert_project_permission(db, user, project_id, "edit")


async def _materialize_and_commit(db: AsyncSession, project_id: UUID, jobs: list) -> None:
    """给复制出的底稿落本底稿自己的文件（按模板目录生成，不复制来源项目文件内容），再提交；失败清理已落文件。

    🔴 原先 ``file_path=''``：在线编辑拿到空路径，打开时懒加载补的又是模板文件（spec procedure-chain-hardening-and-java-contracts R3）。
    """
    from app.services.wp_generate_file import (
        discard_generated_file,
        load_generation_scenario,
        materialize_workpaper_files,
    )

    if not jobs:
        await db.commit()
        return
    scenario, has_fx = await load_generation_scenario(db, project_id)
    generated = await asyncio.to_thread(
        materialize_workpaper_files, project_id, [job for job, _wp in jobs],
        scenario=scenario, has_foreign_currency=has_fx,
    )
    try:
        for (_job, wp), gen in zip(jobs, generated):
            wp.file_path = str(gen.path)
        await db.commit()
    except BaseException:
        for gen in generated:
            discard_generated_file(gen)
        raise


async def _load_source_cycle(
    db: AsyncSession, source_project_id: UUID, audit_cycle: str
) -> list[dict]:
    """加载源项目指定循环的全部底稿。"""
    from app.models.workpaper_models import WorkingPaper, WpIndex

    result = await db.execute(
        sa.select(WorkingPaper, WpIndex)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == source_project_id,
            WorkingPaper.is_deleted == sa.false(),
            WpIndex.audit_cycle == audit_cycle,
        )
    )
    rows = result.all()

    return [
        {
            "wp_code": idx.wp_code,
            "wp_name": idx.wp_name or "",
            "audit_cycle": idx.audit_cycle or "",
            "status": wp.status,
            "review_status": wp.review_status.value if wp.review_status else "not_submitted",
            "is_deleted": False,
            "file_format": "xlsx",
            "data": wp.parsed_data or {},
            "schema": None,
            "wp_id": wp.id,
            "project_id": wp.project_id,
            "wp_index_id": idx.id,
        }
        for wp, idx in rows
    ]


async def _persist_copy_result(db: AsyncSession, copy_result, project_id: UUID):
    """将复制结果持久化为目标项目的 wp_index + working_paper 记录，返回 ``(落文件任务, 底稿行)``。

    🔴 两个模型之间没有 relationship ⇒ 同一次 flush 里 SQLAlchemy 不知道先后，按类名排序先插 working_paper，
       PG 上外键 ``working_paper_wp_index_id_fkey`` 违例 500（SQLite 测试默认不查外键所以一直是绿的）。
       先 flush 索引行再建底稿行。
    """
    import uuid as uuid_mod

    from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType
    from app.services.wp_generate_file import WorkpaperFileJob

    target_record = getattr(copy_result, "target_record", None)
    if not target_record:
        return None

    # 创建 wp_index 记录
    new_index_id = uuid_mod.uuid4()
    wp_index = WpIndex(
        id=new_index_id,
        wp_code=target_record["wp_code"],
        wp_name=target_record.get("wp_name", ""),
        audit_cycle=target_record.get("audit_cycle", ""),
        project_id=project_id,
        is_deleted=False,
    )
    db.add(wp_index)
    await db.flush()

    # 创建 working_paper 记录
    working_paper = WorkingPaper(
        id=target_record["wp_id"],
        project_id=project_id,
        wp_index_id=new_index_id,
        file_version=1,
        status="draft",
        review_status="not_submitted",
        is_deleted=False,
        file_path="",
        source_type=WpSourceType.template,  # NOT NULL：原先没给 ⇒ 复制一律插入失败
        parsed_data=target_record.get("data", {}),
    )
    db.add(working_paper)

    await db.flush()
    job = WorkpaperFileJob(working_paper.id, wp_index.wp_code, wp_index.wp_name or "")
    return job, working_paper
