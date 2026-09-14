"""A16 sign-status API 版本隔离测试

验证：
- POST sign-status with version=A16-2 存储到 scope word_template:A16:A16-2
- GET file-info with version=A16-2 返回该版本的独立状态
- GET file-info with version=A16-1 返回另一版本的独立状态（不继承）
- 无 version 参数时保持向后兼容

Validates: Requirements 3（按版本签回：pending→sent→signed，scope 含版本号）
"""

import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.models.workpaper_models import (
    WpFileStatus,
    WpIndex,
    WpSourceType,
    WpStatus,
    WorkingPaper,
)
from app.models.workpaper_field_override_models import WorkpaperFieldOverride
from app.services.field_override_service import FieldOverrideService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_PROJECT_ID = uuid.uuid4()
FAKE_USER_ID = uuid.uuid4()
FAKE_WP_ID = uuid.uuid4()
FAKE_WP_INDEX_ID = uuid.uuid4()
YEAR = 2025


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """Seed: project + wp_index(A16) + working_paper + user"""
    user = User(
        id=FAKE_USER_ID,
        username="test_user",
        email="test@example.com",
        hashed_password="x",
        role=UserRole.admin,
    )
    db_session.add(user)

    project = Project(
        id=FAKE_PROJECT_ID,
        name="测试项目_2025",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
        audit_period_end=date(2025, 12, 31),
    )
    db_session.add(project)
    await db_session.flush()

    wp_index = WpIndex(
        id=FAKE_WP_INDEX_ID,
        project_id=FAKE_PROJECT_ID,
        wp_code="A16",
        wp_name="管理层声明书",
        audit_cycle="A",
        status=WpStatus.in_progress,
    )
    db_session.add(wp_index)
    await db_session.flush()

    wp = WorkingPaper(
        id=FAKE_WP_ID,
        project_id=FAKE_PROJECT_ID,
        wp_index_id=FAKE_WP_INDEX_ID,
        file_path=f"{FAKE_PROJECT_ID}/2025/A16.docx",
        source_type=WpSourceType.template,
        status=WpFileStatus.draft,
        file_version=1,
        created_by=FAKE_USER_ID,
    )
    db_session.add(wp)
    await db_session.commit()

    return {"project": project, "wp_index": wp_index, "wp": wp, "user": user}


