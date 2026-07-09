"""底稿在线编辑 API 路由（从 working_paper.py 拆出，零行为变更）

在线编辑域端点（与 working_paper 主 router 共用 `/api/projects/{project_id}` 前缀）：
- GET    /working-papers/{wp_id}/online-session   — 在线编辑会话配置
- GET    /working-papers/{wp_id}/univer-data       — Univer 数据
- POST   /working-papers/{wp_id}/univer-save        — Univer 保存
- POST   /working-papers/{wp_id}/sign-status        — 声明书签发状态
- GET    /working-papers/{wp_id}/onlyoffice-config  — OnlyOffice 编辑器配置
- GET    /working-papers/{wp_id}/export-pdf          — 导出 PDF
- POST   /working-papers/{wp_id}/prefill             — 预填充
- POST   /working-papers/{wp_id}/parse               — 解析回写

私有 helper `_prefill_word_template` / `_push_representation_letter_date` 随其唯一调用方迁移。
"""

from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.config import settings
from app.core.database import get_db
from app.deps import require_project_access, require_operation, check_consol_lock
from app.services.project_audit_year import fetch_project_audit_year
from app.models.core import User
from app.services.feature_flags import get_feature_maturity, is_enabled
from app.services.wopi_service import WOPIHostService
from app.models.workpaper_models import WpIndex, WorkingPaper

router = APIRouter(
    prefix="/api/projects/{project_id}",
    tags=["working-papers"],
)


