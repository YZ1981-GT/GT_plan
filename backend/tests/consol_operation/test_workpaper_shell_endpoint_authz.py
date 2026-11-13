"""批 6.2：合并底稿壳路由的项目级鉴权（端点级，经真实门禁）。

用权限世界（authz_world）按生产注册挂 `consol_workpaper` 路由，经 httpx 真发请求。每个请求都核对
生产门禁 `require_project_access` 的代码确实执行过（GateClient）。覆盖：
- GET 壳：readonly 放行；未登录 401。
- 指派负责人（edit）：edit 放行；readonly 403；未登录 401。
- 复核处理（review）：review 放行；readonly 403；未登录 401。
- 移入回收站（edit）：edit 放行；readonly 403；未登录 401。

"该放行的角色真能用" + "未登录 401" 两类都测（不只测 401）。
"""
from __future__ import annotations

import pytest
import pytest_asyncio

import tests.conftest  # noqa: F401
from app.models.base import ProjectStatus
from app.models.consol_workpaper_instance_models import ConsolWorkpaperInstance
from app.models.workpaper_lifecycle_models import WorkpaperLifecycleEvent
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.models.wp_visibility_models import WpVisibilityInvalidationOutbox, WpVisibilityPolicyEpoch
from app.routers import consol_workpaper as shell_router
from app.services import consol_workpaper_shell as shell
from app.services import workpaper_recycle_service as recycle_svc
from tests.authz_world import TARGET_PROJECT_ID, sqlite_world

pytestmark = pytest.mark.asyncio

YEAR = 2025
GATE = "app.deps.require_project_access.<locals>.dependency"

# 壳 + 回收站联动需要的业务表（六张世界表之外补建）
_EXTRA = (
    WpIndex.__table__, WorkingPaper.__table__, ConsolWorkpaperInstance.__table__,
    WorkpaperLifecycleEvent.__table__, WpVisibilityPolicyEpoch.__table__,
    WpVisibilityInvalidationOutbox.__table__,
)


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    # 可见性策略纪元用 pg_insert（PG 专用）；SQLite 鉴权世界里置空（它不是门禁，只是基础设施）。
    async def _no_epoch(_db, _pid, _action, _codes, _actor, _req):
        return None

    monkeypatch.setattr(recycle_svc, "_bump_epoch", _no_epoch)
    async with sqlite_world(monkeypatch, extra_tables=_EXTRA) as w:
        # 目标项目调成「合并项目 + 年度一致 + 未归档」，让 validate_project_boundary 通过
        w.target.report_scope = "consolidated"
        w.target.audit_year = YEAR
        w.target.status = ProjectStatus.execution
        await w.db.flush()
        # 预建壳，使写端点的 service 能跑到（而不是在壳缺失处 404，掩盖鉴权结论）
        await shell.ensure_consol_workpaper_shell(w.db, TARGET_PROJECT_ID, year=YEAR)
        await w.db.flush()
        yield w


def _url(suffix: str) -> str:
    return f"/api/consolidation/{TARGET_PROJECT_ID}/{YEAR}/workpaper-shell{suffix}"


# ─── GET 壳：readonly ────────────────────────────────────────────────────────


async def test_get_shell_allows_readonly_member(world):
    identity = await world.readonly_member()
    async with world.client(shell_router.router, user=identity.user) as client:
        resp = await client.get(_url(""))
    assert resp.status_code == 200, resp.text
    assert resp.json()["wp_code"] == shell.WP_CODE
    client.assert_passed(GATE)


async def test_get_shell_unauthenticated_401(world):
    async with world.client(shell_router.router, user=None) as client:
        resp = await client.get(_url(""))
    assert resp.status_code == 401, resp.text


# ─── 指派负责人：edit ────────────────────────────────────────────────────────


