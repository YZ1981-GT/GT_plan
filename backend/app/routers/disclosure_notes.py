"""附注 API 路由

覆盖：
- POST /api/disclosure-notes/generate — 生成附注初稿
- GET  /api/disclosure-notes/{project_id}/{year} — 获取附注目录树
- GET  /api/disclosure-notes/{project_id}/{year}/{note_section} — 获取章节详情
- PUT  /api/disclosure-notes/{id} — 更新附注章节
- POST /api/disclosure-notes/{project_id}/{year}/validate — 执行附注校验
- GET  /api/disclosure-notes/{project_id}/{year}/validation-results — 获取校验结果
- PUT  /api/disclosure-notes/findings/{validation_id}/confirm — 确认校验发现

Validates: Requirements 4.1-4.11, 5.1-5.5
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access, require_operation, get_user_scope_cycles, check_consol_lock, require_role
from app.models.core import User
from app.models.report_models import DisclosureNote, NoteStatus
from app.models.report_schemas import (
    DisclosureNoteDetail,
    DisclosureNoteGenerateRequest,
    DisclosureNoteUpdate,
    NoteValidationFindingConfirm,
)
from app.services.disclosure_engine import DisclosureEngine
from app.services.note_validation_engine import NoteValidationEngine

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/disclosure-notes",
    tags=["disclosure-notes"],
)


# ---------------------------------------------------------------------------
# Sprint 4 Task 4.4 — NoteFormatConfig 排版规范端点
# ---------------------------------------------------------------------------


@router.get("/format-config")
async def get_format_config(
    current_user: User = Depends(get_current_user),
):
    """致同附注 Word 排版规范单一真源（21 项参数）.

    Spec: .kiro/specs/disclosure-note-full-revamp/ Sprint 4 Task 4.4 (R5.2)

    返回 ``DEFAULT_GT_FORMAT`` 的序列化结果，前端 ``useNoteFormatConfig``
    拉取后注入 CSS 变量。无项目 / 年度参数（全局规范，与项目无关）。
    """
    from app.services.note_format_config import DEFAULT_GT_FORMAT

    return {
        "format_config": DEFAULT_GT_FORMAT.to_dict(),
        "css_variables": DEFAULT_GT_FORMAT.to_css_variables(),
        "field_count": len(DEFAULT_GT_FORMAT.field_names()),
    }


async def _run_validation_best_effort(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    template_type: str | None = None,
) -> dict | None:
    """生成/刷新/同步后自动跑一次附注校验并落库（P0-4，fail-open）。

    历史上校验只有用户手点「✅校验」才跑，导致 ``note_validation_results`` 长期 0 行、
    11 个 executor 与 760/187 条预设全部空转。此处在写操作成功后补跑一次，
    任何异常一律吞掉（回滚校验事务，不影响已提交的主操作）。

    Returns: 校验摘要 dict（供响应 additive 携带）或 None（跳过/失败）。
    """
    from app.services.note_readiness_service import run_validation_best_effort

    return await run_validation_best_effort(db, project_id, year, template_type)


@router.post("/generate")
async def generate_notes(
    data: DisclosureNoteGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """生成附注初稿"""
    from app.services.prerequisite_checker import PrerequisiteChecker

    # 合并锁定检查（project_id 在 body）— Phase 1 Task 5
    await check_consol_lock(project_id=data.project_id, db=db)

    check = await PrerequisiteChecker().check(db, data.project_id, data.year, "generate_notes")
    if not check["ok"]:
        raise HTTPException(status_code=400, detail=check)
    engine = DisclosureEngine(db)
    try:
        results = await engine.generate_notes(
            data.project_id, data.year, data.template_type,
        )
        await db.commit()
        # P0-4（附注联动复盘）：生成后自动跑一次校验并落库，让 findings 在附注树上
        # 可见（历史 note_validation_results 长期 0 行 = 校验能力空转）。fail-open。
        validation = await _run_validation_best_effort(
            db, data.project_id, data.year, data.template_type,
        )
        return {
            "message": "附注生成成功",
            "note_count": len(results),
            "notes": results,
            "validation": validation,
        }
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"附注生成失败: {str(e)}")


@router.get("/{project_id}/{year}")
async def get_notes_tree(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取附注目录树"""
    engine = DisclosureEngine(db)
    tree = await engine.get_notes_tree(project_id, year)
    if not tree:
        raise HTTPException(status_code=404, detail="附注数据不存在，请先生成附注")

    # scope_cycles 过滤：非 admin/partner 用户只能看到被分配循环对应的附注章节
    scope_cycles = await get_user_scope_cycles(current_user, project_id, db)
    if scope_cycles is not None:
        from app.services.mapping_service import get_sections_by_cycles
        allowed_sections = await get_sections_by_cycles(project_id, scope_cycles)
        if allowed_sections:
            tree = [n for n in tree if n.get("note_section") in allowed_sections]

    # P0-4（附注联动复盘）：树节点携带最新一次校验的 findings 计数（additive），
    # 使 error/warning 能直接打点在左侧章节树上，而不必点进右侧面板才看到。fail-open。
    try:
        from app.services.note_readiness_service import latest_findings_by_section

        findings_map, _validated_at = await latest_findings_by_section(db, project_id, year)
        if findings_map:
            for node in tree:
                f = findings_map.get(node.get("note_section") or "")
                if f:
                    node["findings"] = {
                        "error": f.get("error", 0),
                        "warning": f.get("warning", 0),
                    }
    except Exception as err:  # pragma: no cover — 附加信息失败不影响树
        logger.warning("attach findings to notes tree skipped: %s", err)

    return tree


