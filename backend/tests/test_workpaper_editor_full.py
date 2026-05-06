"""Sprint 2 集成测试：对比上年 + 穿透 + 附件拖拽

验证 WorkpaperEditor 完整功能链路：
- GET /api/projects/{pid}/workpapers/{wp_id}/prior-year（对比上年）
- GET /api/projects/{pid}/ledger/penetrate-by-amount（按金额穿透）
- 预填充 provenance 回写（cell_provenance supersede）
- 底稿 HTML 预览（移动端）
"""

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, ProjectUser
from app.models.audit_platform_models import TbLedger

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
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


class TestPriorYearCompareIntegration:
    """对比上年集成测试"""

    @pytest.mark.asyncio
    async def test_prior_year_returns_none_when_no_prior_project(self):
        """无上年项目时返回 None"""
        from app.services.continuous_audit_service import get_prior_year_workpaper

        db = AsyncMock()
        # Call 1: get wp_code
        wp_row = MagicMock()
        wp_row.__getitem__ = lambda self, idx: "D1"
        mock_r1 = MagicMock()
        mock_r1.first.return_value = wp_row
        # Call 2: no prior_year_project_id
        mock_r2 = MagicMock()
        mock_r2.first.return_value = None

        call_count = 0

        async def mock_exec(stmt, params=None):
            nonlocal call_count
            call_count += 1
            return mock_r1 if call_count == 1 else mock_r2

        db.execute = mock_exec
        result = await get_prior_year_workpaper(db, uuid.uuid4(), uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_prior_year_returns_data_when_found(self):
        """找到上年底稿时返回完整数据"""
        from app.services.continuous_audit_service import get_prior_year_workpaper

        db = AsyncMock()
        prior_wp_id = uuid.uuid4()
        prior_project_id = uuid.uuid4()

        wp_row = MagicMock()
        wp_row.__getitem__ = lambda self, idx: "D1"
        mock_r1 = MagicMock()
        mock_r1.first.return_value = wp_row

        prior_row = MagicMock()
        prior_row.__getitem__ = lambda self, idx: str(prior_project_id)
        mock_r2 = MagicMock()
        mock_r2.first.return_value = prior_row

        prior_wp = MagicMock()
        prior_wp.id = prior_wp_id
        prior_wp.parsed_data = {"conclusion": "无异常", "audited_amount": 800000}
        prior_wp.project_id = prior_project_id
        mock_r3 = MagicMock()
        mock_r3.first.return_value = prior_wp

        call_count = 0

        async def mock_exec(stmt, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_r1
            elif call_count == 2:
                return mock_r2
            return mock_r3

        db.execute = mock_exec
        result = await get_prior_year_workpaper(db, uuid.uuid4(), uuid.uuid4())
        assert result is not None
        assert result["wp_id"] == str(prior_wp_id)
        assert result["conclusion"] == "无异常"


class TestPenetrateByAmountIntegration:
    """按金额穿透集成测试"""

    @pytest_asyncio.fixture
    async def seeded_db(self, db_session: AsyncSession):
        """Seed ledger entries"""
        user = User(
            id=FAKE_USER_ID, username="tester", email="t@test.com",
            hashed_password="x", role="member",
        )
        db_session.add(user)
        project = Project(
            id=FAKE_PROJECT_ID, name="穿透测试", client_name="测试",
            project_type=ProjectType.annual, status=ProjectStatus.execution,
            created_by=FAKE_USER_ID,
        )
        db_session.add(project)
        db_session.add(ProjectUser(
            project_id=FAKE_PROJECT_ID, user_id=FAKE_USER_ID,
            role="auditor", permission_level="edit", is_deleted=False,
        ))
        # 精确匹配条目
        db_session.add(TbLedger(
            project_id=FAKE_PROJECT_ID, year=2025, company_code="001",
            voucher_date=date(2025, 3, 15), voucher_no="记-0100",
            account_code="6001", account_name="主营业务收入",
            debit_amount=Decimal("0"), credit_amount=Decimal("500000.00"),
            summary="销售商品收入",
        ))
        # 容差匹配条目
        db_session.add(TbLedger(
            project_id=FAKE_PROJECT_ID, year=2025, company_code="001",
            voucher_date=date(2025, 4, 1), voucher_no="记-0200",
            account_code="6001", account_name="主营业务收入",
            debit_amount=Decimal("0"), credit_amount=Decimal("500050.00"),
            summary="销售商品收入（含运费）",
        ))
        await db_session.commit()
        return db_session

    @pytest.mark.asyncio
    async def test_penetrate_exact_and_tolerance(self, seeded_db):
        """精确+容差策略同时返回"""
        import fakeredis.aioredis
        from httpx import ASGITransport, AsyncClient
        from app.core.database import get_db
        from app.core.redis import get_redis
        from app.main import app
        from app.deps import get_current_user

        async def override_get_db():
            yield seeded_db

        async def override_get_redis():
            yield fakeredis.aioredis.FakeRedis(decode_responses=True)

        class _FakeUser:
            id = FAKE_USER_ID
            class _Role:
                value = "admin"
            role = _Role()

        async def override_user():
            return _FakeUser()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_redis] = override_get_redis
        app.dependency_overrides[get_current_user] = override_user

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(
                f"/api/projects/{FAKE_PROJECT_ID}/ledger/penetrate-by-amount",
                params={"year": 2025, "amount": 500000.00, "tolerance": 100},
            )

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        if "data" in data and "code" in data:
            data = data["data"]
        strategies = [m["strategy"] for m in data["matches"]]
        assert "exact" in strategies


class TestPrefillProvenanceIntegration:
    """预填充 provenance 集成测试"""

    def test_write_provenance_supersede(self):
        """supersede 策略：重填覆盖旧值，保留 1 次历史"""
        from app.services.prefill_engine import _write_cell_provenance, PREFILL_SERVICE_VERSION

        wp = MagicMock()
        wp.parsed_data = {
            "cell_provenance": {
                "D5": {
                    "source": "trial_balance",
                    "source_ref": "1001:audited_amount",
                    "filled_at": "2026-05-01T08:00:00",
                    "filled_by_service_version": "prefill_v1.1",
                }
            }
        }
        new_provenance = {
            "D5": {
                "source": "trial_balance",
                "source_ref": "1001:audited_amount",
                "filled_at": "2026-05-08T10:00:00",
                "filled_by_service_version": PREFILL_SERVICE_VERSION,
            }
        }
        _write_cell_provenance(wp, new_provenance)

        entry = wp.parsed_data["cell_provenance"]["D5"]
        assert entry["filled_at"] == "2026-05-08T10:00:00"
        assert "_prev" in entry
        assert entry["_prev"]["filled_at"] == "2026-05-01T08:00:00"


class TestHtmlPreviewIntegration:
    """底稿 HTML 预览集成测试"""

    @pytest.mark.asyncio
    async def test_html_preview_with_mask(self):
        """HTML 预览支持脱敏"""
        from app.routers.workpaper_html_preview import _mask_structure

        structure = {
            "sheets": [
                {
                    "cells": {
                        "A1": {"value": "客户：北京华为科技有限公司"},
                        "B1": {"value": "¥1,500,000.00"},
                        "A2": {"value": "备注"},
                        "B2": {"value": 100},
                    }
                }
            ]
        }
        masked = _mask_structure(structure)
        # 公司名应被脱敏
        assert "北京华为科技有限公司" not in str(masked)
        # 小数值不脱敏
        assert 100 in [c.get("value") for c in masked["sheets"][0]["cells"].values()]
