"""批 6.6：合并底稿生命周期验收配方（端点级，经真实门禁）。

本文件是批 6 的验证任务（ADR-CRW-006 验收）。按五条配方逐一取证，覆盖整批 6 面：

1. 端点权限配方（recipe 1）——
   - 补齐 6.2 authz 测试未覆盖的写端点（ensure / reviewer / submit-review / restore）的
     「该放行的角色真能用 + 该拒绝的角色 403 + 未登录 401」三类；
   - **配方覆盖守卫**：按生产注册枚举批 6 全部端点（workpaper-shell 9 条 + readiness 2 条），
     断言每条都挂了 `require_project_access` 且级别与配方预期逐一相等；出现未登记 / 漏挂门禁 /
     级别漂移即打红（不是数条数，是逐条对级别）。
2. 证据跨项目隔离（recipe 2）——见 `test_batch6_evidence_cross_project_isolation.py`（需真 PG 双项目）。
3. 回收站恢复 round-trip（recipe 3）——经端点走一遍：指派负责人 / 复核人 → 提交复核 → 移入回收站 →
   恢复，恢复后负责人 / 复核人 / 复核状态原样保留；只恢复 kind=consol 移入的。
4. 复核状态转换（recipe 4）——经端点走状态机：not_submitted→pending→passed / rejected→重新提交；
   非法转换（未提交就复核、退回不填原因、重复提交）一律 409。

配方 5（归档包 hash 验证 / 篡改）在 `test_workpaper_shell_and_archive.py` 与
`test_batch6_archive_package_hash.py` 取证（provider 层篡改 + 通用打包器逐项 sha256 + 根 hash）。
"""
from __future__ import annotations

import pytest
import pytest_asyncio

import tests.conftest  # noqa: F401
from app.models.base import ProjectStatus
from app.models.consol_workpaper_instance_models import ConsolWorkpaperInstance
from app.models.workpaper_lifecycle_models import WorkpaperLifecycleEvent
from app.models.workpaper_models import WorkingPaper, WpIndex, WpReviewStatus
from app.models.wp_visibility_models import WpVisibilityInvalidationOutbox, WpVisibilityPolicyEpoch
from app.routers import consol_readiness as readiness_router
from app.routers import consol_workpaper as shell_router
from app.services import consol_workpaper_shell as shell
from app.services import workpaper_recycle_service as recycle_svc
from tests.authz_world import TARGET_PROJECT_ID, sqlite_world

pytestmark = pytest.mark.asyncio

YEAR = 2025
GATE = "app.deps.require_project_access.<locals>.dependency"

_EXTRA = (
    WpIndex.__table__, WorkingPaper.__table__, ConsolWorkpaperInstance.__table__,
    WorkpaperLifecycleEvent.__table__, WpVisibilityPolicyEpoch.__table__,
    WpVisibilityInvalidationOutbox.__table__,
)


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async def _no_epoch(_db, _pid, _action, _codes, _actor, _req):
        return None

    monkeypatch.setattr(recycle_svc, "_bump_epoch", _no_epoch)
    async with sqlite_world(monkeypatch, extra_tables=_EXTRA) as w:
        w.target.report_scope = "consolidated"
        w.target.audit_year = YEAR
        w.target.status = ProjectStatus.execution
        await w.db.flush()
        await shell.ensure_consol_workpaper_shell(w.db, TARGET_PROJECT_ID, year=YEAR)
        await w.db.flush()
        yield w


def _url(suffix: str) -> str:
    return f"/api/consolidation/{TARGET_PROJECT_ID}/{YEAR}/workpaper-shell{suffix}"


# ══════════════════════════════════════════════════════════════════════════════
# recipe 1 — 端点权限配方：补齐写端点（ensure / reviewer / submit-review / restore）
# ══════════════════════════════════════════════════════════════════════════════


