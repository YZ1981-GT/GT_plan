"""归档包构建（spec attachment-archive-and-a-class-evidence ADR-AE-01 / ADR-AE-02，design §3.2）。

按 ``archive_inventory`` 的清单 + 每张底稿的数据快照 + 归档章节生成器写一个 zip：

- 清单有缺件、章节生成器抛错、Paperless 取不到 ⇒ 抛 :class:`ArchivePackageError`（逐项列出），不留半成品文件；
- 章节生成器返回 ``None`` ⇒ 该章节不适用，``manifest.json`` 的 ``skipped`` 里记一笔；
- ``manifest.json`` 逐项记录类别、来源 id、包内路径、字节数、sha256，最后写入；``manifest_hash`` 是它的 sha256。
"""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.archive_inventory import (
    CATEGORY_LABELS,
    OK,
    SKIPPED,
    InventoryEntry,
    build_project_inventory,
    safe_name,
)

_CHUNK = 1024 * 1024

#: 核对表填写（无 ORM 模型，走轻量表结构；``Uuid`` 类型让 SQLite / PG 各按自己的存法绑定）
_CHECKLIST = sa.table(
    "checklist_responses",
    sa.column("wp_id", sa.Uuid()), sa.column("item_id", sa.String()), sa.column("conclusion", sa.String()),
    sa.column("remark", sa.String()), sa.column("wp_ref", sa.String()),
)


class ArchivePackageError(RuntimeError):
    """归档包缺件；``problems`` 是逐项「类别｜名称｜原因」。"""

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        head = "；".join(self.problems[:5]) + ("…" if len(self.problems) > 5 else "")
        super().__init__(f"归档包有 {len(self.problems)} 项读不到，未生成归档包：{head}")


@dataclass(frozen=True)
class PackageResult:
    path: Path
    sha256: str
    size: int
    manifest_hash: str
    counts: dict[str, int] = field(default_factory=dict)
    skipped: int = 0


def archive_root() -> Path:
    from app.core.config import settings

    return Path(settings.STORAGE_ROOT) / "archives"


def package_path(project_id: UUID, job_id: UUID) -> Path:
    return archive_root() / str(project_id) / f"{job_id}.zip"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


async def _render_sections(db: AsyncSession, project_id: UUID) -> tuple[list[tuple[str, str, bytes]], list[str], list[dict]]:
    """逐个调用章节生成器：返回（[(包内名, 来源前缀, 内容)], 问题, 跳过）。"""
    from app.services import archive_section_registry

    rendered: list[tuple[str, str, bytes]] = []
    problems: list[str] = []
    skipped: list[dict] = []
    for section in archive_section_registry.list_all():
        title = section.description or section.filename
        try:
            content = await section.generator_func(project_id, db)
        except Exception as exc:  # noqa: BLE001 — 生成器失败即缺件（ADR-AE-02）
            problems.append(f"归档章节｜{title}｜生成失败：{exc}")
            continue
        if content is None:
            skipped.append({"category": "section", "label": title, "reason": "本项目不适用（生成器未返回内容）"})
            continue
        if isinstance(content, Path):
            if not content.is_file():
                problems.append(f"归档章节｜{title}｜生成的文件不存在")
                continue
            content = content.read_bytes()
        elif isinstance(content, str):
            content = content.encode("utf-8")
        elif not isinstance(content, (bytes, bytearray)):
            problems.append(f"归档章节｜{title}｜生成器返回了无法写入的内容（{type(content).__name__}）")
            continue
        rendered.append((safe_name(section.filename), section.order_prefix, bytes(content)))
    return rendered, problems, skipped


async def _fetch_paperless(db: AsyncSession, entries: list[InventoryEntry]) -> tuple[dict[str, bytes], list[str]]:
    if not entries:
        return {}, []
    import httpx

    from app.services.attachment_service import AttachmentService

    svc = AttachmentService(db)
    headers = {"Authorization": f"Token {svc.paperless_token}"} if svc.paperless_token else {}
    out: dict[str, bytes] = {}
    problems: list[str] = []
    async with httpx.AsyncClient(timeout=60, mounts={}, trust_env=False) as client:
        for e in entries:
            try:
                resp = await client.get(f"{svc.paperless_url}/api/documents/{e.paperless_document_id}/download/",
                                        headers=headers)
            except httpx.HTTPError as exc:
                problems.append(f"附件｜{e.label}｜Paperless 不可达：{exc}")
                continue
            if resp.status_code != 200:
                problems.append(f"附件｜{e.label}｜Paperless 返回 {resp.status_code}")
                continue
            out[e.source_id] = resp.content
    return out, problems


