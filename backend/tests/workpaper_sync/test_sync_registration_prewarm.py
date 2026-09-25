# -*- coding: utf-8 -*-
"""冷注册预热 + 串行锁守卫。

背景（2026-09-22 活体实测，重启后端后直接打 store-projection）：

    GET #1  200   32325.3 ms
    GET #2  200     232.2 ms
    GET #3  200     291.6 ms

差的那 32 秒**不在** projection 计算里，而在「4 条 pilot attach + register_from_manifest
（186 条 entry）」这段冷注册 —— 它此前完整发生在**首个** sync 请求内。用户点「在线编辑」
看到的就是那 32 秒。

两条不变量：

1. **串行**：并发首请求只建一次冷注册。没有锁时 N 个并发请求各跑一遍 30s（CPU 互抢 +
   openpyxl 全簿解析 ×N 份内存），比串行更慢。
2. **预热走同一条代码**：预热必须调用请求路径用的那个函数，否则会出现「预热建的缓存
   与请求要的不是一回事」——那种预热是纯浪费且看不出来。

本文件不碰真实 PG：注册与指纹两处都换成可计数的替身，测的是**编排**（锁/重查/复用），
而注册准入判据本身由 Task 75 的判据守。
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import textwrap
import uuid

import pytest

from app.routers import wp_sync_router as router_mod
from app.services.workpaper_sync import startup_prewarm as prewarm_mod


@pytest.fixture(autouse=True)
def _clean_registration_cache():
    """每个用例独立：清 ROI-0 缓存与锁，避免跨用例串味。"""
    router_mod._REGISTRATION_CACHE = type(router_mod._REGISTRATION_CACHE)(maxsize=8)
    router_mod._REGISTRATION_BUILD_LOCK = None
    yield
    router_mod._REGISTRATION_CACHE = type(router_mod._REGISTRATION_CACHE)(maxsize=8)
    router_mod._REGISTRATION_BUILD_LOCK = None


class _FakeRegistry:
    """只实现注册路径用到的三个方法。"""

    def __init__(self) -> None:
        self._registrations: list[object] = []
        self.manifest_entries = ("e1", "e2")

    def registrations(self):
        return tuple(self._registrations)

    def register(self, registration) -> None:
        self._registrations.append(registration)

    async def register_from_manifest(self, *, session):  # noqa: ARG002
        await asyncio.sleep(0.05)  # 模拟冷注册耗时，给并发留出重叠窗口

        class _Outcome:
            registered_adapter_ids = ("manifest-adapter",)

        return _Outcome()


def _install_fakes(monkeypatch, *, counter: list[str]) -> None:
    """把四条 pilot attach + 指纹换成计数替身。"""

    async def fake_fingerprint(svc):  # noqa: ARG001
        return "FIXED-FINGERPRINT"

    monkeypatch.setattr(router_mod, "_registration_state_fingerprint", fake_fingerprint)

    async def make_attach(name: str):
        async def attach(registry, *, session):  # noqa: ARG001
            counter.append(name)
            await asyncio.sleep(0.05)
            return (f"{name}-adapter",)

        return attach

    for module_path, label in (
        ("app.services.workpaper_sync.pilot_simple_checklist", "simple"),
        ("app.services.workpaper_sync.pilot_d2_large_json", "d2"),
        ("app.services.workpaper_sync.pilot_h1_grouped_dynamic", "h1"),
        ("app.services.workpaper_sync.pilot_g7_two_level_dynamic", "g7"),
    ):
        module = __import__(module_path, fromlist=["attach_pilot_adapters"])

        async def attach(registry, *, session, _label=label):  # noqa: ARG001
            counter.append(_label)
            await asyncio.sleep(0.05)
            return (f"{_label}-adapter",)

        monkeypatch.setattr(module, "attach_pilot_adapters", attach)


UUID_WP = uuid.UUID("b3ab3c46-828f-4f48-950e-aee9bbdc923f")
UUID_PROJECT = uuid.UUID("0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49")


def _context(registry=None):
    return router_mod._RegistrationWarmupContext(
        session=object(), registry=registry or _FakeRegistry()
    )


# ═══ 1. 冷注册串行化 ═══


@pytest.mark.asyncio
async def test_concurrent_cold_requests_build_the_registration_only_once(
    monkeypatch,
) -> None:
    calls: list[str] = []
    _install_fakes(monkeypatch, counter=calls)

    results = await asyncio.gather(
        *(router_mod._attach_pilot_adapters(_context()) for _ in range(6))
    )

    assert calls.count("d2") == 1, (
        f"6 个并发冷请求触发了 {calls.count('d2')} 次 pilot attach —— "
        "冷注册未串行化，每个请求都在跑 30s 的整册解析"
    )
    assert all(r == results[0] for r in results), "并发请求拿到了不一致的 adapter_ids"
    assert "manifest-adapter" in results[0]


@pytest.mark.asyncio
async def test_cache_hit_path_does_not_take_the_lock(monkeypatch) -> None:
    """绝大多数请求走缓存命中；它们不得被冷注册的锁挡住。"""
    calls: list[str] = []
    _install_fakes(monkeypatch, counter=calls)

    await router_mod._attach_pilot_adapters(_context())
    assert calls.count("d2") == 1

    lock = router_mod._registration_build_lock()
    await lock.acquire()  # 模拟另一个冷注册正持锁
    try:
        # 命中缓存的请求必须立刻返回（若它要等锁，这里会超时）
        got = await asyncio.wait_for(
            router_mod._attach_pilot_adapters(_context()), timeout=1.0
        )
    finally:
        lock.release()
    assert "manifest-adapter" in got
    assert calls.count("d2") == 1, "缓存命中路径不该再次注册"


@pytest.mark.asyncio
async def test_second_waiter_rechecks_cache_after_acquiring_the_lock(
    monkeypatch,
) -> None:
    """等到锁之后必须重查缓存 —— 否则串行化只是把 N 次 30s 排成队，总耗时不变。"""
    calls: list[str] = []
    _install_fakes(monkeypatch, counter=calls)

    await asyncio.gather(
        router_mod._attach_pilot_adapters(_context()),
        router_mod._attach_pilot_adapters(_context()),
        router_mod._attach_pilot_adapters(_context()),
    )
    assert calls.count("g7") == 1, (
        f"等锁者没有重查缓存（g7 attach 跑了 {calls.count('g7')} 次）—— "
        "锁只把并发排成串行，30s×N 的总成本没省掉"
    )


# ═══ 2. 预热走请求路径的同一条代码 ═══


def _called_names(func) -> set[str]:
    """AST 取**真实被调用**的名字。

    🔴 不能用子串判 `"_attach_pilot_adapters" in source`：本函数 docstring 里就写着
    ``:func:`_attach_pilot_adapters```，于是把调用改掉、只留注释时判据仍然绿（本轮变异
    检验实测 SURVIVED 过一次）。只看 AST 的 Call 节点，注释与 docstring 一律不算。
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Name):
                names.add(target.id)
            elif isinstance(target, ast.Attribute):
                names.add(target.attr)
    return names


