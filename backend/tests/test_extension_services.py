"""Tests for Phase 8 Extension Services (Tasks 3, 4, 5, 7, 13)

- AccountingStandardService: seed, list, get, switch project standard
- I18nService: languages, translations, audit terms, set user language
- AuditTypeService: list types, get recommendation
- SignService: sign level1/level2, verify, get signatures, revoke, level3 stub
- AIPluginService: register, list, get, enable, disable, update config, presets, seed

Also tests API endpoints for all 5 routers.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base, UserRole, ProjectStatus
from app.models.core import User, Project
from app.models.extension_models import AccountingStandard, SignatureRecord, AIPlugin

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
FAKE_PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


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
    """Create base test data: user + project"""
    user = User(
        id=FAKE_USER_ID, username="tester", email="t@t.com",
        hashed_password="x", role=UserRole.auditor,
    )
    db_session.add(user)
    project = Project(
        id=FAKE_PROJECT_ID, name="测试项目", client_name="测试客户",
        status=ProjectStatus.created,
    )
    db_session.add(project)
    await db_session.commit()
    return {"user_id": FAKE_USER_ID, "project_id": FAKE_PROJECT_ID}


# ═══════════════════════════════════════════════════════════════════════
# Task 3: AccountingStandardService Tests
# ═══════════════════════════════════════════════════════════════════════

class TestAccountingStandardService:

    @pytest.mark.asyncio
    async def test_seed_loading(self, db_session, seeded_db):
        from app.services.accounting_standard_service import AccountingStandardService
        svc = AccountingStandardService()
        result = await svc.load_seed_data(db_session)
        await db_session.commit()
        assert result["loaded"] == 5
        assert result["existing"] == 0

    @pytest.mark.asyncio
    async def test_seed_idempotent(self, db_session, seeded_db):
        from app.services.accounting_standard_service import AccountingStandardService
        svc = AccountingStandardService()
        await svc.load_seed_data(db_session)
        await db_session.commit()
        result2 = await svc.load_seed_data(db_session)
        assert result2["loaded"] == 0
        assert result2["existing"] == 5

    @pytest.mark.asyncio
    async def test_list_standards(self, db_session, seeded_db):
        from app.services.accounting_standard_service import AccountingStandardService
        svc = AccountingStandardService()
        await svc.load_seed_data(db_session)
        await db_session.commit()
        standards = await svc.list_standards(db_session)
        assert len(standards) == 5
        codes = [s["standard_code"] for s in standards]
        assert "CAS" in codes
        assert "IFRS" in codes

    @pytest.mark.asyncio
    async def test_get_standard(self, db_session, seeded_db):
        from app.services.accounting_standard_service import AccountingStandardService
        svc = AccountingStandardService()
        await svc.load_seed_data(db_session)
        await db_session.commit()
        standards = await svc.list_standards(db_session)
        detail = await svc.get_standard(db_session, uuid.UUID(standards[0]["id"]))
        assert detail is not None
        assert detail["standard_code"] == standards[0]["standard_code"]

    @pytest.mark.asyncio
    async def test_get_standard_not_found(self, db_session, seeded_db):
        from app.services.accounting_standard_service import AccountingStandardService
        svc = AccountingStandardService()
        result = await svc.get_standard(db_session, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_switch_project_standard(self, db_session, seeded_db):
        from app.services.accounting_standard_service import AccountingStandardService
        svc = AccountingStandardService()
        await svc.load_seed_data(db_session)
        await db_session.commit()
        standards = await svc.list_standards(db_session)
        std_id = uuid.UUID(standards[0]["id"])
        result = await svc.switch_project_standard(db_session, FAKE_PROJECT_ID, std_id)
        assert result["standard_id"] == str(std_id)
        assert result["warning"] is None  # first time, no warning

    @pytest.mark.asyncio
    async def test_switch_project_standard_warns_existing(self, db_session, seeded_db):
        from app.services.accounting_standard_service import AccountingStandardService
        svc = AccountingStandardService()
        await svc.load_seed_data(db_session)
        await db_session.commit()
        standards = await svc.list_standards(db_session)
        std_id_1 = uuid.UUID(standards[0]["id"])
        std_id_2 = uuid.UUID(standards[1]["id"])
        await svc.switch_project_standard(db_session, FAKE_PROJECT_ID, std_id_1)
        await db_session.flush()
        result = await svc.switch_project_standard(db_session, FAKE_PROJECT_ID, std_id_2)
        assert result["warning"] is not None

    @pytest.mark.asyncio
    async def test_switch_project_standard_invalid(self, db_session, seeded_db):
        from app.services.accounting_standard_service import AccountingStandardService
        svc = AccountingStandardService()
        with pytest.raises(ValueError, match="会计准则不存在"):
            await svc.switch_project_standard(db_session, FAKE_PROJECT_ID, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_switch_project_not_found(self, db_session, seeded_db):
        from app.services.accounting_standard_service import AccountingStandardService
        svc = AccountingStandardService()
        await svc.load_seed_data(db_session)
        await db_session.commit()
        standards = await svc.list_standards(db_session)
        with pytest.raises(ValueError, match="项目不存在"):
            await svc.switch_project_standard(
                db_session, uuid.uuid4(), uuid.UUID(standards[0]["id"])
            )


# ═══════════════════════════════════════════════════════════════════════
# Task 4: I18nService Tests
# ═══════════════════════════════════════════════════════════════════════

class TestI18nService:

    @pytest.mark.asyncio
    async def test_get_languages(self):
        from app.services.i18n_service import I18nService
        svc = I18nService()
        langs = svc.get_languages()
        assert len(langs) == 2
        codes = [l["code"] for l in langs]
        assert "zh-CN" in codes
        assert "en-US" in codes

    @pytest.mark.asyncio
    async def test_get_translations_zh(self):
        from app.services.i18n_service import I18nService
        svc = I18nService()
        t = svc.get_translations("zh-CN")
        assert t["app_title"] == "审计作业平台"
        assert "workpaper" in t

    @pytest.mark.asyncio
    async def test_get_translations_en(self):
        from app.services.i18n_service import I18nService
        svc = I18nService()
        t = svc.get_translations("en-US")
        assert t["app_title"] == "Audit Workbench"

    @pytest.mark.asyncio
    async def test_get_translations_invalid(self):
        from app.services.i18n_service import I18nService
        svc = I18nService()
        with pytest.raises(ValueError, match="不支持的语言"):
            svc.get_translations("fr-FR")

    @pytest.mark.asyncio
    async def test_get_audit_terms_zh(self):
        from app.services.i18n_service import I18nService
        svc = I18nService()
        terms = svc.get_audit_terms("zh-CN")
        assert terms["AJE"] == "审计调整分录"
        assert terms["RJE"] == "重分类分录"
        assert terms["TB"] == "试算表"
        assert terms["PBC"] == "客户提供资料清单"

    @pytest.mark.asyncio
    async def test_get_audit_terms_en(self):
        from app.services.i18n_service import I18nService
        svc = I18nService()
        terms = svc.get_audit_terms("en-US")
        assert terms["AJE"] == "Audit Adjustment Entry"
        assert terms["RJE"] == "Reclassification Entry"
        assert terms["TB"] == "Trial Balance"
        assert terms["PBC"] == "Prepared By Client"

    @pytest.mark.asyncio
    async def test_get_audit_terms_invalid(self):
        from app.services.i18n_service import I18nService
        svc = I18nService()
        with pytest.raises(ValueError, match="不支持的语言"):
            svc.get_audit_terms("ja-JP")

    @pytest.mark.asyncio
    async def test_set_user_language(self, db_session, seeded_db):
        from app.services.i18n_service import I18nService
        svc = I18nService()
        result = await svc.set_user_language(db_session, FAKE_USER_ID, "en-US")
        assert result["language"] == "en-US"

    @pytest.mark.asyncio
    async def test_set_user_language_invalid_lang(self, db_session, seeded_db):
        from app.services.i18n_service import I18nService
        svc = I18nService()
        with pytest.raises(ValueError, match="不支持的语言"):
            await svc.set_user_language(db_session, FAKE_USER_ID, "xx-XX")

    @pytest.mark.asyncio
    async def test_set_user_language_user_not_found(self, db_session, seeded_db):
        from app.services.i18n_service import I18nService
        svc = I18nService()
        with pytest.raises(ValueError, match="用户不存在"):
            await svc.set_user_language(db_session, uuid.uuid4(), "zh-CN")


# ═══════════════════════════════════════════════════════════════════════
# Task 5: AuditTypeService Tests
# ═══════════════════════════════════════════════════════════════════════

class TestAuditTypeService:

    @pytest.mark.asyncio
    async def test_get_audit_types(self):
        from app.services.audit_type_service import AuditTypeService
        svc = AuditTypeService()
        types = svc.get_audit_types()
        assert len(types) == 6
        type_keys = [t["type"] for t in types]
        assert "annual_financial" in type_keys
        assert "ipo" in type_keys
        assert "soe" in type_keys

    @pytest.mark.asyncio
    async def test_get_audit_types_have_descriptions(self):
        from app.services.audit_type_service import AuditTypeService
        svc = AuditTypeService()
        types = svc.get_audit_types()
        for t in types:
            assert "name" in t
            assert "description" in t
            assert "template_sets" in t

    @pytest.mark.asyncio
    async def test_get_recommendation_annual(self):
        from app.services.audit_type_service import AuditTypeService
        svc = AuditTypeService()
        rec = svc.get_type_recommendation("annual_financial")
        assert rec["template_set"] == "standard"
        assert len(rec["procedures"]) > 0
        assert len(rec["report_templates"]) > 0
        assert rec["name"] == "年度财务报表审计"

    @pytest.mark.asyncio
    async def test_get_recommendation_ipo(self):
        from app.services.audit_type_service import AuditTypeService
        svc = AuditTypeService()
        rec = svc.get_type_recommendation("ipo")
        assert rec["template_set"] == "ipo"

    @pytest.mark.asyncio
    async def test_get_recommendation_invalid(self):
        from app.services.audit_type_service import AuditTypeService
        svc = AuditTypeService()
        with pytest.raises(ValueError, match="未知的审计类型"):
            svc.get_type_recommendation("nonexistent")


# ═══════════════════════════════════════════════════════════════════════
# Task 7: SignService Tests
# ═══════════════════════════════════════════════════════════════════════

class TestSignService:

    @pytest.mark.asyncio
    async def test_sign_level1(self, db_session, seeded_db):
        from app.services.sign_service import SignService
        svc = SignService()
        obj_id = uuid.uuid4()
        result = await svc.sign_document(
            db_session, "working_paper", obj_id, FAKE_USER_ID,
            "level1", ip_address="192.168.1.1",
        )
        await db_session.commit()
        assert result["signature_level"] == "level1"
        assert result["ip_address"] == "192.168.1.1"
        assert result["signer_id"] == str(FAKE_USER_ID)
        assert result["signature_data"] is None

    @pytest.mark.asyncio
    async def test_sign_level2(self, db_session, seeded_db):
        from app.services.sign_service import SignService
        svc = SignService()
        obj_id = uuid.uuid4()
        sig_data = {"image": "base64encodeddata", "format": "png"}
        result = await svc.sign_document(
            db_session, "audit_report", obj_id, FAKE_USER_ID,
            "level2", signature_data=sig_data, ip_address="10.0.0.1",
        )
        await db_session.commit()
        assert result["signature_level"] == "level2"
        assert result["signature_data"]["image"] == "base64encodeddata"

    @pytest.mark.asyncio
    async def test_sign_level3_not_implemented(self, db_session, seeded_db):
        from app.services.sign_service import SignService
        svc = SignService()
        with pytest.raises(NotImplementedError, match="CA证书签名尚未实现"):
            await svc.sign_document(
                db_session, "working_paper", uuid.uuid4(), FAKE_USER_ID, "level3",
            )

    @pytest.mark.asyncio
    async def test_sign_invalid_level(self, db_session, seeded_db):
        from app.services.sign_service import SignService
        svc = SignService()
        with pytest.raises(ValueError, match="无效的签名级别"):
            await svc.sign_document(
                db_session, "working_paper", uuid.uuid4(), FAKE_USER_ID, "level99",
            )

    @pytest.mark.asyncio
    async def test_verify_level1(self, db_session, seeded_db):
        from app.services.sign_service import SignService
        svc = SignService()
        obj_id = uuid.uuid4()
        signed = await svc.sign_document(
            db_session, "working_paper", obj_id, FAKE_USER_ID, "level1",
        )
        await db_session.commit()
        verification = await svc.verify_signature(db_session, uuid.UUID(signed["id"]))
        assert verification["valid"] is True
        assert verification["level"] == "level1"

    @pytest.mark.asyncio
    async def test_verify_level2(self, db_session, seeded_db):
        from app.services.sign_service import SignService
        svc = SignService()
        signed = await svc.sign_document(
            db_session, "adjustment", uuid.uuid4(), FAKE_USER_ID,
            "level2", signature_data={"image": "data"},
        )
        await db_session.commit()
        verification = await svc.verify_signature(db_session, uuid.UUID(signed["id"]))
        assert verification["valid"] is True

    @pytest.mark.asyncio
    async def test_verify_not_found(self, db_session, seeded_db):
        from app.services.sign_service import SignService
        svc = SignService()
        with pytest.raises(ValueError, match="签名记录不存在"):
            await svc.verify_signature(db_session, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_signatures(self, db_session, seeded_db):
        from app.services.sign_service import SignService
        svc = SignService()
        obj_id = uuid.uuid4()
        await svc.sign_document(db_session, "working_paper", obj_id, FAKE_USER_ID, "level1")
        await svc.sign_document(db_session, "working_paper", obj_id, FAKE_USER_ID, "level2",
                                signature_data={"image": "x"})
        await db_session.commit()
        sigs = await svc.get_signatures(db_session, "working_paper", obj_id)
        assert len(sigs) == 2

    @pytest.mark.asyncio
    async def test_get_signatures_empty(self, db_session, seeded_db):
        from app.services.sign_service import SignService
        svc = SignService()
        sigs = await svc.get_signatures(db_session, "working_paper", uuid.uuid4())
        assert len(sigs) == 0

    @pytest.mark.asyncio
    async def test_revoke_signature(self, db_session, seeded_db):
        from app.services.sign_service import SignService
        svc = SignService()
        obj_id = uuid.uuid4()
        signed = await svc.sign_document(
            db_session, "working_paper", obj_id, FAKE_USER_ID, "level1",
        )
        await db_session.commit()
        revoke_result = await svc.revoke_signature(db_session, uuid.UUID(signed["id"]))
        assert revoke_result["revoked"] is True
        await db_session.commit()
        # After revoke, get_signatures should not return it
        sigs = await svc.get_signatures(db_session, "working_paper", obj_id)
        assert len(sigs) == 0

    @pytest.mark.asyncio
    async def test_revoke_not_found(self, db_session, seeded_db):
        from app.services.sign_service import SignService
        svc = SignService()
        with pytest.raises(ValueError, match="签名记录不存在"):
            await svc.revoke_signature(db_session, uuid.uuid4())


# ═══════════════════════════════════════════════════════════════════════
# Task 13: AIPluginService Tests
# ═══════════════════════════════════════════════════════════════════════

class TestAIPluginService:

    @pytest.mark.asyncio
    async def test_register_plugin(self, db_session, seeded_db):
        from app.services.ai_plugin_service import AIPluginService
        svc = AIPluginService()
        result = await svc.register_plugin(
            db_session, "test_plugin", "测试插件", "1.0.0",
            description="测试用插件", config={"key": "value"},
        )
        await db_session.commit()
        assert result["plugin_id"] == "test_plugin"
        assert result["plugin_name"] == "测试插件"
        assert result["is_enabled"] is False

    @pytest.mark.asyncio
    async def test_register_duplicate(self, db_session, seeded_db):
        from app.services.ai_plugin_service import AIPluginService
        svc = AIPluginService()
        await svc.register_plugin(db_session, "dup_plugin", "重复插件", "1.0.0")
        await db_session.commit()
        with pytest.raises(ValueError, match="已存在"):
            await svc.register_plugin(db_session, "dup_plugin", "重复插件2", "2.0.0")

    @pytest.mark.asyncio
    async def test_list_plugins(self, db_session, seeded_db):
        from app.services.ai_plugin_service import AIPluginService
        svc = AIPluginService()
        await svc.register_plugin(db_session, "p1", "插件1", "1.0")
        await svc.register_plugin(db_session, "p2", "插件2", "1.0")
        await db_session.commit()
        plugins = await svc.list_plugins(db_session)
        assert len(plugins) == 2

    @pytest.mark.asyncio
    async def test_get_plugin(self, db_session, seeded_db):
        from app.services.ai_plugin_service import AIPluginService
        svc = AIPluginService()
        await svc.register_plugin(db_session, "detail_test", "详情测试", "1.0")
        await db_session.commit()
        detail = await svc.get_plugin(db_session, "detail_test")
        assert detail is not None
        assert detail["plugin_name"] == "详情测试"

    @pytest.mark.asyncio
    async def test_get_plugin_not_found(self, db_session, seeded_db):
        from app.services.ai_plugin_service import AIPluginService
        svc = AIPluginService()
        result = await svc.get_plugin(db_session, "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_enable_plugin(self, db_session, seeded_db):
        from app.services.ai_plugin_service import AIPluginService
        svc = AIPluginService()
        await svc.register_plugin(db_session, "enable_test", "启用测试", "1.0")
        await db_session.commit()
        result = await svc.enable_plugin(db_session, "enable_test")
        assert result["is_enabled"] is True

    @pytest.mark.asyncio
    async def test_disable_plugin(self, db_session, seeded_db):
        from app.services.ai_plugin_service import AIPluginService
        svc = AIPluginService()
        await svc.register_plugin(db_session, "disable_test", "禁用测试", "1.0")
        await db_session.commit()
        await svc.enable_plugin(db_session, "disable_test")
        result = await svc.disable_plugin(db_session, "disable_test")
        assert result["is_enabled"] is False

    @pytest.mark.asyncio
    async def test_enable_not_found(self, db_session, seeded_db):
        from app.services.ai_plugin_service import AIPluginService
        svc = AIPluginService()
        with pytest.raises(ValueError, match="不存在"):
            await svc.enable_plugin(db_session, "ghost")

    @pytest.mark.asyncio
    async def test_update_config(self, db_session, seeded_db):
        from app.services.ai_plugin_service import AIPluginService
        svc = AIPluginService()
        await svc.register_plugin(db_session, "cfg_test", "配置测试", "1.0",
                                  config={"old": True})
        await db_session.commit()
        result = await svc.update_config(db_session, "cfg_test", {"new": True, "timeout": 60})
        assert result["config"]["new"] is True
        assert result["config"]["timeout"] == 60

    @pytest.mark.asyncio
    async def test_get_preset_plugins(self):
        from app.services.ai_plugin_service import AIPluginService
        svc = AIPluginService()
        presets = svc.get_preset_plugins()
        assert len(presets) == 8
        ids = [p["plugin_id"] for p in presets]
        assert "invoice_verify" in ids
        assert "bank_reconcile" in ids
        assert "team_chat" in ids

    @pytest.mark.asyncio
    async def test_load_preset_plugins(self, db_session, seeded_db):
        from app.services.ai_plugin_service import AIPluginService
        svc = AIPluginService()
        result = await svc.load_preset_plugins(db_session)
        await db_session.commit()
        assert result["loaded"] == 8
        assert result["skipped"] == 0

    @pytest.mark.asyncio
    async def test_load_preset_plugins_idempotent(self, db_session, seeded_db):
        from app.services.ai_plugin_service import AIPluginService
        svc = AIPluginService()
        await svc.load_preset_plugins(db_session)
        await db_session.commit()
        result2 = await svc.load_preset_plugins(db_session)
        assert result2["loaded"] == 0
        assert result2["skipped"] == 8


# ═══════════════════════════════════════════════════════════════════════
# API Endpoint Tests — shared client fixture
# ═══════════════════════════════════════════════════════════════════════

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


# ── Accounting Standards API ──

class TestAccountingStandardsAPI:

    @pytest.mark.asyncio
    async def test_seed_api(self, client):
        resp = await client.post("/api/accounting-standards/seed")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["loaded"] == 5

    @pytest.mark.asyncio
    async def test_list_api(self, client):
        await client.post("/api/accounting-standards/seed")
        resp = await client.get("/api/accounting-standards")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert len(data) == 5

    @pytest.mark.asyncio
    async def test_detail_api(self, client):
        await client.post("/api/accounting-standards/seed")
        list_resp = await client.get("/api/accounting-standards")
        items = list_resp.json().get("data", list_resp.json())
        std_id = items[0]["id"]
        resp = await client.get(f"/api/accounting-standards/{std_id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_detail_not_found(self, client):
        resp = await client.get(f"/api/accounting-standards/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_switch_standard_api(self, client):
        await client.post("/api/accounting-standards/seed")
        list_resp = await client.get("/api/accounting-standards")
        items = list_resp.json().get("data", list_resp.json())
        std_id = items[0]["id"]
        resp = await client.put(
            f"/api/projects/{FAKE_PROJECT_ID}/accounting-standard",
            json={"standard_id": std_id},
        )
        assert resp.status_code == 200


# ── I18n API ──

class TestI18nAPI:

    @pytest.mark.asyncio
    async def test_languages_api(self, client):
        resp = await client.get("/api/i18n/languages")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_translations_api(self, client):
        resp = await client.get("/api/i18n/translations/zh-CN")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_translations_invalid_api(self, client):
        resp = await client.get("/api/i18n/translations/xx-XX")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_audit_terms_api(self, client):
        resp = await client.get("/api/i18n/audit-terms/en-US")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["AJE"] == "Audit Adjustment Entry"

    @pytest.mark.asyncio
    async def test_set_language_api(self, client):
        resp = await client.put(
            f"/api/users/{FAKE_USER_ID}/language",
            json={"language": "en-US"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_set_language_invalid_api(self, client):
        resp = await client.put(
            f"/api/users/{FAKE_USER_ID}/language",
            json={"language": "xx-XX"},
        )
        assert resp.status_code == 400


# ── Audit Types API ──

class TestAuditTypesAPI:

    @pytest.mark.asyncio
    async def test_list_api(self, client):
        resp = await client.get("/api/audit-types")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert len(data) == 6

    @pytest.mark.asyncio
    async def test_recommendation_api(self, client):
        resp = await client.get("/api/audit-types/annual_financial/recommendation")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["template_set"] == "standard"

    @pytest.mark.asyncio
    async def test_recommendation_invalid_api(self, client):
        resp = await client.get("/api/audit-types/nonexistent/recommendation")
        assert resp.status_code == 400


# ── Signatures API ──

class TestSignaturesAPI:

    @pytest.mark.asyncio
    async def test_sign_api(self, client):
        resp = await client.post("/api/signatures/sign", json={
            "object_type": "working_paper",
            "object_id": str(uuid.uuid4()),
            "signer_id": str(FAKE_USER_ID),
            "signature_level": "level1",
            "ip_address": "127.0.0.1",
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_sign_level3_api(self, client):
        resp = await client.post("/api/signatures/sign", json={
            "object_type": "working_paper",
            "object_id": str(uuid.uuid4()),
            "signer_id": str(FAKE_USER_ID),
            "signature_level": "level3",
        })
        assert resp.status_code == 501

    @pytest.mark.asyncio
    async def test_get_signatures_api(self, client):
        obj_id = str(uuid.uuid4())
        await client.post("/api/signatures/sign", json={
            "object_type": "audit_report",
            "object_id": obj_id,
            "signer_id": str(FAKE_USER_ID),
            "signature_level": "level1",
        })
        resp = await client.get(f"/api/signatures/audit_report/{obj_id}")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert len(data) == 1

    @pytest.mark.asyncio
    async def test_verify_api(self, client):
        obj_id = str(uuid.uuid4())
        sign_resp = await client.post("/api/signatures/sign", json={
            "object_type": "working_paper",
            "object_id": obj_id,
            "signer_id": str(FAKE_USER_ID),
            "signature_level": "level1",
        })
        sig_id = sign_resp.json().get("data", sign_resp.json())["id"]
        resp = await client.post(f"/api/signatures/{sig_id}/verify")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_revoke_api(self, client):
        sign_resp = await client.post("/api/signatures/sign", json={
            "object_type": "working_paper",
            "object_id": str(uuid.uuid4()),
            "signer_id": str(FAKE_USER_ID),
            "signature_level": "level1",
        })
        sig_id = sign_resp.json().get("data", sign_resp.json())["id"]
        resp = await client.post(f"/api/signatures/{sig_id}/revoke")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_verify_not_found_api(self, client):
        resp = await client.post(f"/api/signatures/{uuid.uuid4()}/verify")
        assert resp.status_code == 404


# ── AI Plugins API ──

class TestAIPluginsAPI:

    @pytest.mark.asyncio
    async def test_register_api(self, client):
        resp = await client.post("/api/ai-plugins", json={
            "plugin_id": "api_test",
            "plugin_name": "API测试插件",
            "plugin_version": "1.0.0",
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_api(self, client):
        await client.post("/api/ai-plugins", json={
            "plugin_id": "list_test",
            "plugin_name": "列表测试",
            "plugin_version": "1.0",
        })
        resp = await client.get("/api/ai-plugins")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_detail_api(self, client):
        await client.post("/api/ai-plugins", json={
            "plugin_id": "detail_api",
            "plugin_name": "详情API",
            "plugin_version": "1.0",
        })
        resp = await client.get("/api/ai-plugins/detail_api")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_detail_not_found_api(self, client):
        resp = await client.get("/api/ai-plugins/nonexistent_xyz")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_enable_api(self, client):
        await client.post("/api/ai-plugins", json={
            "plugin_id": "enable_api",
            "plugin_name": "启用API",
            "plugin_version": "1.0",
        })
        resp = await client.post("/api/ai-plugins/enable_api/enable")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["is_enabled"] is True

    @pytest.mark.asyncio
    async def test_disable_api(self, client):
        await client.post("/api/ai-plugins", json={
            "plugin_id": "disable_api",
            "plugin_name": "禁用API",
            "plugin_version": "1.0",
        })
        await client.post("/api/ai-plugins/disable_api/enable")
        resp = await client.post("/api/ai-plugins/disable_api/disable")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["is_enabled"] is False

    @pytest.mark.asyncio
    async def test_update_config_api(self, client):
        await client.post("/api/ai-plugins", json={
            "plugin_id": "config_api",
            "plugin_name": "配置API",
            "plugin_version": "1.0",
        })
        resp = await client.put("/api/ai-plugins/config_api/config", json={
            "config": {"timeout": 120},
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_presets_api(self, client):
        resp = await client.get("/api/ai-plugins/presets")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert len(data) == 8

    @pytest.mark.asyncio
    async def test_seed_api(self, client):
        resp = await client.post("/api/ai-plugins/seed")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["loaded"] == 8

    @pytest.mark.asyncio
    async def test_seed_idempotent_api(self, client):
        await client.post("/api/ai-plugins/seed")
        resp = await client.post("/api/ai-plugins/seed")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["loaded"] == 0
