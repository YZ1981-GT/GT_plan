"""交付件版本物理文件不可覆盖（deliverable-writeback-and-online-edit-integrity Phase B）。

覆盖固定展示名连续生成、版本唯一命名、历史路径认领防覆盖、普通/签名下载共用指纹校验入口。
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401 — SQLite JSONB/UUID 兼容
from app.models.base import Base, ProjectStatus, UserRole
from app.models.core import Project, User
from app.models.phase13_models import WordExportTask, WordExportTaskVersion
from app.routers.deliverable import _verified_version_path
from app.services.deliverable_hash_service import DeliverableHashService
from app.services.deliverable_service import DeliverableService, versioned_file_name
from app.services.file_fingerprint_service import FilePersistError


@pytest.mark.parametrize(
    ("raw", "doc_type", "version", "expected"),
    [
        (None, "audit_report", 1, "audit_report_v1.docx"),
        ("disclosure_notes_2025.docx", "disclosure_notes", 12, "disclosure_notes_2025_v12.docx"),
        ("financial_reports_2025.xlsx", "financial_report", 2, "financial_reports_2025_v2.xlsx"),
        ("financial_reports_unadjusted_2025.xlsx", "financial_report_unadjusted", 3,
         "financial_reports_unadjusted_2025_v3.xlsx"),
        ("audit_report_v5.docx", "audit_report", 6, "audit_report_v6.docx"),
        (r"C:\outside\evil_v8.docx", "audit_report", 9, "evil_v9.docx"),
    ],
)
def test_versioned_file_name(raw, doc_type, version, expected):
    assert versioned_file_name(raw, doc_type, version) == expected


def _run(scenario):
    async def _main():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(
                c, tables=[User.__table__, Project.__table__, WordExportTask.__table__, WordExportTaskVersion.__table__]
            ))
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as db:
                user = User(id=uuid.uuid4(), username="version-user", email="version@example.com",
                            hashed_password="x", role=UserRole.admin)
                project = Project(id=uuid.uuid4(), name="版本完整性_2025", client_name="版本完整性",
                                  status=ProjectStatus.created)
                task = WordExportTask(id=uuid.uuid4(), project_id=project.id, doc_type="disclosure_notes",
                                      status="draft", created_by=user.id)
                db.add_all([user, project, task])
                await db.flush()
                return await scenario(db, task, user)
        finally:
            await engine.dispose()

    return asyncio.run(_main())


def test_same_display_name_twice_creates_two_immutable_files(tmp_path: Path):
    async def _scenario(db, task, user):
        svc = DeliverableService(db)
        with patch("app.services.deliverable_service.STORAGE_ROOT", tmp_path), \
                patch.object(DeliverableHashService, "bind_version_hash", new=AsyncMock()):
            first = await svc.render_and_store(task.id, docx_bytes=b"first-version", user_id=user.id,
                                               file_name="disclosure_notes_2025.docx")
            second = await svc.render_and_store(task.id, docx_bytes=b"second-version", user_id=user.id,
                                                file_name="disclosure_notes_2025.docx")
        return first, second

    first, second = _run(_scenario)
    assert first.version.version_no == 1 and second.version.version_no == 2
    assert Path(first.file_path).name == "disclosure_notes_2025_v1.docx"
    assert Path(second.file_path).name == "disclosure_notes_2025_v2.docx"
    assert first.file_path != second.file_path
    assert Path(first.file_path).read_bytes() == b"first-version"
    assert Path(second.file_path).read_bytes() == b"second-version"
    assert first.version.file_hash == hashlib.sha256(b"first-version").hexdigest()
    assert second.version.file_hash == hashlib.sha256(b"second-version").hexdigest()


def test_existing_version_path_is_never_reused(tmp_path: Path):
    async def _scenario(db, task, user):
        svc = DeliverableService(db)
        with patch("app.services.deliverable_service.STORAGE_ROOT", tmp_path), \
                patch.object(DeliverableHashService, "bind_version_hash", new=AsyncMock()):
            first = await svc.render_and_store(task.id, docx_bytes=b"v1", user_id=user.id,
                                               file_name="notes.docx")
            with pytest.raises(FilePersistError, match="历史版本 v1"):
                await svc._assert_version_path_unclaimed(task.id, Path(first.file_path))
            return first.file_path

    path = _run(_scenario)
    assert Path(path).read_bytes() == b"v1"


def _version(path: Path, recorded: bytes) -> SimpleNamespace:
    return SimpleNamespace(
        file_path=str(path),
        file_size=len(recorded),
        file_hash=hashlib.sha256(recorded).hexdigest(),
    )


def test_download_fingerprint_accepts_original_and_rejects_overwritten(tmp_path: Path):
    root = tmp_path / "deliverables"
    path = root / "p" / "t" / "v1.docx"
    path.parent.mkdir(parents=True)
    original = b"version-one-contents"
    path.write_bytes(original)
    version = _version(path, original)

    with patch("app.services.deliverable_service.STORAGE_ROOT", tmp_path):
        assert _verified_version_path(version) == path
        # 同长度篡改，保证打红来自 SHA-256 而非 size。
        path.write_bytes(b"version-nine-content")
        assert len(path.read_bytes()) == len(original)
        with pytest.raises(HTTPException) as exc:
            _verified_version_path(version)
    assert exc.value.status_code == 409
    assert "后续生成覆盖" in str(exc.value.detail)


def test_download_fingerprint_missing_file_is_404(tmp_path: Path):
    path = tmp_path / "deliverables" / "p" / "missing.docx"
    version = _version(path, b"missing")
    with patch("app.services.deliverable_service.STORAGE_ROOT", tmp_path):
        with pytest.raises(HTTPException) as exc:
            _verified_version_path(version)
    assert exc.value.status_code == 404


def test_both_download_routes_call_the_shared_fingerprint_gate():
    """源码级接线守卫：普通下载 + OO 签名下载必须同走唯一入口，不得一条漏校验。"""
    import ast
    import inspect
    from app.routers import deliverable

    tree = ast.parse(inspect.getsource(deliverable))
    calls: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {
            "download_version", "signed_download_version"
        }:
            calls[node.name] = sum(
                1 for n in ast.walk(node)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_verified_version_path"
            )
    assert calls == {"download_version": 1, "signed_download_version": 1}


def test_v191_schema_contract_and_unique_migration_pair():
    """V191 三层一致：迁移 + ORM + 回滚；同号文件唯一。

    原 V189，因并发会话（trio spec）已占用 V189/V190，2026-10-18 改号至 V191。
    """
    from app.core.migration_runner import MigrationRunner
    from app.models.audit_platform_models import DeliverableSectionState
    from app.models.workpaper_models import WorkingPaper

    migrations = Path(__file__).resolve().parents[1] / "migrations"
    runner = MigrationRunner(database_url="sqlite+aiosqlite:///:memory:", migrations_dir=migrations)
    assert [m.filename for m in runner.scan_migrations() if int(m.version) == 191] == [
        "V191__deliverable_edit_and_writeback_integrity.sql"
    ]
    assert [m.filename for m in runner.scan_rollback_scripts() if int(m.version) == 191] == [
        "R191__deliverable_edit_and_writeback_integrity.sql"
    ]

    version_cols = WordExportTaskVersion.__table__.c
    for name in ("base_version_no", "oo_doc_key", "render_context"):
        assert name in version_cols
    section_cols = DeliverableSectionState.__table__.c
    for name in ("text_baseline", "text_source_hash", "outside_hash", "text_render_context"):
        assert name in section_cols
    wp_cols = WorkingPaper.__table__.c
    assert wp_cols.quality_score.type.python_type is int
    assert wp_cols.procedure_completion_rate.type.scale == 2
    indexes = {i.name: i for i in WordExportTaskVersion.__table__.indexes}
    assert indexes["uq_word_export_versions_task_no"].unique is True

    sql = (migrations / "V191__deliverable_edit_and_writeback_integrity.sql").read_text(encoding="utf-8")
    rollback = (migrations / "R191__deliverable_edit_and_writeback_integrity.sql").read_text(encoding="utf-8")
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_word_export_versions_task_no" in sql
    assert "DROP INDEX IF EXISTS uq_word_export_versions_task_no" in rollback
