"""clean close 的冻结身份必须**服务端派生** —— 客户端拿不到，也不该被问。

2026-09-22 真实浏览器实测：点「结构化视图」离开未改动的 OO ⇒
`POST …/rooms/{id}/close-intents` 返回 **422**
`{"error_code":"invalid_identity","message":"adapter_build_digest 必须是非空 64 位小写 hex
且非全零 digest，实得 ''"}`，红字直接糊在页面顶部（用户截图）。

根因不是「少传了一个参数」，而是**取值口径错了**：`adapter_build_digest` 与
`contributor_snapshot_digest` 都是服务端事实（representation 的代码身份、room 的 contributor
快照），`confirm-descriptor` 的响应里根本没有 adapter build digest；而 promotion 的 leader 是在
room lock 内选出来的，HTTP 层连「该冻结谁的 confirmation」都还不知道。于是「让调用方传」在真实
链路上只有一个结局：路由 `str(payload.get(...) or "")` 兜出空串 →
`compute_frozen_request_fingerprint()` 拒绝空 digest → **每一次真实 clean close 都 422**。

同一仓库里 recovery claim 路径早已写明正确口径（`_frozen_adapter_of_confirmation`
「只能来自候选 confirmation 的 representation」、`_contributor_digest_of_room`「不从请求体读」），
close-capture 是唯一的例外 —— 本文件把那条例外钉死。

变异反证：`backend/scripts/diagnose/mutate_close_capture_identity_guards.py`（4 条全 KILLED）。
"""
from __future__ import annotations

import ast
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"

if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import close_intent as ci  # noqa: E402

_ID_MID = uuid.UUID("88888888-8888-4888-8888-888888888888")
_ID_HIGH = uuid.UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")

#
# 真实浏览器实测：点「结构化视图」离开未改动的 OO ⇒
# `POST …/rooms/{id}/close-intents` 返回 **422**
# `{"error_code":"invalid_identity","message":"adapter_build_digest 必须是非空 64 位小写
# hex 且非全零 digest，实得 ''"}`，红字直接糊在页面顶部（用户截图）。
#
# 根因不是「少传了一个参数」，而是**取值口径错了**：`adapter_build_digest` 与
# `contributor_snapshot_digest` 都是服务端事实（representation 的代码身份、room 的
# contributor 快照），`confirm-descriptor` 的响应里根本没有 adapter build digest，
# 客户端无从得知；而 promotion 的 leader 是在 room lock 内选出来的，HTTP 层连「该冻结
# 谁的 confirmation」都还不知道。于是「让调用方传」在真实链路上只有一个结局：
# 路由 `str(payload.get(...) or "")` 兜出空串 → `compute_frozen_request_fingerprint()`
# 拒绝空 digest → 每一次真实 clean close 都 422。
#
# 同一仓库里 recovery claim 路径早已写明正确口径（`_frozen_adapter_of_confirmation`
# 「只能来自候选 confirmation 的 representation」、`_contributor_digest_of_room`
# 「不从请求体读」），close-capture 是唯一的例外 —— 本节把那条例外钉死。


def test_close_path_takes_no_identity_digest_from_its_callers() -> None:
    """close 三级入口（router → service → repository）都不得**接收** identity digest。

    判据放在签名上而不是某一次调用上：只要还留着 `adapter_build_digest=` 形参，
    调用点就还能传一个自己编的值进来，而「编出来的 digest」在 fingerprint 里与
    真实身份不可区分 —— 那正是本缺陷能一路走到 422 的原因。
    """
    import inspect

    from app.services.workpaper_sync.repository import WorkpaperSyncRepository

    for owner, func in (
        ("CloseIntentService.open_close_intent", ci.CloseIntentService.open_close_intent),
        ("CloseIntentService.reconcile", ci.CloseIntentService.reconcile),
        (
            "WorkpaperSyncRepository.reconcile_close_intents",
            WorkpaperSyncRepository.reconcile_close_intents,
        ),
    ):
        offenders = [
            name
            for name in inspect.signature(func).parameters
            if name.endswith("_digest")
        ]
        assert offenders == [], (
            f"{owner} 又开始接收 {offenders} —— identity digest 只能在 room lock 内从"
            "服务端行派生（leader 的 confirmation → representation）。留一个形参就等于"
            "留一条「调用方编一个 digest」的路，而 HTTP 层能编出来的只有空串"
        )


