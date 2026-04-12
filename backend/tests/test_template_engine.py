"""底稿模板引擎测试

Validates: Requirements 1.1-1.8, 6.2, 6.3
"""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.workpaper_models import (
    RegionType,
    WpIndex,
    WpSourceType,
    WpTemplate,
    WpTemplateMeta,
    WpTemplateSet,
    WpTemplateStatus,
    WorkingPaper,
)
from app.services.template_engine import BUILTIN_TEMPLATE_SETS, TemplateEngine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine_db = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine_db.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        test_engine_db, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """Create a test project."""
    project = Project(
        id=FAKE_PROJECT_ID,
        name="模板引擎测试_2025",
        client_name="模板引擎测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.commit()
    return FAKE_PROJECT_ID


# ===== TemplateEngine.upload_template Tests =====


@pytest.mark.asyncio
async def test_upload_template_basic(db_session):
    """6.1: upload_template creates template record"""
    engine = TemplateEngine()
    tpl = await engine.upload_template(
        db=db_session,
        template_code="E1-1",
        template_name="货币资金审定表",
        audit_cycle="货币资金",
        applicable_standard="CAS",
        description="测试模板",
        created_by=FAKE_USER_ID,
    )
    await db_session.commit()

    assert tpl.id is not None
    assert tpl.template_code == "E1-1"
    assert tpl.template_name == "货币资金审定表"
    assert tpl.version_major == 1
    assert tpl.version_minor == 0
    assert tpl.status == WpTemplateStatus.draft
    assert "E1-1" in tpl.file_path


@pytest.mark.asyncio
async def test_upload_template_with_named_ranges(db_session):
    """6.1: upload_template parses Named Ranges into wp_template_meta"""
    engine = TemplateEngine()
    named_ranges = [
        {"range_name": "WP_CONCLUSION", "region_type": RegionType.conclusion},
        {"range_name": "WP_FORMULA_TB", "region_type": RegionType.formula},
        {"range_name": "WP_MANUAL_INPUT", "region_type": RegionType.manual},
    ]
    tpl = await engine.upload_template(
        db=db_session,
        template_code="E1-2",
        template_name="银行存款审定表",
        named_ranges=named_ranges,
    )
    await db_session.commit()

    import sqlalchemy as sa
    result = await db_session.execute(
        sa.select(WpTemplateMeta).where(WpTemplateMeta.template_id == tpl.id)
    )
    metas = result.scalars().all()
    assert len(metas) == 3
    range_names = {m.range_name for m in metas}
    assert "WP_CONCLUSION" in range_names
    assert "WP_FORMULA_TB" in range_names


# ===== TemplateEngine.create_version Tests =====


@pytest.mark.asyncio
async def test_create_version_minor(db_session):
    """6.2: create_version minor increment"""
    engine = TemplateEngine()
    await engine.upload_template(
        db=db_session, template_code="F1-1", template_name="应收账款审定表",
    )
    await db_session.flush()

    new_tpl = await engine.create_version(
        db=db_session, template_code="F1-1", change_type="minor",
    )
    await db_session.commit()

    assert new_tpl.version_major == 1
    assert new_tpl.version_minor == 1


@pytest.mark.asyncio
async def test_create_version_major(db_session):
    """6.2: create_version major increment"""
    engine = TemplateEngine()
    await engine.upload_template(
        db=db_session, template_code="G1-1", template_name="存货审定表",
    )
    await db_session.flush()

    new_tpl = await engine.create_version(
        db=db_session, template_code="G1-1", change_type="major",
    )
    await db_session.commit()

    assert new_tpl.version_major == 2
    assert new_tpl.version_minor == 0


@pytest.mark.asyncio
async def test_create_version_nonexistent(db_session):
    """6.2: create_version for nonexistent template raises error"""
    engine = TemplateEngine()
    with pytest.raises(ValueError, match="不存在"):
        await engine.create_version(
            db=db_session, template_code="NONEXIST", change_type="minor",
        )


# ===== TemplateEngine.delete_template Tests =====


@pytest.mark.asyncio
async def test_delete_template_success(db_session):
    """6.3: delete_template soft deletes when no references"""
    engine = TemplateEngine()
    tpl = await engine.upload_template(
        db=db_session, template_code="H1-1", template_name="固定资产审定表",
    )
    await db_session.flush()

    await engine.delete_template(db=db_session, template_id=tpl.id)
    await db_session.commit()

    # Verify soft deleted
    import sqlalchemy as sa
    result = await db_session.execute(
        sa.select(WpTemplate).where(WpTemplate.id == tpl.id)
    )
    deleted_tpl = result.scalar_one()
    assert deleted_tpl.is_deleted is True


@pytest.mark.asyncio
async def test_delete_template_with_reference(db_session, seeded_db):
    """6.3: delete_template fails when referenced by working papers"""
    engine = TemplateEngine()
    tpl = await engine.upload_template(
        db=db_session, template_code="REF-1", template_name="被引用模板",
    )
    await db_session.flush()

    # Create a working paper that references this template code
    wp_index = WpIndex(
        project_id=FAKE_PROJECT_ID,
        wp_code="REF-1",
        wp_name="被引用底稿",
    )
    db_session.add(wp_index)
    await db_session.flush()

    wp = WorkingPaper(
        project_id=FAKE_PROJECT_ID,
        wp_index_id=wp_index.id,
        file_path=f"{FAKE_PROJECT_ID}/2025/REF-1.xlsx",
        source_type=WpSourceType.template,
    )
    db_session.add(wp)
    await db_session.commit()

    with pytest.raises(ValueError, match="已被.*引用"):
        await engine.delete_template(db=db_session, template_id=tpl.id)


@pytest.mark.asyncio
async def test_delete_template_nonexistent(db_session):
    """6.3: delete_template for nonexistent template raises error"""
    engine = TemplateEngine()
    with pytest.raises(ValueError, match="不存在"):
        await engine.delete_template(
            db=db_session, template_id=uuid.uuid4(),
        )


# ===== Template Set Management Tests =====


@pytest.mark.asyncio
async def test_seed_builtin_template_sets(db_session):
    """6.4: seed 6 built-in template sets"""
    engine = TemplateEngine()
    created = await engine.seed_builtin_template_sets(db=db_session)
    await db_session.commit()

    assert len(created) == 6

    sets = await engine.get_template_sets(db=db_session)
    set_names = {s.set_name for s in sets}
    assert "标准年审" in set_names
    assert "精简版" in set_names
    assert "上市公司" in set_names
    assert "IPO" in set_names
    assert "国企附注" in set_names
    assert "上市附注" in set_names


@pytest.mark.asyncio
async def test_seed_builtin_idempotent(db_session):
    """6.4: seed is idempotent — second call creates 0"""
    engine = TemplateEngine()
    await engine.seed_builtin_template_sets(db=db_session)
    await db_session.commit()

    created2 = await engine.seed_builtin_template_sets(db=db_session)
    await db_session.commit()
    assert len(created2) == 0


@pytest.mark.asyncio
async def test_create_template_set(db_session):
    """6.4: create custom template set"""
    engine = TemplateEngine()
    ts = await engine.create_template_set(
        db=db_session,
        set_name="自定义模板集",
        template_codes=["E1-1", "F1-1"],
        applicable_audit_type="annual",
        description="测试模板集",
    )
    await db_session.commit()

    assert ts.id is not None
    assert ts.set_name == "自定义模板集"
    assert ts.template_codes == ["E1-1", "F1-1"]


@pytest.mark.asyncio
async def test_update_template_set(db_session):
    """6.4: update template set"""
    engine = TemplateEngine()
    ts = await engine.create_template_set(
        db=db_session, set_name="待更新集",
    )
    await db_session.flush()

    updated = await engine.update_template_set(
        db=db_session,
        set_id=ts.id,
        template_codes=["A1-1", "B1-1"],
        description="已更新",
    )
    await db_session.commit()

    assert updated.template_codes == ["A1-1", "B1-1"]
    assert updated.description == "已更新"


@pytest.mark.asyncio
async def test_get_template_set(db_session):
    """6.4: get single template set"""
    engine = TemplateEngine()
    ts = await engine.create_template_set(
        db=db_session, set_name="查询测试集",
    )
    await db_session.commit()

    fetched = await engine.get_template_set(db=db_session, set_id=ts.id)
    assert fetched is not None
    assert fetched.set_name == "查询测试集"


# ===== generate_project_workpapers Tests =====


@pytest.mark.asyncio
async def test_generate_project_workpapers(db_session, seeded_db):
    """6.5: generate workpapers from template set"""
    engine = TemplateEngine()

    # Create templates first
    for code, name in [("T1", "模板1"), ("T2", "模板2"), ("T3", "模板3")]:
        await engine.upload_template(
            db=db_session, template_code=code, template_name=name,
            audit_cycle="测试循环",
        )
    await db_session.flush()

    # Create template set
    ts = await engine.create_template_set(
        db=db_session,
        set_name="生成测试集",
        template_codes=["T1", "T2", "T3"],
    )
    await db_session.flush()

    # Generate workpapers
    workpapers = await engine.generate_project_workpapers(
        db=db_session,
        project_id=FAKE_PROJECT_ID,
        template_set_id=ts.id,
        year=2025,
    )
    await db_session.commit()

    assert len(workpapers) == 3

    # Verify wp_index records
    import sqlalchemy as sa
    idx_result = await db_session.execute(
        sa.select(WpIndex).where(WpIndex.project_id == FAKE_PROJECT_ID)
    )
    indices = idx_result.scalars().all()
    wp_codes = {i.wp_code for i in indices}
    assert "T1" in wp_codes
    assert "T2" in wp_codes
    assert "T3" in wp_codes


@pytest.mark.asyncio
async def test_generate_workpapers_nonexistent_set(db_session, seeded_db):
    """6.5: generate with nonexistent template set raises error"""
    engine = TemplateEngine()
    with pytest.raises(ValueError, match="模板集不存在"):
        await engine.generate_project_workpapers(
            db=db_session,
            project_id=FAKE_PROJECT_ID,
            template_set_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_generate_workpapers_without_templates(db_session, seeded_db):
    """6.5: generate with codes that have no templates still creates records"""
    engine = TemplateEngine()
    ts = await engine.create_template_set(
        db=db_session,
        set_name="无模板集",
        template_codes=["X1", "X2"],
    )
    await db_session.flush()

    workpapers = await engine.generate_project_workpapers(
        db=db_session,
        project_id=FAKE_PROJECT_ID,
        template_set_id=ts.id,
    )
    await db_session.commit()

    assert len(workpapers) == 2
    # wp_name should fallback
    import sqlalchemy as sa
    idx_result = await db_session.execute(
        sa.select(WpIndex).where(
            WpIndex.project_id == FAKE_PROJECT_ID,
            WpIndex.wp_code == "X1",
        )
    )
    idx = idx_result.scalar_one()
    assert "底稿X1" in idx.wp_name


# ===== list_templates / get_template Tests =====


@pytest.mark.asyncio
async def test_list_templates(db_session):
    """list_templates returns all non-deleted templates"""
    engine = TemplateEngine()
    await engine.upload_template(
        db=db_session, template_code="L1", template_name="列表测试1",
        audit_cycle="货币资金",
    )
    await engine.upload_template(
        db=db_session, template_code="L2", template_name="列表测试2",
        audit_cycle="应收账款",
    )
    await db_session.commit()

    all_tpls = await engine.list_templates(db=db_session)
    assert len(all_tpls) >= 2

    filtered = await engine.list_templates(db=db_session, audit_cycle="货币资金")
    assert all(t.audit_cycle == "货币资金" for t in filtered)


@pytest.mark.asyncio
async def test_get_template_latest(db_session):
    """get_template returns latest version by default"""
    engine = TemplateEngine()
    await engine.upload_template(
        db=db_session, template_code="VER-1", template_name="版本测试",
    )
    await db_session.flush()
    await engine.create_version(db=db_session, template_code="VER-1", change_type="minor")
    await db_session.commit()

    tpl = await engine.get_template(db=db_session, template_code="VER-1")
    assert tpl is not None
    assert tpl.version_minor == 1


# ===== API Route Tests =====


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, seeded_db):
    """Create test HTTP client"""
    from app.core.database import get_db
    from app.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_upload_template(client: AsyncClient):
    """POST /api/templates"""
    resp = await client.post(
        "/api/templates",
        json={
            "template_code": "API-1",
            "template_name": "API测试模板",
            "audit_cycle": "货币资金",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["template_code"] == "API-1"


@pytest.mark.asyncio
async def test_api_list_templates(client: AsyncClient):
    """GET /api/templates"""
    # Upload one first
    await client.post(
        "/api/templates",
        json={"template_code": "LIST-1", "template_name": "列表API测试"},
    )
    resp = await client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("data", data)
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_api_get_template(client: AsyncClient):
    """GET /api/templates/{code}"""
    await client.post(
        "/api/templates",
        json={"template_code": "GET-1", "template_name": "详情API测试"},
    )
    resp = await client.get("/api/templates/GET-1")
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["template_code"] == "GET-1"


@pytest.mark.asyncio
async def test_api_get_template_not_found(client: AsyncClient):
    """GET /api/templates/{code} — 404"""
    resp = await client.get("/api/templates/NONEXIST")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_create_version(client: AsyncClient):
    """POST /api/templates/{code}/versions"""
    await client.post(
        "/api/templates",
        json={"template_code": "VER-API", "template_name": "版本API测试"},
    )
    resp = await client.post(
        "/api/templates/VER-API/versions",
        json={"change_type": "minor"},
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["version_minor"] == 1


@pytest.mark.asyncio
async def test_api_delete_template(client: AsyncClient):
    """DELETE /api/templates/{id}"""
    resp = await client.post(
        "/api/templates",
        json={"template_code": "DEL-API", "template_name": "删除API测试"},
    )
    data = resp.json()
    result = data.get("data", data)
    template_id = result["id"]

    resp = await client.delete(f"/api/templates/{template_id}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_seed_template_sets(client: AsyncClient):
    """POST /api/template-sets/seed"""
    resp = await client.post("/api/template-sets/seed")
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["count"] == 6


@pytest.mark.asyncio
async def test_api_list_template_sets(client: AsyncClient):
    """GET /api/template-sets"""
    await client.post("/api/template-sets/seed")
    resp = await client.get("/api/template-sets")
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("data", data)
    assert len(results) >= 6


@pytest.mark.asyncio
async def test_api_create_template_set(client: AsyncClient):
    """POST /api/template-sets"""
    resp = await client.post(
        "/api/template-sets",
        json={
            "set_name": "API自定义集",
            "template_codes": ["A1", "B1"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["set_name"] == "API自定义集"


@pytest.mark.asyncio
async def test_api_generate_workpapers(client: AsyncClient):
    """POST /api/projects/{id}/working-papers/generate"""
    # Create template set
    resp = await client.post(
        "/api/template-sets",
        json={
            "set_name": "生成API测试集",
            "template_codes": ["GEN-1", "GEN-2"],
        },
    )
    data = resp.json()
    result = data.get("data", data)
    set_id = result["id"]

    resp = await client.post(
        f"/api/projects/{FAKE_PROJECT_ID}/working-papers/generate",
        json={"template_set_id": set_id, "year": 2025},
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["count"] == 2