async def test_ensure_allows_edit_member(world):
    identity = await world.edit_member()
    async with world.client(shell_router.router, user=identity.user) as client:
        resp = await client.post(_url("/ensure"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["wp_code"] == shell.WP_CODE
    client.assert_passed(GATE)


async def test_ensure_denies_readonly_member(world):
    identity = await world.readonly_member()
    async with world.client(shell_router.router, user=identity.user) as client:
        resp = await client.post(_url("/ensure"))
    assert resp.status_code == 403, resp.text


async def test_ensure_unauthenticated_401(world):
    async with world.client(shell_router.router, user=None) as client:
        resp = await client.post(_url("/ensure"))
    assert resp.status_code == 401, resp.text


async def test_reviewer_allows_edit_member(world):
    identity = await world.edit_member()
    async with world.client(shell_router.router, user=identity.user) as client:
        resp = await client.put(_url("/reviewer"), json={"reviewer": str(identity.user.id)})
    assert resp.status_code == 200, resp.text
    assert resp.json()["reviewer"] == str(identity.user.id)
    client.assert_passed(GATE)


async def test_reviewer_denies_readonly_member(world):
    identity = await world.readonly_member()
    async with world.client(shell_router.router, user=identity.user) as client:
        resp = await client.put(_url("/reviewer"), json={"reviewer": None})
    assert resp.status_code == 403, resp.text


async def test_reviewer_unauthenticated_401(world):
    async with world.client(shell_router.router, user=None) as client:
        resp = await client.put(_url("/reviewer"), json={"reviewer": None})
    assert resp.status_code == 401, resp.text


async def test_submit_review_allows_edit_member(world):
    identity = await world.edit_member()
    async with world.client(shell_router.router, user=identity.user) as client:
        resp = await client.post(_url("/submit-review"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["review_status"] == WpReviewStatus.pending_level1.value
    client.assert_passed(GATE)


async def test_submit_review_denies_readonly_member(world):
    identity = await world.readonly_member()
    async with world.client(shell_router.router, user=identity.user) as client:
        resp = await client.post(_url("/submit-review"))
    assert resp.status_code == 403, resp.text


async def test_submit_review_unauthenticated_401(world):
    async with world.client(shell_router.router, user=None) as client:
        resp = await client.post(_url("/submit-review"))
    assert resp.status_code == 401, resp.text


async def test_restore_allows_edit_member(world):
    # 先移入回收站，再由 edit 成员恢复（恢复是 edit 级写端点）
    editor = await world.edit_member()
    async with world.client(shell_router.router, user=editor.user) as client:
        recycled = await client.post(_url("/recycle"))
    assert recycled.status_code == 200, recycled.text

    async with world.client(shell_router.router, user=editor.user) as client:
        resp = await client.post(_url("/restore"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["restored"] == [shell.WP_CODE]
    client.assert_passed(GATE)


async def test_restore_denies_readonly_member(world):
    identity = await world.readonly_member()
    async with world.client(shell_router.router, user=identity.user) as client:
        resp = await client.post(_url("/restore"))
    assert resp.status_code == 403, resp.text


async def test_restore_unauthenticated_401(world):
    async with world.client(shell_router.router, user=None) as client:
        resp = await client.post(_url("/restore"))
    assert resp.status_code == 401, resp.text


# ══════════════════════════════════════════════════════════════════════════════
# recipe 1 — 配方覆盖守卫：批 6 全部端点都挂了正确级别的 require_project_access
# ══════════════════════════════════════════════════════════════════════════════

# 批 6 每条端点的「谁会用」定级（ADR-CRW-006 / 路由 docstring）。
# key = (METHOD, path)；value = require_project_access 的级别。
# 新增 / 改级 / 漏挂门禁时此表与实际路由对不上即打红。
_EXPECTED_SHELL_LEVELS: dict[tuple[str, str], str] = {
    ("GET", "/api/consolidation/{project_id}/{year}/workpaper-shell"): "readonly",
    ("POST", "/api/consolidation/{project_id}/{year}/workpaper-shell/evidence-target"): "readonly",
    ("POST", "/api/consolidation/{project_id}/{year}/workpaper-shell/ensure"): "edit",
    ("PUT", "/api/consolidation/{project_id}/{year}/workpaper-shell/owner"): "edit",
    ("PUT", "/api/consolidation/{project_id}/{year}/workpaper-shell/reviewer"): "edit",
    ("POST", "/api/consolidation/{project_id}/{year}/workpaper-shell/submit-review"): "edit",
    ("POST", "/api/consolidation/{project_id}/{year}/workpaper-shell/review"): "review",
    ("POST", "/api/consolidation/{project_id}/{year}/workpaper-shell/recycle"): "edit",
    ("POST", "/api/consolidation/{project_id}/{year}/workpaper-shell/restore"): "edit",
}
_EXPECTED_READINESS_LEVELS: dict[tuple[str, str], str] = {
    ("GET", "/api/consolidation/readiness/{project_id}/{year}"): "readonly",
    ("GET", "/api/consolidation/readiness/{project_id}/{year}/role-views"): "readonly",
}


def _project_access_levels(dependant) -> list[str]:
    """递归找该路由挂的全部 `require_project_access` 门禁的级别（读闭包里的 min_permission）。

    只认 `require_project_access`（不含 `_stream` 变体），按闭包自由变量 min_permission 取级别。
    """
    levels: list[str] = []

    def walk(dep) -> None:
        call = getattr(dep, "call", None)
        code = getattr(call, "__code__", None)
        freevars = getattr(code, "co_freevars", ())
        if (
            call is not None
            and getattr(call, "__name__", "") == "dependency"
            and "min_permission" in freevars
            and "require_project_access." in getattr(call, "__qualname__", "")
            and ".require_project_access_stream." not in getattr(call, "__qualname__", "")
        ):
            idx = freevars.index("min_permission")
            levels.append(call.__closure__[idx].cell_contents)
        for sub in getattr(dep, "dependencies", []):
            walk(sub)

    walk(dependant)
    return levels


def _route_level_map(router) -> dict[tuple[str, str], list[str]]:
    out: dict[tuple[str, str], list[str]] = {}
    for route in router.routes:
        methods = getattr(route, "methods", None)
        if not methods:
            continue
        for method in methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            out[(method, route.path)] = _project_access_levels(route.dependant)
    return out


async def test_recipe_coverage_shell_endpoints_all_gated_with_expected_level():
    """批 6 薄壳路由：每条端点恰好挂一个 require_project_access，且级别与配方预期逐一相等。

    - 没在预期表里的端点 ⇒ 打红（新增端点必须登记并定级，不得默默无门禁）。
    - 预期表里的端点在实际路由里不存在 ⇒ 打红（防止预期表与实现漂移）。
    - 级别不符 / 漏挂门禁（0 个）/ 多挂（>1 个）⇒ 打红。

    纯静态内省（不发请求），但声明为 async 以统一模块 asyncio 口径。
    """
    actual = _route_level_map(shell_router.router)
    _assert_recipe_coverage(actual, _EXPECTED_SHELL_LEVELS, "合并薄壳")


async def test_recipe_coverage_readiness_endpoints_all_gated_with_expected_level():
    """批 6 readiness 路由：两条只读端点都挂 readonly 门禁。"""
    actual = _route_level_map(readiness_router.router)
    _assert_recipe_coverage(actual, _EXPECTED_READINESS_LEVELS, "合并 readiness")


def _assert_recipe_coverage(
    actual: dict[tuple[str, str], list[str]],
    expected: dict[tuple[str, str], str],
    label: str,
) -> None:
    # 1) 实际路由集合 == 预期集合（无遗漏、无未登记）
    actual_keys = set(actual)
    expected_keys = set(expected)
    ungated_new = sorted(actual_keys - expected_keys)
    assert not ungated_new, (
        f"{label}：出现未登记端点（新增端点必须登记并定级）：{ungated_new}"
    )
    missing = sorted(expected_keys - actual_keys)
    assert not missing, f"{label}：预期端点在实际路由中不存在（预期表与实现漂移）：{missing}"
    # 2) 每条端点恰好一个 require_project_access 且级别相符
    problems: list[str] = []
    for key, want in expected.items():
        got = actual[key]
        if len(got) != 1:
            problems.append(f"{key} 挂了 {len(got)} 个 require_project_access（应恰好 1 个）：{got}")
        elif got[0] != want:
            problems.append(f"{key} 门禁级别 {got[0]!r} ≠ 预期 {want!r}")
    assert not problems, f"{label} 配方覆盖不符：" + "；".join(problems)


# ══════════════════════════════════════════════════════════════════════════════
# recipe 3 — 回收站恢复 round-trip（经端点，owner/reviewer/review-state 保留）
# ══════════════════════════════════════════════════════════════════════════════


async def test_recycle_restore_round_trip_preserves_owner_reviewer_review_state(world):
    editor = await world.edit_member()
    reviewer = await world.review_member()

    # 指派负责人 + 复核人，提交复核 ⇒ 状态 pending_level1
    async with world.client(shell_router.router, user=editor.user) as client:
        r1 = await client.put(_url("/owner"), json={"assigned_to": str(editor.user.id)})
        assert r1.status_code == 200, r1.text
        r2 = await client.put(_url("/reviewer"), json={"reviewer": str(reviewer.user.id)})
        assert r2.status_code == 200, r2.text
        r3 = await client.post(_url("/submit-review"))
        assert r3.status_code == 200, r3.text
        assert r3.json()["review_status"] == WpReviewStatus.pending_level1.value

        # 移入回收站 ⇒ GET 壳 404（只看未删除）
        rec = await client.post(_url("/recycle"))
        assert rec.status_code == 200, rec.text
        assert rec.json()["recycled"] == [shell.WP_CODE]
        gone = await client.get(_url(""))
        assert gone.status_code == 404, gone.text

        # 恢复 ⇒ 壳回来，负责人 / 复核人 / 复核状态原样保留
        restored = await client.post(_url("/restore"))
        assert restored.status_code == 200, restored.text
        assert restored.json()["restored"] == [shell.WP_CODE]

        back = await client.get(_url(""))
        assert back.status_code == 200, back.text
        body = back.json()
        assert body["assigned_to"] == str(editor.user.id)
        assert body["reviewer"] == str(reviewer.user.id)
        assert body["review_status"] == WpReviewStatus.pending_level1.value


async def test_restore_only_consol_kind_through_service_then_endpoint(world):
    """别的 kind（手工删除）移入的，端点恢复不碰（只恢复 kind=consol）。"""
    editor = await world.edit_member()
    # 以非 consol kind 直接移入（模拟程序裁剪 / 手工删除把同一编码移入）
    await recycle_svc.move_to_recycle_bin(
        world.db, TARGET_PROJECT_ID, [shell.WP_CODE], kind="manual",
        reason="手工删除", actor_user_id=editor.user.id,
    )
    await world.db.flush()

    async with world.client(shell_router.router, user=editor.user) as client:
        resp = await client.post(_url("/restore"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["restored"] == []  # kind 不匹配，不恢复


# ══════════════════════════════════════════════════════════════════════════════
# recipe 4 — 复核状态转换（经端点；非法转换 409）
# ══════════════════════════════════════════════════════════════════════════════


async def test_full_review_cycle_submit_approve(world):
    editor = await world.edit_member()
    reviewer = await world.review_member()
    async with world.client(shell_router.router, user=editor.user) as client:
        assert (await client.post(_url("/submit-review"))).status_code == 200
    async with world.client(shell_router.router, user=reviewer.user) as client:
        resp = await client.post(_url("/review"), json={"approved": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["review_status"] == WpReviewStatus.level1_passed.value


async def test_review_reject_then_resubmit(world):
    editor = await world.edit_member()
    reviewer = await world.review_member()
    async with world.client(shell_router.router, user=editor.user) as client:
        assert (await client.post(_url("/submit-review"))).status_code == 200
    # 退回（带原因）
    async with world.client(shell_router.router, user=reviewer.user) as client:
        rej = await client.post(_url("/review"), json={"approved": False, "rejection_reason": "抵销分录缺失"})
    assert rej.status_code == 200, rej.text
    assert rej.json()["review_status"] == WpReviewStatus.level1_rejected.value
    assert rej.json()["rejection_reason"] == "抵销分录缺失"
    # 退回后可重新提交
    async with world.client(shell_router.router, user=editor.user) as client:
        resub = await client.post(_url("/submit-review"))
    assert resub.status_code == 200, resub.text
    assert resub.json()["review_status"] == WpReviewStatus.pending_level1.value


async def test_review_without_submit_is_409(world):
    """not_submitted 直接复核 ⇒ 非法转换 409。"""
    reviewer = await world.review_member()
    async with world.client(shell_router.router, user=reviewer.user) as client:
        resp = await client.post(_url("/review"), json={"approved": True})
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "REVIEW_TRANSITION_INVALID"


async def test_reject_without_reason_is_409(world):
    """退回不填原因 ⇒ 409（经端点）。

    注：端点 409 分支会 ``db.rollback()`` 本次世界会话，故不在同一会话里再发请求取状态
    （那会在共享会话回滚后让 ORM 对象过期 → 门禁读属性 MissingGreenlet，是测试夹具的共享会话
    约束，不是生产行为）。「退回不填原因不改状态」已由服务层
    ``test_workpaper_shell_lifecycle.py::test_submit_then_reject_requires_reason_then_resubmit``
    显式取证（回滚后读状态仍 pending_level1）。
    """
    editor = await world.edit_member()
    reviewer = await world.review_member()
    async with world.client(shell_router.router, user=editor.user) as client:
        assert (await client.post(_url("/submit-review"))).status_code == 200
    async with world.client(shell_router.router, user=reviewer.user) as client:
        resp = await client.post(_url("/review"), json={"approved": False})
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "REVIEW_TRANSITION_INVALID"


async def test_double_submit_is_409(world):
    """pending_level1 再提交 ⇒ 409。"""
    editor = await world.edit_member()
    async with world.client(shell_router.router, user=editor.user) as client:
        assert (await client.post(_url("/submit-review"))).status_code == 200
        resp = await client.post(_url("/submit-review"))
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "REVIEW_TRANSITION_INVALID"


async def test_approve_after_pass_is_409(world):
    """已通过（level1_passed）再复核 ⇒ 409（终态不可再转）。"""
    editor = await world.edit_member()
    reviewer = await world.review_member()
    async with world.client(shell_router.router, user=editor.user) as client:
        assert (await client.post(_url("/submit-review"))).status_code == 200
    async with world.client(shell_router.router, user=reviewer.user) as client:
        assert (await client.post(_url("/review"), json={"approved": True})).status_code == 200
        resp = await client.post(_url("/review"), json={"approved": True})
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "REVIEW_TRANSITION_INVALID"
