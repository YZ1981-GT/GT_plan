"""Backend test environment configuration. Validates: Requirements 2.8"""
import os
from collections.abc import AsyncGenerator
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")
import fakeredis.aioredis  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.core.redis import get_redis  # noqa: E402
from app.models.base import Base  # noqa: E402
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.dataset_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401
import app.models.consolidation_models  # noqa: E402, F401
import app.models.staff_models  # noqa: E402, F401  — Phase 9: must be before collaboration_models
import app.models.collaboration_models  # noqa: E402, F401
import app.models.ai_models  # noqa: E402, F401
import app.models.extension_models  # noqa: E402, F401
import app.models.gt_coding_models  # noqa: E402, F401
import app.models.t_account_models  # noqa: E402, F401
import app.models.attachment_models  # noqa: E402, F401
import app.models.phase13_models  # noqa: E402, F401  — Phase 13: Word导出
import app.models.phase10_models  # noqa: E402, F401  — Phase 10: 批注/报告溯源（R1 QC 依赖）
import app.models.phase12_models  # noqa: E402, F401  — Phase 12: AI generation 等
import app.models.phase14_enums  # noqa: E402, F401  — Phase 14: Gate 引擎枚举
import app.models.phase14_models  # noqa: E402, F401  — Phase 14: Gate 引擎模型
import app.models.phase15_enums  # noqa: E402, F401  — Phase 15: 任务树枚举
import app.models.phase15_models  # noqa: E402, F401  — Phase 15: 任务树模型
import app.models.phase16_enums  # noqa: E402, F401  — Phase 16: 证据包枚举
import app.models.phase16_models  # noqa: E402, F401  — Phase 16: 证据包模型
import app.models.archive_models  # noqa: E402, F401  — R1 归档作业
import app.models.knowledge_models  # noqa: E402, F401
import app.models.note_trim_models  # noqa: E402, F401
import app.models.procedure_models  # noqa: E402, F401
import app.models.shared_config_models  # noqa: E402, F401
import app.models.template_library_models  # noqa: E402, F401
import app.models.eqcr_models  # noqa: E402, F401  — Round 5
import app.models.related_party_models  # noqa: E402, F401  — Round 5
import app.models.independence_models  # noqa: E402, F401  — Round 5

# Stub for 'workpapers' table referenced by AI models FK
import sqlalchemy as _sa
class _WorkpaperStub(Base):
    __tablename__ = "workpapers"
    __table_args__ = {"extend_existing": True}
    id = _sa.Column(_sa.Uuid, primary_key=True)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