def test_prewarm_delegates_to_the_request_path_function() -> None:
    called = _called_names(prewarm_mod.prewarm_sync_registration_cache)
    assert "_attach_pilot_adapters" in called, (
        f"预热没有**调用**请求路径的 _attach_pilot_adapters（实际调用 {sorted(called)}）"
        " —— 预热建的缓存与请求需要的不是一回事时，预热是纯浪费且无法察觉"
    )
    assert "build_production_registry" in called, "预热必须用生产 registry 构造点"


@pytest.mark.asyncio
async def test_prewarm_populates_the_cache_so_the_first_request_hits_it(
    monkeypatch,
) -> None:
    calls: list[str] = []
    _install_fakes(monkeypatch, counter=calls)

    class _FakeSessionCtx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(
        "app.core.database.async_session", lambda: _FakeSessionCtx(), raising=True
    )
    # 预热模块在函数体内 import 构造点 ⇒ 打在真源模块上才生效。
    monkeypatch.setattr(
        "app.services.workpaper_sync.adapters.registry.build_production_registry",
        lambda **kw: _FakeRegistry(),
        raising=True,
    )

    await prewarm_mod.prewarm_sync_registration_cache()
    assert calls.count("d2") == 1, "预热没有真的执行注册"

    # 预热之后，首个真实请求必须命中缓存（不再触发 attach）
    await router_mod._attach_pilot_adapters(_context())
    assert calls.count("d2") == 1, (
        "预热后首请求仍走了冷注册 —— 预热没有落进请求路径读的那个缓存"
    )


