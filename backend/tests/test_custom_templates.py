"""Tests for Task 6: 用户自定义底稿模板

Validates: Requirements 4.1-4.6
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import User, UserRole
from app.models.extension_models import WpTemplateCustom

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
OTHER_USER_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    user = User(id=FAKE_USER_ID, username="tester", email="t@t.com",
                hashed_password="x", role=UserRole.auditor)
    db_session.add(user)
    other = User(id=OTHER_USER_ID, username="other", email="o@o.com",
                 hashed_password="x", role=UserRole.auditor)
    db_session.add(other)
    await db_session.commit()
    return {}


class TestCustomTemplateService:

    @pytest.mark.asyncio
    async def test_create(self, db_session, seeded_db):
        from app.services.custom_template_service import CustomTemplateService
        svc = CustomTemplateService()
        result = await svc.create_template(db_session, FAKE_USER_ID, {
            "template_name": "行业专用-银行审计", "category": "industry",
            "template_file_path": "/templates/bank.xlsx", "version": "1.0",
        })
        await db_session.commit()
        assert result["template_name"] == "行业专用-银行审计"
        assert result["category"] == "industry"
        assert result["is_published"] is False

    @pytest.mark.asyncio
    async def test_update(self, db_session, seeded_db):
        from app.services.custom_template_service import CustomTemplateService
        svc = CustomTemplateService()
        created = await svc.create_template(db_session, FAKE_USER_ID, {
            "template_name": "原始名", "template_file_path": "/a.xlsx",
        })
        await db_session.flush()
        updated = await svc.update_template(db_session, uuid.UUID(created["id"]), FAKE_USER_ID, {
            "template_name": "新名称",
        })
        assert updated["template_name"] == "新名称"

    @pytest.mark.asyncio
    async def test_update_not_owner(self, db_session, seeded_db):
        from app.services.custom_template_service import CustomTemplateService
        svc = CustomTemplateService()
        created = await svc.create_template(db_session, FAKE_USER_ID, {
            "template_name": "我的模板", "template_file_path": "/a.xlsx",
        })
        await db_session.flush()
        with pytest.raises(ValueError, match="无权限"):
            await svc.update_template(db_session, uuid.UUID(created["id"]), OTHER_USER_ID, {
                "template_name": "篡改",
            })

    @pytest.mark.asyncio
    async def test_delete(self, db_session, seeded_db):
        from app.services.custom_template_service import CustomTemplateService
        svc = CustomTemplateService()
        created = await svc.create_template(db_session, FAKE_USER_ID, {
            "template_name": "待删除", "template_file_path": "/a.xlsx",
        })
        await db_session.flush()
        await svc.delete_template(db_session, uuid.UUID(created["id"]), FAKE_USER_ID)
        await db_session.flush()
        detail = await svc.get_template(db_session, uuid.UUID(created["id"]))
        assert detail is None

    @pytest.mark.asyncio
    async def test_list_my(self, db_session, seeded_db):
        from app.services.custom_template_service import CustomTemplateService
        svc = CustomTemplateService()
        await svc.create_template(db_session, FAKE_USER_ID, {
            "template_name": "模板A", "template_file_path": "/a.xlsx", "category": "personal",
        })
        await svc.create_template(db_session, FAKE_USER_ID, {
            "template_name": "模板B", "template_file_path": "/b.xlsx", "category": "industry",
        })
        await db_session.commit()
        all_items = await svc.list_my_templates(db_session, FAKE_USER_ID)
        assert len(all_items) == 2
        personal = await svc.list_my_templates(db_session, FAKE_USER_ID, category="personal")
        assert len(personal) == 1

    @pytest.mark.asyncio
    async def test_publish_and_market(self, db_session, seeded_db):
        from app.services.custom_template_service import CustomTemplateService
        svc = CustomTemplateService()
        created = await svc.create_template(db_session, FAKE_USER_ID, {
            "template_name": "共享模板", "template_file_path": "/share.xlsx",
        })
        await db_session.flush()

        # 发布前市场为空
        market = await svc.list_market(db_session)
        assert len(market) == 0

        # 发布
        await svc.publish_template(db_session, uuid.UUID(created["id"]), FAKE_USER_ID)
        await db_session.flush()
        market = await svc.list_market(db_session)
        assert len(market) == 1
        assert market[0]["is_published"] is True

        # 取消发布
        await svc.unpublish_template(db_session, uuid.UUID(created["id"]), FAKE_USER_ID)
        await db_session.flush()
        market = await svc.list_market(db_session)
        assert len(market) == 0

    @pytest.mark.asyncio
    async def test_create_version(self, db_session, seeded_db):
        from app.services.custom_template_service import CustomTemplateService
        svc = CustomTemplateService()
        v1 = await svc.create_template(db_session, FAKE_USER_ID, {
            "template_name": "版本测试", "template_file_path": "/v1.xlsx", "version": "1.0",
        })
        await db_session.flush()
        v2 = await svc.create_version(
            db_session, uuid.UUID(v1["id"]), FAKE_USER_ID, "2.0", "/v2.xlsx",
        )
        assert v2["version"] == "2.0"
        assert v2["template_name"] == "版本测试"
        assert v2["id"] != v1["id"]

    @pytest.mark.asyncio
    async def test_validate_valid(self):
        from app.services.custom_template_service import CustomTemplateService
        svc = CustomTemplateService()
        result = await svc.validate_template('=TB("1001","期末余额") =WP("E1-1","B5")')
        assert result["valid"] is True
        assert result["formula_count"] == 2

    @pytest.mark.asyncio
    async def test_validate_no_formulas(self):
        from app.services.custom_template_service import CustomTemplateService
        svc = CustomTemplateService()
        result = await svc.validate_template("普通文本内容")
        assert result["valid"] is True
        assert len(result["issues"]) == 1  # warning: no formulas

    @pytest.mark.asyncio
    async def test_validate_bracket_mismatch(self):
        from app.services.custom_template_service import CustomTemplateService
        svc = CustomTemplateService()
        result = await svc.validate_template('=TB("1001","期末余额"')
        assert result["valid"] is False

    @pytest.mark.asyncio
    async def test_validate_empty(self):
        from app.services.custom_template_service import CustomTemplateService
        svc = CustomTemplateService()
        result = await svc.validate_template(None)
        assert result["valid"] is True


# ── API Tests ──

@pytest_asyncio.fixture
async def client(db_session: AsyncSession, seeded_db):
    import fakeredis.aioredis
    from httpx import ASGITransport, AsyncClient
    from app.core.database import get_db
    from app.core.redis import get_redis
    from app.main import app

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def override_get_db():
        yield db_session

    async def override_get_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


class TestCustomTemplateAPI:

    @pytest.mark.asyncio
    async def test_create_api(self, client):
        resp = await client.post("/api/custom-templates", json={
            "template_name": "API测试模板", "template_file_path": "/api.xlsx",
        })
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["template_name"] == "API测试模板"

    @pytest.mark.asyncio
    async def test_list_api(self, client):
        await client.post("/api/custom-templates", json={
            "template_name": "列表测试", "template_file_path": "/list.xlsx",
        })
        resp = await client.get("/api/custom-templates")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_market_api(self, client):
        resp = await client.get("/api/custom-templates/market")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_detail_api(self, client):
        create_resp = await client.post("/api/custom-templates", json={
            "template_name": "详情测试", "template_file_path": "/detail.xlsx",
        })
        tid = create_resp.json().get("data", create_resp.json())["id"]
        resp = await client.get(f"/api/custom-templates/{tid}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_api(self, client):
        create_resp = await client.post("/api/custom-templates", json={
            "template_name": "待更新", "template_file_path": "/update.xlsx",
        })
        tid = create_resp.json().get("data", create_resp.json())["id"]
        resp = await client.put(f"/api/custom-templates/{tid}", json={
            "template_name": "已更新",
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_publish_api(self, client):
        create_resp = await client.post("/api/custom-templates", json={
            "template_name": "待发布", "template_file_path": "/pub.xlsx",
        })
        tid = create_resp.json().get("data", create_resp.json())["id"]
        resp = await client.post(f"/api/custom-templates/{tid}/publish")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["is_published"] is True

    @pytest.mark.asyncio
    async def test_version_api(self, client):
        create_resp = await client.post("/api/custom-templates", json={
            "template_name": "版本测试", "template_file_path": "/v1.xlsx",
        })
        tid = create_resp.json().get("data", create_resp.json())["id"]
        resp = await client.post(f"/api/custom-templates/{tid}/version", json={
            "new_version": "2.0", "file_path": "/v2.xlsx",
        })
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["version"] == "2.0"

    @pytest.mark.asyncio
    async def test_delete_api(self, client):
        create_resp = await client.post("/api/custom-templates", json={
            "template_name": "待删除", "template_file_path": "/del.xlsx",
        })
        tid = create_resp.json().get("data", create_resp.json())["id"]
        resp = await client.delete(f"/api/custom-templates/{tid}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_not_found_api(self, client):
        resp = await client.get(f"/api/custom-templates/{uuid.uuid4()}")
        assert resp.status_code == 404
