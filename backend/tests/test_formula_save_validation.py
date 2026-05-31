"""P2-2: 地址有效性校验接入公式保存流

验证公式保存端点（report_config update / 公式管理保存）保存前调 validate_formula_refs，
含悬空引用拒绝保存 + 返校验错误。

Validates: Requirements 2.1, 2.2, 2.3
"""
from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.models.report_models import FinancialReportType, ReportConfig
from app.models.workpaper_models import WorkingPaper, WpFileStatus, WpSourceType

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()
FAKE_WP_ID = uuid.uuid4()
FAKE_WP_INDEX_ID = uuid.uuid4()


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
    """创建基础测试数据：用户、项目、底稿"""
    user = User(
        id=FAKE_USER_ID,
        username="test_formula_user",
        email="formula@example.com",
        hashed_password="hashed",
        role=UserRole.admin,
    )
    db_session.add(user)
    await db_session.flush()

    project = Project(
        id=FAKE_PROJECT_ID,
        name="公式校验测试项目",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
        audit_period_end=date(2025, 12, 31),
        template_type="soe",
    )
    db_session.add(project)
    await db_session.flush()

    # 创建 wp_index 记录（WorkingPaper 需要 wp_index_id 外键）
    from app.models.workpaper_models import WpIndex
    wp_index = WpIndex(
        id=FAKE_WP_INDEX_ID,
        project_id=FAKE_PROJECT_ID,
        wp_code="E1-1",
        wp_name="测试底稿",
        audit_cycle="E",
    )
    db_session.add(wp_index)
    await db_session.flush()

    wp = WorkingPaper(
        id=FAKE_WP_ID,
        project_id=FAKE_PROJECT_ID,
        wp_index_id=FAKE_WP_INDEX_ID,
        file_path="/test/path.xlsx",
        source_type=WpSourceType.template,
        status=WpFileStatus.draft,
        parsed_data={},
    )
    db_session.add(wp)
    await db_session.flush()

    # 创建一个 report_config 行（带 project 级 applicable_standard）
    rc = ReportConfig(
        id=uuid.uuid4(),
        report_type=FinancialReportType.balance_sheet,
        row_number=1,
        row_code="BS001",
        row_name="货币资金",
        formula="TB('1001','期末余额')",
        applicable_standard=f"project:{FAKE_PROJECT_ID}",
    )
    db_session.add(rc)
    await db_session.commit()
    return {"project_id": FAKE_PROJECT_ID, "wp_id": FAKE_WP_ID, "config_id": rc.id}


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, seeded_db):
    """创建测试 HTTP 客户端"""
    from app.main import app
    from tests._test_auth_helper import override_auth

    async with override_auth(app, db_session=db_session) as c:
        yield c


# ===== report_config update 端点校验测试 =====


@pytest.mark.asyncio
async def test_report_config_update_rejects_dangling_refs(client, seeded_db):
    """PUT /api/report-config/{id} 含悬空引用时返回 422"""
    config_id = str(seeded_db["config_id"])
    project_id = str(seeded_db["project_id"])

    # Mock validate_formula_refs 返回悬空引用
    mock_issues = [
        {"ref": "TB('9999','期末余额')", "uri": "tb://9999/期末余额", "status": "not_found",
         "message": "引用地址 tb://9999/期末余额 在当前项目中不存在"}
    ]
    with patch(
        "app.services.address_registry.AddressRegistryService.validate_formula_refs",
        new_callable=AsyncMock,
        return_value=mock_issues,
    ) as mock_validate:
        resp = await client.put(
            f"/api/report-config/{config_id}",
            json={
                "formula": "TB('9999','期末余额')",
                "project_id": project_id,
                "year": 2025,
                "template_type": "soe",
            },
        )
    assert resp.status_code == 422
    data = resp.json()
    # ResponseWrapperMiddleware 包装为 {"code": 422, "message": {...}}
    detail = data.get("message", data.get("detail", data))
    if isinstance(detail, str):
        assert "悬空引用" in detail or "DANGLING" in detail
    else:
        assert detail.get("error_code") == "FORMULA_DANGLING_REFS"
        assert len(detail.get("issues", [])) > 0
    mock_validate.assert_called_once()


