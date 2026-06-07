"""科目工作包摘要服务测试

覆盖:
- 2.1 Registry 读取服务（验证 service 包装）
- 2.2 wp_code 到 wp_id 解析
- 2.3 DTO 结构验证
- 2.4 Summary 聚合（sheet、程序状态、字段来源、stale）
- 2.5 API 端点（列表、详情、摘要）
- 2.6 D2 部分 sheet/schema 缺失时返回 missing 卡片但工作包仍可打开
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx
from httpx import ASGITransport

from app.services.account_package_registry_service import AccountPackageRegistryService
from app.services.account_package_summary_service import (
    AccountPackageSummaryDTO,
    AccountPackageSummaryService,
)


# ─── 2.1: Registry 读取服务 ─────────────────────────────────────────────────


class TestRegistryReadingService:
    """2.1 验证 summary service 正确包装 registry 读取"""

    def test_registry_loads_packages(self):
        """注册表能加载工作包列表"""
        registry = AccountPackageRegistryService()
        packages = registry.get_packages()
        assert len(packages) >= 2
        ids = [p["account_package_id"] for p in packages]
        assert "D1_notes_receivable" in ids
        assert "D2_accounts_receivable" in ids

    def test_registry_get_package_by_id(self):
        """按 ID 获取单个工作包"""
        registry = AccountPackageRegistryService()
        pkg = registry.get_package("D2_accounts_receivable")
        assert pkg is not None
        assert pkg["cycle"] == "D"
        assert pkg["account_code"] == "1122"

    def test_registry_get_packages_by_cycle(self):
        """按循环过滤"""
        registry = AccountPackageRegistryService()
        d_packages = registry.get_packages_by_cycle("D")
        assert len(d_packages) == 2
        assert all(p["cycle"] == "D" for p in d_packages)

    def test_registry_nonexistent_package_returns_none(self):
        """不存在的包返回 None"""
        registry = AccountPackageRegistryService()
        assert registry.get_package("NONEXISTENT") is None


# ─── 2.2: wp_code 到 wp_id 解析 ─────────────────────────────────────────────


class TestWpCodeResolution:
    """2.2 验证 wp_code → wp_id 解析"""

    @pytest.mark.asyncio
    async def test_resolve_wp_code_found(self):
        """wp_code 存在时返回对应 UUID"""
        expected_id = uuid.uuid4()
        project_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_id
        mock_db.execute.return_value = mock_result

        service = AccountPackageSummaryService(mock_db)
        result = await service.resolve_wp_code_to_id(project_id, "D2")
        assert result == expected_id

    @pytest.mark.asyncio
    async def test_resolve_wp_code_not_found(self):
        """wp_code 不存在时返回 None"""
        project_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = AccountPackageSummaryService(mock_db)
        result = await service.resolve_wp_code_to_id(project_id, "ZZZZ")
        assert result is None


# ─── 2.3: DTO 结构验证 ───────────────────────────────────────────────────────


class TestSummaryDTO:
    """2.3 验证 DTO 包含所有必要字段"""

    def test_dto_has_all_fields(self):
        """DTO 包含 registry_status, mapping_status, program_status_summary,
        external_cards, stale_summary, missing_sources"""
        dto = AccountPackageSummaryDTO(
            registry_status="loaded",
            mapping_status="confirmed_production",
        )
        assert dto.registry_status == "loaded"
        assert dto.mapping_status == "confirmed_production"
        assert "total" in dto.program_status_summary
        assert "completed" in dto.program_status_summary
        assert "pending" in dto.program_status_summary
        assert "not_applicable" in dto.program_status_summary
        assert isinstance(dto.external_cards, list)
        assert "has_stale" in dto.stale_summary
        assert "stale_items" in dto.stale_summary
        assert isinstance(dto.missing_sources, list)

    def test_dto_defaults(self):
        """DTO 默认值正确"""
        dto = AccountPackageSummaryDTO(
            registry_status="not_found",
            mapping_status="unknown",
        )
        assert dto.program_status_summary["total"] == 0
        assert dto.stale_summary["has_stale"] is False
        assert dto.missing_sources == []
        assert dto.external_cards == []


# ─── 2.4: 聚合逻辑 ──────────────────────────────────────────────────────────


class TestSummaryAggregation:
    """2.4 验证 summary 聚合 sheet、程序状态、字段来源、stale 状态"""

    @pytest.mark.asyncio
    async def test_aggregation_with_all_wp_codes_present(self):
        """所有 wp_code 都存在时，missing_sources 为空"""
        project_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        mock_db.execute.return_value = mock_result

        service = AccountPackageSummaryService(mock_db)
        dto = await service.get_summary(project_id, "D1_notes_receivable")

        assert dto.registry_status == "loaded"
        assert dto.mapping_status == "pending_inventory_reconciliation"
        # D1 has procedure sheets
        assert dto.program_status_summary["total"] > 0

    @pytest.mark.asyncio
    async def test_aggregation_external_cards(self):
        """外部卡片从注册表 external_cards 字段聚合"""
        project_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        mock_db.execute.return_value = mock_result

        service = AccountPackageSummaryService(mock_db)
        dto = await service.get_summary(project_id, "D2_accounts_receivable")

        card_types = [c["card_type"] for c in dto.external_cards]
        assert "confirmation_summary" in card_types
        assert "adjustment_impact" in card_types
        assert "note_disclosure" in card_types

    @pytest.mark.asyncio
    async def test_aggregation_nonexistent_package(self):
        """不存在的包返回 not_found status"""
        mock_db = AsyncMock()
        service = AccountPackageSummaryService(mock_db)
        dto = await service.get_summary(uuid.uuid4(), "NONEXISTENT")
        assert dto.registry_status == "not_found"
        assert dto.mapping_status == "unknown"

    @pytest.mark.asyncio
    async def test_stale_summary_placeholder(self):
        """stale_summary 当前为 placeholder（无 stale）"""
        project_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        mock_db.execute.return_value = mock_result

        service = AccountPackageSummaryService(mock_db)
        dto = await service.get_summary(project_id, "D1_notes_receivable")

        assert dto.stale_summary["has_stale"] is False
        assert dto.stale_summary["stale_items"] == []


# ─── 2.5: API 端点测试 ───────────────────────────────────────────────────────


class TestAccountPackageAPI:
    """2.5 验证 API 端点"""

    @pytest.fixture
    def project_id(self):
        return str(uuid.uuid4())

    @pytest.fixture
    def mock_user(self):
        """Mock authenticated user"""
        user = MagicMock()
        user.id = uuid.uuid4()
        return user

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        db.execute.return_value = mock_result
        return db

    @pytest.fixture
    def app(self, mock_user, mock_db):
        """Create test app with dependency overrides"""
        from fastapi import FastAPI
        from app.routers.account_packages import router
        from app.core.database import get_db
        from app.deps import get_current_user

        app = FastAPI()
        app.include_router(router)

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: mock_db

        return app

    @pytest.mark.asyncio
    async def test_list_packages(self, app, project_id):
        """GET /projects/{id}/account-packages 返回工作包列表"""
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(f"/projects/{project_id}/account-packages")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 2
        # Check structure
        item = data[0]
        assert "account_package_id" in item
        assert "cycle" in item
        assert "sheet_count" in item

    @pytest.mark.asyncio
    async def test_list_packages_filter_by_cycle(self, app, project_id):
        """GET /projects/{id}/account-packages?cycle=D 只返回 D 循环"""
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/projects/{project_id}/account-packages?cycle=D"
            )

        assert resp.status_code == 200
        data = resp.json()
        assert all(item["cycle"] == "D" for item in data)

    @pytest.mark.asyncio
    async def test_get_package_detail(self, app, project_id):
        """GET /projects/{id}/account-packages/{pkg_id} 返回详情"""
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/projects/{project_id}/account-packages/D2_accounts_receivable"
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["account_package_id"] == "D2_accounts_receivable"
        assert data["account_code"] == "1122"
        assert "sheets" in data
        assert len(data["sheets"]) > 0

    @pytest.mark.asyncio
    async def test_get_package_detail_not_found(self, app, project_id):
        """GET 不存在的包返回 404"""
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/projects/{project_id}/account-packages/NONEXISTENT"
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_summary(self, app, project_id):
        """GET /projects/{id}/account-packages/{pkg_id}/summary 返回摘要"""
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/projects/{project_id}/account-packages/D1_notes_receivable/summary"
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["registry_status"] == "loaded"
        assert data["mapping_status"] == "pending_inventory_reconciliation"
        assert "program_status_summary" in data
        assert "external_cards" in data
        assert "stale_summary" in data
        assert "missing_sources" in data


# ─── 2.6: D2 缺失 sheet/schema 时仍可打开 ────────────────────────────────────


class TestMissingSheetsStillOpenable:
    """2.6 D2 部分 sheet 或 schema 缺失时，summary 返回 missing 卡片但工作包仍可打开"""

    @pytest.mark.asyncio
    async def test_missing_wp_code_returns_missing_source(self):
        """wp_code 在 wp_index 中不存在时，missing_sources 包含该项"""
        project_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        # All wp_code lookups return None (not found)
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = AccountPackageSummaryService(mock_db)
        dto = await service.get_summary(project_id, "D2_accounts_receivable")

        # Should still return loaded (registry itself is fine)
        assert dto.registry_status == "loaded"
        # Should have missing sources
        assert len(dto.missing_sources) > 0
        # Check reasons
        reasons = [m["reason"] for m in dto.missing_sources]
        assert "wp_index_not_found" in reasons

    @pytest.mark.asyncio
    async def test_missing_schema_returns_missing_source(self):
        """schema 文件不存在时，missing_sources 包含该项"""
        project_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        mock_db.execute.return_value = mock_result

        service = AccountPackageSummaryService(mock_db)

        # Patch Path.exists to return False for schema files
        with patch("app.services.account_package_summary_service.Path.exists", return_value=False):
            # We need a more targeted patch
            pass

        # Use a targeted approach: mock _PRODUCTION_SCHEMA_DIR
        with patch(
            "app.services.account_package_summary_service._PRODUCTION_SCHEMA_DIR",
            MagicMock(),
        ) as mock_dir:
            # Make __truediv__ (/) return a path-like object whose .exists() = False
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            dto = await service.get_summary(project_id, "D2_accounts_receivable")

        # D2 has schema_refs in sheets (D2A.yaml, D-D2-8.yaml, etc.)
        schema_missing = [
            m for m in dto.missing_sources if m["reason"] == "schema_file_not_found"
        ]
        assert len(schema_missing) > 0

    @pytest.mark.asyncio
    async def test_package_still_openable_with_missing(self):
        """即使有 missing_sources，registry_status 仍为 loaded（不是 404）"""
        project_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = AccountPackageSummaryService(mock_db)
        dto = await service.get_summary(project_id, "D2_accounts_receivable")

        # Package is openable (not 404, not invalid)
        assert dto.registry_status == "loaded"
        # Has missing but that's informational
        assert len(dto.missing_sources) > 0
        # mapping_status still computed correctly
        assert dto.mapping_status == "pending_inventory_reconciliation"

    @pytest.mark.asyncio
    async def test_api_returns_200_with_missing_sources(self):
        """API 端点在有 missing_sources 时仍返回 200"""
        from fastapi import FastAPI
        from app.routers.account_packages import router
        from app.core.database import get_db
        from app.deps import get_current_user

        app = FastAPI()
        app.include_router(router)

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: mock_db

        project_id = str(uuid.uuid4())
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/projects/{project_id}/account-packages/D2_accounts_receivable/summary"
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["registry_status"] == "loaded"
        assert len(data["missing_sources"]) > 0
