"""WOPI PutFile：被拒绝的保存不得留在磁盘上（preexisting-test-failures-closure G1）。

`put_file` 先把载荷写进底稿文件，再交给 ContentMutationService 提交；OOXML 结构校验、
bundle 解析与 revision CAS 都在提交里。原先提交失败时只有 DB 回滚，磁盘上已是被拒的
字节（GetFile 照发），首次保存的文件也不删 —— 旧用例跑一次就在 backend/ 下留一个
``<project_id>/2025/B1-1.xlsx``。

本文件的底稿文件与 artifact store 都落在 ``tmp_path``，并按生产 provision 宿主
（``fix_task65_provision_opaque_authority_bundles.py``）的同一入口为 ``wopi_put_file``
lane 发布 approved bundle，让拒绝发生在它真正该发生的 OOXML 结构门。
"""
from __future__ import annotations

import importlib
import io
import pkgutil
import uuid

import pytest
import pytest_asyncio
from openpyxl import Workbook
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpSourceType,
    WpStatus,
)

for _module in pkgutil.walk_packages(app.models.__path__, "app.models."):
    importlib.import_module(_module.name)  # create_all 需要全部表（外键引用跨模块）

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


def _xlsx_bytes(marker: str) -> bytes:
    book = Workbook()
    book.active["A1"] = marker
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


@pytest_asyncio.fixture
async def wopi_env(tmp_path, monkeypatch):
    """SQLite 库 + 临时存储根 + 已发布 ``wopi_put_file`` lane 的 approved bundle。

    返回 ``(session, wp, path)``；``path`` 是底稿文件位置（此时尚不存在）。
    """
    from app.services.workpaper_sync import canonical_paths
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.opaque_entry_gate import authority_model_for_lane
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService
    from app.services.workpaper_sync.writer_migration import OpaqueAuthorityProvisioner

    monkeypatch.chdir(tmp_path)  # cwd 是 legacy 根之一：底稿路径须落在它下面才过边界校验
    monkeypatch.setattr(canonical_paths, "BACKEND_ROOT", tmp_path)  # artifact store 根（调用期取值）

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)()

    project_id, user_id = uuid.uuid4(), uuid.uuid4()
    path = tmp_path / str(project_id) / "2025" / "B1-1.xlsx"
    session.add(Project(id=project_id, name="【测试】WOPI 回滚_2025", client_name="测试客户",
                        project_type=ProjectType.annual, status=ProjectStatus.planning,
                        created_by=user_id))
    await session.flush()
    idx = WpIndex(project_id=project_id, wp_code="B1-1", wp_name="穿行测试底稿",
                  audit_cycle="B", status=WpStatus.in_progress)
    session.add(idx)
    await session.flush()
    wp = WorkingPaper(project_id=project_id, wp_index_id=idx.id, file_path=str(path),
                      source_type=WpSourceType.template, status=WpFileStatus.draft,
                      file_version=1, created_by=user_id)
    session.add(wp)
    await session.flush()

    artifacts = CanonicalArtifactRepository(tmp_path)
    await OpaqueAuthorityProvisioner(
        session=session,
        repository=WorkpaperSyncRepository(session),
        artifacts=artifacts,
        resolution=CanonicalResolutionService(session, artifacts),
    ).provision(
        project_id=project_id,
        wp_id=wp.id,
        authority_model=authority_model_for_lane("wopi_put_file"),
    )
    await session.commit()
    try:
        yield session, wp, path
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_put_file_rejects_a_non_ooxml_payload(wopi_env):
    """**Validates: Requirements 10.8**（原在 test_wopi_working_paper_qc_review）

    统一入口按版本化安全策略在 stage 阶段拒绝非 OOXML 载荷，且拒绝后磁盘上的底稿
    仍是保存前的字节。
    """
    from app.services.wopi_service import WOPIHostService

    session, wp, path = wopi_env
    original = _xlsx_bytes("保存前")
    path.parent.mkdir(parents=True)
    path.write_bytes(original)

    with pytest.raises(Exception) as exc:
        await WOPIHostService().put_file(session, wp.id, b"content")

    assert "ZIP magic" in str(exc.value), exc.value
    assert path.read_bytes() == original, "被拒的载荷留在了底稿文件里（GetFile 会把它当底稿发出去）"


@pytest.mark.asyncio
async def test_rejected_first_save_leaves_no_file(wopi_env):
    """首次保存被拒：不得留下刚写出的文件（旧行为在 backend/ 下留 UUID 目录的根因）。"""
    from app.services.wopi_service import WOPIHostService

    session, wp, path = wopi_env
    assert not path.exists()

    with pytest.raises(Exception) as exc:
        await WOPIHostService().put_file(session, wp.id, b"not an ooxml archive")

    assert "ZIP magic" in str(exc.value), exc.value
    assert not path.exists()