async def test_assign_owner_allows_edit_member(world):
    identity = await world.edit_member()
    async with world.client(shell_router.router, user=identity.user) as client:
        resp = await client.put(_url("/owner"), json={"assigned_to": str(identity.user.id)})
    assert resp.status_code == 200, resp.text
    assert resp.json()["assigned_to"] == str(identity.user.id)
    client.assert_passed(GATE)


async def test_assign_owner_denies_readonly_member(world):
    identity = await world.readonly_member()
    async with world.client(shell_router.router, user=identity.user) as client:
        resp = await client.put(_url("/owner"), json={"assigned_to": None})
    assert resp.status_code == 403, resp.text


async def test_assign_owner_unauthenticated_401(world):
    async with world.client(shell_router.router, user=None) as client:
        resp = await client.put(_url("/owner"), json={"assigned_to": None})
    assert resp.status_code == 401, resp.text


# ─── 复核处理：review ────────────────────────────────────────────────────────


async def test_review_allows_review_member(world):
    # 先由 edit 成员提交复核，使状态进入 pending_level1
    editor = await world.edit_member()
    async with world.client(shell_router.router, user=editor.user) as client:
        submit = await client.post(_url("/submit-review"))
    assert submit.status_code == 200, submit.text

    reviewer = await world.review_member()
    async with world.client(shell_router.router, user=reviewer.user) as client:
        resp = await client.post(_url("/review"), json={"approved": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["review_status"] == "level1_passed"
    client.assert_passed(GATE)


async def test_review_denies_readonly_member(world):
    identity = await world.readonly_member()
    async with world.client(shell_router.router, user=identity.user) as client:
        resp = await client.post(_url("/review"), json={"approved": True})
    assert resp.status_code == 403, resp.text


async def test_review_unauthenticated_401(world):
    async with world.client(shell_router.router, user=None) as client:
        resp = await client.post(_url("/review"), json={"approved": True})
    assert resp.status_code == 401, resp.text


# ─── 移入回收站：edit ────────────────────────────────────────────────────────


async def test_recycle_allows_edit_member(world):
    identity = await world.edit_member()
    async with world.client(shell_router.router, user=identity.user) as client:
        resp = await client.post(_url("/recycle"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["recycled"] == [shell.WP_CODE]
    client.assert_passed(GATE)


async def test_recycle_denies_readonly_member(world):
    identity = await world.readonly_member()
    async with world.client(shell_router.router, user=identity.user) as client:
        resp = await client.post(_url("/recycle"))
    assert resp.status_code == 403, resp.text


async def test_recycle_unauthenticated_401(world):
    async with world.client(shell_router.router, user=None) as client:
        resp = await client.post(_url("/recycle"))
    assert resp.status_code == 401, resp.text


# ─── 证据坐标解析：readonly（任务 6.3）─────────────────────────────────────────


async def test_evidence_target_allows_readonly_member(world):
    """任何项目成员可解析稳定证据坐标（身份构造纯函数，不写库）。"""
    identity = await world.readonly_member()
    async with world.client(shell_router.router, user=identity.user) as client:
        resp = await client.post(
            _url("/evidence-target"),
            json={
                "sheet_type": "trial",
                "node_key": "consol_trial",
                "row_fields": {"standard_account_code": "1001"},
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sheet_name"] == "consol_trial"
    # 行身份 = 科目码（稳定）；cell_ref 段内的 ':' 被转义，解析可无歧义还原
    from app.services.consol_evidence_identity import parse_cell_ref

    parsed = parse_cell_ref(body["cell_ref"])
    assert parsed is not None
    assert parsed.node_key == "consol_trial"
    assert parsed.row_identity == "id:1001"
    assert body["shell_exists"] is True  # 世界 fixture 预建了壳
    client.assert_passed(GATE)


async def test_evidence_target_unauthenticated_401(world):
    async with world.client(shell_router.router, user=None) as client:
        resp = await client.post(
            _url("/evidence-target"),
            json={"sheet_type": "worksheet", "node_key": "cost", "row_fields": {"company_code": "C1"}},
        )
    assert resp.status_code == 401, resp.text
