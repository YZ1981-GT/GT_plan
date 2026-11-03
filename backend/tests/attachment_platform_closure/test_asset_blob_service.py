"""不可变字节登记与领域根读取边界测试。"""
from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.asset_blob_models import AssetBlob
from app.services.asset_blob_service import AssetBlobService, resolve_within_root


_CREATE_ASSET_BLOBS = """
CREATE TABLE asset_blobs (
    id CHAR(32) PRIMARY KEY,
    content_hash VARCHAR(64) NOT NULL,
    byte_size BIGINT NOT NULL,
    detected_media_type VARCHAR(128),
    storage_type VARCHAR(24) NOT NULL,
    storage_key TEXT NOT NULL UNIQUE,
    ingress_policy_version VARCHAR(32) NOT NULL DEFAULT 'apc-v1',
    security_status VARCHAR(20) NOT NULL DEFAULT 'accepted',
    actor_type VARCHAR(20) NOT NULL,
    actor_user_id CHAR(32),
    actor_service_identity_id CHAR(32),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (storage_type, storage_key)
)
"""


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(sa.text(_CREATE_ASSET_BLOBS))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_bytes_is_idempotent_for_same_locator_and_content(db: AsyncSession) -> None:
    service = AssetBlobService(db)
    actor = uuid.uuid4()

    first = await service.register_bytes(
        storage_type="local",
        storage_key="knowledge/a.txt",
        content=b"same bytes",
        media_type="text/plain",
        actor_user_id=actor,
    )
    second = await service.register_bytes(
        storage_type="local",
        storage_key="knowledge/a.txt",
        content=b"same bytes",
        media_type="text/plain",
        actor_user_id=actor,
    )

    assert first.id == second.id
    assert first.content_hash == hashlib.sha256(b"same bytes").hexdigest()
    assert first.byte_size == 10
    assert (await db.execute(sa.select(sa.func.count()).select_from(AssetBlob))).scalar_one() == 1


@pytest.mark.asyncio
async def test_register_bytes_rejects_changed_bytes_at_existing_locator(db: AsyncSession) -> None:
    service = AssetBlobService(db)
    actor = uuid.uuid4()
    await service.register_bytes(
        storage_type="local", storage_key="fixed", content=b"v1",
        media_type=None, actor_user_id=actor,
    )

    with pytest.raises(RuntimeError, match="字节已变化"):
        await service.register_bytes(
            storage_type="local", storage_key="fixed", content=b"v2",
            media_type=None, actor_user_id=actor,
        )


@pytest.mark.asyncio
async def test_available_and_shadow_registration(db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    service = AssetBlobService(db)
    assert await service.available() is True
    monkeypatch.setenv("TEST_ASSET_MODE", "shadow")

    row = await service.register_if_enabled(
        storage_type="local",
        storage_key="shadow/file.pdf",
        content=b"%PDF-shadow",
        media_type="application/pdf",
        actor_user_id=uuid.uuid4(),
        mode_env="TEST_ASSET_MODE",
    )

    assert row is not None and row.storage_key == "shadow/file.pdf"


@pytest.mark.asyncio
async def test_missing_table_or_actor_degrades_only_in_shadow(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        service = AssetBlobService(db)
        monkeypatch.setenv("TEST_ASSET_MODE", "shadow")
        assert await service.register_if_enabled(
            storage_type="local", storage_key="x", content=b"x", media_type=None,
            actor_user_id=uuid.uuid4(), mode_env="TEST_ASSET_MODE",
        ) is None
        assert await service.register_if_enabled(
            storage_type="local", storage_key="x", content=b"x", media_type=None,
            actor_user_id=None, mode_env="TEST_ASSET_MODE",
        ) is None

        monkeypatch.setenv("TEST_ASSET_MODE", "blob_only")
        with pytest.raises(RuntimeError, match="迁移尚未就绪"):
            await service.register_if_enabled(
                storage_type="local", storage_key="x", content=b"x", media_type=None,
                actor_user_id=uuid.uuid4(), mode_env="TEST_ASSET_MODE",
            )
        with pytest.raises(RuntimeError, match="缺少或存在多个操作者"):
            await service.register_if_enabled(
                storage_type="local", storage_key="x", content=b"x", media_type=None,
                actor_user_id=None, mode_env="TEST_ASSET_MODE",
            )
    await engine.dispose()


def test_resolve_within_root_accepts_only_real_files_inside_domain_root(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    inside = root / "nested" / "evidence.txt"
    inside.parent.mkdir(parents=True)
    inside.write_text("safe", encoding="utf-8")
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")

    assert resolve_within_root(str(inside), root) == inside.resolve()
    assert resolve_within_root("nested/evidence.txt", root) == inside.resolve()
    assert resolve_within_root(str(outside), root) is None
    assert resolve_within_root("https://example.test/evidence.txt", root) is None
    assert resolve_within_root(str(root / "missing.txt"), root) is None


def test_resolve_within_root_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    link = root / "linked.txt"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不允许创建符号链接")

    assert resolve_within_root(str(link), root) is None


@pytest.mark.asyncio
async def test_read_verified_checks_root_size_and_hash(
    db: AsyncSession, tmp_path: Path,
) -> None:
    root = tmp_path / "knowledge"
    path = root / "doc.txt"
    path.parent.mkdir()
    path.write_bytes(b"trusted bytes")
    service = AssetBlobService(db)
    row = await service.register_bytes(
        storage_type="local", storage_key=str(path), content=b"trusted bytes",
        media_type="text/plain", actor_user_id=uuid.uuid4(),
    )

    verified = await service.read_verified(row.id, allowed_roots=(root,))
    assert verified.content == b"trusted bytes"
    assert verified.canonical_path == path.resolve()

    path.write_bytes(b"tampered bytes")
    from app.services.asset_blob_service import AssetBlobReadRejected

    with pytest.raises(AssetBlobReadRejected, match="integrity_mismatch"):
        await service.read_verified(row.id, allowed_roots=(root,))


@pytest.mark.asyncio
async def test_read_verified_rejects_locator_outside_trusted_roots(
    db: AsyncSession, tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"secret")
    service = AssetBlobService(db)
    row = await service.register_bytes(
        storage_type="local", storage_key=str(outside), content=b"secret",
        media_type="text/plain", actor_user_id=uuid.uuid4(),
    )
    from app.services.asset_blob_service import AssetBlobReadRejected

    with pytest.raises(AssetBlobReadRejected, match="outside_trusted_storage_or_missing"):
        await service.read_verified(row.id, allowed_roots=(tmp_path / "trusted",))


@pytest.mark.asyncio
async def test_register_bytes_accepts_exactly_one_service_actor(db: AsyncSession) -> None:
    service = AssetBlobService(db)
    service_id = uuid.uuid4()
    row = await service.register_bytes(
        storage_type="local", storage_key="service/generated.pdf", content=b"%PDF-service",
        media_type="application/pdf", actor_service_identity_id=service_id,
    )
    assert row.actor_type == "service"
    assert row.actor_service_identity_id == service_id and row.actor_user_id is None
    with pytest.raises(RuntimeError, match="必须且只能提供一个操作者"):
        await service.register_bytes(
            storage_type="local", storage_key="invalid", content=b"x", media_type=None,
            actor_user_id=uuid.uuid4(), actor_service_identity_id=service_id,
        )