def test_warmup_context_exposes_exactly_what_the_registration_path_needs() -> None:
    """预热上下文不得伪造 guard/user：注册路径只该用 session + registry。"""
    fields = set(router_mod._RegistrationWarmupContext.__dataclass_fields__)
    assert fields == {"session", "registry"}, (
        f"预热上下文字段漂移：{sorted(fields)} —— 多出来的字段说明注册路径开始依赖"
        "请求态（user/guard），预热就不再等价于请求路径"
    )

    attach_source = inspect.getsource(router_mod._attach_pilot_adapters)
    forbidden = [
        token
        for token in ("svc.user_id", "svc.probe", "svc.guard", "svc.scope")
        if token in attach_source
    ]
    assert not forbidden, (
        f"_attach_pilot_adapters 用到了请求态 {forbidden} —— 预热上下文给不出这些，"
        "预热会在启动时崩（或被迫伪造匿名用户）"
    )


# ═══ 2b. 基线 projection 预热（第二段） ═══


def test_baseline_projection_prewarm_only_touches_switchable_entries() -> None:
    """只预热能切 OO 的 entry：其余 entry 预热了也没人走 OO 往返，纯浪费后台 CPU。"""
    called = _called_names(prewarm_mod.prewarm_sync_baseline_projections)
    assert "assert_bidirectional_ready" in called, (
        f"没有按 bidirectional 过滤（实际调用 {sorted(called)}）—— "
        "会把 store-only entry 也整册反读一遍"
    )
    assert "compute_store_projection_response" in called, (
        "预热没有调用端点用的那个 projection 函数 —— 建的缓存与请求要的不是一回事"
    )
    assert "_attach_pilot_adapters" in called, "projection 预热前必须先有注册"


def test_baseline_projection_prewarm_is_bounded() -> None:
    """库长大后预热不得变成无界后台负载。"""
    assert isinstance(prewarm_mod.PREWARM_PROJECTION_MAX_ENTRIES, int)
    assert 0 < prewarm_mod.PREWARM_PROJECTION_MAX_ENTRIES <= 256

    source = inspect.getsource(prewarm_mod.prewarm_sync_baseline_projections)
    assert ".limit(PREWARM_PROJECTION_MAX_ENTRIES)" in source, (
        "枚举 entry_state 时没有 LIMIT —— 上限常量存在但没接上，等于没有上限"
    )
    assert "gather" not in source, (
        "预热不得并发：这些解析 CPU 密集且持 GIL，并发只会和前台请求互抢"
    )


def test_baseline_projection_prewarm_skips_a_failing_entry_instead_of_aborting(
    monkeypatch,
) -> None:
    """单 entry 失败只跳过：一个坏底稿不得让整段预热（以及后面的 entry）全丢。"""
    source = inspect.getsource(prewarm_mod.prewarm_sync_baseline_projections)
    # 两处 except 分别对应「非 bidirectional」与「projection 算不出来」，都必须 continue/跳过。
    # 🔴 必须是**两个不同**的计数器：合并成一个 `skipped` 时，「暖 5 / 跳过 7」与
    # 「暖 4 / 跳过 8（含 1 个异常）」在日志里长相一致 ⇒ 故障与健康不可区分。
    assert "not_eligible += 1" in source, (
        "非 bidirectional 分流没有独立计数 —— 与真失败混在一个数里就分不出故障"
    )
    assert "failed += 1" in source, (
        "projection 抛错没有独立计数 —— 真故障会被当成正常跳过"
    )
    assert "raise" not in source.split('"""')[-1], (
        "预热里出现 raise —— 会把失败冒泡成启动告警/任务崩溃"
    )