@router.get("/{project_id}/{year}/readiness")
async def get_notes_readiness(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """附注「披露同步 / 校验就绪度」看板（只读，附注联动复盘 P0-1）。

    回答审计师最需要的三个问题：
    - 哪些章节**应由底稿维护但从未同步过**（``needs_sync``，实测生产 0 条同步记录）
    - 哪些章节**没有数据**（``has_data=false``，与 Word 导出同一 helper 判定）
    - 哪些章节**有校验问题 / 上游已变更**（``findings`` / ``is_stale``）

    ``wp_ids`` / ``wp_sheet`` 供前端直接跳转到对应底稿披露 sheet。
    """
    from app.services.note_readiness_service import build_readiness

    data = await build_readiness(db, project_id, year)

    # scope_cycles 过滤（与目录树一致：非 admin/partner 只看被分配循环的章节）
    scope_cycles = await get_user_scope_cycles(current_user, project_id, db)
    if scope_cycles is not None:
        from app.services.mapping_service import get_sections_by_cycles

        allowed_sections = await get_sections_by_cycles(project_id, scope_cycles)
        if allowed_sections:
            data["sections"] = [
                s for s in data["sections"] if s.get("note_section") in allowed_sections
            ]
    return data


@router.put("/{project_id}/formula-gray")
async def set_formula_gray(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role(["admin", "partner", "signing_partner", "manager"])
    ),
):
    """设置项目级附注公式灰度开关。

    Body: {"enabled": true/false}
    写入 project.wizard_state["disclosure_note_formula_enabled"]。
    权限：manager+。

    Validates: Requirements 5.1, 6.1
    """
    from sqlalchemy.orm.attributes import flag_modified
    from app.models.core import Project

    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=400, detail="body.enabled must be boolean")

    result = await db.execute(
        sa.select(Project).where(
            Project.id == project_id,
            Project.is_deleted == sa.false(),
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    ws = dict(project.wizard_state) if project.wizard_state else {}
    ws["disclosure_note_formula_enabled"] = enabled
    project.wizard_state = ws
    flag_modified(project, "wizard_state")

    await db.flush()
    await db.commit()

    return {
        "project_id": str(project_id),
        "disclosure_note_formula_enabled": enabled,
        "message": f"附注公式灰度已{'启用' if enabled else '关闭'}",
    }


@router.get("/{project_id}/{year}/linkage-gaps")
async def get_linkage_gaps(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """只读诊断：列出「有报表↔附注勾稽但无写值 linkage」的章节（spec R5 / Task 5.1）。

    委托 ``ReportNoteLinkage.diagnose_missing_write_linkage``，仅呈现不修改任何数据。
    按决策 1（报表↔附注只校验不写值），``cells_updated=0`` 是正确行为；本端点把
    「需人工评估是否逐节增量维护 linkage」的章节显性化，**不自动填 linkage**。
    """
    from app.models.report_models import DisclosureNote
    from app.services.report_note_linkage import ReportNoteLinkage

    notes = (
        (
            await db.execute(
                sa.select(DisclosureNote).where(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.is_deleted == sa.false(),
                )
            )
        )
        .scalars()
        .all()
    )
    try:
        gaps = ReportNoteLinkage().diagnose_missing_write_linkage(list(notes))
    except Exception:  # pragma: no cover - 诊断 fail-open 不阻断
        gaps = []
    return {"project_id": str(project_id), "year": year, "gaps": gaps, "count": len(gaps)}


@router.post("/{project_id}/{year}/pull-from-workpapers")
async def pull_from_workpapers(
    project_id: UUID,
    year: int,
    note_section: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """附注主动从底稿拉取最新数据（刷新/生成时调用）。

    对有底稿映射（registry）的章节：
    - 已同步过（`_source=workpaper`）：刷新 `_last_sync_at` 标记 + 确保 refill 跳过表格
    - 从未同步过：标记 `_source=workpaper`（让后续 refill 跳过表格覆盖）并保留现有数据

    如果传 note_section：只处理该章节（单页刷新）；不传：处理全部有映射的章节（全部刷新）。

    返回 { synced: int, skipped: int }
    """
    from datetime import datetime, timezone
    from app.services.note_readiness_service import _load_registry_entries

    # 确定项目变体
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    variant = project.template_type or "soe"  # listed/soe

    # 从 registry 获取有映射的章节
    entries = _load_registry_entries()
    target_sections: list[str] = []
    if note_section:
        target_sections = [note_section]
    else:
        for e in entries:
            sec = e.get(variant) or e.get("listed") or e.get("soe")
            if isinstance(sec, str) and sec.strip():
                target_sections.append(sec.strip())

    if not target_sections:
        return {"synced": 0, "skipped": 0, "message": "无底稿映射章节"}

    now = datetime.now(timezone.utc)
    synced = 0
    skipped = 0

    for section in target_sections:
        # 查该章节是否存在
        note = (
            await db.execute(
                sa.select(DisclosureNote).where(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.note_section == section,
                    DisclosureNote.is_deleted == False,
                )
            )
        ).scalar_one_or_none()

        if not note:
            skipped += 1
            continue

        # 更新 table_data：标记 _source=workpaper + 刷新 _last_sync_at
        td = note.table_data or {}
        if not isinstance(td, dict):
            td = {}

        td["_source"] = "workpaper"
        td["_last_sync_at"] = now.isoformat()
        note.table_data = td
        # 强制 ORM 脏标记（JSONB 就地改不触发）
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(note, "table_data")
        synced += 1

    await db.commit()
    return {"synced": synced, "skipped": skipped}


@router.get("/{project_id}/{year}/wp-sync-status")
async def get_wp_sync_status(
    project_id: UUID,
    year: int,
    wp_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """某底稿对应附注章节的同步状态（只读，附注联动复盘 P0-2）。

    供底稿披露 sheet 顶部统一状态条使用：告诉审计师"本页披露表是否已同步到附注、
    上次同步于何时"。映射真源 = ``note_workpaper_sync_registry.json``。

    Returns::

        {"wp_code": "D1", "variants": [
            {"variant": "listed", "note_section": "五、4", "exists": true,
             "last_sync_at": "...", "last_sync_source": "workpaper", "has_data": true}
        ]}
    """
    from app.services.note_content_utils import note_has_data
    from app.services.note_readiness_service import _load_registry_entries

    code = (wp_code or "").strip().upper()
    entry = next(
        (e for e in _load_registry_entries() if str(e.get("wp_code", "")).upper() == code),
        None,
    )
    if entry is None:
        return {"wp_code": code, "variants": []}

    sections = {
        v: entry.get(v)
        for v in ("listed", "soe")
        if isinstance(entry.get(v), str) and entry.get(v)
    }
    if not sections:
        return {"wp_code": code, "variants": []}

    notes = (
        (
            await db.execute(
                sa.select(DisclosureNote).where(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.is_deleted == sa.false(),
                    DisclosureNote.note_section.in_(list(sections.values())),
                )
            )
        )
        .scalars()
        .all()
    )
    by_section = {n.note_section: n for n in notes}

    variants = []
    for variant, section in sections.items():
        n = by_section.get(section)
        variants.append(
            {
                "variant": variant,
                "note_section": section,
                "exists": n is not None,
                "last_sync_at": n.last_sync_at.isoformat() if (n and n.last_sync_at) else None,
                "last_sync_source": (n.last_sync_source if n else None),
                "has_data": bool(note_has_data(n)) if n else False,
            }
        )
    return {"wp_code": code, "variants": variants}


@router.get("/{project_id}/{year}/validation-results")
async def get_validation_results(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取最新校验结果。

    `get_latest_results` 返回 `{project_id,year,total_rules,passed,failed,findings}`
    结构化 dict。尚未校验或本次校验 0 规则/0 发现（result 为 None）时，返回空结果
    （200，findings=[]），前端显示"未发现问题"而非把 404 冒泡崩溃整页。
    """
    engine = NoteValidationEngine(db)
    result = await engine.get_latest_results(project_id, year)
    if result is None:
        return {
            "project_id": str(project_id),
            "year": year,
            "total_rules": 0,
            "passed": 0,
            "failed": 0,
            "findings": [],
        }
    return result


# ---------------------------------------------------------------------------
# Sprint 2 Task 2.3 — CellTrace 溯源链端点（R3.1 验收 22）
# ---------------------------------------------------------------------------


@router.get("/{note_id}/cells/{row_idx}/{col_idx}/trace")
async def trace_cell(
    note_id: UUID,
    row_idx: int,
    col_idx: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """单元格溯源：返回 binding 元数据 + 公式展开 + 命中数据行采样.

    Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 2 Task 2.3
    Design: D5 CellTrace 溯源链 端点 schema
    Reqs:   R3.1 验收 22

    返回示例：
    ```json
    {
      "binding": {"source": "trial_balance", "field": "audited_amount",
                  "account_codes": ["1601","1602"], "agg": "sum"},
      "formula_resolved": "=SUM(TB('1601','audited_amount'), TB('1602','audited_amount'))",
      "computed_value": 1234.56,
      "evidence": {
        "trial_balance_rows": [{"account_code": "1601", "audited": 600.0, ...}],
        "ledger_sample": [],
        "aux_balance_sample": []
      },
      "computed_at": "2026-..."
    }
    ```

    错误语义（始终 200 + ``error`` 字段，前端友好降级）：
      - ``note_not_found``           — note_id 不存在
      - ``cell_index_out_of_range``  — row_idx / col_idx 越界
      - ``no_binding``               — cell_meta 缺 binding_id
      - ``binding_not_found``        — 反查 binding 失败
    """
    engine = DisclosureEngine(db)
    return await engine.trace_cell(note_id, row_idx, col_idx)


@router.get("/{project_id}/{year}/section-numbers")
async def get_section_numbers(
    project_id: UUID,
    year: int,
    scope: str = Query("both", description="standalone/consolidated/both"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取附注章节编号映射（供前端渲染序号）。

    返回 {note_section: rendered_number} 映射，如 {"五、1": "1", "五、2": "2"}.
    规则：按章节前缀分组，组内连续编号；若组内仅 1 个条目则不编号。
    """
    from app.models.core import Project
    from app.services.note_section_numbering import compute_section_numbers
    from app.services.note_section_catalog import normalize_template_type

    engine = DisclosureEngine(db)
    tree = await engine.get_notes_tree(project_id, year)
    if not tree:
        return {}

    proj = (
        await db.execute(
            sa.select(Project.template_type, Project.report_scope).where(
                Project.id == project_id,
                Project.is_deleted == sa.false(),
            )
        )
    ).one_or_none()
    template_type = normalize_template_type(proj[0] if proj else "soe")
    effective_scope = scope if scope in ("standalone", "consolidated", "both") else "both"
    if effective_scope == "both" and proj and proj[1]:
        effective_scope = proj[1]

    return compute_section_numbers(
        tree,
        report_scope=effective_scope,
        template_type=template_type,
    )


@router.get("/{project_id}/{year}/{note_section}/prior-year")
async def get_prior_year_note(
    project_id: UUID,
    year: int,
    note_section: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取上年同一附注章节数据，用于前端双列对比。"""
    engine = DisclosureEngine(db)
    data = await engine.get_prior_year_data(project_id, year, note_section)
    return data or {"year": year - 1, "table_data": None, "text_content": None}


@router.get("/{project_id}/{year}/{note_section}")
async def get_note_detail(
    project_id: UUID,
    year: int,
    note_section: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取指定附注章节详情"""
    engine = DisclosureEngine(db)
    note = await engine.get_note_detail(project_id, year, note_section)
    if note is None:
        raise HTTPException(status_code=404, detail="附注章节不存在")
    detail = DisclosureNoteDetail.model_validate(note)
    # 读时投影（不写库）：workpaper 来源记录把 sub_table_data + _sub_table_columns 投影为
    # 可渲染 _tables，供附注模块/Word 忠实呈现源模板表样（spec disclosure-table-sync-convergence
    # Req6.1，Property7）。非 workpaper 来源返回 None → 不投影，沿用既有 _tables/rows（Req6.2）。
    try:
        from app.services.note_sub_table_projector import project_sub_tables

        projected = project_sub_tables(detail.table_data)
        if projected and detail.table_data is not None:
            detail.table_data = {**detail.table_data, "_tables": projected}
    except Exception:  # pragma: no cover - 投影失败降级不阻断读取
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "get_note_detail: sub_table projection failed section=%s", note_section,
            exc_info=True,
        )
    # 读时补齐表头（不写库）：legacy 单表 headers 为空但行携 _cell_meta 语义时，
    # 派生可渲染表头，修复前端 el-table 零列坍缩（"附注表格只有一行"）。
    # 前端整表保存时派生表头随之落库，实现自愈。
    try:
        from app.services.note_header_projector import project_headers

        with_headers = project_headers(
            detail.table_data,
            section_number=note_section,
            source_template=getattr(note, "source_template", None),
        )
        if with_headers is not None:
            detail.table_data = with_headers
    except Exception:  # pragma: no cover - 派生失败降级不阻断读取
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "get_note_detail: header projection failed section=%s", note_section,
            exc_info=True,
        )
    return detail


@router.put("/{note_id}")
async def update_note(
    note_id: UUID,
    data: DisclosureNoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operation("note:edit")),
    _lock_check=Depends(check_consol_lock),
):
    """更新附注章节内容"""
    engine = DisclosureEngine(db)
    note = await engine.update_note(
        note_id,
        table_data=data.table_data,
        text_content=data.text_content,
        guidance_text=data.guidance_text,
        status=data.status,
    )
    if note is None:
        raise HTTPException(status_code=404, detail="附注章节不存在")
    await db.commit()

    # Publish NOTE_SECTION_SAVED event
    try:
        from app.models.audit_platform_schemas import EventPayload, EventType
        from app.services.event_bus import event_bus

        await event_bus.publish(EventPayload(
            event_type=EventType.NOTE_SECTION_SAVED,
            project_id=note.project_id,
            year=note.year,
            extra={
                "section_code": note.section_code if hasattr(note, "section_code") else str(note_id),
            },
        ))
    except Exception:
        pass  # Never block main operation

    return DisclosureNoteDetail.model_validate(note)


@router.delete("/{project_id}/{year}/sections/{note_section:path}")
async def delete_section(
    project_id: UUID,
    year: int,
    note_section: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("editor")),
):
    """软删除指定附注章节。"""
    result = await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.note_section == note_section,
            DisclosureNote.is_deleted == sa.false(),
        )
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="章节不存在")
    note.is_deleted = True
    # get_db 不自动 commit：只 flush 会在会话关闭时回滚，删除从不落库（刷新后章节复现）
    await db.commit()
    return {"ok": True}


@router.patch("/{project_id}/{year}/sections/{note_section:path}")
async def patch_section(
    project_id: UUID,
    year: int,
    note_section: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("editor")),
):
    """部分更新附注章节字段（如 status → 用 is_empty 标记排除导出）。"""
    result = await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.note_section == note_section,
            DisclosureNote.is_deleted == sa.false(),
        )
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="章节不存在")
    # 用 is_empty 标记"不导出"（Word export 已有 skip empty 逻辑）
    if "status" in body:
        if body["status"] == "not_applicable":
            note.is_empty = True
        else:
            note.is_empty = False
    # get_db 不自动 commit：只 flush 会在会话关闭时回滚，状态变更从不落库
    await db.commit()
    status_val = "not_applicable" if note.is_empty else (note.status.value if note.status else "draft")
    return {"ok": True, "status": status_val}


