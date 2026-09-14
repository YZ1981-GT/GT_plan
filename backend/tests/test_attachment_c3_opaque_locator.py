"""C3 opaque-locator 泄露回归测试（legacy 附件层）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Baseline: R1/R14 §6.1 C3 — 兼容响应的 ``file_path`` 只能是 opaque 定位符
（受控下载 URL ``/api/attachments/{id}/download`` 或 ``paperless://`` scheme），
绝不返回绝对路径 / 原始 local storage key。

覆盖：
1. ``AttachmentService._to_dict`` 及经它序列化的 legacy 入口
   （create/get/list/search/list_versions/rollback_to_version）投影为 opaque locator。
2. 断言投影值 **只** 匹配允许模式，**绝不** 匹配 Windows 盘符 / UNC / POSIX 绝对路径。
3. 内部真实路径读取通道 ``get_raw_storage`` 仍返回真实存储位置（不受投影影响）。
4. 共享投影单一真源 ``project_attachment_locator`` 的属性测试（治理层与 legacy 层共用）。
"""

from __future__ import annotations

import re
import uuid

import pytest
import pytest_asyncio
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.models.evidence_governance_models import ServiceIdentity
from app.services.attachment_locator import project_attachment_locator
from app.services.attachment_service import AttachmentService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# ── C3 断言用正则 ──────────────────────────────────────────────────────────
_ALLOWED_DOWNLOAD_RE = re.compile(r"^/api/attachments/.+/download$")
_ALLOWED_PAPERLESS_RE = re.compile(r"^paperless://")

_FORBIDDEN_WIN_DRIVE_RE = re.compile(r"[A-Za-z]:\\")
_FORBIDDEN_UNC_RE = re.compile(r"\\\\")
_FORBIDDEN_POSIX_ABS_RE = re.compile(r"^/(home|var|srv|mnt|opt|storage|data|tmp|Users|root)/")


def assert_opaque(locator: str) -> None:
    """断言 locator 是 opaque（允许模式之一），且绝不泄露真实文件系统位置。"""
    assert isinstance(locator, str) and locator, f"empty locator: {locator!r}"
    is_allowed = bool(_ALLOWED_DOWNLOAD_RE.match(locator)) or bool(
        _ALLOWED_PAPERLESS_RE.match(locator)
    )
    assert is_allowed, f"locator 不是受控 opaque 形态: {locator!r}"
    assert not _FORBIDDEN_WIN_DRIVE_RE.search(locator), f"泄露 Windows 盘符: {locator!r}"
    assert not _FORBIDDEN_UNC_RE.search(locator), f"泄露 UNC 路径: {locator!r}"
    assert not _FORBIDDEN_POSIX_ABS_RE.match(locator), f"泄露 POSIX 绝对路径: {locator!r}"


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        tables = [
            User.__table__,
            Project.__table__,
            ServiceIdentity.__table__,  # Attachment.actor_service_identity_id FK 目标
            Attachment.__table__,
            AttachmentWorkingPaper.__table__,
        ]
        await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=tables))
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    project_id = uuid.uuid4()
    user_id = uuid.uuid4()
    project = Project(
        id=project_id,
        name="C3 opaque-locator 测试",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        created_by=user_id,
    )
    db_session.add(project)
    await db_session.commit()
    return {"project_id": project_id, "user_id": user_id}


# 会泄露的原始 file_path 样本（若被逐字返回，assert_opaque 必失败）。
_LEAKY_LOCAL_PATHS = [
    r"C:\Users\auditor\secret\合同_v1.pdf",   # Windows 盘符
    r"\\fileserver\share\evidence\发票.pdf",   # UNC
    "/var/storage/attachments/银行流水.pdf",   # POSIX 绝对
    "/home/app/data/凭证.png",
    "storage/projects/x/attachments/raw_key.bin",  # 原始 local storage key（相对）
]


