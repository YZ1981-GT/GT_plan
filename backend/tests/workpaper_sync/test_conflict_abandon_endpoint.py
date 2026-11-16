"""作废端点的**端点级**鉴权守卫：未认证 / 只读 / 复核 / 编辑 / 非成员 / admin 六类真发请求。

spec `frozen-contract-read-path-and-legacy-operation-settlement` 任务 8
Requirements: R3.3（带原因与操作者）· memory 铁律 ㉕（新增端点必做端点级测试）

═══ 为什么不能只测 service ═══

memory ㉕ 的原文教训：`disclosure-payload` 轮新增端点只挂 `Depends(get_db)` 零鉴权，
任意 `project_id` 可未授权读项目数据；**前两轮复盘没发现，因为从未真实调用过端点**
（只验 `router.routes` 长度 + service 纯函数）⇒ 鉴权/依赖链/响应信封全在盲区。

| 身份 | 期望 |
| --- | --- |
| 未带令牌 | 401（`get_current_user` 先拦） |
| 只读成员（readonly, readonly） | **403** —— 作废是复核级动作 |
| 复核成员（qc, review） | 放行 |
| 编辑成员（manager, edit） | 放行 |
| 非成员（只在别的项目有成员行） | **403** |
| admin（不是本项目成员） | 放行（`require_project_access` 的 admin 直通） |

🔴 **不 override `require_project_access`**：它是依赖工厂，每次返回**新函数对象**，
`dependency_overrides` 拿不到同一个 key ⇒ override 静默失效 ⇒ 全部 401 的假绿
（memory ㉕ 配套坑①）。这里用 `tests/authz_world.py` 的权限世界，只 override
`get_current_user` 与 `get_db`（世界自检 `assert_world_overrides` 会核对这些）。

🔴 **诚实说明可替换点**：本文件的被测对象是**项目级门禁**，不是 sync 域的 scope
guard。`SR._guard` 被打桩成返回一个 `GuardedScope`（它需要
`working_paper_sync_scope_index` 与整套 bottom-up 可见性表，与本判据无关）；被观测的
是 `require_project_access("review")` —— 它是**生产对象**（`world.client` 每次请求前
`assert_gates_are_production()` + 请求内 `assert_passed` 观测其代码真的执行过）。
「`_guard` 本身也判鉴权」这件事由 `test_task28_sync_router*.py` 覆盖，不在本文件重复。
"""

from __future__ import annotations

import inspect
import uuid
from datetime import datetime, timezone
from typing import Any

import pytest
import pytest_asyncio

from app.routers import wp_sync_router as SR
from app.services.workpaper_sync import conflict_abandon as CA
from app.services.workpaper_sync.models import OperationShape
from app.services.workpaper_sync.request_application import CanonicalRead
from tests.authz_world import (
    TARGET_PROJECT_ID,
    AuthzWorld,
    Identity,
    ServiceStub,
    build_app,
    sqlite_world,
)

PID = TARGET_PROJECT_ID
WP = uuid.UUID("33333333-3333-3333-3333-333333333333")
OP = uuid.UUID("44444444-4444-4444-4444-444444444444")
ENTRY = "xlsx/gt-d2-accounts-receivable"
PATH = f"/api/projects/{PID}/workpapers/{WP}/sync/entries/{ENTRY}/operations/{OP}/abandon"
BODY = {"reason": "契约已换代，这批冲突不再需要处理"}

#: 依赖工厂**内部**的 `dependency` 闭包才是每请求真正执行的代码对象。
GATE = "app.deps.require_project_access.<locals>.dependency"


class _Op:
    """最小 operation 行形状（本文件只关心「放行后业务被调了几次」）。"""

    def __init__(self) -> None:
        self.id = OP
        self.application_id = uuid.uuid4()
        self.duplicate_of_operation_id = None
        self.state = "conflict"


def _canonical_read() -> CanonicalRead:
    return CanonicalRead(
        requested_operation=_Op(),  # type: ignore[arg-type]
        requested_shape=OperationShape.primary,
        canonical_operation=_Op(),  # type: ignore[arg-type]
        canonical_application_id=None,
        effective_request_sequence=None,
        stages=(),
    )


def _outcome(reason: str = BODY["reason"], actor: uuid.UUID | None = None) -> CA.AbandonOutcome:
    return CA.AbandonOutcome(
        operation_id=OP,
        from_state="conflict",
        to_state="superseded",
        abandoned_conflicts=3,
        already_abandoned=0,
        abandon_reason=reason,
        abandoned_by=actor or uuid.uuid4(),
        abandoned_at=datetime.now(timezone.utc),
        idempotent_replay=False,
    )


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch) as w:
        yield w


