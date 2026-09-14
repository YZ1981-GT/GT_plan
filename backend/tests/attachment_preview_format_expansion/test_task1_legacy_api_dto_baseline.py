"""Task 1 — preview/download/upload/DTO 行为契约冻结

Spec: audit-evidence-attachment-preview-format-expansion
Properties: 16, 18, 31
"""

from __future__ import annotations

import ast
import json
import re
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.attachment_models import Attachment
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.services.attachment_service import AttachmentService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

REPO = Path(__file__).resolve().parents[3]
EVIDENCE = (
    REPO
    / ".kiro"
    / "specs"
    / "_archive"
    / "05-business-features"
    / "audit-evidence-attachment-preview-format-expansion"
    / "evidence"
    / "attachment-preview-format-expansion"
)
ATTACHMENTS_ROUTER = REPO / "backend" / "app" / "routers" / "attachments.py"
PROCESS_RECORD = REPO / "backend" / "app" / "services" / "process_record_service.py"

PROJECT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
WP_ID = uuid.uuid4()

_CORE_TABLES = [User.__table__, Project.__table__, Attachment.__table__]


def _load(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=_CORE_TABLES))
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_CORE_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed_attachment(
    db: AsyncSession,
    *,
    file_name: str,
    file_type: str,
    ocr_status: str = "ok",
    ocr_text: str = "ocr-body",
) -> uuid.UUID:
    db.add(
        User(
            id=USER_ID,
            username="t1-baseline",
            email="t1-baseline@example.com",
            hashed_password="x",
            role=UserRole.admin,
            is_active=True,
        )
    )
    db.add(
        Project(
            id=PROJECT_ID,
            name="T1 baseline",
            client_name="T1",
            project_type=ProjectType.annual,
            status=ProjectStatus.execution,
            created_by=USER_ID,
        )
    )
    att_id = uuid.uuid4()
    # dashed 字符串插入，兼容 process-record raw SQL 在 SQLite 下的 UUID 表征；
    # created_at 置 NULL，避免 sqlite 把时间戳读成 str 触发 isoformat 崩。
    await db.execute(
        sa.text(
            "INSERT INTO attachments "
            "(id, project_id, file_name, file_path, file_type, file_size, "
            " attachment_type, reference_type, reference_id, storage_type, "
            " ocr_status, ocr_text, is_deleted, version, is_key_evidence, "
            " metadata_status, state, original_creator_unknown, created_at) "
            "VALUES "
            "(:id, :pid, :fn, :fp, :ft, 12, "
            " 'general', 'working_paper', :wp, 'local', "
            " :ocr_s, :ocr_t, 0, 1, 0, "
            " 'incomplete', 'available', 0, '2026-09-08T00:00:00')"
        ),
        {
            "id": str(att_id),
            "pid": str(PROJECT_ID),
            "fn": file_name,
            "fp": f"storage/{att_id}/{file_name}",
            "ft": file_type,
            "wp": str(WP_ID),
            "ocr_s": ocr_status,
            "ocr_t": ocr_text,
        },
    )
    await db.commit()
    return att_id


class TestPreviewWhitelistContract:
    def test_whitelist_frozen_and_includes_svg(self) -> None:
        contract = _load("backend_preview_api_contract.json")
        src = ATTACHMENTS_ROUTER.read_text(encoding="utf-8")
        m = re.search(r"previewable_types\s*=\s*\{([^}]+)\}", src)
        assert m, "previewable_types set missing"
        found = {
            part.strip().strip("'\"")
            for part in m.group(1).split(",")
            if part.strip().strip("'\"")
        }
        expect = set(contract["preview_whitelist_exts"])
        assert found == expect
        assert ".svg" in found
        for ext in contract["preview_whitelist_excludes"]:
            assert ext not in found

    def test_non_whitelist_json_shape_keys_documented(self) -> None:
        contract = _load("backend_preview_api_contract.json")
        keys = set(contract["non_whitelist_response_shape"]["required_keys"])
        assert keys == {"previewable", "file_name", "file_type", "ocr_text", "download_url"}

    def test_upload_handler_has_size_gate_no_extension_whitelist(self) -> None:
        contract = _load("backend_preview_api_contract.json")
        src = ATTACHMENTS_ROUTER.read_text(encoding="utf-8")
        tree = ast.parse(src)
        upload_fn = None
        for node in tree.body:
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "upload_attachment":
                upload_fn = node
                break
        assert upload_fn is not None
        body = ast.get_source_segment(src, upload_fn) or ""
        assert "ATTACHMENT_MAX_UPLOAD_BYTES" in body
        assert contract["upload_rules"]["extension_whitelist"] is False
        assert "previewable_types" not in body
        assert not re.search(r"suffix.*not in|ext not in.*\{", body)