class TestToDictProjection:
    """_to_dict 及经它序列化的 legacy 入口投影为 opaque locator。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("leaky_path", _LEAKY_LOCAL_PATHS)
    async def test_create_attachment_local_never_leaks(self, db_session, seeded_db, leaky_path):
        svc = AttachmentService(db_session)
        result = await svc.create_attachment(
            seeded_db["project_id"],
            {"file_name": "合同.pdf", "file_path": leaky_path, "file_type": "pdf", "file_size": 10},
        )
        # 对外投影为受控下载 URL，绝不回显真实路径。
        assert result["file_path"] == f"/api/attachments/{result['id']}/download"
        assert_opaque(result["file_path"])
        assert result["file_path"] != leaky_path

    @pytest.mark.asyncio
    async def test_get_attachment_local_never_leaks(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        created = await svc.create_attachment(
            seeded_db["project_id"],
            {"file_name": "x.pdf", "file_path": "/var/storage/x.pdf", "file_type": "pdf"},
        )
        await db_session.commit()
        got = await svc.get_attachment(uuid.UUID(created["id"]))
        assert got is not None
        assert_opaque(got["file_path"])
        assert got["file_path"] == f"/api/attachments/{created['id']}/download"

    @pytest.mark.asyncio
    async def test_paperless_returns_scheme(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        created = await svc.create_attachment(
            seeded_db["project_id"],
            {
                "file_name": "回函.pdf",
                "file_path": "ignored-local",
                "file_type": "pdf",
                "paperless_document_id": 4321,
                "storage_type": "paperless",
            },
        )
        # paperless 入库时 file_path 规范化为 paperless://documents/4321，投影保留 scheme。
        assert created["file_path"] == "paperless://documents/4321"
        assert_opaque(created["file_path"])

    @pytest.mark.asyncio
    async def test_list_attachments_never_leaks(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        for p in _LEAKY_LOCAL_PATHS:
            await svc.create_attachment(
                seeded_db["project_id"],
                {"file_name": "e.pdf", "file_path": p, "file_type": "pdf"},
            )
        await db_session.commit()
        items = await svc.list_attachments(seeded_db["project_id"])
        assert len(items) == len(_LEAKY_LOCAL_PATHS)
        for it in items:
            assert_opaque(it["file_path"])

    @pytest.mark.asyncio
    async def test_search_never_leaks(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        await svc.create_attachment(
            seeded_db["project_id"],
            {"file_name": "搜索命中.pdf", "file_path": r"C:\secret\搜索命中.pdf", "file_type": "pdf"},
        )
        await db_session.commit()
        results = await svc.search(seeded_db["project_id"], "搜索命中")
        assert results, "搜索应命中一条"
        for r in results:
            assert_opaque(r["file_path"])

    @pytest.mark.asyncio
    async def test_list_versions_and_rollback_never_leak(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        ref_id = uuid.uuid4()
        for i in range(2):
            await svc.create_attachment(
                seeded_db["project_id"],
                {
                    "file_name": "合同.pdf",
                    "file_path": f"/var/storage/合同_v{i}.pdf",
                    "file_type": "pdf",
                    "reference_id": ref_id,
                    "reference_type": "contract",
                },
            )
        await db_session.commit()

        versions = await svc.list_versions(
            seeded_db["project_id"], "合同.pdf", ref_id, "contract"
        )
        assert len(versions) == 2
        for v in versions:
            assert_opaque(v["file_path"])

        rolled = await svc.rollback_to_version(
            project_id=seeded_db["project_id"],
            file_name="合同.pdf",
            target_version=1,
            reference_id=ref_id,
            reference_type="contract",
        )
        await db_session.commit()
        assert_opaque(rolled["file_path"])


class TestRawStorageInternalRead:
    """内部真实路径通道不受投影影响（供受控下载/预览的字节读取使用）。"""

    @pytest.mark.asyncio
    async def test_get_raw_storage_returns_real_local_path(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        real = "/var/storage/attachments/真实.pdf"
        created = await svc.create_attachment(
            seeded_db["project_id"],
            {"file_name": "真实.pdf", "file_path": real, "file_type": "pdf"},
        )
        await db_session.commit()
        raw = await svc.get_raw_storage(uuid.UUID(created["id"]))
        assert raw is not None
        # 内部通道返回真实路径（对外 _to_dict 则已脱敏）。
        assert raw["file_path"] == real
        # 同一附件对外投影仍为 opaque。
        assert_opaque(created["file_path"])

    @pytest.mark.asyncio
    async def test_get_raw_storage_paperless_key(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        created = await svc.create_attachment(
            seeded_db["project_id"],
            {
                "file_name": "回函.pdf",
                "file_path": "x",
                "file_type": "pdf",
                "paperless_document_id": 99,
                "storage_type": "paperless",
            },
        )
        await db_session.commit()
        raw = await svc.get_raw_storage(uuid.UUID(created["id"]))
        assert raw is not None
        assert raw["file_path"] == "paperless://documents/99"
        assert raw["storage_type"] == "paperless"


class TestSharedProjectorProperty:
    """共享投影单一真源属性：输出恒为 opaque，绝不泄露真实位置。"""

    @settings(max_examples=50)
    @given(
        storage_key=st.one_of(
            st.none(),
            st.just(""),
            st.text(max_size=40),
            st.builds(lambda p: p, st.sampled_from(_LEAKY_LOCAL_PATHS)),
            st.builds(lambda n: f"paperless://documents/{n}", st.integers(min_value=0, max_value=10**9)),
        ),
        storage_type=st.sampled_from([None, "local", "paperless", "unknown", ""]),
    )
    def test_projection_always_opaque(self, storage_key, storage_type):
        att_id = uuid.uuid4()
        locator = project_attachment_locator(att_id, storage_type=storage_type, storage_key=storage_key)
        assert_opaque(locator)
        # paperless scheme 原样透传；其它一切退回受控下载 URL。
        if isinstance(storage_key, str) and storage_key.startswith("paperless://"):
            assert locator == storage_key
        else:
            assert locator == f"/api/attachments/{att_id}/download"