@router.get("/working-papers/{wp_id}/online-session")
async def get_online_edit_session(
    project_id: UUID,
    wp_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """获取在线编辑会话配置。

    在线编辑使用 Univer 纯前端方案；此端点保留向后兼容。
    """
    wp_result = await db.execute(
        sa.select(WorkingPaper.id).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    if wp_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="底稿不存在")

    maturity = get_feature_maturity().get("online_editing", "pilot")
    enabled = is_enabled("online_editing", project_id)
    if not enabled:
        return {
            "enabled": False,
            "maturity": maturity,
            "preferred_mode": "offline",
            "wopi_src": None,
            "access_token": None,
            "editor_base_url": None,
        }

    access_token = WOPIHostService.generate_access_token(
        user_id=current_user.id,
        project_id=project_id,
        file_id=wp_id,
    )
    wopi_base_url = settings.WOPI_BASE_URL.rstrip("/")
    wopi_src = f"{wopi_base_url}/files/{wp_id}?access_token={access_token}"

    # 构造编辑器 URL（向后兼容，前端已使用 Univer）
    onlyoffice_url = getattr(settings, "ONLYOFFICE_URL", "http://localhost:8080").rstrip("/")
    editor_url = f"{onlyoffice_url}/hosting/wopi/cell/edit?WOPISrc={wopi_src}"

    return {
        "enabled": True,
        "maturity": maturity,
        "preferred_mode": "online",
        "wopi_src": wopi_src,
        "access_token": access_token,
        "editor_url": editor_url,
        "editor_base_url": str(request.base_url).rstrip("/"),
        "onlyoffice_url": onlyoffice_url,
    }


@router.get("/working-papers/{wp_id}/univer-data")
async def get_univer_data(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取底稿的 Univer IWorkbookData 格式数据（含所有 Sheet、样式、公式）"""
    result = await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    wp = result.scalar_one_or_none()
    if not wp:
        raise HTTPException(status_code=404, detail="底稿不存在")

    if not wp.file_path:
        raise HTTPException(status_code=404, detail="底稿文件不存在")

    from app.services.xlsx_to_univer import xlsx_to_univer_data
    data = xlsx_to_univer_data(wp.file_path)
    return data


@router.post("/working-papers/{wp_id}/univer-save")
async def save_univer_data(
    project_id: UUID,
    wp_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operation("wp:edit")),
    _lock_check=Depends(check_consol_lock),
):
    """Univer 编辑器保存 — 完整保存链路

    接收 Univer IWorkbookData snapshot，执行：
    1. xlsx 回写（保留样式/公式/多Sheet）
    2. parsed_data['univer_snapshot'] JSONB 落库（三式联动权威数据源）
    3. 版本递增 + 审计留痕
    4. 事件发布（触发五环联动）
    5. 自动解析 parsed_data
    """
    import hashlib
    import json
    import shutil
    from datetime import datetime, timezone
    from pathlib import Path

    snapshot = body.get("snapshot")
    if not snapshot or not snapshot.get("sheets"):
        raise HTTPException(status_code=400, detail="缺少 snapshot 数据")

    result = await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    wp = result.scalar_one_or_none()
    if not wp:
        raise HTTPException(status_code=404, detail="底稿不存在")

    # 需求 45.1/45.2：并发编辑版本冲突检测
    expected_version = body.get("expected_version")
    if expected_version is not None and wp.file_version != expected_version:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "VERSION_CONFLICT",
                "message": "底稿已被他人修改，请刷新后重试",
                "server_version": wp.file_version,
                "expected_version": expected_version,
            },
        )

    if not wp.file_path:
        raise HTTPException(status_code=400, detail="底稿文件路径为空")

    fp = Path(wp.file_path)

    # 1. 版本快照（保存前备份）
    if fp.exists():
        snapshot_dir = fp.parent / ".versions"
        snapshot_dir.mkdir(exist_ok=True)
        snapshot_name = f"{fp.stem}_v{wp.file_version}{fp.suffix}"
        shutil.copy2(fp, snapshot_dir / snapshot_name)

    # 2. xlsx 回写
    from app.services.univer_to_xlsx import univer_data_to_xlsx
    write_result = univer_data_to_xlsx(snapshot, str(fp))

    # 3. [Req 6 单源化] structure.json 写入已移除
    #    权威数据源 = parsed_data['univer_snapshot'] JSONB（步骤 5 写入）
    #    三式联动读取路径已改为从 JSONB 解析，不再依赖 structure.json 文件

    # 4. 哈希校验
    content_hash = hashlib.sha256(fp.read_bytes()).hexdigest()

    # 5. DB 更新（同时把 Univer snapshot 落到 parsed_data 供高级查询零计算读取，
    #    snapshot 已含公式 + Univer 计算后的 v 值，按 sheet/row/col 精确索引）
    old_version = wp.file_version
    # 提取轻量化的 cellData（只保留 v 和 f，剥离样式 s 减小 JSONB 体积）
    try:
        from sqlalchemy.orm.attributes import flag_modified
        from app.services.univer_snapshot_helper import build_slim_snapshot, merge_snapshot_incremental, SNAPSHOT_TOO_LARGE
        existing = dict(wp.parsed_data) if isinstance(wp.parsed_data, dict) else {}
        prev_snap = existing.get("univer_snapshot") if isinstance(existing.get("univer_snapshot"), dict) else None
        # P0-1 + P0-2: slim 化 + 增量合并 + 体积保护
        new_snap = build_slim_snapshot(snapshot, wp.file_version)
        if new_snap is SNAPSHOT_TOO_LARGE:
            # 单次保存的 sheet 太大（> 5MB / > 50K cells），降级只存元数据
            existing["univer_snapshot"] = {
                "sheets": {},
                "sheet_order_names": list((snapshot.get("sheets") or {}).keys()),
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "version": wp.file_version,
                "skipped_reason": "single_save_too_large",
            }
        else:
            existing["univer_snapshot"] = merge_snapshot_incremental(prev_snap, new_snap)
        wp.parsed_data = existing
        flag_modified(wp, "parsed_data")
    except Exception as exc:
        # snapshot 缓存失败不阻塞保存主流程，但要记录便于追查
        import logging as _logging
        _logging.getLogger(__name__).warning("univer_snapshot 落库失败 wp=%s: %s", wp_id, exc)

    # 6. 统一后处理（orchestrator）— file_version++, prefill_stale, updated_at, audit log, event_bus.publish
    try:
        from app.services.workpaper_save_orchestrator import orchestrator as save_orchestrator

        # 推导项目年度
        saved_year: int | None = None
        try:
            from app.models.core import Project
            saved_year = (
                await db.execute(
                    sa.select(sa.extract("year", Project.audit_period_end)).where(
                        Project.id == project_id
                    )
                )
            ).scalar_one_or_none()
            saved_year = int(saved_year) if saved_year is not None else None
        except Exception:
            saved_year = None

        await save_orchestrator.after_save(
            db, wp, current_user,
            trigger="univer_save",
            extra={
                "content_hash": content_hash,
                "sheets": write_result.get("sheets", 0),
                "cells": write_result.get("cells", 0),
                "year": saved_year,
            },
            # expected_version 已在上面早期检查，此处不再重复校验
            expected_version=None,
        )
    except Exception as exc:
        from app.services.workpaper_save_orchestrator import OptimisticLockError
        if isinstance(exc, OptimisticLockError):
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "VERSION_CONFLICT",
                    "message": "底稿已被他人修改，请刷新后重试",
                    "server_version": wp.file_version,
                    "expected_version": expected_version,
                },
            )
        import logging as _logging
        _logging.getLogger(__name__).warning("orchestrator.after_save failed in univer_save wp=%s: %s", wp_id, exc)

    # 8. 自动解析（非阻塞）
    try:
        import asyncio
        from app.services.prefill_engine import parse_workpaper_real

        async def _auto_parse():
            try:
                from app.core.database import async_session
                async with async_session() as parse_db:
                    await parse_workpaper_real(parse_db, project_id, wp_id)
                    await parse_db.commit()
            except Exception as e:
                import logging as _logging
                _logging.getLogger(__name__).warning("后台自动解析底稿失败 wp=%s: %s", wp_id, e)

        asyncio.create_task(_auto_parse())
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).warning("启动后台自动解析任务失败 wp=%s: %s", wp_id, e)

    await db.commit()

    from app.services.wp_parsed_data_service import touch_after_parsed_data_commit

    await touch_after_parsed_data_commit(wp, source="univer_save", project_id=project_id)

    # 获取索引信息
    idx_result = await db.execute(
        sa.select(WpIndex.wp_code).where(WpIndex.id == wp.wp_index_id)
    )
    wp_code = idx_result.scalar_one_or_none() or ""

    return {
        "success": True,
        "version": wp.file_version,
        "content_hash": content_hash,
        "wp_code": wp_code,
        "sheets": write_result.get("sheets", 0),
        "cells": write_result.get("cells", 0),
        "message": f"保存成功 v{wp.file_version}",
    }


class SignStatusUpdateBody(BaseModel):
    """签署状态更新请求体（通用化：支持所有 word-template wp_code）"""
    status: Literal["draft", "pending", "signed"] = Field(
        default="draft", description="签署状态: draft(草稿)/pending(待签署)/signed(已签署)"
    )
    wp_code: Optional[str] = Field(
        default=None, description="目标 wp_code（如 A9-1/A16-1 等）；为空时从底稿索引获取"
    )
    # 向后兼容 A16 旧调用方（version 等效于 wp_code）
    version: Optional[str] = Field(default=None, description="A16 子版本（向后兼容，优先使用 wp_code）")
    sign_date: Optional[str] = Field(default=None, description="签署日期 ISO 格式: 2025-03-15")


@router.post("/working-papers/{wp_id}/sign-status")
async def update_sign_status(
    project_id: UUID,
    wp_id: UUID,
    body: SignStatusUpdateBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("member")),
):
    """更新 word-template 底稿签署状态（通用化，支持所有 word-template wp_code）。

    scope 格式:
    - A16 子版本: word_template:A16:{wp_code}
    - 独立底稿: word_template:{wp_code}

    CW-76: 当 status='signed' 且为 A16 主版本(A16-1~6)时，sign_date 为必填，
    将 push 到 audit_report.representation_letter_date。
    A16-7 补充声明 sign_date 为可选，不 push 到审计报告。
    """
    status = body.status
    # wp_code 优先，向后兼容 version 字段
    target_wp_code = body.wp_code or body.version
    sign_date = body.sign_date

    from app.services.field_override_service import FieldOverrideService

    wp = (await db.execute(
        sa.select(WorkingPaper).where(WorkingPaper.id == wp_id, WorkingPaper.project_id == project_id)
    )).scalar_one_or_none()
    if not wp:
        raise HTTPException(status_code=404, detail="底稿不存在")

    # 从 wp_index 获取底稿编码（当 body 中未指定 wp_code 时使用）
    wp_index_code = (await db.execute(
        sa.select(WpIndex.wp_code).where(WpIndex.id == wp.wp_index_id)
    )).scalar_one_or_none()

    # 最终确定 wp_code：body 指定 > wp_index 查出 > fallback "A16"
    effective_wp_code = target_wp_code or wp_index_code or "A16"

    # CW-76: A16 主版本 signed 时 sign_date 必填
    is_a16_sub = effective_wp_code.startswith("A16-")
    is_a16_main = is_a16_sub and effective_wp_code != "A16-7"
    if status == "signed" and is_a16_main and not sign_date:
        raise HTTPException(status_code=422, detail="A16 主版本签回时必须提供签署日期(sign_date)")

    year_val = await fetch_project_audit_year(db, project_id) or 0

    # scope 确定：A16 子版本 → word_template:A16:{wp_code}，其他 → word_template:{wp_code}
    svc = FieldOverrideService(db)
    if is_a16_sub:
        scope = f"word_template:A16:{effective_wp_code}"
    else:
        scope = f"word_template:{effective_wp_code}"

    # ── 签署状态回退权限控制 ──
    # signed → draft/pending 需要 signing_partner/partner/qc/eqcr 角色
    current_sign_status = await svc.get(
        project_id, year_val or 2025, scope, "sign_status", "value"
    )
    if current_sign_status == "signed" and status in ("draft", "pending"):
        from app.models.staff_models import ProjectAssignment, StaffMember
        _SIGN_ROLLBACK_ROLES = {"signing_partner", "partner", "qc", "eqcr"}
        role_result = await db.execute(
            sa.select(ProjectAssignment.role).join(
                StaffMember, ProjectAssignment.staff_id == StaffMember.id
            ).where(
                ProjectAssignment.project_id == project_id,
                StaffMember.user_id == current_user.id,
                ProjectAssignment.is_deleted == sa.false(),
            )
        )
        user_role = role_result.scalar_one_or_none()
        if user_role not in _SIGN_ROLLBACK_ROLES:
            raise HTTPException(
                status_code=403,
                detail="仅业务合伙人及以上角色可撤回签署",
            )

    await svc.set(project_id, year_val or 2025, scope, "sign_status", "value", status, current_user.id)

    # CW-76: push sign_date → audit_report.representation_letter_date
    if status == "signed" and is_a16_main and sign_date:
        await _push_representation_letter_date(db, project_id, year_val, sign_date)

    await db.commit()
    return {"status": status, "wp_code": effective_wp_code, "version": body.version, "sign_date": sign_date}


async def _push_representation_letter_date(
    db: "AsyncSession", project_id: UUID, year: int, sign_date_str: str
) -> None:
    """CW-76: 将用户输入的签署日期 push 到 audit_report.representation_letter_date。

    如果 audit_report 行存在则 UPDATE，不存在则仅记录到 field_overrides（降级）。
    绝对不从 docx 元数据读取日期。
    """
    from datetime import date as date_type
    from app.models.report_models import AuditReport

    try:
        parsed_date = date_type.fromisoformat(sign_date_str)
    except (ValueError, TypeError):
        # 无效日期格式，不阻塞签回，只跳过 push
        return

    effective_year = year or parsed_date.year

    # 尝试更新已有的 audit_report 行
    result = await db.execute(
        sa.update(AuditReport)
        .where(AuditReport.project_id == project_id, AuditReport.year == effective_year)
        .values(representation_letter_date=parsed_date)
    )

    if result.rowcount == 0:
        # audit_report 不存在时，降级写入 field_overrides 供后续读取
        from app.services.field_override_service import FieldOverrideService
        svc = FieldOverrideService(db)
        await svc.set(
            project_id, effective_year,
            "audit_report", "representation_letter_date", "value",
            sign_date_str, None,
        )


@router.get("/working-papers/{wp_id}/onlyoffice-config")
async def get_wp_onlyoffice_config(
    project_id: UUID,
    wp_id: UUID,
    version: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
):
    """返回底稿的 OnlyOffice 编辑器配置（复用 deliverable 模块的 signed-download 机制）

    如果底稿是 Word 模板（A16 声明书），先用 python-docx 预填占位符生成临时文件，
    document_url 指向预填后的文件。
    """
    from app.core.config import settings
    from app.services.onlyoffice_session_limiter import acquire_session

    # 并发编辑会话限制
    doc_key = f"wp-{wp_id}-{version or 'latest'}"
    allowed = await acquire_session(_user.id, doc_key)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="当前在线编辑人数已达上限（10人），请稍后再试",
        )

    wp = (await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()
    if not wp:
        raise HTTPException(status_code=404, detail="底稿不存在")

    if not settings.ONLYOFFICE_URL:
        raise HTTPException(status_code=503, detail="OnlyOffice 未配置")

    # 构建 document URL（用 signed-download 免 auth 端点）
    callback_base = settings.ONLYOFFICE_CALLBACK_BASE or f"http://localhost:{settings.PORT}"
    document_url = f"{callback_base}/api/projects/{project_id}/working-papers/{wp_id}/download"
    if version:
        document_url += f"?version={version}"

    # A16 声明书预填占位符（如果文件是 docx 且有模板路径）
    prefilled = False
    if wp.file_path and wp.file_path.endswith(('.docx', '.doc')):
        try:
            prefilled = await _prefill_word_template(db, wp, project_id, user=_user)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("A16 占位符预填失败（降级不阻塞）: %s", e)

    # 构建 callback URL（word-template 使用 __word__ 作为 sheet_name 标识）
    word_callback_url = f"{callback_base}/api/workpapers/{wp_id}/sheets/__word__/onlyoffice-callback"

    return {
        "document_url": document_url,
        "document_key": f"wp-{wp_id}-{wp.file_version}-{'pf' if prefilled else 'raw'}",
        "title": wp.file_path.split("/")[-1] if wp.file_path else "声明书.docx",
        "onlyoffice_url": settings.ONLYOFFICE_URL,
        "callback_url": word_callback_url,
        "prefilled": prefilled,
    }


async def _prefill_word_template(db: AsyncSession, wp, project_id: UUID, *, user: "User | None" = None) -> bool:
    """用 python-docx 替换 Word 模板中的占位符，写回底稿文件。

    支持的占位符 token:
      {{entity_name}}  — 被审计单位名称
      {{client_name}}  — 同 entity_name（向后兼容）
      {{period_end}}   — 审计期末日期（YYYY年MM月DD日）
      {{audit_period}} — 同 period_end（向后兼容，YYYY-MM-DD 格式）
      {{preparer}}     — 编制人（当前用户姓名）
      {{current_date}} — 当前日期（YYYY年MM月DD日）
      {{partner_name}} — 签字合伙人
      {{uncorrected_misstatements}} — 未更正错报摘要
      {{date}}         — 当前日期 ISO（向后兼容）

    规则：
    - 若对应值为 None，保留 {{token}} 不替换（用户可手动填写）
    - 替换操作在项目级副本上执行，原模板文件不变
    - 已有快照时直接返回 False（幂等，不重复预填）
    - 替换后记录日志：logger.info("prefill wp_code=%s fields=%s", ...)
    """
    import logging
    import shutil
    from datetime import date as _date
    from pathlib import Path

    logger = logging.getLogger(__name__)

    file_path = Path(wp.file_path)
    if not file_path.suffix.lower() == '.docx':
        return False

    # ─── 快照幂等逻辑：已有快照则跳过预填 ───────────────────────────────────
    # 获取 wp_code（从 wp_index 表 JOIN）
    wp_code: str | None = None
    if hasattr(wp, 'wp_index_id') and wp.wp_index_id:
        idx_result = await db.execute(
            sa.select(WpIndex.wp_code).where(WpIndex.id == wp.wp_index_id)
        )
        wp_code = idx_result.scalar_one_or_none()
    if not wp_code:
        # fallback: 从 file_path 提取 stem
        wp_code = file_path.stem

    snapshot_path = Path(f"storage/{project_id}/workpapers/{wp_code}.docx")

    # 幂等检查：快照已存在 → 直接返回，不重复预填
    if snapshot_path.exists():
        # 确保 wp.file_path 指向快照（后续操作使用快照）
        if str(wp.file_path) != str(snapshot_path):
            wp.file_path = str(snapshot_path)
        return False

    # 原模板文件必须存在才能复制
    if not file_path.exists():
        return False

    # 创建快照目录并复制模板到快照路径（原模板不修改）
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(file_path), str(snapshot_path))

    # 更新 wp.file_path 指向快照，后续替换在快照上执行
    wp.file_path = str(snapshot_path)

    try:
        from docx import Document
    except ImportError:
        return False

    doc = Document(str(snapshot_path))

    # 检查段落和表格中是否存在占位符
    all_text_parts: list[str] = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    all_text_parts.append(para.text)
    full_text = "\n".join(all_text_parts)
    if "{{" not in full_text:
        return False  # 无占位符或已替换

    # ─── 取项目信息 ─────────────────────────────────────────────────────────
    proj_row = (await db.execute(
        sa.text("SELECT name, client_name, audit_period_end FROM projects WHERE id = :pid"),
        {"pid": str(project_id)},
    )).first()

    # entity_name / client_name: client_name 优先，fallback 到 name
    entity_name: str | None = None
    if proj_row:
        entity_name = proj_row[1] or proj_row[0] or None

    # period_end: 格式化为 YYYY年MM月DD日
    period_end_formatted: str | None = None
    audit_period_iso: str | None = None
    if proj_row and proj_row[2]:
        try:
            raw_date = proj_row[2]
            if hasattr(raw_date, 'strftime'):
                period_end_formatted = raw_date.strftime("%Y年%m月%d日")
                audit_period_iso = raw_date.strftime("%Y-%m-%d")
            else:
                # 字符串 fallback
                ds = str(raw_date)[:10]  # YYYY-MM-DD
                parts = ds.split("-")
                if len(parts) == 3:
                    period_end_formatted = f"{parts[0]}年{parts[1]}月{parts[2]}日"
                    audit_period_iso = ds
        except Exception:
            pass

    # current_date: YYYY年MM月DD日
    today = _date.today()
    current_date_formatted = today.strftime("%Y年%m月%d日")

    # ─── 取编制人（当前用户） ───────────────────────────────────────────────
    preparer_name: str | None = None
    if user:
        # 从 staff_members 通过 user_id 获取中文姓名
        staff_row = (await db.execute(sa.text(
            "SELECT name FROM staff_members WHERE user_id = :uid AND is_deleted = false LIMIT 1"
        ), {"uid": str(user.id)})).first()
        preparer_name = staff_row[0] if staff_row else user.username

    # ─── 取签字合伙人 ──────────────────────────────────────────────────────
    partner_row = (await db.execute(sa.text(
        "SELECT s.name FROM project_assignments pa JOIN staff_members s ON s.id=pa.staff_id "
        "WHERE pa.project_id=:pid AND pa.role='partner' LIMIT 1"
    ), {"pid": str(project_id)})).first()
    partner_name: str | None = partner_row[0] if partner_row else None

    # ─── 取未更正错报摘要 ──────────────────────────────────────────────────
    misstatement_text: str | None = "无"
    try:
        from app.services.misstatement_summary_service import MisstatementSummaryService
        svc = MisstatementSummaryService(db)
        year = int(str(proj_row[2])[:4]) if proj_row and proj_row[2] else 2025
        misstatement_text = await svc.get_for_representation_letter(project_id, year)
    except Exception as e:
        logger.warning("获取未更正错报摘要失败 pid=%s: %s", project_id, e)

    # ─── 构建替换映射（None 值不替换） ─────────────────────────────────────
    token_values: dict[str, str | None] = {
        "{{entity_name}}": entity_name,
        "{{client_name}}": entity_name,  # 向后兼容，同 entity_name
        "{{period_end}}": period_end_formatted,
        "{{audit_period}}": audit_period_iso,  # 向后兼容 YYYY-MM-DD
        "{{preparer}}": preparer_name,
        "{{current_date}}": current_date_formatted,
        "{{partner_name}}": partner_name,
        "{{uncorrected_misstatements}}": misstatement_text,
        "{{date}}": today.isoformat(),  # 向后兼容
    }

    # 过滤掉值为 None 的 token（保留原始 {{token}} 不替换）
    replacements: dict[str, str] = {k: v for k, v in token_values.items() if v is not None}

    if not replacements:
        return False

    # ─── 执行替换 ──────────────────────────────────────────────────────────
    replaced_fields: list[str] = []

    def _replace_in_paragraphs(paragraphs) -> None:
        for para in paragraphs:
            for key, val in replacements.items():
                if key in para.text:
                    for run in para.runs:
                        if key in run.text:
                            run.text = run.text.replace(key, val)
                            if key not in replaced_fields:
                                replaced_fields.append(key)

    # 替换段落
    _replace_in_paragraphs(doc.paragraphs)

    # 替换表格中的占位符
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                _replace_in_paragraphs(cell.paragraphs)

    if replaced_fields:
        doc.save(str(snapshot_path))
        logger.info("prefill wp_code=%s fields=%s", wp_code, replaced_fields)

    return bool(replaced_fields)


@router.get("/working-papers/{wp_id}/export-pdf")
async def export_workpaper_pdf(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """导出底稿为 PDF（使用 LibreOffice headless 转换）— 需求 16"""
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path
    from urllib.parse import quote
    from fastapi import Response

    # 1. 查底稿 + 校验文件存在
    result = await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    wp = result.scalar_one_or_none()
    if not wp or not wp.file_path:
        raise HTTPException(status_code=404, detail="底稿不存在")

    fp = Path(wp.file_path)
    if not fp.exists():
        raise HTTPException(status_code=404, detail=f"底稿文件不存在: {fp}")

    # 2. LibreOffice 可用性检查
    soffice = shutil.which("libreoffice") or shutil.which("soffice")
    if soffice is None:
        raise HTTPException(
            status_code=500,
            detail="LibreOffice 不可用，无法转换为 PDF。请在服务器安装 libreoffice 或 soffice。",
        )

    # 3. 使用临时目录作为输出目录（LibreOffice 不支持指定输出文件名，只支持 --outdir）
    with tempfile.TemporaryDirectory(prefix="wp_pdf_") as tmpdir:
        try:
            proc = subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf", "--outdir", tmpdir, str(fp)],
                capture_output=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=500, detail="PDF 转换超时（60s）")
        if proc.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"PDF 转换失败: {proc.stderr.decode('utf-8', errors='ignore')[:500]}",
            )

        pdf_path = Path(tmpdir) / f"{fp.stem}.pdf"
        if not pdf_path.exists():
            raise HTTPException(status_code=500, detail="LibreOffice 未生成 PDF 文件")

        pdf_bytes = pdf_path.read_bytes()

    # 4. 构造文件名（中文用 RFC 5987 编码）
    display_name = f"{wp.wp_code or 'workpaper'}_{wp.wp_name or ''}.pdf".strip()
    ascii_name = display_name.encode("ascii", "ignore").decode() or "workpaper.pdf"
    utf8_name = quote(display_name, safe="")
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )


@router.post("/working-papers/{wp_id}/prefill")
async def prefill_workpaper(
    project_id: UUID,
    wp_id: UUID,
    year: int = 2025,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """手动触发预填充（需编辑权限）— 真正打开 .xlsx 扫描公式并写入

    使用 Redis 缓存优化：key=wp_id+tb_version，避免重复计算。
    """
    from app.services.prefill_engine import prefill_workpaper_real
    from app.services.cache_service import CacheService
    from app.core.redis import redis_client

    # 计算 TB 版本标识（用于缓存 key）
    tb_version = CacheService.compute_tb_version(project_id, year)
    cache_svc = CacheService(redis_client)

    # 尝试从缓存获取
    cached = await cache_svc.get_prefill_cache(wp_id, tb_version)
    if cached is not None and cached.get("status") == "ok":
        return cached

    # 缓存未命中，执行 prefill
    result = await prefill_workpaper_real(db=db, project_id=project_id, year=year, wp_id=wp_id)
    await db.commit()

    # 写入缓存（仅成功结果）
    if result.get("status") == "ok":
        await cache_svc.set_prefill_cache(wp_id, tb_version, result)

    return result


@router.post("/working-papers/{wp_id}/parse")
async def parse_workpaper(
    project_id: UUID,
    wp_id: UUID,
    dry_run: bool = Query(False, description="仅预览解析结果，不写入 parsed_data"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """手动触发解析回写（需编辑权限）— 真正打开 .xlsx 提取关键数据

    dry_run=true：仅返回解析预览，不写入 parsed_data（用于两步确认流程步骤1）
    dry_run=false（默认）：解析并写入 parsed_data（用于步骤2用户确认后）
    """
    from app.services.prefill_engine import parse_workpaper_real
    result = await parse_workpaper_real(db=db, project_id=project_id, wp_id=wp_id, dry_run=dry_run)
    if not dry_run and result.get("status") == "ok":
        await db.commit()
        try:
            from app.services.wp_parsed_data_service import touch_wp_registry

            await touch_wp_registry(project_id)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "touch_wp_registry after parse: %s", exc
            )
    elif not dry_run:
        await db.commit()
    return result


@router.get("/a16/recommended-version")
async def get_a16_recommended_version(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
):
    """根据项目 business_category 推荐 A16 声明书版本。

    返回推荐版本、所有变体列表（含项目中是否已创建）、始终必需列表。
    """
    from app.services.template_selector import (
        A16_ALL_VERSIONS,
        A16_ALWAYS_REQUIRED,
        A16_LABELS,
        get_a16_label,
        recommend_a16_version,
    )

    # 1. 查询项目 business_category
    row = (await db.execute(
        sa.text("SELECT business_category FROM projects WHERE id = :pid"),
        {"pid": str(project_id)},
    )).first()
    business_category: str | None = row[0] if row else None

    # 2. 推荐版本
    recommended_code = recommend_a16_version(business_category)
    recommended_label = get_a16_label(recommended_code)

    # 3. 查询项目中已存在的 A16-x 底稿
    existing_result = await db.execute(
        sa.select(WpIndex.wp_code).where(
            WpIndex.project_id == project_id,
            WpIndex.wp_code.like("A16-%"),
            WpIndex.is_deleted == sa.false(),
        )
    )
    existing_codes: set[str] = {r[0] for r in existing_result.all()}

    # 4. 构建 all_versions
    all_versions = [
        {
            "code": code,
            "label": A16_LABELS.get(code, ""),
            "exists_in_project": code in existing_codes,
        }
        for code in A16_ALL_VERSIONS
    ]

    return {
        "recommended_code": recommended_code,
        "recommended_label": recommended_label,
        "all_versions": all_versions,
        "always_required": A16_ALWAYS_REQUIRED,
    }
