"""高级查询证据封存与管理（AQF §6）。

导出文件写进证据目录（`{QUERY_ARTIFACT_ROOT}/{yyyy}/{mm}/{artifact_id}.xlsx`），
流式计算 SHA-256，原子改名；独立短事务写证据记录并提交。

降级策略（ADR-AQF-06）：保存失败不阻断导出 —— 改走现有临时文件路径，响应头
``X-Query-Artifact-Status: unavailable``；已登记的运行记录保留。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

ARTIFACT_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ─── 证据目录 ─────────────────────────────────────────────────────────────────

def _artifact_root() -> Path:
    from app.core.config import settings
    root = (settings.QUERY_ARTIFACT_ROOT or "").strip()
    if not root:
        root = os.path.join(settings.STORAGE_ROOT, "query_artifacts")
    return Path(root)


def artifact_directory(artifact_id: uuid.UUID, now: datetime | None = None) -> Path:
    """证据文件的存储子目录 `{root}/{yyyy}/{mm}/`；若不存在则自动创建。"""
    t = now or datetime.now(timezone.utc)
    d = _artifact_root() / f"{t.year:04d}" / f"{t.month:02d}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def artifact_path(directory: Path, artifact_id: uuid.UUID) -> Path:
    """最终文件路径（`.xlsx`）。"""
    return directory / f"{artifact_id}.xlsx"


def partial_path(directory: Path, artifact_id: uuid.UUID) -> Path:
    """写入中的临时文件路径（`.{id}.partial`）。"""
    return directory / f".{artifact_id}.partial"


def storage_key(directory: Path, artifact_id: uuid.UUID) -> str:
    """相对证据根目录的存储键（用于 query_artifacts.storage_key 列）。"""
    root = _artifact_root()
    try:
        return str(Path(directory / f"{artifact_id}.xlsx").relative_to(root))
    except ValueError:
        return str(directory / f"{artifact_id}.xlsx")


# ─── SHA-256 流式计算 ─────────────────────────────────────────────────────────

def file_sha256(path: str | Path) -> str:
    """计算文件 SHA-256（流式，不全量读进内存）。"""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ─── 清单（manifest v1）──────────────────────────────────────────────────────

def _canonical_manifest(
    *,
    artifact_id: uuid.UUID,
    run_id: uuid.UUID | str | None,
    entry: str,
    origin: str,
    template_id: uuid.UUID | str | None,
    project_id: str | None,
    project_name: str | None,
    year: int | None,
    source_key: str,
    source_label: str,
    definition: dict,
    definition_hash: str,
    scope: dict,
    version_vector: dict,
    vector_hash: str,
    vector_weak: bool,
    captured_at: str | None,
    columns: list[dict],
    row_count: int,
    warnings: list[str],
    info_rows: list[list[Any]],
    file_name: str,
    byte_size: int,
    sha256: str,
    generated_at: str,
    user_id: str,
    username: str,
) -> dict:
    return {
        "schema": "gt.query-artifact/v1",
        "artifact_id": str(artifact_id),
        "run_id": str(run_id) if run_id else None,
        "entry": entry,
        "origin": origin,
        "template_id": str(template_id) if template_id else None,
        "project": {"id": project_id, "name": project_name},
        "year": year,
        "source": {"key": source_key, "label": source_label},
        "definition": definition,
        "definition_hash": definition_hash,
        "scope": scope,
        "version_vector": version_vector,
        "vector_hash": vector_hash,
        "vector_weak": vector_weak,
        "captured_at": captured_at,
        "columns": columns,
        "row_count": row_count,
        "warnings": warnings,
        "info_rows": [[str(k), str(v)] for k, v in (info_rows or [])],
        "file": {"name": file_name, "byte_size": byte_size, "sha256": sha256, "media_type": ARTIFACT_MEDIA_TYPE},
        "generated_at": generated_at,
        "generated_by": {"user_id": user_id, "username": username},
    }


def canonical_manifest_json(manifest: dict) -> bytes:
    """规范序列化：键排序，ensure_ascii=False，最紧凑分隔符。"""
    return json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def manifest_sha256(manifest: dict) -> str:
    return hashlib.sha256(canonical_manifest_json(manifest)).hexdigest()


# ─── 说明页 info_rows 追加四行（AQF §4.2/§6.3）──────────────────────────────

def artifact_extra_info_rows(
    *,
    run_id: str | None,
    artifact_id: str,
    version_components: list[dict],
    vector_hash: str,
) -> list[tuple[str, str]]:
    """在现有 export_info_rows 之后追加的四行（R4.2）。"""
    components_text = "；".join(
        f"{c.get('label','?')}={str(c.get('digest',''))[:8] or '—'}" for c in version_components
    ) or "（未采集）"
    return [
        ("查询编号", run_id or "未记录"),
        ("证据编号", artifact_id),
        ("数据版本", components_text),
        ("版本摘要", vector_hash[:16] if vector_hash else "—"),
    ]


# ─── 封存主流程 ─────────────────────────────────────────────────────────────

async def seal_artifact(
    *,
    db: AsyncSession,
    user: Any,
    entry: str,
    origin: str = "direct",
    template_id: uuid.UUID | str | None = None,
    project_id: str | uuid.UUID | None,
    year: int | None,
    source_key: str,
    source_label: str,
    definition: dict,
    definition_hash: str,
    scope: dict,
    version_vector: dict,
    vector_hash: str,
    vector_weak: bool,
    captured_at: datetime | None,
    run_id: uuid.UUID | str | None,
    rows: Any,
    columns: Any,
    info_rows_base: list[tuple[str, Any]],
    file_name: str,
    sheet_title: str | None,
    extra_sheets: Any = (),
    session_factory: async_sessionmaker | None = None,
) -> "SealResult":
    """封存流程（design §6.3）：写 partial → SHA-256 → 原子改名 → 写证据记录。

    返回 SealResult；失败时 SealResult.ok=False，不抛异常（降级由调用方处理）。
    """
    from app.services.custom_query.export_service import export_service
    from app.services.custom_query.query_runs import canonical_json
    from app.attachment_upload_policy import ensure_within_root

    artifact_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # 计算保留截止日
    from app.core.config import settings
    retention_days = getattr(settings, "QUERY_ARTIFACT_RETENTION_DAYS", 30)
    retention_until = now + timedelta(days=retention_days)

    try:
        directory = artifact_directory(artifact_id, now)
        ensure_within_root(str(_artifact_root()), str(directory))
        part = partial_path(directory, artifact_id)
        final = artifact_path(directory, artifact_id)

        # 预生成说明页追加四行，用于写文件时注入
        extra_rows = artifact_extra_info_rows(
            run_id=str(run_id) if run_id else None,
            artifact_id=str(artifact_id),
            version_components=version_vector.get("components", []),
            vector_hash=vector_hash,
        )

        def make_info(written_rows: int) -> list[tuple[str, Any]]:
            return list(info_rows_base) + list(extra_rows)

        # 写 .partial 文件
        built = await export_service.build_xlsx_file(
            rows, columns,
            directory=str(part.parent),
            file_stem=f".{artifact_id}",
            info_rows=make_info,
            sheet_title=sheet_title,
            extra_sheets=extra_sheets,
        )

        # 流式算 SHA-256 + 取文件大小
        sha = file_sha256(built.path)
        byte_size = os.path.getsize(built.path)

        # 原子改名
        os.replace(built.path, str(final))

        # 构建清单
        user_id = str(getattr(user, "id", ""))
        username = str(getattr(user, "username", "") or user_id)
        # 获取项目名
        project_name = None
        try:
            from sqlalchemy import select as sa_select
            from app.models.core import Project
            if project_id:
                pid_uuid = project_id if isinstance(project_id, uuid.UUID) else uuid.UUID(str(project_id))
                row = (await db.execute(
                    sa_select(Project.name).where(Project.id == pid_uuid).limit(1)
                )).scalar_one_or_none()
                project_name = row
        except Exception:
            pass

        manifest = _canonical_manifest(
            artifact_id=artifact_id, run_id=run_id, entry=entry, origin=origin,
            template_id=template_id,
            project_id=str(project_id) if project_id else None, project_name=project_name,
            year=year, source_key=source_key, source_label=source_label,
            definition=definition, definition_hash=definition_hash,
            scope=scope, version_vector=version_vector, vector_hash=vector_hash,
            vector_weak=vector_weak, captured_at=captured_at.isoformat() if captured_at else None,
            columns=[{"key": c.key if hasattr(c, "key") else str(c), "title": c.title if hasattr(c, "title") else str(c)} for c in columns],
            row_count=built.row_count, warnings=[],
            info_rows=make_info(built.row_count),
            file_name=file_name, byte_size=byte_size, sha256=sha,
            generated_at=now.isoformat(), user_id=user_id, username=username,
        )
        msha = manifest_sha256(manifest)

        # 写证据记录（独立短事务）
        from app.core.database import async_session as default_factory
        factory = session_factory or default_factory
        try:
            async with factory() as short_db:
                async with short_db.begin():
                    await short_db.execute(text("""
                        INSERT INTO query_artifacts (
                            id, run_id, user_id, entry, project_id, year, source_key,
                            definition_hash, version_vector, vector_hash, scope,
                            status, file_name, storage_key, media_type,
                            byte_size, sha256, row_count, columns,
                            manifest, manifest_sha256, retention_until,
                            created_at, updated_at
                        ) VALUES (
                            :id, :run_id, :user_id, :entry, :project_id, :year, :source_key,
                            :definition_hash, cast(:version_vector AS jsonb), :vector_hash, cast(:scope AS jsonb),
                            'ready', :file_name, :storage_key, :media_type,
                            :byte_size, :sha256, :row_count, cast(:columns AS jsonb),
                            cast(:manifest AS jsonb), :manifest_sha256, :retention_until,
                            now(), now()
                        )
                    """), {
                        "id": str(artifact_id),
                        "run_id": str(run_id) if run_id else None,
                        "user_id": user_id,
                        "entry": entry,
                        "project_id": str(project_id) if project_id else None,
                        "year": year,
                        "source_key": source_key[:200],
                        "definition_hash": definition_hash,
                        "version_vector": canonical_json(version_vector),
                        "vector_hash": vector_hash,
                        "scope": canonical_json(scope),
                        "file_name": file_name[:255],
                        "storage_key": storage_key(directory, artifact_id),
                        "media_type": ARTIFACT_MEDIA_TYPE,
                        "byte_size": byte_size,
                        "sha256": sha,
                        "row_count": built.row_count,
                        "columns": canonical_json(manifest["columns"]),
                        "manifest": canonical_json(manifest),
                        "manifest_sha256": msha,
                        "retention_until": retention_until.isoformat(),
                    })
        except Exception as db_exc:
            logger.warning("AQF 证据记录写库失败: %s", db_exc)
            return SealResult(ok=False, reason=f"证据记录写入失败：{type(db_exc).__name__}")

        return SealResult(
            ok=True,
            artifact_id=artifact_id,
            run_id=run_id,
            file_path=str(final),
            sha256=sha,
            byte_size=byte_size,
            manifest_sha256=msha,
        )
    except Exception as exc:
        logger.warning("AQF 封存失败: %s", exc, exc_info=True)
        # 清理 partial
        try:
            part.unlink(missing_ok=True)
        except Exception:
            pass
        return SealResult(ok=False, reason=f"证据封存失败：{type(exc).__name__}")


class SealResult:
    __slots__ = ("ok", "artifact_id", "run_id", "file_path", "sha256", "byte_size",
                 "manifest_sha256", "reason")

    def __init__(
        self, *, ok: bool,
        artifact_id: uuid.UUID | None = None,
        run_id: Any = None,
        file_path: str | None = None,
        sha256: str | None = None,
        byte_size: int | None = None,
        manifest_sha256: str | None = None,
        reason: str | None = None,
    ) -> None:
        self.ok = ok
        self.artifact_id = artifact_id
        self.run_id = run_id
        self.file_path = file_path
        self.sha256 = sha256
        self.byte_size = byte_size
        self.manifest_sha256 = manifest_sha256
        self.reason = reason

    @property
    def status(self) -> str:
        return "stored" if self.ok else "unavailable"


# ─── 下载重验 ─────────────────────────────────────────────────────────────────

async def verify_and_stream(
    db: AsyncSession,
    artifact_id: uuid.UUID,
    *,
    user: Any,
) -> "tuple[str, str, str] | None":
    """验证文件完整性，返回 (file_path, file_name, content_disposition)；失败抛 HTTPException。

    non-ok 状态（purged/missing）分别 410/409。
    """
    from fastapi import HTTPException
    from app.services.custom_query.export_service import export_service

    dialect = db.get_bind().dialect.name
    if dialect != "postgresql":
        raise HTTPException(status_code=503, detail={"error_code": "QUERY_EVIDENCE_UNAVAILABLE",
                                                      "message": "查询证据功能仅在 PostgreSQL 上可用"})

    row = (await db.execute(text("""
        SELECT id, user_id, status, storage_key, sha256, byte_size, file_name
          FROM query_artifacts WHERE id = :id AND user_id = :uid LIMIT 1
    """), {"id": str(artifact_id), "uid": str(getattr(user, "id", ""))})).first()

    if row is None:
        raise HTTPException(status_code=404, detail={"error_code": "QUERY_ARTIFACT_NOT_FOUND",
                                                      "message": "查询证据不存在"})
    _id, _uid, status, storage_key_val, expected_sha, expected_size, fname = row
    if status == "purged":
        raise HTTPException(status_code=410, detail={"error_code": "QUERY_ARTIFACT_PURGED",
                                                      "message": "查询证据已超期清理"})
    root = _artifact_root()
    file_path = str(root / storage_key_val)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=410, detail={"error_code": "QUERY_ARTIFACT_PURGED",
                                                      "message": "证据文件已不存在（可能已被清理）"})
    actual_sha = file_sha256(file_path)
    actual_size = os.path.getsize(file_path)
    if actual_sha != expected_sha or actual_size != expected_size:
        raise HTTPException(status_code=409, detail={"error_code": "QUERY_ARTIFACT_INTEGRITY",
                                                      "message": "证据文件摘要校验失败，文件可能已损坏"})
    content_disp = export_service.build_content_disposition(fname or f"查询证据_{artifact_id}.xlsx")
    return file_path, str(fname), content_disp


__all__ = [
    "artifact_directory", "artifact_path", "partial_path", "storage_key",
    "file_sha256", "canonical_manifest_json", "manifest_sha256",
    "artifact_extra_info_rows", "seal_artifact", "verify_and_stream",
    "SealResult", "ARTIFACT_MEDIA_TYPE",
]