@router.get("/{project_id}/{year}/deleted")
async def list_deleted_sections(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """列出已软删除的附注章节，供恢复使用。"""
    result = await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.is_deleted == sa.true(),
        ).order_by(DisclosureNote.sort_order)
    )
    notes = result.scalars().all()
    return [
        {"id": str(n.id), "note_section": n.note_section, "section_title": n.section_title}
        for n in notes
    ]


@router.patch("/{project_id}/{year}/restore/{note_id}")
async def restore_section(
    project_id: UUID,
    year: int,
    note_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("editor")),
):
    """恢复已删除的附注章节。"""
    result = await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.id == note_id,
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.is_deleted == sa.true(),
        )
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="章节不存在或未被删除")
    note.is_deleted = False
    # get_db 不自动 commit：只 flush 会在会话关闭时回滚，恢复从不落库
    await db.commit()
    return {"ok": True}


@router.post("/{project_id}/{year}/validate")
async def validate_notes(
    project_id: UUID,
    year: int,
    template_type: str = "soe",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """执行附注校验

    template_type: soe（国企版）或 listed（上市版），决定使用哪套预设公式
    """
    if template_type not in ("soe", "listed"):
        raise HTTPException(status_code=400, detail="template_type 必须是 soe 或 listed")
    engine = NoteValidationEngine(db)
    try:
        result = await engine.validate_all(project_id, year, template_type=template_type)
        await db.commit()
        return result
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"校验执行失败: {str(e)}")