def _stub_business(world: AuthzWorld, *, user_id: uuid.UUID) -> dict[str, ServiceStub]:
    """把两条业务调用换成计数桩 —— **项目级门禁不打桩**，那正是要观测的对象。"""
    read = world.stub(
        SR.RequestApplicationService, "read_operation", returns=_canonical_read()
    )
    abandon = world.stub(CA.ConflictAbandonService, "abandon", returns=_outcome(actor=user_id))
    return {"read_operation": read, "abandon": abandon}


def _install_guard(world: AuthzWorld, user_id: uuid.UUID):
    """`SR._guard` 打桩（`GuardedScope.user_id` 用当前身份的真实 id）。"""
    from app.services.workpaper_sync.endpoint_guard import REQUIRED_PHASES, GuardedScope

    seen: list[dict[str, Any]] = []

    async def _guarded(svc: Any, **kwargs: Any) -> GuardedScope:
        seen.append(kwargs)
        return GuardedScope(
            project_id=kwargs["project_id"],
            wp_id=kwargs["wp_id"],
            entry_id=kwargs["entry_id"],
            user_id=user_id,
            action=kwargs["action"],
            refs=tuple(kwargs.get("refs") or ()),
            attributions={},
            phases=REQUIRED_PHASES,
            observed={"project_visible": True, "workflow_locked": False},
        )

    world.monkeypatch.setattr(SR, "_guard", _guarded)
    return seen


async def _identity(world: AuthzWorld, key: str) -> Identity:
    return await world.identity(key)


