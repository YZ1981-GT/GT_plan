"""Phase4 Task 4 — 文件指纹与版本 fail-closed 五类故障注入.

spec: ``.kiro/specs/chain-closure-phase4-deliverable-center-trio``（需求 3.1~3.6, 7.3）。

需求 7.3 要求五类文件故障注入，每类都必须阻止正式成功：

1. 文件写失败（write 抛错）
2. 文件被删除（落盘后、校验前消失）
3. 文件被截断（落盘后大小变 0）
4. 哈希不匹配（磁盘内容与版本记录指纹不一致）
5. 版本先写后校验（旧 fail-open：先 create_version 再校验）

故障注入纪律（memory 铁律）：**注入在被测函数的下一层**（文件系统原语 /
``deliverable_file_fingerprint`` 指纹模块），**不替换** ``render_and_store`` 本身；
并断言被测路径确实是生产函数（``render_and_store is 生产方法``）。

每类都在本文件内配「正向（故障被拦，fail-closed）+ 反向变异证明」思路：
- 正向：注入故障 → render_and_store 返回 version=None、0 版本行（或 verify 抛明确异常）。
- 反向（revert-to-red）：见 task4 证据文档，描述把校验前移/去掉后该用例必红。
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import app.services.deliverable_service as ds_module
from app.models.base import Base
from app.models.core import Project, User
from app.models.phase13_models import WordExportDocType, WordExportTaskVersion
import app.services.deliverable_file_fingerprint as fp_module
from app.services.deliverable_file_fingerprint import (
    FileFingerprintError,
    compute_file_fingerprint,
    verify_file_fingerprint,
)
from app.services.deliverable_service import DeliverableService


# ===================================================================
# fixtures（SQLite 内存库 + 真实 ORM；STORAGE_ROOT 指向 tmp_path）
# ===================================================================


@pytest_asyncio.fixture
async def test_db():
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded(test_db: AsyncSession):
    user = User(
        id=uuid.uuid4(),
        username="phase4_fp",
        email="phase4fp@test.com",
        hashed_password="x",
        role="admin",
    )
    project = Project(
        id=uuid.uuid4(),
        name="指纹fail-closed项目",
        client_name="测试",
        status="created",
    )
    test_db.add_all([user, project])
    await test_db.flush()
    return test_db, project, user


@pytest.fixture
def storage_root(tmp_path, monkeypatch):
    """把交付存储根指向 pytest tmp（在系统临时目录下，指纹模块允许）。"""
    monkeypatch.setattr(ds_module, "STORAGE_ROOT", tmp_path)
    return tmp_path


async def _new_task(dsvc: DeliverableService, project, user):
    task, _ = await dsvc.export_or_new_deliverable(
        project.id, WordExportDocType.financial_report.value, None, user.id
    )
    await dsvc.db.flush()
    return task


async def _versions(db, task_id):
    return (
        (
            await db.execute(
                sa.select(WordExportTaskVersion).where(
                    WordExportTaskVersion.word_export_task_id == task_id
                )
            )
        )
        .scalars()
        .all()
    )


def _assert_production_render_and_store():
    """断言被测路径是生产 render_and_store（故障注入未替换它本身）。"""
    assert (
        DeliverableService.render_and_store.__module__
        == "app.services.deliverable_service"
    ), "render_and_store 必须是生产实现，不得被测试替换"
    assert not getattr(
        DeliverableService.render_and_store, "__wrapped_by_test__", False
    )


# ===================================================================
# 故障 1：文件写失败
# ===================================================================


class TestFault1WriteFailure:
    @pytest.mark.asyncio
    async def test_write_failure_no_version(self, seeded, storage_root, monkeypatch):
        db, project, user = seeded
        dsvc = DeliverableService(db)
        task = await _new_task(dsvc, project, user)

        _assert_production_render_and_store()

        # 注入在「下一层」：文件系统 write_bytes 抛 OSError（磁盘满/权限）
        def _boom(self, *a, **k):  # noqa: ANN001
            raise OSError("磁盘写入失败（注入）")

        monkeypatch.setattr(Path, "write_bytes", _boom)

        store = await dsvc.render_and_store(
            task.id,
            docx_bytes=b"PK\x03\x04data",
            user_id=user.id,
            file_name="fr.xlsx",
        )
        assert store.platform_persist_failed is True
        assert store.version is None
        assert await _versions(db, task.id) == []


# ===================================================================
# 故障 2：文件被删除（落盘后、校验前消失）
# ===================================================================


class TestFault2Deleted:
    @pytest.mark.asyncio
    async def test_deleted_before_verify_no_version(
        self, seeded, storage_root, monkeypatch
    ):
        db, project, user = seeded
        dsvc = DeliverableService(db)
        task = await _new_task(dsvc, project, user)

        _assert_production_render_and_store()

        real = compute_file_fingerprint

        # 注入在指纹模块（下一层）：真实删除刚落盘的文件，再走真实校验逻辑
        # ⇒ 真实 compute_file_fingerprint 命中 missing_file。
        def _delete_then_compute(path, **kwargs):
            try:
                os.remove(path)
            except OSError:
                pass
            return real(path, **kwargs)

        monkeypatch.setattr(
            fp_module, "compute_file_fingerprint", _delete_then_compute
        )

        store = await dsvc.render_and_store(
            task.id,
            docx_bytes=b"PK\x03\x04data",
            user_id=user.id,
            file_name="fr.xlsx",
        )
        assert store.platform_persist_failed is True
        assert store.version is None
        assert await _versions(db, task.id) == []


# ===================================================================
# 故障 3：文件被截断（落盘后大小变 0）
# ===================================================================


class TestFault3Truncated:
    @pytest.mark.asyncio
    async def test_truncated_to_zero_no_version(
        self, seeded, storage_root, monkeypatch
    ):
        db, project, user = seeded
        dsvc = DeliverableService(db)
        task = await _new_task(dsvc, project, user)

        _assert_production_render_and_store()

        real = compute_file_fingerprint

        def _truncate_then_compute(path, **kwargs):
            # 截断为 0 字节后走真实校验 ⇒ size<=0 命中 unreadable_file
            with open(path, "wb"):
                pass
            return real(path, **kwargs)

        monkeypatch.setattr(
            fp_module, "compute_file_fingerprint", _truncate_then_compute
        )

        store = await dsvc.render_and_store(
            task.id,
            docx_bytes=b"PK\x03\x04data",
            user_id=user.id,
            file_name="fr.xlsx",
        )
        assert store.platform_persist_failed is True
        assert store.version is None
        assert await _versions(db, task.id) == []


# ===================================================================
# 故障 4：哈希不匹配（磁盘内容与版本记录指纹不一致）
# ===================================================================


class TestFault4HashMismatch:
    def test_verify_detects_content_change(self, tmp_path):
        """统一校验入口：内容改变后 SHA-256 比对必抛 file_hash_mismatch。"""
        p = tmp_path / "f.xlsx"
        p.write_bytes(b"original-bytes")
        fp = compute_file_fingerprint(p, enforce_root=False)
        # 内容被篡改
        p.write_bytes(b"tampered-bytes-different-length")
        with pytest.raises(FileFingerprintError) as ei:
            verify_file_fingerprint(
                p, expected_sha256=fp.sha256, enforce_root=False
            )
        assert ei.value.code == "file_hash_mismatch"

    @pytest.mark.asyncio
    async def test_readiness_surfaces_hash_mismatch(
        self, seeded, storage_root, monkeypatch
    ):
        """readiness 既有版本物理校验：记录哈希与磁盘不一致 ⇒ 硬闸门 file_hash_mismatch。

        注入在磁盘层（落盘后改文件内容），readiness 走统一 verify_file_fingerprint
        发现指纹漂移。这与 render / 下载共享同一校验函数（单一真源）。
        """
        from app.services.deliverable_readiness_service import (
            DeliverableReadinessService,
        )

        db, project, user = seeded
        dsvc = DeliverableService(db)
        task = await _new_task(dsvc, project, user)

        store = await dsvc.render_and_store(
            task.id,
            docx_bytes=b"PK\x03\x04good-bytes",
            user_id=user.id,
            file_name="fr.xlsx",
        )
        assert store.version is not None
        version = store.version
        # 版本记录已绑定 file_sha256（phase4 新链路）
        assert version.file_sha256

        # 磁盘文件被篡改（哈希不再匹配版本记录）
        Path(store.file_path).write_bytes(b"PK\x03\x04TAMPERED-different")

        svc = DeliverableReadinessService(db)
        blockers: list = []
        srcs: dict = {}
        await svc._check_existing_version_files(project.id, blockers, srcs)
        codes = {b.code for b in blockers}
        assert "file_hash_mismatch" in codes, (
            f"篡改后应产出 file_hash_mismatch 硬闸门，实际 {codes}"
        )


# ===================================================================
# 故障 5：版本先写后校验（旧 fail-open 的反向证明）
# ===================================================================


class TestFault5VersionBeforeVerify:
    @pytest.mark.asyncio
    async def test_create_version_not_called_when_verify_fails(
        self, seeded, storage_root, monkeypatch
    ):
        """校验必须先于 create_version：校验失败时 create_version 绝不被调用。

        注入：让指纹校验（下一层）抛错；spy create_version。
        正确实现（verify→create）下 create_version 调用次数为 0、无版本行。
        若把顺序改回「先 create_version 再 verify」（旧 fail-open），该断言必红。
        """
        db, project, user = seeded
        dsvc = DeliverableService(db)
        task = await _new_task(dsvc, project, user)

        _assert_production_render_and_store()

        # 下一层：指纹校验直接抛 FileFingerprintError（模拟校验不通过）
        def _reject(path, **kwargs):
            raise FileFingerprintError("unreadable_file", "校验失败（注入）")

        monkeypatch.setattr(fp_module, "compute_file_fingerprint", _reject)

        # spy create_version：记录是否被调用
        calls = {"n": 0}
        real_create = DeliverableService.create_version

        async def _spy_create(self, *a, **k):
            calls["n"] += 1
            return await real_create(self, *a, **k)

        monkeypatch.setattr(DeliverableService, "create_version", _spy_create)

        store = await dsvc.render_and_store(
            task.id,
            docx_bytes=b"PK\x03\x04data",
            user_id=user.id,
            file_name="fr.xlsx",
        )
        assert store.version is None
        assert calls["n"] == 0, (
            "校验失败时 create_version 不得被调用（否则是先写版本后校验的 fail-open）"
        )
        assert await _versions(db, task.id) == []
