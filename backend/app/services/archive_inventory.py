"""项目归档清单（spec attachment-archive-and-a-class-evidence ADR-AE-01 / ADR-AE-02）。

归档包与归档完整性检查共用这一份清单：底稿文件、现行附件、已确认交付件逐项判定能否读到。
改造前打包只把 ``storage/projects/{pid}`` 目录打成 tar —— 真库多数底稿文件不在那里，附件与交付件
根本不进包，打包失败也只返回 ``{"error": ...}``，编排照样判成功。

判定口径：
- 底稿文件：``resolve_wp_file(..., allow_template_fallback=False)``；路径为空或指向模板库 ⇒ 未生成文件（只收数据
  快照，不算缺件）；路径配了但读不到 / 越界 / 类型不符 ⇒ 缺件。
- 附件：未删除、状态 ``available``、未被其他未删除附件以 ``previous_version_id`` 指向（已被新版本取代的不收）；
  本地按下载同口径找文件，``paperless://`` 打包时经 Paperless 下载，Paperless 未配置 ⇒ 缺件。
- 交付件：``word_export_task`` 状态为已确认 / 已签字 / 已归档。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

OK, MISSING, SKIPPED = "ok", "missing", "skipped"

CATEGORY_LABELS: dict[str, str] = {
    "workpaper_file": "底稿文件",
    "workpaper_data": "底稿数据",
    "attachment": "附件",
    "deliverable": "交付件",
    "section": "归档章节",
}

_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


@dataclass(frozen=True)
class InventoryEntry:
    category: str
    source_id: str
    label: str
    arcname: str
    status: str
    reason: str = ""
    local_path: Path | None = None
    paperless_document_id: int | None = None
    wp_code: str = ""


@dataclass
class ProjectInventory:
    project_id: UUID
    entries: list[InventoryEntry] = field(default_factory=list)

    def by_status(self, status: str) -> list[InventoryEntry]:
        return [e for e in self.entries if e.status == status]

    @property
    def missing(self) -> list[InventoryEntry]:
        return self.by_status(MISSING)


def safe_name(text: str, fallback: str = "未命名") -> str:
    """包内文件名：去掉路径分隔符与 Windows 非法字符，首尾空白与点去掉。"""
    cleaned = _UNSAFE_NAME.sub("_", text or "").strip().strip(".")
    return cleaned or fallback


class _ArcNames:
    """包内路径去重（同名第二次起加 ``-2``、``-3``）。"""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def take(self, folder: str, stem: str, suffix: str) -> str:
        base = f"{folder}/{stem}"
        name, n = f"{base}{suffix}", 1
        while name.casefold() in self._seen:
            n += 1
            name = f"{base}-{n}{suffix}"
        self._seen.add(name.casefold())
        return name


def _template_root() -> Path:
    from app.services.wp_export.wp_file_resolver import BACKEND_ROOT

    return (BACKEND_ROOT / "wp_templates").resolve()


def _paperless_doc_id(att) -> int | None:
    if att.paperless_document_id is not None:
        return int(att.paperless_document_id)
    raw = (att.file_path or "").replace("paperless://", "", 1).strip("/")
    raw = raw.removeprefix("documents/").strip("/")
    return int(raw) if raw.isdigit() else None


async def _workpaper_entries(db: AsyncSession, project_id: UUID, names: _ArcNames) -> list[InventoryEntry]:
    from app.models.workpaper_models import WorkingPaper, WpIndex
    from app.services.wp_export.wp_file_resolver import VERDICT_LABELS, resolve_wp_file

    rows = (await db.execute(
        sa.select(WorkingPaper.id, WorkingPaper.file_path, WpIndex.wp_code, WpIndex.wp_name)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == sa.false())
        .order_by(WpIndex.wp_code, WorkingPaper.id)
    )).all()
    templates = _template_root()
    out: list[InventoryEntry] = []
    for wp_id, file_path, wp_code, wp_name in rows:
        # 名称首尾空白先去掉（模板名带前导空格，如「 管理层声明书程序表」⇒ 包内名出现双空格）
        label = f"{wp_code} {(wp_name or '').strip()}".strip()
        base = dict(category="workpaper_file", source_id=str(wp_id), label=label, wp_code=wp_code or "")
        res = resolve_wp_file(file_path, wp_code=None, allow_template_fallback=False)
        if res.verdict == "file" and res.path is not None:
            if res.path.resolve().is_relative_to(templates):
                out.append(InventoryEntry(**base, arcname="", status=SKIPPED, reason="未生成底稿文件（指向模板库），仅收数据快照"))
                continue
            arcname = names.take("10-底稿", safe_name(label), res.path.suffix.lower())
            out.append(InventoryEntry(**base, arcname=arcname, status=OK, local_path=res.path))
        elif res.verdict == "empty":
            out.append(InventoryEntry(**base, arcname="", status=SKIPPED, reason="未生成底稿文件，仅收数据快照"))
        else:
            out.append(InventoryEntry(**base, arcname="", status=MISSING,
                                      reason=VERDICT_LABELS.get(res.verdict, "底稿文件读不到")))
    return out


async def _attachment_entries(db: AsyncSession, project_id: UUID, names: _ArcNames) -> list[InventoryEntry]:
    from app.models.attachment_models import Attachment
    from app.services.asset_blob_service import AssetBlobReadRejected, AssetBlobService
    from app.services.attachment_service import AttachmentService
    from app.services.attachment_storage_resolver import resolve_project_attachment_file

    atts = (await db.execute(
        sa.select(Attachment).where(Attachment.project_id == project_id, Attachment.is_deleted == sa.false())
        .order_by(Attachment.created_at, Attachment.id)
    )).scalars().all()
    superseded = {a.previous_version_id for a in atts if a.previous_version_id is not None}
    paperless_on = AttachmentService(db).paperless_enabled()
    out: list[InventoryEntry] = []
    for att in atts:
        if att.id in superseded or att.state in ("inactive", "tombstoned"):
            continue
        label = att.file_name or str(att.id)
        base = dict(category="attachment", source_id=str(att.id), label=label)
        if att.state != "available":
            out.append(InventoryEntry(**base, arcname="", status=SKIPPED, reason="附件尚未通过检测，不入包"))
            continue
        stem, suffix = os.path.splitext(safe_name(label))
        arcname = names.take("40-附件", f"{str(att.id)[:8]}-{stem}", suffix.lower())
        if (att.file_path or "").startswith("paperless://"):  # 与附件下载同口径：按路径前缀判存储
            doc_id = _paperless_doc_id(att)
            if doc_id is None:
                out.append(InventoryEntry(**base, arcname="", status=MISSING, reason="附件存于 Paperless，但没有文档编号"))
            elif not paperless_on:
                out.append(InventoryEntry(**base, arcname="", status=MISSING, reason="附件存于 Paperless，但平台未配置 Paperless"))
            else:
                out.append(InventoryEntry(**base, arcname=arcname, status=OK, paperless_document_id=doc_id))
            continue
        try:
            blob = await AssetBlobService(db).read_current_attachment_blob(
                att.id,
                project_id=att.project_id,
            )
        except AssetBlobReadRejected:
            from app.services.attachment_asset_projection import asset_blob_read_authoritative

            if att.storage_type == "asset_blob" or asset_blob_read_authoritative():
                out.append(InventoryEntry(
                    **base,
                    arcname="",
                    status=MISSING,
                    reason="附件不可变版本完整性校验失败",
                ))
                continue
            blob = None
        path = blob.canonical_path if blob is not None else resolve_project_attachment_file(
            att.project_id,
            att.storage_type,
            att.file_path,
        )
        if path is None:
            out.append(InventoryEntry(**base, arcname="", status=MISSING, reason="附件文件不存在"))
        else:
            out.append(InventoryEntry(**base, arcname=arcname, status=OK, local_path=path))
    return out


async def _deliverable_entries(db: AsyncSession, project_id: UUID, names: _ArcNames) -> list[InventoryEntry]:
    from app.models.phase13_models import WordExportTask
    from app.services.attachment_upload_policy import resolve_local_attachment_file
    from app.services.deliverable_service import TERMINAL_REEXPORT_STATUSES

    tasks = (await db.execute(
        sa.select(WordExportTask).where(
            WordExportTask.project_id == project_id,
            WordExportTask.status.in_(sorted(TERMINAL_REEXPORT_STATUSES)),
        ).order_by(WordExportTask.doc_type, WordExportTask.created_at, WordExportTask.id)
    )).scalars().all()
    out: list[InventoryEntry] = []
    for task in tasks:
        label = f"{task.doc_type}（{task.status}）"
        base = dict(category="deliverable", source_id=str(task.id), label=label)
        path = resolve_local_attachment_file(task.file_path)
        if path is None:
            out.append(InventoryEntry(**base, arcname="", status=MISSING, reason="交付件文件不存在"))
            continue
        arcname = names.take("50-交付件", f"{safe_name(task.doc_type)}-{str(task.id)[:8]}", path.suffix.lower())
        out.append(InventoryEntry(**base, arcname=arcname, status=OK, local_path=path))
    return out


async def _consol_entries(db: AsyncSession, project_id: UUID, names: _ArcNames) -> list[InventoryEntry]:
    """合并项目归档清单项（spec consolidation-run-and-workpaper-lifecycle-closure 任务 6.5 / ADR-CRW-006）。

    只对 ``report_scope='consolidated'`` 的项目生效；调 ``consol_archive_provider`` 把成功 operation、
    正式报表运行、不可变 artifact、签字快照、附件证据和审计清单汇成的清单映射进通用 ``InventoryEntry``：

    - ``missing`` ⇒ ``MISSING``（归档缺件，``build_archive_package`` 据此 fail-closed，不降级为成功）；
    - ``report_excel`` / ``consol_workpaper`` 的 ``ready`` artifact ⇒ 真文件入包（解析合并存储根下的文件）；
    - operation / report_run / sign_snapshot / attachments / audit_manifest / workpaper_shell 的 ``ready``
      是数据/引用型 required source，记 ``SKIPPED`` 并写明（manifest 里保留，不作为文件入包）；
    - ``not_applicable`` ⇒ ``SKIPPED``。

    非合并项目返回空列表（口径不变，generic 清单照旧）。
    """
    from app.models.core import Project

    row = (await db.execute(
        sa.select(Project.report_scope, Project.audit_year).where(Project.id == project_id)
    )).first()
    if row is None or (row[0] or "").strip().lower() != "consolidated":
        return []
    year = int(row[1]) if row[1] is not None else 0

    from app.services.consol_archive_provider import collect_consol_archive_items

    items = await collect_consol_archive_items(db, project_id, year)
    out: list[InventoryEntry] = []
    for item in items:
        kind = item.get("kind", "consol")
        label = f"合并｜{item.get('label') or kind}"
        base = dict(category="workpaper_data", source_id=f"consol:{kind}", label=label, wp_code="A3-CONSOL")
        status = item.get("status")
        if status == "missing":
            out.append(InventoryEntry(**base, arcname="", status=MISSING,
                                      reason=item.get("reason") or f"{label} 缺失"))
            continue
        if status == "ready" and kind in ("report_excel", "consol_workpaper") and item.get("storage_path"):
            entry = _resolve_consol_artifact_entry(base, item, names)
            out.append(entry)
            continue
        # 其余 ready / not_applicable 的 required source 以引用形式记录（不作为文件入包）
        detail = item.get("reason") or _consol_ready_detail(item)
        out.append(InventoryEntry(**base, arcname="", status=SKIPPED, reason=detail))
    return out


def _consol_ready_detail(item: dict) -> str:
    """合并 ready 数据/引用项的 SKIPPED 说明（写进 manifest 的 skipped，便于追溯）。"""
    kind = item.get("kind")
    if kind == "consol_operation":
        return f"已成功合并运行 {item.get('operation_id')}（rev {item.get('operation_revision')}）"
    if kind == "report_run":
        return f"正式报表运行 {item.get('report_run_id')}（digest {item.get('row_digest')}）"
    if kind == "sign_snapshot":
        return f"签字快照 {item.get('snapshot_id')}（hash {item.get('hash')}）"
    if kind == "attachments":
        return f"附件证据 {item.get('attachment_count', 0)} 项（随附件类目入包）"
    if kind == "audit_manifest":
        return f"审计留痕 {item.get('entry_count', 0)} 条（链尾 {item.get('tail_hash')}）"
    if kind == "workpaper_shell":
        return f"合并底稿壳 {item.get('working_paper_id')}"
    return "合并产物引用（非文件）"


def _resolve_consol_artifact_entry(base: dict, item: dict, names: _ArcNames) -> InventoryEntry:
    """把 ready 的合并 artifact 映射成真文件入包项；文件读不到 ⇒ MISSING（fail-closed）。"""
    from app.services.consol_artifact_service import ArtifactError, resolve_artifact_path

    try:
        path = resolve_artifact_path(item["storage_path"])
    except ArtifactError:
        return InventoryEntry(**base, arcname="", status=MISSING, reason=f"{base['label']} 存储路径不合法")
    if not path.is_file():
        return InventoryEntry(**base, arcname="", status=MISSING, reason=f"{base['label']} 文件不存在")
    stem = safe_name(item.get("file_name") or base["label"])
    arcname = names.take("12-合并产物", stem, path.suffix.lower() or ".xlsx")
    return InventoryEntry(**base, arcname=arcname, status=OK, local_path=path)


async def build_project_inventory(db: AsyncSession, project_id: UUID) -> ProjectInventory:
    """底稿文件 + 现行附件 + 已确认交付件的清单（数据快照与章节在打包时生成，不在清单里）。

    合并项目额外纳入合并产物清单（成功 operation/artifact/签字快照/附件/审计），缺件 fail-closed。
    """
    names = _ArcNames()
    inv = ProjectInventory(project_id=project_id)
    inv.entries.extend(await _workpaper_entries(db, project_id, names))
    inv.entries.extend(await _attachment_entries(db, project_id, names))
    inv.entries.extend(await _deliverable_entries(db, project_id, names))
    inv.entries.extend(await _consol_entries(db, project_id, names))
    return inv


def normalized_path(path: Path) -> str:
    """路径比较口径：resolve 后按平台规则规范大小写（Windows 不区分大小写）。"""
    return os.path.normcase(str(path.resolve()))


async def referenced_local_paths(db: AsyncSession, *, name_hint: str | None = None,
                                 project_id: UUID | None = None) -> set[str]:
    """附件行（含已删除）与治理版本行引用的本地文件（规范化绝对路径）。

    ``project_id`` 给定 ⇒ 取该项目全部附件行；``name_hint`` 给定 ⇒ 取路径以该文件名结尾的行（跨项目）。
    """
    from app.models.attachment_models import Attachment
    from app.models.evidence_governance_models import AttachmentVersion
    from app.services.attachment_storage_resolver import resolve_project_attachment_file

    att_q = sa.select(Attachment.project_id, Attachment.storage_type, Attachment.file_path)
    ver_q = sa.select(
        AttachmentVersion.project_id,
        AttachmentVersion.storage_type,
        AttachmentVersion.storage_key,
        AttachmentVersion.config_snapshot,
    )
    if project_id is not None:
        att_q = att_q.where(Attachment.project_id == project_id)
        ver_q = ver_q.where(AttachmentVersion.project_id == project_id)
    if name_hint:
        att_q = att_q.where(Attachment.file_path.like(f"%{name_hint}"))
        ver_q = ver_q.where(AttachmentVersion.storage_key.like(f"%{name_hint}"))
    refs: list[tuple[UUID, str | None, str | None]] = list((await db.execute(att_q)).all())
    for pid, storage_type, storage_key, snapshot in (await db.execute(ver_q)).all():
        finalized = snapshot.get("finalized_storage") if isinstance(snapshot, dict) else None
        finalized = finalized if isinstance(finalized, dict) else {}
        refs.append((
            pid,
            finalized.get("storage_type") or storage_type,
            finalized.get("storage_key") or finalized.get("file_path") or storage_key,
        ))
    out: set[str] = set()
    for pid, storage_type, storage_key in refs:
        path = resolve_project_attachment_file(pid, storage_type, storage_key)
        if path is not None:
            out.add(normalized_path(path))
    return out


async def orphan_files(db: AsyncSession, project_id: UUID) -> list[Path]:
    """附件存储根 ``{root}/{pid}`` 下没有任何附件行（含已删除）/ 版本行引用的文件。"""
    from app.services.attachment_storage_resolver import project_attachment_root

    project_dir = project_attachment_root(project_id)
    if not project_dir.is_dir():
        return []
    referenced = await referenced_local_paths(db, project_id=project_id)
    return sorted(p for p in project_dir.rglob("*") if p.is_file() and normalized_path(p) not in referenced)