class TestGuessFileTypeProductionShape:
    @pytest.mark.parametrize(
        "file_name,expected",
        [
            ("a.jpg", "image"),
            ("a.jpeg", "image"),
            ("a.png", "image"),
            ("a.gif", "image"),
            ("a.bmp", "image"),
            ("a.webp", "image"),
            ("a.xls", "excel"),
            ("a.xlsx", "excel"),
            ("a.csv", "excel"),
            ("a.doc", "word"),
            ("a.docx", "word"),
            ("a.zip", "zip"),
            ("a.eml", "eml"),
            ("a.msg", "msg"),
            ("a.dxf", "dxf"),
            ("a.PDF", "pdf"),
            ("noext", "unknown"),
        ],
    )
    def test_guess_file_type_matrix(self, file_name: str, expected: str) -> None:
        svc = AttachmentService.__new__(AttachmentService)
        assert svc._guess_file_type(file_name) == expected


class TestProcessRecordDtoProjection:
    @pytest.mark.asyncio
    async def test_list_projection_includes_ocr_fields(self, db_session: AsyncSession) -> None:
        ledger = _load("process_record_dto_red_baseline.json")
        await _seed_attachment(
            db_session, file_name="scan.png", file_type="image", ocr_status="ok", ocr_text="发票"
        )
        result = await db_session.execute(
            sa.text(
                "SELECT a.id, a.file_name, a.file_size, a.file_type, a.created_at, "
                "a.ocr_status, a.ocr_text "
                "FROM attachments a "
                "WHERE a.reference_type = 'working_paper' "
                "AND a.reference_id = :wp_id "
                "AND a.project_id = :project_id "
                "AND (a.is_deleted = false OR a.is_deleted IS NULL) "
                "ORDER BY a.created_at DESC"
            ),
            {"wp_id": str(WP_ID), "project_id": str(PROJECT_ID)},
        )
        rows = result.fetchall()
        assert len(rows) == 1
        mapping = rows[0]._mapping
        assert set(mapping.keys()) == set(ledger["sql_projection_today"])
        assert mapping["ocr_status"] == "ok"
        assert mapping["ocr_text"] == "发票"

    def test_sql_select_list_includes_ocr(self) -> None:
        src = PROCESS_RECORD.read_text(encoding="utf-8")
        method_src = src.split("async def get_workpaper_attachments")[1].split(
            "async def get_attachment_workpapers"
        )[0]
        assert "a.ocr_status" in method_src
        assert "a.ocr_text" in method_src


class TestRegisteredDebtLedger:
    def test_three_debts_out_of_scope(self) -> None:
        debt = _load("registered_debt.json")
        by_id = {d["id"]: d for d in debt["debts"]}
        assert set(by_id) == {
            "xlsx-0.18.5-cve",
            "attachment-hub-dead-import",
            "dual-host-convergence",
        }
        # xlsx 与 attachment-hub 仍明确不在本 spec 修复范围（M31 变异翻 true 必须打红此处）
        assert by_id["xlsx-0.18.5-cve"]["in_scope"] is False
        assert by_id["attachment-hub-dead-import"]["in_scope"] is False
        # dual-host-convergence 已随本次收敛执行完成（单一逻辑宿主 + 两薄壳）
        assert by_id["dual-host-convergence"]["in_scope"] is True
        assert by_id["dual-host-convergence"]["resolved"] is True