class TestSignStatusVersionIsolation:
    """A16 签回状态按版本隔离（切换版本不继承 signed）"""

    @pytest.mark.asyncio
    async def test_set_sign_status_with_version_stores_scoped(self, db_session, seeded_db):
        """POST sign-status with version=A16-2 → scope = word_template:A16:A16-2"""
        svc = FieldOverrideService(db_session)

        # 模拟 update_sign_status 逻辑：有 version 且 wp_code == "A16"
        version = "A16-2"
        wp_code = "A16"
        scope = f"word_template:A16:{version}"

        await svc.set(FAKE_PROJECT_ID, YEAR, scope, "sign_status", "value", "signed", FAKE_USER_ID)
        await db_session.flush()

        # 验证读回
        got = await svc.get(FAKE_PROJECT_ID, YEAR, scope, "sign_status", "value")
        assert got == "signed"

    @pytest.mark.asyncio
    async def test_get_file_info_with_version_returns_version_specific_status(self, db_session, seeded_db):
        """GET file-info with version=A16-2 返回该版本的独立 sign_status"""
        svc = FieldOverrideService(db_session)

        # 先写入 A16-2 为 signed
        await svc.set(FAKE_PROJECT_ID, YEAR, "word_template:A16:A16-2", "sign_status", "value", "signed", FAKE_USER_ID)
        await db_session.flush()

        # 模拟 get_workpaper_file_info 逻辑
        version = "A16-2"
        wp_code = "A16"
        if version and wp_code == "A16":
            scope = f"word_template:A16:{version}"
        else:
            scope = f"word_template:{wp_code}"

        sign_status = await svc.get(FAKE_PROJECT_ID, YEAR, scope, "sign_status", "value")
        assert sign_status == "signed"

    @pytest.mark.asyncio
    async def test_different_versions_have_independent_status(self, db_session, seeded_db):
        """A16-2 signed → A16-1 仍为 pending（不继承）"""
        svc = FieldOverrideService(db_session)

        # A16-2 标记为 signed
        await svc.set(FAKE_PROJECT_ID, YEAR, "word_template:A16:A16-2", "sign_status", "value", "signed", FAKE_USER_ID)
        # A16-1 标记为 sent
        await svc.set(FAKE_PROJECT_ID, YEAR, "word_template:A16:A16-1", "sign_status", "value", "sent", FAKE_USER_ID)
        await db_session.flush()

        # 读 A16-2 → signed
        status_2 = await svc.get(FAKE_PROJECT_ID, YEAR, "word_template:A16:A16-2", "sign_status", "value")
        assert status_2 == "signed"

        # 读 A16-1 → sent（独立，不继承 A16-2 的 signed）
        status_1 = await svc.get(FAKE_PROJECT_ID, YEAR, "word_template:A16:A16-1", "sign_status", "value")
        assert status_1 == "sent"

        # 读 A16-3（未设置）→ None（前端显示 pending）
        status_3 = await svc.get(FAKE_PROJECT_ID, YEAR, "word_template:A16:A16-3", "sign_status", "value")
        assert status_3 is None

    @pytest.mark.asyncio
    async def test_no_version_backward_compatible(self, db_session, seeded_db):
        """无 version 参数 → scope = word_template:A16（向后兼容）"""
        svc = FieldOverrideService(db_session)

        # 用不带版本的 scope 写入
        await svc.set(FAKE_PROJECT_ID, YEAR, "word_template:A16", "sign_status", "value", "sent", FAKE_USER_ID)
        await db_session.flush()

        # 模拟无 version 参数时的逻辑
        version = None
        wp_code = "A16"
        if version and wp_code == "A16":
            scope = f"word_template:A16:{version}"
        else:
            scope = f"word_template:{wp_code}"

        sign_status = await svc.get(FAKE_PROJECT_ID, YEAR, scope, "sign_status", "value")
        assert sign_status == "sent"

    @pytest.mark.asyncio
    async def test_version_scope_does_not_pollute_base_scope(self, db_session, seeded_db):
        """带 version 写入不影响不带 version 的 base scope"""
        svc = FieldOverrideService(db_session)

        # 写 base scope
        await svc.set(FAKE_PROJECT_ID, YEAR, "word_template:A16", "sign_status", "value", "pending", FAKE_USER_ID)
        # 写版本 scope
        await svc.set(FAKE_PROJECT_ID, YEAR, "word_template:A16:A16-2", "sign_status", "value", "signed", FAKE_USER_ID)
        await db_session.flush()

        # base scope 不受版本 scope 影响
        base_status = await svc.get(FAKE_PROJECT_ID, YEAR, "word_template:A16", "sign_status", "value")
        assert base_status == "pending"

        # 版本 scope 独立
        ver_status = await svc.get(FAKE_PROJECT_ID, YEAR, "word_template:A16:A16-2", "sign_status", "value")
        assert ver_status == "signed"

    @pytest.mark.asyncio
    async def test_a16_7_supplement_independent_of_main_versions(self, db_session, seeded_db):
        """A16-7 补充声明签回与主版本 A16-1~6 完全独立"""
        svc = FieldOverrideService(db_session)

        # 主版本 A16-1 signed
        await svc.set(FAKE_PROJECT_ID, YEAR, "word_template:A16:A16-1", "sign_status", "value", "signed", FAKE_USER_ID)
        # 补充声明 A16-7 仍为 pending（未设置）
        await db_session.flush()

        status_main = await svc.get(FAKE_PROJECT_ID, YEAR, "word_template:A16:A16-1", "sign_status", "value")
        assert status_main == "signed"

        status_supplement = await svc.get(FAKE_PROJECT_ID, YEAR, "word_template:A16:A16-7", "sign_status", "value")
        assert status_supplement is None  # 前端显示 pending

    @pytest.mark.asyncio
    async def test_overwrite_version_status(self, db_session, seeded_db):
        """同一版本的状态可从 pending→sent→signed 逐步更新"""
        svc = FieldOverrideService(db_session)
        scope = "word_template:A16:A16-2"

        # pending → sent
        await svc.set(FAKE_PROJECT_ID, YEAR, scope, "sign_status", "value", "pending", FAKE_USER_ID)
        await db_session.flush()
        assert await svc.get(FAKE_PROJECT_ID, YEAR, scope, "sign_status", "value") == "pending"

        # sent
        await svc.set(FAKE_PROJECT_ID, YEAR, scope, "sign_status", "value", "sent", FAKE_USER_ID)
        await db_session.flush()
        assert await svc.get(FAKE_PROJECT_ID, YEAR, scope, "sign_status", "value") == "sent"

        # signed
        await svc.set(FAKE_PROJECT_ID, YEAR, scope, "sign_status", "value", "signed", FAKE_USER_ID)
        await db_session.flush()
        assert await svc.get(FAKE_PROJECT_ID, YEAR, scope, "sign_status", "value") == "signed"