#: (身份键, 期望 status, 说明)
_DENY_CASES: list[tuple[str, int, str]] = [
    ("readonly_member", 403, "只读成员不得作废（review 级动作）"),
    ("non_member", 403, "非本项目成员"),
]
_ALLOW_CASES: list[tuple[str, str]] = [
    ("review_member", "复核成员（qc, review）"),
    ("edit_member", "编辑成员（manager, edit）"),
    ("admin_non_member", "admin 直通"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("key,expected,why", _DENY_CASES, ids=[c[0] for c in _DENY_CASES])
async def test_a_denied_identity_is_refused_before_any_business_call(
    world: AuthzWorld, key: str, expected: int, why: str
) -> None:
    """被拒身份必须拿到 403，且**业务零调用**（鉴权排在业务之前）。"""
    identity = await _identity(world, key)
    stubs = _stub_business(world, user_id=identity.user.id)
    guard_seen = _install_guard(world, identity.user.id)
    app = build_app(SR.router)
    async with world.client_for_app(app, user=identity.user) as client:
        resp = await client.post(PATH, json=BODY)
        client.assert_passed(GATE)
    assert resp.status_code == expected, f"{why}：期望 {expected}，实得 {resp.status_code} {resp.text}"
    assert not guard_seen, f"{why}：请求越过了项目级门禁进入 handler（_guard 被调了）"
    assert stubs["read_operation"].count == 0, (
        f"{why}：业务读被调了 {stubs['read_operation'].count} 次 —— 鉴权没排在业务之前"
    )
    assert stubs["abandon"].count == 0, f"{why}：作废被调了 {stubs['abandon'].count} 次"


@pytest.mark.asyncio
@pytest.mark.parametrize("key,why", _ALLOW_CASES, ids=[c[0] for c in _ALLOW_CASES])
async def test_an_allowed_identity_reaches_the_business_layer_exactly_once(
    world: AuthzWorld, key: str, why: str
) -> None:
    """放行身份必须真的走到业务层且**恰一次**。

    memory ㉕ 的教训：只测 401 测不出「该放行的人被拦」（Phase 8 曾把鉴权全挂 edit，
    合伙人签不了字而测试全绿）。
    """
    identity = await _identity(world, key)
    stubs = _stub_business(world, user_id=identity.user.id)
    guard_seen = _install_guard(world, identity.user.id)
    app = build_app(SR.router)
    async with world.client_for_app(app, user=identity.user) as client:
        resp = await client.post(PATH, json=BODY)
        client.assert_passed(GATE)
    assert resp.status_code == 200, f"{why} 被拦住：{resp.status_code} {resp.text}"
    assert len(guard_seen) == 1, f"{why}：_guard 被调了 {len(guard_seen)} 次"
    assert stubs["read_operation"].count == 1
    assert stubs["abandon"].count == 1
    assert resp.json()["to_state"] == "superseded"


@pytest.mark.asyncio
async def test_an_unauthenticated_request_is_401(world: AuthzWorld) -> None:
    """未带令牌 → 401（`get_current_user` 是唯一 401 来源）。"""
    stubs = _stub_business(world, user_id=uuid.uuid4())
    _install_guard(world, uuid.uuid4())
    app = build_app(SR.router)
    async with world.client_for_app(app, user=None) as client:
        resp = await client.post(PATH, json=BODY)
    assert resp.status_code == 401
    assert stubs["read_operation"].count == 0
    assert stubs["abandon"].count == 0


@pytest.mark.asyncio
async def test_the_actor_is_the_server_side_user_not_the_request_body(
    world: AuthzWorld,
) -> None:
    """变异 d 的端点级判据：请求体里的 `actor_id` / `abandoned_by` 必须被忽略。

    🔴 与 `test_conflict_abandon.py` 的 AST 判据是两重锁：AST 看「实参是不是
    `scope.user_id`」，本条看**真实运行**时传进 service 的到底是谁。
    """
    identity = await _identity(world, "edit_member")
    stubs = _stub_business(world, user_id=identity.user.id)
    _install_guard(world, identity.user.id)
    forged = uuid.uuid4()
    app = build_app(SR.router)
    async with world.client_for_app(app, user=identity.user) as client:
        resp = await client.post(
            PATH, json={**BODY, "actor_id": str(forged), "abandoned_by": str(forged)}
        )
    assert resp.status_code == 200, resp.text
    assert stubs["abandon"].count == 1
    _args, kwargs = stubs["abandon"].calls[0]
    assert kwargs["actor_id"] == identity.user.id, (
        "作废操作者不是服务端当前用户 —— 审计轨迹可被请求体伪造"
    )
    assert kwargs["actor_id"] != forged


@pytest.mark.asyncio
async def test_a_blank_reason_is_refused_with_422(world: AuthzWorld) -> None:
    """缺原因必须 422（不是 200 也不是 500）—— 入参校验在端点路径上真的跑。

    🔴 本条**不打桩 `abandon`**（要的就是真入参校验），只把 `read_operation` 与
    `_guard` 打桩，让 `normalize_abandon_reason` 在端点路径上真的执行。
    """
    identity = await _identity(world, "edit_member")
    stubs = {
        "read_operation": world.stub(
            SR.RequestApplicationService, "read_operation", returns=_canonical_read()
        )
    }
    _install_guard(world, identity.user.id)
    app = build_app(SR.router)
    async with world.client_for_app(app, user=identity.user) as client:
        resp = await client.post(PATH, json={"reason": "  "})
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["error_code"] == "conflict_abandon_reason_required"
    assert stubs["read_operation"].count >= 1


# ═══════════════════════════════════════════════════════════════════════════
# 端点形态：路由级 review 门 + 写 action 登记 + 显式 scope 前缀
# ═══════════════════════════════════════════════════════════════════════════


def _abandon_route():
    for route in SR.router.routes:
        if getattr(route, "endpoint", None).__name__ == "abandon_conflicts":
            return route
    raise AssertionError("router 里没有 abandon_conflicts 路由")


def test_the_route_carries_the_review_level_project_gate() -> None:
    """🔴 路由必须挂 `require_project_access("review")` —— 上面那些用例的前提。

    本断言把「鉴权依赖还挂在路由上」独立钉住：`_guard` 的 action 词表**不判项目成员
    级别**（`WpGateVisibilityProbe` 的 `readonly` 只进 `observed`、不拦写），所以只读
    成员能通过词表检查 —— 「挂的是 review 门」必须自证。
    """
    route = _abandon_route()
    sources = " ".join(
        inspect.getsource(dep.call) for dep in route.dependant.dependencies if dep.call
    )
    assert "assert_project_permission" in sources, (
        "abandon_conflicts 路由没有挂项目级鉴权依赖（review 门）"
    )


def test_the_gate_level_is_review_not_edit() -> None:
    """级别必须是 `review`：`require_project_access("edit")` 会拦住 review 级质控 / EQCR。

    用闭包捕获值断言（工厂把 `min_permission` 捕获进闭包）。
    """
    from app.deps import require_project_access

    route = _abandon_route()
    levels: set[str] = set()
    for dep in route.dependant.dependencies:
        for cell in getattr(dep.call, "__closure__", None) or ():
            if isinstance(cell.cell_contents, str):
                levels.add(cell.cell_contents)
    assert "review" in levels, f"路由上挂的门级别是 {sorted(levels)}，期望 review"
    # 自检：工厂对不同级别返回不同闭包（防工厂退化成恒真）
    assert require_project_access("review") is not require_project_access("edit")


def test_the_action_is_registered_as_a_write_action() -> None:
    assert "abandon_conflicts" in SR._WRITE_ACTIONS
    assert "abandon_conflicts" not in SR._READ_ONLY_ACTIONS


def test_the_route_is_under_the_explicit_scope_prefix() -> None:
    route = _abandon_route()
    assert str(route.path).startswith(SR.USER_SYNC_PREFIX), (
        f"{route.path!r} 不在显式 scope 前缀下 —— 缺 scope 段的端点必须从 room/operation "
        "反推归属（AC 10.5 明令禁止）"
    )
