"""Tests for Task 9: 致同底稿编码体系

Tests cover:
- 种子数据加载（幂等）
- 编码体系列表/详情/树形结构
- 三测联动关系
- 底稿索引自动生成
- API 端点

Validates: Requirements 7.1-7.6
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.gt_coding_models import GTWpCoding, GT_CODING_SEED_DATA, THREE_TEST_LINKAGE
from app.models.workpaper_models import WpIndex

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()


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
    """Create project for index generation tests"""
    project = Project(
        id=FAKE_PROJECT_ID,
        name="致同编码测试项目",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.commit()
    return {"project_id": FAKE_PROJECT_ID}


# ===================================================================
# 种子数据
# ===================================================================


class TestSeedData:

    def test_seed_data_not_empty(self):
        assert len(GT_CODING_SEED_DATA) > 0

    def test_seed_data_has_all_types(self):
        types = {item["wp_type"] for item in GT_CODING_SEED_DATA}
        assert "preliminary" in types
        assert "risk_assessment" in types
        assert "control_test" in types
        assert "substantive" in types
        assert "completion" in types
        assert "specific" in types
        assert "general" in types
        assert "permanent" in types

    def test_seed_data_has_all_substantive_cycles(self):
        substantive = [i for i in GT_CODING_SEED_DATA if i["wp_type"] == "substantive"]
        prefixes = {i["code_prefix"] for i in substantive}
        for p in ["D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "Q"]:
            assert p in prefixes, f"缺少实质性程序循环: {p}"

    def test_three_test_linkage_not_empty(self):
        assert len(THREE_TEST_LINKAGE) > 0

    def test_three_test_linkage_has_all_fields(self):
        for link in THREE_TEST_LINKAGE:
            assert "cycle" in link
            assert "substantive_prefix" in link
            assert "b_code" in link
            assert "c_code" in link


# ===================================================================
# GTCodingService
# ===================================================================


class TestGTCodingService:

    @pytest.mark.asyncio
    async def test_load_seed_data(self, db_session):
        from app.services.gt_coding_service import GTCodingService
        svc = GTCodingService()
        result = await svc.load_seed_data(db_session)
        await db_session.commit()
        assert result["loaded"] == len(GT_CODING_SEED_DATA)
        assert result["existing"] == 0

    @pytest.mark.asyncio
    async def test_load_seed_data_idempotent(self, db_session):
        from app.services.gt_coding_service import GTCodingService
        svc = GTCodingService()
        await svc.load_seed_data(db_session)
        await db_session.commit()
        # Second load should skip
        result = await svc.load_seed_data(db_session)
        assert result["loaded"] == 0
        assert result["existing"] > 0

    @pytest.mark.asyncio
    async def test_list_codings(self, db_session):
        from app.services.gt_coding_service import GTCodingService
        svc = GTCodingService()
        await svc.load_seed_data(db_session)
        await db_session.commit()

        codings = await svc.list_codings(db_session)
        assert len(codings) == len(GT_CODING_SEED_DATA)

    @pytest.mark.asyncio
    async def test_list_codings_filter_by_type(self, db_session):
        from app.services.gt_coding_service import GTCodingService
        svc = GTCodingService()
        await svc.load_seed_data(db_session)
        await db_session.commit()

        substantive = await svc.list_codings(db_session, wp_type="substantive")
        assert len(substantive) == 12  # D-N + Q

    @pytest.mark.asyncio
    async def test_list_codings_filter_by_prefix(self, db_session):
        from app.services.gt_coding_service import GTCodingService
        svc = GTCodingService()
        await svc.load_seed_data(db_session)
        await db_session.commit()

        b_codings = await svc.list_codings(db_session, code_prefix="B")
        assert len(b_codings) >= 2  # At least preliminary + risk_assessment

    @pytest.mark.asyncio
    async def test_get_coding(self, db_session):
        from app.services.gt_coding_service import GTCodingService
        svc = GTCodingService()
        await svc.load_seed_data(db_session)
        await db_session.commit()

        codings = await svc.list_codings(db_session)
        first = codings[0]
        detail = await svc.get_coding(db_session, uuid.UUID(first["id"]))
        assert detail is not None
        assert detail["code_prefix"] == first["code_prefix"]

    @pytest.mark.asyncio
    async def test_get_coding_not_found(self, db_session):
        from app.services.gt_coding_service import GTCodingService
        svc = GTCodingService()
        result = await svc.get_coding(db_session, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_tree(self, db_session):
        from app.services.gt_coding_service import GTCodingService
        svc = GTCodingService()
        await svc.load_seed_data(db_session)
        await db_session.commit()

        tree = await svc.get_tree(db_session)
        assert len(tree) > 0
        # Should have groups for each type
        keys = [node["key"] for node in tree]
        assert "substantive" in keys
        assert "control_test" in keys

    @pytest.mark.asyncio
    async def test_get_three_test_linkage(self):
        from app.services.gt_coding_service import GTCodingService
        svc = GTCodingService()
        linkage = svc.get_three_test_linkage()
        assert len(linkage) == len(THREE_TEST_LINKAGE)
        # Check sales cycle linkage
        sales = next(l for l in linkage if l["cycle"] == "销售循环")
        assert sales["b_code"] == "B23-1"
        assert sales["c_code"] == "C2"
        assert sales["substantive_prefix"] == "D"

    @pytest.mark.asyncio
    async def test_generate_project_index(self, db_session, seeded_db):
        from app.services.gt_coding_service import GTCodingService
        svc = GTCodingService()
        await svc.load_seed_data(db_session)
        await db_session.commit()

        result = await svc.generate_project_index(db_session, FAKE_PROJECT_ID)
        await db_session.commit()
        assert result["generated"] > 0
        assert result["generated"] == len(GT_CODING_SEED_DATA)

    @pytest.mark.asyncio
    async def test_generate_project_index_idempotent(self, db_session, seeded_db):
        from app.services.gt_coding_service import GTCodingService
        svc = GTCodingService()
        await svc.load_seed_data(db_session)
        await db_session.commit()

        await svc.generate_project_index(db_session, FAKE_PROJECT_ID)
        await db_session.commit()
        # Second generation should skip
        result = await svc.generate_project_index(db_session, FAKE_PROJECT_ID)
        assert result["generated"] == 0
        assert result["existing"] > 0

    @pytest.mark.asyncio
    async def test_generate_project_index_simplified(self, db_session, seeded_db):
        from app.services.gt_coding_service import GTCodingService
        svc = GTCodingService()
        await svc.load_seed_data(db_session)
        await db_session.commit()

        result = await svc.generate_project_index(
            db_session, FAKE_PROJECT_ID, template_set="simplified"
        )
        await db_session.commit()
        # Simplified should skip specific and general types
        assert result["generated"] < len(GT_CODING_SEED_DATA)


# ===================================================================
# API 端点测试
# ===================================================================


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


class TestGTCodingAPI:

    @pytest.mark.asyncio
    async def test_load_seed_api(self, client):
        resp = await client.post("/api/gt-coding/seed")
        assert resp.status_code == 200
        data = resp.json()
        result = data.get("data", data)
        assert result["loaded"] > 0

    @pytest.mark.asyncio
    async def test_list_codings_api(self, client):
        await client.post("/api/gt-coding/seed")
        resp = await client.get("/api/gt-coding")
        assert resp.status_code == 200
        data = resp.json()
        items = data.get("data", data)
        assert len(items) > 0

    @pytest.mark.asyncio
    async def test_list_codings_filter_api(self, client):
        await client.post("/api/gt-coding/seed")
        resp = await client.get("/api/gt-coding", params={"wp_type": "substantive"})
        assert resp.status_code == 200
        data = resp.json()
        items = data.get("data", data)
        assert len(items) == 12

    @pytest.mark.asyncio
    async def test_get_tree_api(self, client):
        await client.post("/api/gt-coding/seed")
        resp = await client.get("/api/gt-coding/tree")
        assert resp.status_code == 200
        data = resp.json()
        tree = data.get("data", data)
        assert len(tree) > 0

    @pytest.mark.asyncio
    async def test_get_linkage_api(self, client):
        resp = await client.get("/api/gt-coding/linkage")
        assert resp.status_code == 200
        data = resp.json()
        linkage = data.get("data", data)
        assert len(linkage) > 0

    @pytest.mark.asyncio
    async def test_get_coding_detail_api(self, client):
        await client.post("/api/gt-coding/seed")
        list_resp = await client.get("/api/gt-coding")
        items = list_resp.json().get("data", list_resp.json())
        coding_id = items[0]["id"]

        resp = await client.get(f"/api/gt-coding/{coding_id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_coding_not_found_api(self, client):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/gt-coding/{fake_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_index_api(self, client):
        await client.post("/api/gt-coding/seed")
        resp = await client.post(
            f"/api/projects/{FAKE_PROJECT_ID}/generate-index",
            json={"template_set": "standard"},
        )
        assert resp.status_code == 200
        data = resp.json()
        result = data.get("data", data)
        assert result["generated"] > 0

    @pytest.mark.asyncio
    async def test_generate_index_simplified_api(self, client):
        await client.post("/api/gt-coding/seed")
        resp = await client.post(
            f"/api/projects/{FAKE_PROJECT_ID}/generate-index",
            json={"template_set": "simplified"},
        )
        assert resp.status_code == 200
        data = resp.json()
        result = data.get("data", data)
        assert result["generated"] > 0
