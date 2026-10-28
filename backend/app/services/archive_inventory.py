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
    from app.services.attachment_service import AttachmentService
    from app.services.attachment_upload_policy import resolve_local_attachment_file

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
        path = resolve_local_attachment_file(att.file_path)
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


async def build_project_inventory(db: AsyncSession, project_id: UUID) -> ProjectInventory:
    """底稿文件 + 现行附件 + 已确认交付件的清单（数据快照与章节在打包时生成，不在清单里）。"""
    names = _ArcNames()
    inv = ProjectInventory(project_id=project_id)
    inv.entries.extend(await _workpaper_entries(db, project_id, names))
    inv.entries.extend(await _attachment_entries(db, project_id, names))
    inv.entries.extend(await _deliverable_entries(db, project_id, names))
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
    from app.services.attachment_upload_policy import resolve_local_attachment_file

    raws: list[str | None] = []
    att_q = sa.select(Attachment.file_path)
    ver_q = sa.select(AttachmentVersion.storage_key)
    if project_id is not None:
        att_q = att_q.where(Attachment.project_id == project_id)
        ver_q = ver_q.where(AttachmentVersion.project_id == project_id)
    if name_hint:
        att_q = att_q.where(Attachment.file_path.like(f"%{name_hint}"))
        ver_q = ver_q.where(AttachmentVersion.storage_key.like(f"%{name_hint}"))
    raws.extend((await db.execute(att_q)).scalars().all())
    raws.extend((await db.execute(ver_q)).scalars().all())
    out: set[str] = set()
    for raw in raws:
        path = resolve_local_attachment_file(raw)
        if path is not None:
            out.add(normalized_path(path))
    return out


async def orphan_files(db: AsyncSession, project_id: UUID) -> list[Path]:
    """附件存储根 ``{root}/{pid}`` 下没有任何附件行（含已删除）/ 版本行引用的文件。"""
    from app.core.config import settings

    project_dir = Path(settings.ATTACHMENT_LOCAL_STORAGE_ROOT) / str(project_id)
    if not project_dir.is_dir():
        return []
    referenced = await referenced_local_paths(db, project_id=project_id)
    return sorted(p for p in project_dir.rglob("*") if p.is_file() and normalized_path(p) not in referenced)