def test_baseline_projection_failure_is_logged_above_info() -> None:
    """🔴 失败详情必须 WARNING 起步：生产 log_level=WARNING，info 一律不输出。

    这正是本次修复的起因 —— 失败分支原本只 `logger.info`，于是「预热失败」在生产上
    既不体现在汇总数字里（被并进 skipped），也不体现在日志里（info 被过滤），
    完全静默。判据盯的是失败分支本身，不是整个函数里出现过 warning 就算过。
    """
    source = inspect.getsource(prewarm_mod.prewarm_sync_baseline_projections)
    failure_branch = source.split("failed += 1", 1)[-1]
    assert "logger.warning" in failure_branch, (
        "failed 分支没有 logger.warning —— log_level=WARNING 下预热失败完全静默"
    )


def test_every_deferred_import_inside_the_prewarm_actually_resolves() -> None:
    """🔴 函数体内的延迟 import 必须**真的**能解析到那个名字。

    本轮真栈实测的漏网：`prewarm_sync_baseline_projections` 里写了
    ``from app.models.core import WorkingPaper``，而 `WorkingPaper` 住在
    `app.models.workpaper_models`。后果是第二段预热每次启动都抛
    ``cannot import name 'WorkingPaper'``、被「失败不阻塞启动」如实吞成一条 WARNING，
    于是**预热看起来接好了、实际从未跑过**（首请求仍 2.5s 而不是 0.12s）。

    为什么原有判据抓不到：那一组是 AST / 源码文本判据（「有没有调用
    assert_bidirectional_ready」「有没有 LIMIT」），它们只看**写了什么**，
    看不出「写的这个名字在那个模块里不存在」。延迟 import 又不会在模块导入期报错。
    本判据把两段预热函数体里的每条 `from X import a, b` 真的 import 一遍。
    """
    import importlib

    for func in (
        prewarm_mod.prewarm_sync_registration_cache,
        prewarm_mod.prewarm_sync_baseline_projections,
    ):
        tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
        checked = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            module = importlib.import_module(node.module)
            for alias in node.names:
                assert hasattr(module, alias.name), (
                    f"{func.__name__} 里 `from {node.module} import {alias.name}` "
                    f"解析不到 —— 延迟 import 不会在模块导入期报错，这条会被"
                    "「预热失败不阻塞启动」吞成一条 WARNING，预热从此静默不跑"
                )
                checked += 1
        assert checked > 0, f"{func.__name__} 里没扫到任何延迟 import —— 判据恒真"


