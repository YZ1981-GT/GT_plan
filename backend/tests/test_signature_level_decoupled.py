"""签字字段控制流解耦测试

验证 CA 证书验证分支走 required_role + required_order，而非 signature_level 字符串。
需求 5 AC1-5。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

# 注册所有模型
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401
import app.models.consolidation_models  # noqa: E402, F401
import app.models.staff_models  # noqa: E402, F401
import app.models.collaboration_models  # noqa: E402, F401
import app.models.ai_models  # noqa: E402, F401
import app.models.extension_models  # noqa: E402, F401
import app.models.gt_coding_models  # noqa: E402, F401
import app.models.t_account_models  # noqa: E402, F401
import app.models.attachment_models  # noqa: E402, F401
import app.models.phase13_models  # noqa: E402, F401
import app.models.eqcr_models  # noqa: E402, F401
import app.models.related_party_models  # noqa: E402, F401
import app.models.phase14_models  # noqa: E402, F401

from app.models.extension_models import SignatureRecord  # noqa: E402
from app.services.sign_service import SignService  # noqa: E402


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_ca_verification_triggered_by_required_role_not_signature_level(db_session: AsyncSession):
    """CA 验证走 required_role='signing_partner' + required_order=3，而非 signature_level 字符串。

    场景：signature_level='eqcr'（非 'level3'），但 required_role='signing_partner' + required_order=3
    预期：仍触发 CA 证书验证分支（NotImplementedError）
    """
    record_id = uuid.uuid4()
    signer_id = uuid.uuid4()
    record = SignatureRecord(
        id=record_id,
        object_type="audit_report",
        object_id=uuid.uuid4(),
        signer_id=signer_id,
        signature_level="eqcr",  # 非 "level3"
        required_order=3,
        required_role="signing_partner",
        signature_timestamp=datetime.now(timezone.utc),
    )
    db_session.add(record)
    await db_session.flush()

    service = SignService()
    with pytest.raises(NotImplementedError, match="CA证书验证尚未实现"):
        await service.verify_signature(db_session, record_id)


@pytest.mark.asyncio
async def test_level3_string_alone_does_not_trigger_ca_verification(db_session: AsyncSession):
    """仅 signature_level='level3' 但 required_role/required_order 不匹配时，不触发 CA 验证。

    场景：signature_level='level3'，但 required_role=None, required_order=None
    预期：正常返回验证通过（不走 CA 分支）
    """
    record_id = uuid.uuid4()
    signer_id = uuid.uuid4()
    record = SignatureRecord(
        id=record_id,
        object_type="audit_report",
        object_id=uuid.uuid4(),
        signer_id=signer_id,
        signature_level="level3",  # 旧字符串
        required_order=None,
        required_role=None,
        signature_timestamp=datetime.now(timezone.utc),
    )
    db_session.add(record)
    await db_session.flush()

    service = SignService()
    result = await service.verify_signature(db_session, record_id)
    assert result["valid"] is True
    assert result["signature_id"] == str(record_id)


@pytest.mark.asyncio
async def test_normal_signature_passes_verification(db_session: AsyncSession):
    """普通签字（非 CA 级别）正常通过验证。"""
    record_id = uuid.uuid4()
    signer_id = uuid.uuid4()
    record = SignatureRecord(
        id=record_id,
        object_type="working_paper",
        object_id=uuid.uuid4(),
        signer_id=signer_id,
        signature_level="level1",
        required_order=1,
        required_role="auditor",
        signature_timestamp=datetime.now(timezone.utc),
    )
    db_session.add(record)
    await db_session.flush()

    service = SignService()
    result = await service.verify_signature(db_session, record_id)
    assert result["valid"] is True
    assert result["level"] == "level1"
    assert result["signer_id"] == str(signer_id)