async def _workpaper_snapshots(db: AsyncSession, project_id: UUID) -> list[tuple[str, str, dict]]:
    """每张未删除底稿：（编码, 名称, 快照 JSON）。"""
    from app.models.workpaper_models import WorkingPaper, WpIndex

    rows = (await db.execute(
        sa.select(WorkingPaper, WpIndex.wp_code, WpIndex.wp_name)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == sa.false())
        .order_by(WpIndex.wp_code, WorkingPaper.id)
    )).all()
    ids = [wp.id for wp, _, _ in rows]
    answers: dict[UUID, list[dict]] = {}
    if ids:
        res = await db.execute(
            sa.select(_CHECKLIST.c.wp_id, _CHECKLIST.c.item_id, _CHECKLIST.c.conclusion,
                      _CHECKLIST.c.remark, _CHECKLIST.c.wp_ref)
            .where(_CHECKLIST.c.wp_id.in_(ids)).order_by(_CHECKLIST.c.item_id)
        )
        for wp_id, item_id, conclusion, remark, wp_ref in res.all():
            answers.setdefault(wp_id, []).append(
                {"item_id": item_id, "conclusion": conclusion, "remark": remark, "wp_ref": wp_ref})
    out = []
    for wp, code, name in rows:
        status = getattr(wp.status, "value", wp.status)
        out.append((code or str(wp.id), name or "", {
            "wp_id": str(wp.id), "wp_code": code, "wp_name": name, "status": status,
            "parsed_data": wp.parsed_data, "checklist_responses": answers.get(wp.id, []),
        }))
    return out


class _Writer:
    def __init__(self, zf: zipfile.ZipFile):
        self.zf = zf
        self.entries: list[dict] = []
        self.names: set[str] = set()

    def _unique(self, arcname: str) -> str:
        stem, suffix = os.path.splitext(arcname)
        name, n = arcname, 1
        while name.casefold() in self.names:
            n += 1
            name = f"{stem}-{n}{suffix}"
        self.names.add(name.casefold())
        return name

    def add_bytes(self, arcname: str, data: bytes, *, category: str, source_id: str, label: str) -> None:
        arcname = self._unique(arcname)
        self.zf.writestr(arcname, data)
        self.entries.append({"category": category, "source_id": source_id, "label": label, "arcname": arcname,
                             "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})

    def add_file(self, arcname: str, src: Path, *, category: str, source_id: str, label: str) -> None:
        arcname = self._unique(arcname)
        h, size = hashlib.sha256(), 0
        with open(src, "rb") as f, self.zf.open(arcname, "w", force_zip64=True) as dst:
            while chunk := f.read(_CHUNK):
                h.update(chunk)
                size += len(chunk)
                dst.write(chunk)
        self.entries.append({"category": category, "source_id": source_id, "label": label, "arcname": arcname,
                             "size": size, "sha256": h.hexdigest()})


async def build_archive_package(db: AsyncSession, project_id: UUID, job_id: UUID) -> PackageResult:
    inventory = await build_project_inventory(db, project_id)
    problems = [f"{CATEGORY_LABELS[e.category]}｜{e.label}｜{e.reason}" for e in inventory.missing]
    sections, section_problems, skipped = await _render_sections(db, project_id)
    problems.extend(section_problems)
    ok_entries = [e for e in inventory.entries if e.status == OK]
    paperless, paperless_problems = await _fetch_paperless(
        db, [e for e in ok_entries if e.local_path is None and e.paperless_document_id is not None])
    problems.extend(paperless_problems)
    if problems:
        raise ArchivePackageError(problems)
    snapshots = await _workpaper_snapshots(db, project_id)
    skipped.extend({"category": e.category, "label": e.label, "reason": e.reason}
                   for e in inventory.entries if e.status == SKIPPED)

    target = package_path(project_id, job_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    try:
        with zipfile.ZipFile(part, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            w = _Writer(zf)
            for name, prefix, data in sections:
                w.add_bytes(name, data, category="section", source_id=prefix, label=name)
            for e in ok_entries:
                if e.local_path is not None:
                    w.add_file(e.arcname, e.local_path, category=e.category, source_id=e.source_id, label=e.label)
                else:
                    w.add_bytes(e.arcname, paperless[e.source_id], category=e.category, source_id=e.source_id,
                                label=e.label)
            for code, name, snap in snapshots:
                data = json.dumps(snap, ensure_ascii=False, sort_keys=True, indent=2, default=str).encode("utf-8")
                w.add_bytes(f"11-底稿数据/{safe_name(code)}.json", data, category="workpaper_data",
                            source_id=snap["wp_id"], label=f"{code} {(name or '').strip()}".strip())
            manifest = {
                "project_id": str(project_id), "job_id": str(job_id),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "entries": w.entries, "skipped": skipped,
            }
            manifest_bytes = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
            zf.writestr("manifest.json", manifest_bytes)
        os.replace(part, target)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    counts: dict[str, int] = {}
    for item in w.entries:
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    return PackageResult(
        path=target, sha256=file_sha256(target), size=target.stat().st_size,
        manifest_hash=hashlib.sha256(manifest_bytes).hexdigest(), counts=counts, skipped=len(skipped),
    )