@pytest.mark.asyncio
async def test_baseline_projection_prewarm_really_runs_and_splits_warmed_from_skipped(
    monkeypatch,
) -> None:
    """真跑第二段：只有源码级判据时，一个写错的 import 就能让它从未执行过。"""
    calls: list[str] = []
    _install_fakes(monkeypatch, counter=calls)

    rows = [
        (UUID_WP, "xlsx/gt-d4-operating-revenue", UUID_PROJECT),
        (UUID_WP, "xlsx/gt-d3-prepaid-accounts", UUID_PROJECT),  # 非 bidirectional
        (UUID_WP, "xlsx/gt-g7-long-term-equity-main", UUID_PROJECT),  # projection 抛错
    ]

    class _Result:
        def all(self):
            return rows

    class _FakeSession:
        async def execute(self, *_args, **_kwargs):
            return _Result()

    class _FakeSessionCtx:
        async def __aenter__(self):
            return _FakeSession()

        async def __aexit__(self, *exc):
            return False

    class _RegistryWithGate(_FakeRegistry):
        def assert_bidirectional_ready(self, entry_id: str):
            if "d3-prepaid" in entry_id:
                raise RuntimeError("不是 bidirectional")
            return object()

    monkeypatch.setattr(
        "app.core.database.async_session", lambda: _FakeSessionCtx(), raising=True
    )
    monkeypatch.setattr(
        "app.services.workpaper_sync.adapters.registry.build_production_registry",
        lambda **kw: _RegistryWithGate(),
        raising=True,
    )

    projected: list[str] = []

    async def fake_projection(*, entry_id, **_kwargs):
        projected.append(str(entry_id))
        if "g7" in str(entry_id):
            raise RuntimeError("这张表算不出来")
        return {"values": {}}

    monkeypatch.setattr(
        "app.services.workpaper_sync.store_projection_response"
        ".compute_store_projection_response",
        fake_projection,
        raising=True,
    )

    outcome = await prewarm_mod.prewarm_sync_baseline_projections()

    assert projected == [
        "xlsx/gt-d4-operating-revenue",
        "xlsx/gt-g7-long-term-equity-main",
    ], f"非 bidirectional 的 entry 不该被投影，实际投影了 {projected}"
    assert outcome.warmed == 1, f"成功数应为 1（只有 D4 算成功），实际 {outcome.warmed}"
    # 🔴 D3（非双向，设计内分流）与 G7（projection 抛错，真故障）必须落在**不同**的数上：
    # 这两件事都让 entry 没暖到，但只有后者需要有人去看。
    assert outcome.not_eligible == 1, (
        f"不适用数应为 1（D3 非双向），实际 {outcome.not_eligible}"
    )
    assert outcome.failed == 1, (
        f"失败数应为 1（G7 抛错），实际 {outcome.failed} —— "
        "真故障被并进「不适用」就等于没被报告"
    )


# ═══ 3. 启动接线 ═══


def test_startup_schedules_the_prewarm_in_the_background() -> None:
    """预热必须是后台任务：25~30s 若 await 在 Ready 之前会把 health 等待拖超时。"""
    from app import main as main_mod

    lifespan_source = inspect.getsource(main_mod.lifespan)
    assert "_warm_workpaper_sync_registry" in lifespan_source, (
        "lifespan 没有接预热 —— 首个 sync 请求仍要自己付 30s"
    )
    assert "create_task(_warm_workpaper_sync_registry())" in lifespan_source, (
        "预热被 await 在启动路径上 —— 会把 Ready 推迟 25~30s"
    )
    assert "tasks.append" in lifespan_source, (
        "后台任务未存引用 —— 可能被 GC 静默回收，预热白做"
    )

    warm_source = inspect.getsource(main_mod._warm_workpaper_sync_registry)
    assert "except Exception" in warm_source, "预热失败必须被吞（不阻塞启动）"
    assert "CancelledError" in warm_source, (
        "关闭阶段的 cancel 不得被当成预热失败记 WARNING"
    )

    warm_calls = _called_names(main_mod._warm_workpaper_sync_registry)
    for required in (
        "prewarm_sync_registration_cache",
        "prewarm_sync_baseline_projections",
    ):
        assert required in warm_calls, (
            f"启动预热没有调用 {required}（实际 {sorted(warm_calls)}）—— "
            "少一段就有一段成本留在用户的首次点击里"
        )


def test_startup_log_reports_projection_failures_as_their_own_number() -> None:
    """启动汇总行必须把「失败」单独报出来，而不是并进「跳过」。

    预热失败**按设计**不阻塞启动，那么这条汇总行就是运维唯一的信号面：它若把
    「本就不该预热」与「该预热但炸了」印成同一个数，「有故障」与「一切正常」在
    日志里就是同一个样子，于是「失败不阻塞启动」退化成「失败不被知道」。
    """
    from app import main as main_mod

    warm_source = inspect.getsource(main_mod._warm_workpaper_sync_registry)
    assert "outcome.failed" in warm_source, (
        "汇总日志没有单独打印失败数 —— 故障与健康在日志里长得一样"
    )
    assert "outcome.not_eligible" in warm_source, (
        "汇总日志没有单独打印不适用数 —— 与失败混在一个数里就分不出哪种"
    )
    assert "跳过 %d 个" not in warm_source, (
        "仍在用合并的「跳过」口径 —— 本次修复正是要拆掉它"
    )
