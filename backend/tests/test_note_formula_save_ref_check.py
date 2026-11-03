"""附注公式集保存前在服务端校验跨表引用（spec formula-fetch-followup-defect-closure R5.3）。

原先 ``PUT /api/disclosure-notes/{pid}/{year}/{section}/formulas`` 不校验引用：前端的校验又被 ACNR「写法能换算即存在」
短路，悬空引用照常入库，执行时取不到数也不报。现行：与报表 / 底稿公式保存同一 helper（``validate_refs_via_acnr``）、
同一 422 契约（``FORMULA_DANGLING_REFS``），每条问题带所在单元格；不写库。
SQLite 内存库 + 真 ORM + 真路由；编辑门禁 / Redis / EventBus 同 ``test_disclosure_note_edit_stamp`` 打桩。
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.core.database import get_db
from app.deps import check_consol_lock, get_current_user
from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectUserRole
from app.models.core import Project, ProjectUser, User
from app.models.report_models import DisclosureNote, ReportConfig
from app.models.staff_models import ProjectAssignment, StaffMember
from app.routers import disclosure_notes
from app.services.disclosure_mutation_coordinator import DisclosureMutationCoordinator
from app.services.formula_settings import note_settings
from tests.test_note_text_batch_endpoints import _Actor

YEAR = 2025
SECTION = "五、1"
TABLE = {"headers": ["项目", "期末余额", "期初余额"],
         "rows": [{"label": "库存现金", "values": [1, 2]}, {"label": "合计", "values": [1, 2], "is_total": True}]}


@pytest_asyncio.fixture
async def env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [User.__table__, Project.__table__, ProjectUser.__table__, StaffMember.__table__,
              ProjectAssignment.__table__, DisclosureNote.__table__, TrialBalance.__table__, ReportConfig.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    me, pid = uuid.uuid4(), uuid.uuid4()
    async with factory() as s:
        s.add(Project(id=pid, name="附注公式_2025", client_name="附注公式", template_type="soe", report_scope="standalone",
                      status=ProjectStatus.execution, audit_year=YEAR))
        await s.flush()
        s.add_all([
            ProjectUser(project_id=pid, user_id=me, role=ProjectUserRole.auditor, permission_level=PermissionLevel.edit),
            DisclosureNote(project_id=pid, year=YEAR, note_section=SECTION, section_title="货币资金", table_data=TABLE),
            TrialBalance(project_id=pid, year=YEAR, company_code="001", standard_account_code="1001", account_name="库存现金",
                         account_category=AccountCategory.asset, audited_amount=Decimal("1"), opening_balance=Decimal("2")),
        ])
        await s.commit()

    app = FastAPI()
    app.include_router(disclosure_notes.router)

    async def _override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _Actor(me)
    app.dependency_overrides[check_consol_lock] = lambda: None
    # 编辑门禁走生产判定（本项目 edit 级成员行），只替换 Redis 与事件总线
    with patch.object(DisclosureMutationCoordinator, "_redis", new=AsyncMock(return_value=None)), \
            patch("app.services.event_bus.event_bus.publish", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield {"client": client, "url": f"/api/disclosure-notes/{pid}/{YEAR}/{SECTION}/formulas"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_dangling_cross_table_ref_is_422_and_nothing_saved(env):
    body = {"formulas": [
        {"target": "1:1", "formula": "TB('1001','期末余额') + cell(0,1)"},           # 存在（表内引用不校验）
        {"target": "1:0", "formula": "TB('9999','期末余额')"},                        # 科目不存在
        {"target": "0:1", "formula": "NOTE('五、1','银行存款','期末余额')"},           # 行不存在
        {"target": "0:2", "formula": ""},                                             # 空行跳过
    ]}
    with patch.object(note_settings, "save_section", new=AsyncMock()) as save:
        resp = await env["client"].put(env["url"], json=body)
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert (detail["error_code"], detail["message"]) == ("FORMULA_DANGLING_REFS", "公式含悬空引用，拒绝保存")
    assert [(i["target"], i["ref"]) for i in detail["issues"]] == [
        ("1:0", "TB('9999','期末余额')"), ("0:1", "NOTE('五、1','银行存款','期末余额')")]
    assert all(i["message"] for i in detail["issues"]), "每条都写明原因"
    save.assert_not_awaited()


@pytest.mark.asyncio
async def test_formula_without_valid_target_is_422_not_silently_dropped(env):
    """原先没选目标的公式被当空行丢掉、仍回 200「已保存」（spec note-pull-header-formula-closure F7）。"""
    body = {"formulas": [
        {"target": "", "formula": "SUM(0:0, 0)"},          # 新增公式没选目标
        {"target": "合计行", "formula": "cell(0,0)"},       # 不是单元格
        {"target": "1:5", "formula": "cell(0,0)"},          # 超出表格（2 行 × 2 列）
        {"target": "1:0", "formula": "cell(0,0)"},          # 正常
    ]}
    with patch.object(note_settings, "save_section", new=AsyncMock()) as save:
        resp = await env["client"].put(env["url"], json=body)
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["error_code"] == "FORMULA_TARGET_INVALID"
    assert [i["target"] for i in detail["issues"]] == ["第 1 条", "合计行", "1:5"]
    assert "没有选择目标" in detail["issues"][0]["message"] and "2 行 × 2 列" in detail["issues"][2]["message"]
    save.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_refs_are_saved(env):
    saved = {"formulas": [{"target": "1:1"}], "loaded": {}, "events": []}
    body = {"formulas": [{"target": "1:1", "formula": "TB('1001','期末余额') - NOTE('五、1','库存现金','期初余额')"}]}
    with patch.object(note_settings, "save_section", new=AsyncMock(return_value=saved)) as save:
        resp = await env["client"].put(env["url"], json=body)
    assert resp.status_code == 200, resp.text
    save.assert_awaited_once()