@pytest.mark.asyncio
async def test_report_config_update_allows_valid_formula(client, seeded_db):
    """PUT /api/report-config/{id} 无悬空引用时正常保存"""
    config_id = str(seeded_db["config_id"])
    project_id = str(seeded_db["project_id"])

    # Mock validate_formula_refs 返回空列表（无问题）
    with patch(
        "app.services.address_registry.AddressRegistryService.validate_formula_refs",
        new_callable=AsyncMock,
        return_value=[],
    ):
        resp = await client.put(
            f"/api/report-config/{config_id}",
            json={
                "formula": "TB('1001','期末余额')",
                "project_id": project_id,
                "year": 2025,
                "template_type": "soe",
            },
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_report_config_update_skips_validation_without_project_context(client, seeded_db):
    """PUT /api/report-config/{id} 无 project_id+year 时跳过校验（降级兼容）"""
    config_id = str(seeded_db["config_id"])

    # 不传 project_id 和 year，但 applicable_standard 是 project:xxx 格式
    # 没有 year 所以跳过校验
    with patch(
        "app.services.address_registry.AddressRegistryService.validate_formula_refs",
        new_callable=AsyncMock,
        return_value=[{"ref": "x", "uri": "y", "status": "not_found", "message": "z"}],
    ) as mock_validate:
        resp = await client.put(
            f"/api/report-config/{config_id}",
            json={"formula": "TB('1001','期末余额')"},
        )
    # 没有 year 所以不调用校验，正常保存
    assert resp.status_code == 200
    mock_validate.assert_not_called()


# ===== wp_user_formulas update 端点校验测试 =====


@pytest.mark.asyncio
async def test_user_formulas_update_rejects_dangling_refs(client, seeded_db):
    """PUT /api/workpapers/{wp_id}/user-formulas 含悬空引用时返回 422"""
    wp_id = str(seeded_db["wp_id"])

    mock_issues = [
        {"ref": "TB('9999','期末余额')", "uri": "tb://9999/期末余额", "status": "not_found",
         "message": "引用地址 tb://9999/期末余额 在当前项目中不存在"}
    ]
    with patch(
        "app.services.address_registry.AddressRegistryService.validate_formula_refs",
        new_callable=AsyncMock,
        return_value=mock_issues,
    ):
        resp = await client.put(
            f"/api/workpapers/{wp_id}/user-formulas",
            json={"formulas": {"Sheet1!A1": "=TB('9999','期末余额')"}},
        )
    assert resp.status_code == 422
    data = resp.json()
    # ResponseWrapperMiddleware 包装为 {"code": 422, "message": {...}}
    detail = data.get("message", data.get("detail", data))
    if isinstance(detail, str):
        assert "悬空引用" in detail or "DANGLING" in detail
    else:
        assert detail.get("error_code") == "FORMULA_DANGLING_REFS"


@pytest.mark.asyncio
async def test_user_formulas_update_allows_valid_formula(client, seeded_db):
    """PUT /api/workpapers/{wp_id}/user-formulas 无悬空引用时正常保存"""
    wp_id = str(seeded_db["wp_id"])

    with patch(
        "app.services.address_registry.AddressRegistryService.validate_formula_refs",
        new_callable=AsyncMock,
        return_value=[],
    ):
        resp = await client.put(
            f"/api/workpapers/{wp_id}/user-formulas",
            json={"formulas": {"Sheet1!A1": "=TB('1001','期末余额')"}},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_user_formulas_delete_skips_validation(client, seeded_db):
    """PUT /api/workpapers/{wp_id}/user-formulas 空字符串（删除）不触发校验"""
    wp_id = str(seeded_db["wp_id"])

    with patch(
        "app.services.address_registry.AddressRegistryService.validate_formula_refs",
        new_callable=AsyncMock,
    ) as mock_validate:
        resp = await client.put(
            f"/api/workpapers/{wp_id}/user-formulas",
            json={"formulas": {"Sheet1!A1": ""}},
        )
    assert resp.status_code == 200
    mock_validate.assert_not_called()