def test_the_close_intent_endpoint_reads_no_digest_out_of_the_request_body() -> None:
    """路由处理函数体内不得出现任何 `payload` 里的 `*_digest` 键。

    与上一条不重复：签名判据管的是「服务端不收」，这条管的是「路由不读」。两者分开才
    能分辨「参数删了但路由仍在解析 body 并丢弃」这种半修（那会让前端继续送一个永远
    没人看的字段，下一个人照着它再接一遍）。
    """
    router_src = (
        _BACKEND / "app" / "routers" / "wp_sync_router.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(router_src)
    handler = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and node.name == "create_close_intent"
        ),
        None,
    )
    assert handler is not None, "路由里找不到 create_close_intent —— 判据失去承重对象"
    digest_keys = {
        node.value
        for node in ast.walk(handler)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.endswith("_digest")
    }
    assert digest_keys == set(), (
        f"create_close_intent 处理函数里仍在读 {sorted(digest_keys)} —— "
        "客户端拿不到这些值，读它只会读到空串"
    )


class _ScalarOnce:
    """`session.execute()` 的最小返回面：只有 `scalar_one_or_none()`。"""

    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _RecordingSession:
    """记录被执行的 statement 的最小 session stand-in。"""

    def __init__(self, value: Any) -> None:
        self._value = value
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> _ScalarOnce:
        self.statements.append(statement)
        return _ScalarOnce(self._value)


def _repo_with(value: Any) -> tuple[Any, _RecordingSession, Any]:
    from app.models.workpaper_sync_models import WorkpaperOoClientConfirmation
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository

    session = _RecordingSession(value)
    repo = WorkpaperSyncRepository(session)  # type: ignore[arg-type]
    confirmation = WorkpaperOoClientConfirmation(
        id=_ID_MID, representation_id=_ID_HIGH
    )
    return repo, session, confirmation


@pytest.mark.asyncio
async def test_capture_freezes_the_adapter_build_of_the_representation_it_froze_as_base() -> None:
    """代码身份取自 **leader confirmation 的那份 representation**，且按它的 id 查。

    只断「返回值等于库里的值」不够：那样一个「查任意一行 representation」的实现也能通过，
    而模板升级后的 room 里「任意一行」与冻结的 base 不同代际，extract 会少一半字段且
    不报错（recovery claim 那边的注释写的就是这个）。所以这里连 WHERE 绑的 id 一起断。
    """
    digest = "a" * 64
    repo, session, confirmation = _repo_with(digest)

    got = await repo._frozen_base_adapter_build_digest(confirmation)

    assert got == digest
    assert len(session.statements) == 1, session.statements
    bound = set(session.statements[0].compile().params.values())
    assert _ID_HIGH in bound, (
        f"查询没有按 confirmation.representation_id={_ID_HIGH} 绑定，实得 {bound} —— "
        "换成任意一行 representation 会冻结出一个与 base 不同代际的代码身份"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value, label",
    [
        (None, "representation 行不存在"),
        ("", "空串"),
        ("0" * 64, "全零"),
        ("A" * 64, "大写 hex"),
        ("a" * 63, "长度不足"),
    ],
    ids=["missing_row", "empty", "all_zero", "uppercase", "too_short"],
)
async def test_unusable_adapter_build_fails_visible_instead_of_freezing_a_fake_identity(
    value: Any, label: str
) -> None:
    """取不到 / 非法一律抛 —— 绝不把「身份未知」冻结成一份合法身份。

    这是本缺陷的**反面**：旧实现在 HTTP 层用 `or ""` 把「不知道」补成空串，一路带到
    fingerprint 才炸；而 fingerprint 是 idempotency cache hit 的唯一判据，若它哪天放过
    空串，两次不同身份的请求会被判成同一次重放。
    """
    from app.services.workpaper_sync.models import IdentityError

    repo, _session, confirmation = _repo_with(value)

    with pytest.raises(IdentityError) as excinfo:
        await repo._frozen_base_adapter_build_digest(confirmation)
    assert "close-capture" in str(excinfo.value), (label, str(excinfo.value))
