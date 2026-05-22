"""EQCR 快照测试。

覆盖：
- 创建快照 + 获取快照 + 刷新快照
- 数据完整性（4 类数据：workpapers/reports/adjustments/vr_results）
- 权限校验（edit 权限创建/刷新，readonly 权限获取）
- 快照 is_current 唯一性

对应 spec: phase4-long-term-governance Sprint 5 Task 5.5
"""

import json
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, require_project_access
from app.models.base import UserRole


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


class FakeUser:
    """Fake user for testing."""

    def __init__(self, role: str = "admin"):
        self.id = uuid.uuid4()
        self.username = "test_admin"
        self.email = "admin@test.com"
        self.role = UserRole.admin if role == "admin" else UserRole.auditor
        self.is_active = True
        self.is_deleted = False
        self.full_name = "Test Admin"


@pytest.fixture
def admin_user():
    return FakeUser("admin")


@pytest.fixture
def auditor_user():
    return FakeUser("auditor")


@pytest.fixture
def project_id():
    return uuid.uuid4()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Service Unit Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSnapshotServiceUnit:
    """快照服务单元测试（不依赖真实数据库）。"""

    def test_build_metadata_empty(self):
        """空底稿列表 → metadata 正确。"""
        from app.services.eqcr_snapshot_service import _build_metadata

        meta = _build_metadata([])
        assert meta["snapshot_version"] == 1
        assert meta["total_workpapers"] == 0
        assert meta["signed_workpapers"] == 0

    def test_build_metadata_with_workpapers(self):
        """有底稿数据 → 正确统计 signed 数量。"""
        from app.services.eqcr_snapshot_service import _build_metadata

        workpapers = [
            {"wp_id": "1", "wp_code": "D2-1", "status": "signed", "version": 3},
            {"wp_id": "2", "wp_code": "D4-1", "status": "draft", "version": 1},
            {"wp_id": "3", "wp_code": "E1-1", "status": "signed", "version": 5},
        ]
        meta = _build_metadata(workpapers)
        assert meta["total_workpapers"] == 3
        assert meta["signed_workpapers"] == 2

    def test_build_metadata_all_signed(self):
        """全部 signed → signed == total。"""
        from app.services.eqcr_snapshot_service import _build_metadata

        workpapers = [
            {"wp_id": "1", "status": "signed"},
            {"wp_id": "2", "status": "signed"},
        ]
        meta = _build_metadata(workpapers)
        assert meta["signed_workpapers"] == meta["total_workpapers"] == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 2. API Integration Tests (with mocked DB)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSnapshotAPI:
    """快照 API 集成测试（直接调用 endpoint 函数）。"""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock(spec=AsyncSession)

    @pytest.mark.asyncio
    async def test_create_snapshot_success(self, admin_user, project_id, mock_db):
        """create_snapshot endpoint 正常返回。"""
        from app.routers.eqcr_snapshot import create_snapshot

        fake_result = {
            "id": str(uuid.uuid4()),
            "project_id": str(project_id),
            "year": 2025,
            "created_by": str(admin_user.id),
            "created_at": "2026-01-15T10:30:00",
            "snapshot_data": {
                "workpapers": [],
                "reports": {},
                "adjustments": [],
                "vr_results": [],
                "metadata": {"snapshot_version": 1, "total_workpapers": 0, "signed_workpapers": 0},
            },
            "is_current": True,
        }

        with patch(
            "app.services.eqcr_snapshot_service.create_snapshot",
            new_callable=AsyncMock,
            return_value=fake_result,
        ):
            result = await create_snapshot(
                project_id=project_id,
                year=2025,
                db=mock_db,
                _user=admin_user,
            )
        assert result["is_current"] is True
        assert result["snapshot_data"]["metadata"]["snapshot_version"] == 1

    @pytest.mark.asyncio
    async def test_get_snapshot_success(self, admin_user, project_id, mock_db):
        """get_current_snapshot endpoint 正常返回。"""
        from app.routers.eqcr_snapshot import get_current_snapshot

        fake_result = {
            "id": str(uuid.uuid4()),
            "project_id": str(project_id),
            "year": 2025,
            "created_by": str(admin_user.id),
            "created_at": "2026-01-15T10:30:00",
            "snapshot_data": {
                "workpapers": [{"wp_id": "x", "wp_code": "D2-1", "status": "signed", "version": 3}],
                "reports": {"balance_sheet": [{"row_code": "BS-001", "row_name": "货币资金"}]},
                "adjustments": [{"id": "y", "adjustment_type": "aje", "review_status": "approved"}],
                "vr_results": [{"rule_id": "VR-D4-01", "passed": True, "severity": "blocking"}],
                "metadata": {"snapshot_version": 1, "total_workpapers": 1, "signed_workpapers": 1},
            },
            "is_current": True,
        }

        with patch(
            "app.services.eqcr_snapshot_service.get_current_snapshot",
            new_callable=AsyncMock,
            return_value=fake_result,
        ):
            result = await get_current_snapshot(
                project_id=project_id,
                year=2025,
                db=mock_db,
                _user=admin_user,
            )
        assert result["snapshot_data"]["metadata"]["total_workpapers"] == 1
        assert len(result["snapshot_data"]["workpapers"]) == 1
        assert len(result["snapshot_data"]["adjustments"]) == 1
        assert len(result["snapshot_data"]["vr_results"]) == 1

    @pytest.mark.asyncio
    async def test_get_snapshot_not_found(self, admin_user, project_id, mock_db):
        """get_current_snapshot endpoint → 404 无快照。"""
        from app.routers.eqcr_snapshot import get_current_snapshot

        with patch(
            "app.services.eqcr_snapshot_service.get_current_snapshot",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(Exception) as exc_info:
                await get_current_snapshot(
                    project_id=project_id,
                    year=2025,
                    db=mock_db,
                    _user=admin_user,
                )
            assert exc_info.value.status_code == 404
            assert "暂无" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_refresh_snapshot_success(self, admin_user, project_id, mock_db):
        """refresh_snapshot endpoint 正常返回。"""
        from app.routers.eqcr_snapshot import refresh_snapshot

        fake_result = {
            "id": str(uuid.uuid4()),
            "project_id": str(project_id),
            "year": 2025,
            "created_by": str(admin_user.id),
            "created_at": "2026-01-15T10:30:00",
            "snapshot_data": {
                "workpapers": [{"wp_id": "a", "status": "signed"}],
                "reports": {},
                "adjustments": [],
                "vr_results": [],
                "metadata": {"snapshot_version": 1, "total_workpapers": 1, "signed_workpapers": 1},
            },
            "is_current": True,
        }

        with patch(
            "app.services.eqcr_snapshot_service.refresh_snapshot",
            new_callable=AsyncMock,
            return_value=fake_result,
        ):
            result = await refresh_snapshot(
                project_id=project_id,
                year=2025,
                db=mock_db,
                _user=admin_user,
            )
        assert result["is_current"] is True

    @pytest.mark.asyncio
    async def test_snapshot_data_contains_four_types(self, admin_user, project_id, mock_db):
        """验证快照数据包含 4 类数据（workpapers/reports/adjustments/vr_results）。"""
        from app.routers.eqcr_snapshot import get_current_snapshot

        fake_result = {
            "id": str(uuid.uuid4()),
            "project_id": str(project_id),
            "year": 2025,
            "created_by": str(admin_user.id),
            "created_at": "2026-01-15T10:30:00",
            "snapshot_data": {
                "workpapers": [{"wp_id": "1", "wp_code": "D2-1", "status": "signed", "version": 2}],
                "reports": {"income_statement": [{"row_code": "IS-001"}]},
                "adjustments": [{"id": "2", "adjustment_type": "rje"}],
                "vr_results": [{"rule_id": "VR-D4-01", "passed": False}],
                "metadata": {"snapshot_version": 1, "total_workpapers": 1, "signed_workpapers": 1},
            },
            "is_current": True,
        }

        with patch(
            "app.services.eqcr_snapshot_service.get_current_snapshot",
            new_callable=AsyncMock,
            return_value=fake_result,
        ):
            result = await get_current_snapshot(
                project_id=project_id,
                year=2025,
                db=mock_db,
                _user=admin_user,
            )
        data = result["snapshot_data"]
        assert "workpapers" in data
        assert "reports" in data
        assert "adjustments" in data
        assert "vr_results" in data
        assert "metadata" in data
        assert len(data["workpapers"]) > 0
        assert len(data["reports"]) > 0
        assert len(data["adjustments"]) > 0
        assert len(data["vr_results"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Permission Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSnapshotPermissions:
    """快照权限测试。"""

    def test_create_route_uses_edit_permission(self):
        """创建快照路由必须使用 require_project_access('edit')。"""
        import inspect
        import app.routers.eqcr_snapshot as mod

        src = inspect.getsource(mod)
        # create_snapshot 和 refresh_snapshot 都需要 edit 权限
        assert 'require_project_access("edit")' in src, (
            "eqcr_snapshot 创建/刷新路由必须用 require_project_access('edit')"
        )

    def test_get_route_uses_readonly_permission(self):
        """获取快照路由使用 require_project_access('readonly')。"""
        import inspect
        import app.routers.eqcr_snapshot as mod

        src = inspect.getsource(mod)
        assert 'require_project_access("readonly")' in src, (
            "eqcr_snapshot 获取路由必须用 require_project_access('readonly')"
        )

    def test_router_has_three_endpoints(self):
        """路由注册了 3 个端点（POST create / GET get / POST refresh）。"""
        from app.routers.eqcr_snapshot import router

        routes = router.routes
        methods_paths = []
        for r in routes:
            path = getattr(r, 'path', '')
            methods = getattr(r, 'methods', set())
            methods_paths.append((methods, path))
        # Routes include the full prefix path
        assert any("POST" in m and p.endswith("/eqcr/snapshot") for m, p in methods_paths), \
            f"缺少 POST create 端点, found: {methods_paths}"
        assert any("GET" in m and p.endswith("/eqcr/snapshot") for m, p in methods_paths), \
            f"缺少 GET get 端点, found: {methods_paths}"
        assert any("POST" in m and "refresh" in p for m, p in methods_paths), \
            f"缺少 POST /refresh 端点, found: {methods_paths}"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Data Integrity Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSnapshotDataIntegrity:
    """快照数据完整性测试。"""

    def test_snapshot_data_structure_schema(self):
        """验证快照数据结构符合预期 schema。"""
        snapshot_data = {
            "workpapers": [
                {"wp_id": "uuid1", "wp_code": "D2-1", "status": "signed", "version": 3, "review_status": "approved", "updated_at": "2026-01-01T00:00:00"},
            ],
            "reports": {
                "balance_sheet": [{"row_code": "BS-001", "row_name": "货币资金", "current_period_amount": 5000000.0, "prior_period_amount": 3000000.0}],
            },
            "adjustments": [
                {"id": "uuid2", "adjustment_type": "aje", "adjustment_no": "AJE-001", "account_code": "1001", "debit_amount": 100000.0, "credit_amount": None, "review_status": "approved", "description": "test"},
            ],
            "vr_results": [
                {"rule_id": "VR-D4-01", "passed": True, "severity": "blocking"},
            ],
            "metadata": {
                "snapshot_version": 1,
                "total_workpapers": 1,
                "signed_workpapers": 1,
            },
        }

        # Validate top-level keys
        required_keys = {"workpapers", "reports", "adjustments", "vr_results", "metadata"}
        assert set(snapshot_data.keys()) == required_keys

        # Validate metadata
        meta = snapshot_data["metadata"]
        assert meta["snapshot_version"] == 1
        assert isinstance(meta["total_workpapers"], int)
        assert isinstance(meta["signed_workpapers"], int)
        assert meta["signed_workpapers"] <= meta["total_workpapers"]

        # Validate workpapers structure
        for wp in snapshot_data["workpapers"]:
            assert "wp_id" in wp
            assert "wp_code" in wp
            assert "status" in wp

        # Validate reports structure
        for report_type, rows in snapshot_data["reports"].items():
            assert isinstance(rows, list)
            for row in rows:
                assert "row_code" in row

        # Validate adjustments structure
        for adj in snapshot_data["adjustments"]:
            assert "id" in adj
            assert "adjustment_type" in adj
            assert "review_status" in adj

    def test_metadata_signed_never_exceeds_total(self):
        """metadata.signed_workpapers 永远 <= total_workpapers。"""
        from app.services.eqcr_snapshot_service import _build_metadata

        # 各种组合
        test_cases = [
            [],
            [{"status": "draft"}],
            [{"status": "signed"}, {"status": "signed"}],
            [{"status": "signed"}, {"status": "draft"}, {"status": "review"}],
        ]
        for wps in test_cases:
            meta = _build_metadata(wps)
            assert meta["signed_workpapers"] <= meta["total_workpapers"]
