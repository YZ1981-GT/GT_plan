"""看板数据按项目可见性过滤（仪表盘 / 管理看板 / 合伙人看板）。

拓扑：合伙人甲（签字 P_jia）、合伙人乙（签字 P_yi）、admin。两个项目各 1 张待复核底稿、
各 1 条本周工时、各委派 1 名人员。断言：甲只看到 P_jia 的数据，乙只看到 P_yi 的，admin 看到两者；
缓存键按可见集区分，甲的结果不会被乙读到。
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.base import UserRole
from app.models.core import Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember, WorkHour
from app.models.workpaper_models import WorkingPaper, WpIndex, WpReviewStatus

pytestmark = pytest.mark.asyncio

_TABLES = (
    User.__table__, Project.__table__, ProjectUser.__table__,
    StaffMember.__table__, ProjectAssignment.__table__, WorkHour.__table__,
    WpIndex.__table__, WorkingPaper.__table__,
)


def _user(name: str, role: UserRole) -> User:
    return User(id=uuid.uuid4(), username=name, email=f"{name}@example.com",
                hashed_password="x", role=role, full_name=name)


@pytest_asyncio.fixture
async def world():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        for t in _TABLES:
            await conn.run_sync(t.create, checkfirst=True)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        admin, jia, yi = _user("adm", UserRole.admin), _user("jia", UserRole.partner), _user("yi", UserRole.partner)
        db.add_all([admin, jia, yi])
        await db.flush()
        projects = {}
        for key, owner in (("jia", jia), ("yi", yi)):
            p = Project(
                id=uuid.uuid4(), name=f"【测试】{key}项目", client_name=f"【测试】{key}客户",
                audit_period_start=date(2025, 1, 1), audit_period_end=date(2025, 12, 31),
                partner_id=owner.id, status="execution",
            )
            db.add(p)
            await db.flush()
            wpi = WpIndex(id=uuid.uuid4(), project_id=p.id, wp_code="D1", wp_name="底稿")
            db.add(wpi)
            await db.flush()
            db.add(WorkingPaper(
                id=uuid.uuid4(), project_id=p.id, wp_index_id=wpi.id, file_path="/x",
                source_type="upload", review_status=WpReviewStatus.pending_level1,
            ))
            staff = StaffMember(id=uuid.uuid4(), name=f"{key}的助理")
            db.add(staff)
            await db.flush()
            db.add(ProjectAssignment(id=uuid.uuid4(), project_id=p.id, staff_id=staff.id,
                                     role="auditor", assigned_at=datetime.now(timezone.utc)))
            db.add(WorkHour(id=uuid.uuid4(), staff_id=staff.id, project_id=p.id,
                            work_date=date.today(), hours=3 if key == "jia" else 5))
            projects[key] = p
        await db.commit()
        yield {"db": db, "admin": admin, "jia": jia, "yi": yi, "p": projects}
    await engine.dispose()


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    """进程内假 Redis：验证缓存键按可见集区分。"""
    store: dict[str, str] = {}

    class _R:
        async def get(self, k):
            return store.get(k)

        async def set(self, k, v, ex=None):
            store[k] = v

    import app.core.redis as redis_mod

    monkeypatch.setattr(redis_mod, "redis_client", _R(), raising=False)
    return store


async def _call(fn, world, who, **kw):
    return await fn(db=world["db"], user=world[who], **kw)


async def test_overview_scoped_per_partner(world, _fake_redis):
    from app.routers.dashboard import overview

    jia = await _call(overview, world, "jia")
    yi = await _call(overview, world, "yi")
    adm = await _call(overview, world, "admin")
    assert (jia["active_projects"], jia["week_hours"], jia["pending_review_workpapers"], jia["staff_count"]) == (1, 3.0, 1, 1)
    assert (yi["active_projects"], yi["week_hours"], yi["pending_review_workpapers"], yi["staff_count"]) == (1, 5.0, 1, 1)
    assert (adm["active_projects"], adm["week_hours"], adm["pending_review_workpapers"]) == (2, 8.0, 2)
    # 三份缓存各自独立（原实现共用一个 dashboard:global:overview 键）
    assert len([k for k in _fake_redis if k.endswith(":overview")]) == 3


async def test_project_lists_scoped(world):
    from app.routers.dashboard import project_progress, schedule, staff_workload

    pj, py_ = world["p"]["jia"], world["p"]["yi"]
    assert {r["project_id"] for r in await _call(project_progress, world, "jia")} == {str(pj.id)}
    assert {r["project_id"] for r in await _call(project_progress, world, "yi")} == {str(py_.id)}
    assert {r["project_id"] for r in await _call(project_progress, world, "admin")} == {str(pj.id), str(py_.id)}
    assert {r["project_name"] for r in await _call(schedule, world, "jia")} == {pj.name}
    assert {r["name"] for r in await _call(staff_workload, world, "jia")} == {"jia的助理"}


async def test_risk_and_quality_scoped(world):
    from app.routers.dashboard import quality_metrics, risk_alerts

    alerts = {a["type"]: a["count"] for a in await _call(risk_alerts, world, "jia")}
    assert alerts.get("unassigned_wp") == 1  # 只算自己项目那 1 张
    admin_alerts = {a["type"]: a["count"] for a in await _call(risk_alerts, world, "admin")}
    assert admin_alerts.get("unassigned_wp") == 2
    _ = quality_metrics  # 质量指标单独一条用例（需额外建表）


async def test_quality_metrics_scoped(world):
    from app.models.audit_platform_models import Adjustment
    from app.models.workpaper_models import WorkingPaper, WpQcResult
    from app.routers.dashboard import quality_metrics
    from sqlalchemy import select

    db = world["db"]
    async with db.bind.begin() as conn:
        for t in (WpQcResult.__table__, Adjustment.__table__):
            await conn.run_sync(t.create, checkfirst=True)
    wp_jia = (await db.execute(
        select(WorkingPaper.id).where(WorkingPaper.project_id == world["p"]["jia"].id)
    )).scalar_one()
    wp_yi = (await db.execute(
        select(WorkingPaper.id).where(WorkingPaper.project_id == world["p"]["yi"].id)
    )).scalar_one()
    now = datetime.now(timezone.utc)
    db.add_all([
        WpQcResult(id=uuid.uuid4(), working_paper_id=wp_jia, passed=True, check_timestamp=now, findings={}),
        WpQcResult(id=uuid.uuid4(), working_paper_id=wp_yi, passed=False, check_timestamp=now, findings={}),
    ])
    await db.commit()

    jia = await _call(quality_metrics, world, "jia")
    yi = await _call(quality_metrics, world, "yi")
    adm = await _call(quality_metrics, world, "admin")
    assert jia["qc_pass_rate"] == 100.0
    assert yi["qc_pass_rate"] == 0
    assert adm["qc_pass_rate"] == 50.0


async def test_staff_detail_hides_other_projects(world):
    from app.routers.dashboard import project_staff_hours

    rows = await _call(project_staff_hours, world, "jia", project_id=None)
    assert {r["project_id"] for r in rows} == {str(world["p"]["jia"].id)}


async def test_partner_urgency_scoped(world):
    from app.routers.partner_urgency import get_partner_urgency

    res = await get_partner_urgency(db=world["db"], current_user=world["jia"])
    assert {r["project_id"] for r in res["projects"]} == {str(world["p"]["jia"].id)}


async def test_partner_overview_and_efficiency_scoped(world):
    from app.services.partner_service import PartnerOverviewService, TeamEfficiencyService

    ov = await PartnerOverviewService(world["db"]).get_my_projects_overview(world["jia"].id)
    assert {p["id"] for p in ov["projects"]} == {str(world["p"]["jia"].id)}
    # 合伙人没有人员档案：原实现会当 admin 处理、统计前 50 个项目的底稿
    # 给甲项目的底稿设编制人，确认乙的团队效能统计不到它
    from sqlalchemy import update

    from app.models.workpaper_models import WorkingPaper

    await world["db"].execute(
        update(WorkingPaper).where(WorkingPaper.project_id == world["p"]["jia"].id).values(assigned_to=world["jia"].id)
    )
    await world["db"].commit()
    eff_yi = await TeamEfficiencyService(world["db"]).get_team_efficiency(world["yi"].id)
    assert eff_yi["staff_metrics"] == []
    eff_jia = await TeamEfficiencyService(world["db"]).get_team_efficiency(world["jia"].id)
    assert eff_jia["summary"]["total_workpapers"] == 1
    adm_ov = await PartnerOverviewService(world["db"]).get_my_projects_overview(world["admin"].id)
    assert len(adm_ov["projects"]) == 2
