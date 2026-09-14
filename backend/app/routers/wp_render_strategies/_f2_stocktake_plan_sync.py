"""F2-22 监盘计划 — 结构化 ↔ OnlyOffice docx 双向同步 API."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db, set_rls_context
from app.deps import get_current_user
from app.models.core import User
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.f2_stocktake_plan_sync import (
    FIELDS_ITEM_ID,
    create_g2_6_2_template_docx,
    extract_fields_from_docx,
    fill_plan_docx,
    merge_extracted_into_existing,
    parse_fields_json,
)
from app.services.workpaper_sync.content_mutation import (
    ONLYOFFICE,
    ContentCommitReceipt,
)
from app.services.workpaper_sync.models import RevisionConflictError
from app.services.workpaper_sync.writer_migration import (
    build_content_mutation_service_writer,
    opaque_entry_id,
)
from app.services.wp_template_finder import TEMPLATES_DIR, find_template_file_any

logger = logging.getLogger(__name__)

router = APIRouter(tags=["f2-st-plan-sync"])

#: 本模块服务的唯一 sheet code（`entry_id` 与 docx 缓存文件名的单一真源）。
_SHEET_CODE = "F2-22"
_SHEET_CODES = {"F2-22", "监盘计划F2-22"}


def _onlyoffice_dir(project_id: UUID) -> Path:
    """项目 OnlyOffice 缓存目录（避免从 wp_onlyoffice_router 循环导入）。"""
    return Path(settings.STORAGE_ROOT) / "projects" / str(project_id) / "workpapers" / "onlyoffice"


async def _load_wp(db: AsyncSession, wp_id: UUID) -> tuple[WorkingPaper, str]:
    result = await db.execute(
        sa.select(WorkingPaper, WpIndex.wp_code)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false())
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="底稿不存在")
    return row[0], row[1]


def _ensure_template() -> Path:
    """确保 F2-22 占位符模板存在；缺失则按 G2-6-2 结构生成。"""
    existing = find_template_file_any("F2-22")
    if existing and existing.suffix.lower() == ".docx":
        try:
            from docx import Document

            text = "\n".join(p.text for p in Document(str(existing)).paragraphs)
            if "${purpose}" in text:
                return existing
        except Exception:  # noqa: BLE001
            pass
    target = TEMPLATES_DIR / "F" / "F2-22 存货监盘计划.docx"
    return create_g2_6_2_template_docx(target)


async def _load_fields(db: AsyncSession, wp_id: UUID) -> dict[str, str]:
    result = await db.execute(
        sa.text(
            "SELECT remark FROM checklist_responses "
            "WHERE wp_id = :wid AND item_id = :iid LIMIT 1"
        ),
        {"wid": str(wp_id), "iid": FIELDS_ITEM_ID},
    )
    row = result.first()
    return parse_fields_json(row.remark if row else None)


async def _save_fields(
    db: AsyncSession,
    *,
    project_id: UUID,
    wp_id: UUID,
    wp_code: str | None,
    docx_path: Path,
    fields: dict[str, str],
) -> ContentCommitReceipt:
    """把抽出的字段与**产生它们的 docx 本体**在一次业务事务里提交。

    🔴 Task 19（workpaper-html-onlyoffice-bidirectional-writeback-closure /
    Requirement 2.2、12.7、Property 61）：本函数改造前 `INSERT ... ON CONFLICT` 之后
    直接 `await db.commit()`，整条 F2 半闭环因此完全在 `working_paper` 版本域之外 ——
    一次 from-OO 写回既不推进任何版本，也不留下「这份 docx 就是当时的权威内容」的
    immutable 记录。用户在 OnlyOffice 里改完点同步，平台侧的版本号一动不动，编辑器
    base 与附注 stale 判定都看不出内容换了。

    **走 authoritative-bytes lane 而不是 projection lane**，理由是 manifest 事实而不是
    偏好：`workpaper_sync_entry_manifest.json` 里 F2 的 entry（`xlsx/gt-f2-stocktake-
    bundle`）`capability=single_onlyoffice`。Task 19 的边界是「F2 暂保现有能力但版本域
    统一」（第二套流程由 Task 60 删除），所以 capability 不动；而对
    `single_onlyoffice` 来说权威内容就是 OOXML 本体（Requirement 2.11），projection
    lane 会在 `HtmlOnlyCommitPlan.__post_init__` 就把它拒掉。

    `checklist_responses` 里那份 fields JSON 是**派生视图**（供结构化 UI 读），docx 才
    是权威载荷 —— 因此 `payload` 传的是 `docx_path.read_bytes()`，绝不是
    `json.dumps(fields)`。

    本函数自己**没有** commit、没有任何版本字段赋值：fields 行、content version、
    `content_revision` CAS、published representation 与 outbox 同生共死。
    """
    import json

    payload = json.dumps(fields, ensure_ascii=False)
    await db.execute(
        sa.text(
            "INSERT INTO checklist_responses "
            "(project_id, wp_id, item_id, conclusion, remark) "
            "VALUES (:pid, :wid, :iid, NULL, :remark) "
            "ON CONFLICT (wp_id, item_id) "
            "DO UPDATE SET remark = EXCLUDED.remark, "
            "project_id = COALESCE(checklist_responses.project_id, EXCLUDED.project_id)"
        ),
        {
            "pid": str(project_id),
            "wid": str(wp_id),
            "iid": FIELDS_ITEM_ID,
            "remark": payload,
        },
    )

    writer = build_content_mutation_service_writer(db)
    receipt = await writer.commit_bytes(
        project_id=project_id,
        wp_id=wp_id,
        # 🔴 entry_id 必须带 sheet code：F2-22 与 F2-23 是同一个底稿的**两份不同文档**。
        #    共用一个 entry 会让两者互相顶掉对方的 entry pointer / representation
        #    generation，历史读取拿到的是另一张表的 docx。
        entry_id=opaque_entry_id(wp_code=f"{wp_code or wp_id}#{_SHEET_CODE}", wp_id=wp_id),
        source=ONLYOFFICE,
        payload=docx_path.read_bytes(),
        document_type="docx",
        expected_revision=await writer.current_revision(wp_id),
        substrate_path=docx_path,
        # Task 65：authority model 由 lane 登记决定（`f2_stocktake_plan` →
        # `opaque_single_onlyoffice`），不再由调用点传一个可漏可错的身份参数。
        lane_id="f2_stocktake_plan",
        reason="f2_st_plan_sync_from_oo",
    )
    await writer.publish_committed_events(receipt)
    return receipt


async def _project_context(db: AsyncSession, project_id: UUID) -> dict:
    result = await db.execute(
        sa.text(
            "SELECT client_name, audit_year, "
            "to_char(audit_period_end, 'YYYY-MM-DD') AS bs_date "
            "FROM projects WHERE id = :pid"
        ),
        {"pid": str(project_id)},
    )
    row = result.first()
    if not row:
        return {}
    return {
        "client_name": row.client_name or "",
        "audit_year": str(row.audit_year or ""),
        "bs_date": row.bs_date or "",
    }


def _normalize_sheet(sheet: str) -> str:
    s = (sheet or "").strip()
    if "F2-22" in s or s in _SHEET_CODES:
        return "F2-22"
    raise HTTPException(status_code=400, detail=f"不支持的 sheet: {sheet}")


@router.post("/api/workpapers/{wp_id}/f2-st/plan-sync-to-oo")
async def f2_st_plan_sync_to_oo(
    wp_id: UUID,
    sheet: str = Query("F2-22"),
    project_id: UUID | None = Query(None, description="可选；缺省时从底稿反查"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """结构化 → OnlyOffice：用 F2-22-fields 填充 docx 缓存。"""
    _ = current_user
    _normalize_sheet(sheet)
    wp, _wp_code = await _load_wp(db, wp_id)
    pid = project_id or wp.project_id
    if project_id and project_id != wp.project_id:
        raise HTTPException(status_code=400, detail="project_id 与底稿所属项目不一致")
    await set_rls_context(db, pid)
    template = _ensure_template()
    fields = await _load_fields(db, wp_id)
    ctx = await _project_context(db, pid)
    target = _onlyoffice_dir(pid) / f"{_SHEET_CODE}.docx"
    legacy = target.with_suffix(".xlsx")
    if legacy.exists():
        try:
            legacy.unlink()
        except OSError:
            pass
    fill_plan_docx(template, target, fields, project_context=ctx)
    return {
        "ok": True,
        "direction": "to_oo",
        "path": str(target),
        "filled_keys": [k for k, v in fields.items() if v],
        "size": target.stat().st_size,
    }


@router.post("/api/workpapers/{wp_id}/f2-st/plan-sync-from-oo")
async def f2_st_plan_sync_from_oo(
    wp_id: UUID,
    sheet: str = Query("F2-22"),
    project_id: UUID | None = Query(None, description="可选；缺省时从底稿反查"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """OnlyOffice → 结构化：解析 docx 缓存写回 F2-22-fields。"""
    _ = current_user
    _normalize_sheet(sheet)
    wp, wp_code = await _load_wp(db, wp_id)
    pid = project_id or wp.project_id
    if project_id and project_id != wp.project_id:
        raise HTTPException(status_code=400, detail="project_id 与底稿所属项目不一致")
    await set_rls_context(db, pid)
    target = _onlyoffice_dir(pid) / f"{_SHEET_CODE}.docx"
    if not target.exists():
        raise HTTPException(status_code=404, detail="尚未生成监盘计划 Word 缓存，请先打开在线编辑")
    existing = await _load_fields(db, wp_id)
    try:
        extracted = extract_fields_from_docx(target)
    except Exception as exc:  # noqa: BLE001
        logger.exception("F2-22 plan-sync-from-oo 解析失败 wp_id=%s", wp_id)
        raise HTTPException(status_code=500, detail=f"Word 解析失败: {exc}") from exc
    merged = merge_extracted_into_existing(existing, extracted)
    try:
        receipt = await _save_fields(
            db,
            project_id=pid,
            wp_id=wp_id,
            wp_code=wp_code,
            docx_path=target,
            fields=merged,
        )
    # 🔴 窄捕获必须排在宽捕获**之前**：并发保存是用户可行动的 409（重新打开再同步），
    #    被下面那条 `except Exception` 吞成 500「结构化落库失败」时用户看到的原因是错的
    #    （Requirement 5.12）。宽捕获本身是本端点的既有形态，Task 60 删第二套流程时一并
    #    收口，这里只保证冲突不被误报。
    except RevisionConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="底稿已被其他用户修改，请重新打开在线编辑后再同步",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("F2-22 plan-sync-from-oo 落库失败 wp_id=%s", wp_id)
        raise HTTPException(status_code=500, detail=f"结构化落库失败: {exc}") from exc
    return {
        "ok": True,
        "direction": "from_oo",
        "extracted_keys": list(extracted.keys()),
        "fields": merged,
        # 回传 CAS **实际推进到的** business revision，让前端下次提交的 expected 与
        # 服务端事实同源。
        "content_revision": receipt.revision,
    }