@router.get("/{project_id}/{year}/formula-health")
async def formula_health(
    project_id: UUID,
    year: int,
    template_type: str = "soe",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """附注公式/校验管线健康度诊断（只读，不跑规则、不写库）。

    把"哪些管线真正生效 / 哪些休眠"显性化（P0-B）：附注 binding/inline 规则/report
    绑定计数 + preset 规则数 + linkage 配置条目 + 三条管线激活标志。
    """
    if template_type not in ("soe", "listed"):
        raise HTTPException(status_code=400, detail="template_type 必须是 soe 或 listed")
    engine = NoteValidationEngine(db)
    health = await engine.diagnose_formula_health(
        project_id, year, template_type=template_type
    )
    # 附加只读诊断（spec disclosure-note-formula-data-population Task 5.1）：
    # 「有报表↔附注勾稽但无写值 linkage」的章节 —— cells_updated=0 属正确行为
    # （决策 1：报表↔附注只做校验不做写值），此处只呈现不写入。fail-open。
    try:
        from app.services.report_note_linkage import ReportNoteLinkage

        notes = (
            (
                await db.execute(
                    sa.select(DisclosureNote).where(
                        DisclosureNote.project_id == project_id,
                        DisclosureNote.year == year,
                        DisclosureNote.is_deleted == sa.false(),
                    )
                )
            )
            .scalars()
            .all()
        )
        missing = ReportNoteLinkage().diagnose_missing_write_linkage(list(notes))
        if isinstance(health, dict):
            health["missing_write_linkage"] = missing
            health["missing_write_linkage_count"] = len(missing)
    except Exception as err:  # pragma: no cover — 诊断失败不影响健康度主体
        logger.warning("formula_health: linkage diagnose failed: %s", err)
    return health


@router.put("/findings/{validation_id}/confirm")
async def confirm_finding(
    validation_id: UUID,
    finding_index: int,
    data: NoteValidationFindingConfirm,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """确认校验发现为"已确认-无需修改" """
    engine = NoteValidationEngine(db)
    success = await engine.confirm_finding(
        validation_id, finding_index, data.reason,
    )
    if not success:
        raise HTTPException(status_code=404, detail="校验结果或发现不存在")
    await db.commit()
    return {"message": "校验发现已确认", "confirmed": True}


# Phase 9 Task 9.30: 附注 Word 导出
@router.post("/{project_id}/{year}/export-word")
async def export_word(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """导出附注为 Word 文档"""
    from fastapi.responses import StreamingResponse
    from app.models.core import Project
    from app.services.note_section_catalog import normalize_report_scope
    from app.services.note_word_exporter import NoteWordExporter

    proj_row = (
        await db.execute(
            sa.select(Project.report_scope).where(
                Project.id == project_id,
                Project.is_deleted == sa.false(),
            )
        )
    ).scalar_one_or_none()

    exporter = NoteWordExporter(db)
    try:
        output = await exporter.export(
            project_id,
            year,
            report_scope=normalize_report_scope(
                proj_row if isinstance(proj_row, str) else None
            ),
        )
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename=disclosure_notes_{year}.docx"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


# Phase 9 Task 9.28: 历史附注上传与解析
@router.post("/{project_id}/upload-history")
async def upload_history(
    project_id: UUID,
    year: int = 2025,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """上传历史附注文件（Word/PDF）并解析"""
    from fastapi import UploadFile, File
    # 简化实现：返回解析结果结构
    # 实际需要接收文件上传，保存到临时目录，调用 HistoryNoteParser
    return {
        "message": "历史附注上传接口已就绪",
        "project_id": str(project_id),
        "year": year,
        "note": "请通过 multipart/form-data 上传 .docx 或 .pdf 文件",
    }


@router.get("/{project_id}/{year}/{note_section}/template-structure")
async def get_template_structure(
    project_id: UUID,
    year: int,
    note_section: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取附注章节的原始模板表格结构（用于"恢复模板结构"操作）。

    从附注模板种子数据中获取该章节的默认表格结构（headers + rows），
    不包含项目实际数据，仅返回模板定义的列名和行标签。
    Requirements: 38.5, 38.6
    """
    engine = DisclosureEngine(db)
    template = await engine.get_template_structure(project_id, year, note_section)
    if template is None:
        raise HTTPException(
            status_code=404,
            detail=f"未找到章节 {note_section} 的模板结构"
        )
    return template


@router.post("/{project_id}/{year}/{note_section}/clear-formulas")
async def clear_formulas(
    project_id: UUID,
    year: int,
    note_section: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """一键清除指定附注章节的所有自动公式，切换为手动编辑模式。

    将所有 auto 模式的单元格切换为 manual，保留当前数值不变。
    用户后续编辑不会被自动提数覆盖。
    """
    from app.services.note_wp_mapping_service import NoteWpMappingService

    svc = NoteWpMappingService(db)
    try:
        count = await svc.clear_formulas(project_id, year, note_section)
        await db.commit()
        return {"message": f"已清除 {count} 个单元格的自动公式", "cleared_count": count}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{project_id}/{year}/{note_section}/restore-auto")
async def restore_auto_mode(
    project_id: UUID,
    year: int,
    note_section: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """恢复指定附注章节的自动提数模式。

    从底稿 parsed_data 重新提取数据，将 manual 单元格恢复为 auto。
    """
    from app.services.note_wp_mapping_service import NoteWpMappingService

    svc = NoteWpMappingService(db)
    try:
        count = await svc.restore_auto_mode(project_id, year, note_section)
        await db.commit()
        return {"message": f"已恢复 {count} 个单元格为自动提数", "restored_count": count}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{project_id}/{year}/{note_section}/auto-pull")
async def get_auto_pull(
    project_id: UUID,
    year: int,
    note_section: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取附注章节的 cross_ref auto_pull 只读联动值.

    从来源底稿/报表/试算表拉取 schema 中 auto_pull=true && direction=inbound
    的 cross_ref 真实值。只读查询，不写入 table_data，无需 commit。

    Spec:   .kiro/specs/disclosure-note-linkage-and-slimdown/
    Design: 缺口 2 — cross_ref auto_pull 真实取数
    Reqs:   3.1, 3.2, 3.3, 3.4
    """
    from dataclasses import asdict

    import sqlalchemy as sa

    from app.models.report_models import DisclosureNote
    from app.services.note_auto_pull_service import NoteAutoPullService
    from app.services.note_wp_mapping_service import DEFAULT_WP_MAPPING
    from app.services.wp_render_schema_service import WpRenderSchemaService

    # 1. 加载该章节对应的 schema
    #    note_section → wp_code 映射（如 "五、3" → "D1"）
    wp_code = DEFAULT_WP_MAPPING.get(note_section)
    schema: dict = {}
    if wp_code:
        try:
            schema_service = WpRenderSchemaService()
            schema = schema_service.load_schema(wp_code)
        except FileNotFoundError:
            schema = {}

    # 2. 加载该 note 的 table_data
    result = await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.note_section == note_section,
            DisclosureNote.is_deleted == sa.false(),
        )
    )
    note = result.scalar_one_or_none()
    note_table_data = note.table_data if note else None

    # 3. 调 NoteAutoPullService 取数（只读，无需 commit）
    results = await NoteAutoPullService(db).pull_for_section(
        project_id, year, schema, note_table_data=note_table_data,
    )

    return {"refs": [asdict(r) for r in results]}


@router.post("/{project_id}/{year}/{note_section}/apply-formulas")
async def apply_formulas(
    project_id: UUID,
    year: int,
    note_section: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """执行附注表格中的自动运算公式，回填计算结果。

    只更新 mode=auto 的单元格，manual 单元格不受影响。
    公式从 check_presets 自动生成（纵向合计/横向平衡/账面价值）。
    """
    from app.services.note_formula_generator import execute_note_formulas

    try:
        result = await execute_note_formulas(db, project_id, year, note_section)
        await db.commit()
        return {
            "message": f"公式已执行：{result['executed']} 个公式，更新 {result['updated']} 个单元格",
            **result,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"公式执行失败: {str(e)}")


# ---------------------------------------------------------------------------
# acnr-consumer-wiring P10 / Req 15.6 — 附注公式列表 + 持久化端点
# ---------------------------------------------------------------------------


@router.get("/{project_id}/{year}/{note_section}/formulas")
async def list_note_formulas(
    project_id: UUID,
    year: int,
    note_section: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """列出附注章节的当前公式集（已保存用户编辑集优先，否则 generator 预览）。

    供 NoteFormulaDialog onOpen 加载（Req 15.1）——替代此前 `formulas = ref([])`
    从不加载的空态。只读查询，无需 commit。

    返回 ``{"formulas": [...]}``；每条含 target/formula/description/category/source/type。
    note 不存在或无表格 → 空列表（弹窗不阻断）。
    """
    from app.services.note_formula_service import note_formula_service

    formulas = await note_formula_service.list_by_section(
        db, project_id, year, note_section
    )
    return {"formulas": formulas}


@router.put("/{project_id}/{year}/{note_section}/formulas")
async def upsert_note_formulas(
    project_id: UUID,
    year: int,
    note_section: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """upsert 附注章节的用户编辑公式集（Req 15.2/15.3）。

    body: ``{"formulas": [{target, formula, description, category, source?}, ...]}``
    整体替换该章节的 ``_user_formulas`` 集（"这套就是最新集"语义），空行被过滤。

    service 只 flush，router 统一 commit（工程铁律）。
    """
    from app.services.note_formula_service import note_formula_service

    formulas = body.get("formulas")
    if not isinstance(formulas, list):
        raise HTTPException(status_code=400, detail="formulas 必须是列表")

    try:
        saved = await note_formula_service.save_many(
            db, project_id, year, note_section, formulas
        )
        await db.commit()
        return {"formulas": saved, "saved_count": len(saved)}
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"公式保存失败: {str(e)}")


# ---------------------------------------------------------------------------
# 附注 ↔ 底稿/试算表 联动（P1 落地：WpNoteLinkageService 一致性校验 + 一键取数预览）
# ---------------------------------------------------------------------------


@router.get("/{project_id}/{year}/note-linkage/consistency")
async def note_linkage_consistency(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """校验附注合计与试算表审定数一致性（按 account_name 匹配）。

    仅比较"存在可比 TB 审定数 + 附注有数值合计"的节；其余如实计入 skipped。
    返回 ``{consistent, checked_sections, skipped_sections, inconsistencies:[...]}``。
    """
    from app.services.wp_note_linkage_service import WpNoteLinkageService

    svc = WpNoteLinkageService(db)
    return await svc.check_consistency(project_id=project_id, year=year)


@router.get("/{project_id}/{year}/note-linkage/one-click-preview")
async def note_linkage_one_click_preview(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """一键取数预览（只读）：列出每节可从试算表带入的审定数。

    不改写 disclosure_notes（各节 table_data 结构各异，改写风险高）；返回预览供前端
    逐节确认后应用。返回 ``{available_sections, sections:[{note_section, account_name,
    tb_audited_amount, current_note_amount}]}``。
    """
    from app.services.wp_note_linkage_service import WpNoteLinkageService

    svc = WpNoteLinkageService(db)
    return await svc.one_click_fetch(project_id=project_id, year=year)


# ---------------------------------------------------------------------------
# 附注知识库 RAG + AI 正文预填（disclosure-note-knowledge-ai-enrichment / Task 7）
#   POST /{project_id}/{year}/{note_section}/ai-fill —— 单章节 AI 填充 / 参照文档填充预览
#   POST /{project_id}/{year}/batch-ai-fill          —— 一键批量预填充空/草稿章节
# 两端点均**不落库**（Property 11：绝不写 DisclosureNote.text_content）；采纳走既有
# /api/ai-chat/adopt 确认流，落库仅写 text_content（substantive），不碰 guidance_text（Req5.2）。
# ---------------------------------------------------------------------------


class NoteAiFillRequest(BaseModel):
    """单章节 AI 填充请求（字段均可选）。"""

    doc_filter: list[UUID] | None = None  # 指定参照的知识库文档 id 范围；空=项目+Global_KB
    reference_only: bool = False  # True=只返回检索片段供人工引用，不调 LLM 生成（Req4.5）


class NoteBatchAiFillRequest(BaseModel):
    """一键批量 AI 预填充请求。"""

    doc_filter: list[UUID] | None = None


def _citation_to_dict(c) -> dict:
    """把 Citation dataclass 序列化为响应 dict（含 is_stale 索引新鲜度标记）。"""
    return {
        "document_name": getattr(c, "document_name", None),
        "folder_path": getattr(c, "folder_path", None),
        "snippet": getattr(c, "snippet", ""),
        "score": getattr(c, "score", 0.0),
        "source_id": getattr(c, "source_id", ""),
        "is_stale": bool(getattr(c, "is_stale", False)),
    }


@router.post("/{project_id}/{year}/{note_section}/ai-fill")
async def ai_fill_note_section(
    project_id: UUID,
    year: int,
    note_section: str,
    body: NoteAiFillRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """单章节 AI 填充 / 参照文档填充（**不落库**，仅返回预览供采纳，Property 11）。

    行为：查该 section 的 section_title/account_name（缺失则用 note_section 兜底），
    调 `NoteKnowledgeEnricher.generate_note_text`（RAG 检索→反幻觉起草 或 reference_only 仅回片段）。

    resp: ``{ text, citations:[{document_name, folder_path, snippet, score, source_id, is_stale}],
              degraded, skipped_docs }``
    - skipped_docs：doc_filter 中不存在/已删（无权）被跳过的文档 id；无则空（不 500，Req4.3）。
    - 无命中/检索或 LLM 降级 → degraded=true（前端据此提示"已用通用生成"，Req3.4）。
    """
    from app.models.knowledge_models import KnowledgeDocument
    from app.services.note_knowledge_enricher import NoteKnowledgeEnricher

    req = body or NoteAiFillRequest()

    # 查该 section 的 section_title / account_name（缺失则用 note_section 兜底）
    row = (
        await db.execute(
            sa.select(
                DisclosureNote.section_title, DisclosureNote.account_name
            ).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.note_section == note_section,
                DisclosureNote.is_deleted == sa.false(),
            )
        )
    ).one_or_none()
    section_title = (row[0] if row else None) or note_section
    account_name = (row[1] if row else None) or ""

    # 权限跳过文档：doc_filter 中不存在/已删的文档 → skipped_docs（不将其纳入上下文，不 500）
    skipped_docs: list[str] = []
    if req.doc_filter:
        active = (
            await db.execute(
                sa.select(KnowledgeDocument.id).where(
                    KnowledgeDocument.id.in_(req.doc_filter),
                    KnowledgeDocument.is_deleted == sa.false(),
                )
            )
        ).scalars().all()
        active_ids = {str(d) for d in active}
        skipped_docs = [str(d) for d in req.doc_filter if str(d) not in active_ids]

    enricher = NoteKnowledgeEnricher(db)
    draft = await enricher.generate_note_text(
        project_id,
        year,
        note_section,
        section_title,
        account_name,
        user=current_user,
        doc_filter=req.doc_filter,
        reference_only=req.reference_only,
    )
    return {
        "text": draft.text,
        "citations": [_citation_to_dict(c) for c in draft.citations],
        "degraded": draft.degraded,
        "skipped_docs": skipped_docs,
    }


@router.post("/{project_id}/{year}/batch-ai-fill")
async def batch_ai_fill_notes(
    project_id: UUID,
    year: int,
    body: NoteBatchAiFillRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """一键批量预填充空/草稿章节（**不落库**，逐章结果供前端确认采纳，Req10）。

    行为：查该 project/year 所有"文字为空或 status=draft"且未锁定/无 manual_override（`is_local_override`）
    的章节，构造 sections 列表调 `NoteKnowledgeEnricher.batch_prefill`（单章 try/except 隔离降级，Property 12）。

    resp: ``{ results:[{note_section, status, text, citations}], generated, degraded, skipped }``
    """
    from app.services.note_knowledge_enricher import NoteKnowledgeEnricher

    req = body or NoteBatchAiFillRequest()

    rows = (
        await db.execute(
            sa.select(DisclosureNote)
            .where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.is_deleted == sa.false(),
                DisclosureNote.is_local_override == sa.false(),
                sa.or_(
                    DisclosureNote.text_content.is_(None),
                    sa.func.length(sa.func.trim(DisclosureNote.text_content)) == 0,
                    DisclosureNote.status == NoteStatus.draft,
                ),
            )
            .order_by(DisclosureNote.sort_order)
        )
    ).scalars().all()

    sections = [
        {
            "note_section": n.note_section,
            "section_title": n.section_title or n.note_section,
            "account_name": n.account_name or "",
            "account_code": None,
            "audit_area": None,
            "text_content": n.text_content,
            "is_draft": n.status == NoteStatus.draft,
            "manual_override": n.is_local_override,
        }
        for n in rows
    ]

    enricher = NoteKnowledgeEnricher(db)
    raw_results = await enricher.batch_prefill(
        project_id,
        year,
        sections,
        user=current_user,
        doc_filter=req.doc_filter,
    )

    results = [
        {
            "note_section": r.get("note_section"),
            "status": r.get("status"),
            "text": r.get("text"),
            "citations": [_citation_to_dict(c) for c in (r.get("citations") or [])],
        }
        for r in raw_results
    ]
    generated = sum(1 for r in results if r["status"] == "generated")
    degraded = sum(1 for r in results if r["status"] == "degraded")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    return {
        "results": results,
        "generated": generated,
        "degraded": degraded,
        "skipped": skipped,
    }
