"""R14 生产接线 + R15 / R16 注册缓存（零数据库，结构 + 编排判据）。

spec: d2-online-edit-platform-closure · R14 / R15 / R16

从 ``test_target_bound_registration.py`` 原样迁出（§4~§7，行数门：单文件 ≤ 800）。两份共用的
只有 ``ENTRY`` / ``OTHER_ENTRY`` 两个字面量与 ``_Result`` 的形状，这里各自声明，不跨测试模块 import。

* §4 生产接线（AST）：三个调用点都经绑定入口，且按**本行 / 本请求**的底稿绑；
* §5 全部 provider 都经共享解析器取 representation（pin 才对全平台生效）；
* §6 R15：entry 级注册缓存的指纹不随「保存」变（只随首版发布 / bundle 重发布变）；
* §7 R16：callback apply 复用同一份 entry 级注册缓存，失败不冒出 apply。
"""
from __future__ import annotations

import ast
import importlib
import inspect
import os
import sys
import textwrap
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Final

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync.adapters import registry as RG  # noqa: E402

#: 与 ``test_target_bound_registration.py`` 同值（指纹判据只需要两个互不相同的 entry 名）。
ENTRY = "xlsx/r14-target-entry"
OTHER_ENTRY = "xlsx/r14-other-entry"


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)

    def scalars(self) -> Any:
        rows = self._rows

        class _Scalars:
            def first(self) -> Any:
                return rows[0][0] if rows else None

        return _Scalars()


# ═══════════════════════════════════════════════════════════════════════════
# 4. 生产接线：三个调用点都经绑定入口，且按本请求 / 本行的底稿绑
# ═══════════════════════════════════════════════════════════════════════════

_ROUTER = _BACKEND / "app" / "routers" / "wp_sync_router.py"
_PREWARM = _BACKEND / "app" / "services" / "workpaper_sync" / "startup_prewarm.py"


def _function(path: Path, name: str) -> ast.AsyncFunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name
    )


def _awaited_bind_calls(fn: ast.AST) -> list[ast.Call]:
    return [
        node.value
        for node in ast.walk(fn)
        if isinstance(node, ast.Await)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "bind_registration_to_target"
    ]


def _kw(call: ast.Call, name: str) -> str:
    for kw in call.keywords:
        if kw.arg == name:
            return ast.unparse(kw.value)
    raise AssertionError(f"调用缺关键字参数 {name}=")


class TestProductionWiring:
    # 🔴 参数里放模块全局名而不是 Path：parametrize 在 import 时求值，直接放 `_ROUTER`
    #    会把路径冻进参数，变异探针改写模块全局后判据仍读旧文件（W2/W3 实测漏网）。
    @pytest.mark.parametrize(
        "path_name, func, wp_expr",
        [
            ("_ROUTER", "_registration", "scope.wp_id"),
            ("_ROUTER", "_apply_durable_incoming", "app_row.wp_id"),
            ("_PREWARM", "prewarm_sync_baseline_projections", "wp_id"),
        ],
    )
    def test_every_production_path_binds_to_its_own_workpaper(
        self, path_name: str, func: str, wp_expr: str
    ) -> None:
        calls = _awaited_bind_calls(_function(globals()[path_name], func))
        assert len(calls) == 1, f"{func} 应恰好 await 一次 bind_registration_to_target，实为 {len(calls)}"
        assert _kw(calls[0], "wp_id") == wp_expr, (
            f"{func} 按 {_kw(calls[0], 'wp_id')} 绑定 —— 必须是本请求/本行的底稿 {wp_expr}"
        )

    @pytest.mark.parametrize("func", ["_registration", "_apply_durable_incoming"])
    def test_router_never_hands_out_the_entry_level_registration_directly(
        self, func: str
    ) -> None:
        """两条路径都不得再把 `registry.assert_bidirectional_ready(...)` 的结果直接交给端点。"""
        fn = _function(_ROUTER, func)
        direct = [
            ast.unparse(node)
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "assert_bidirectional_ready"
        ]
        assert not direct, f"{func} 仍直接取 entry 级注册: {direct}"

    def test_registration_binding_sits_inside_the_422_translation(self) -> None:
        fn = _function(_ROUTER, "_registration")
        for node in ast.walk(fn):
            if not isinstance(node, ast.Try):
                continue
            handled = {
                elt.id
                for handler in node.handlers
                for elt in (
                    handler.type.elts
                    if isinstance(handler.type, ast.Tuple)
                    else [handler.type]
                )
                if isinstance(elt, ast.Name)
            }
            if "SyncDomainError" in handled and any(
                _awaited_bind_calls(stmt) for stmt in node.body
            ):
                return
        raise AssertionError("绑定调用不在 SyncDomainError→422 的 try 里 —— 绑不上会冒成 500")


# ═══════════════════════════════════════════════════════════════════════════
# 5. 全部 provider 都经共享解析器取 representation（pin 才对全平台生效）
# ═══════════════════════════════════════════════════════════════════════════

_RESOLVER = "resolve_visible_current_representation_id"

#: 不造 adapter 的 provider（capability 未放行恒返回空 / 显式 raise）。豁免必须可证伪：
#: 它们的 attach 源码里不得出现 `register` / `build_excel_adapter`。
_NO_ADAPTER_PROVIDERS: Final[dict[str, str]] = {
    "app.services.workpaper_sync.phase5_e1_monetary_fund": (
        "E1 capability 关闭：attach 恒返回空或显式 raise，不造 adapter（BP-61-1）"
    ),
}


def _reaches_resolver(fn: Any, *, depth: int = 0) -> bool:
    """attach 自身或它 await 的公共骨架（H/L 循环 common）里调用了共享解析器。"""
    source = textwrap.dedent(inspect.getsource(fn))
    tree = ast.parse(source)
    names = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    if _RESOLVER in names:
        return True
    if depth >= 2:
        return False
    module = inspect.getmodule(fn)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Await) and isinstance(node.value, ast.Call)):
            continue
        target = node.value.func
        resolved: Any = None
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
            holder = getattr(module, target.value.id, None)
            resolved = getattr(holder, target.attr, None)
        elif isinstance(target, ast.Name):
            resolved = getattr(module, target.id, None)
        if callable(resolved) and _reaches_resolver(resolved, depth=depth + 1):
            return True
    return False


def test_every_registered_provider_reaches_the_shared_resolver() -> None:
    offenders: list[str] = []
    checked = 0
    for module_path in sorted(RG._ALLOWED_PROVIDER_MODULES):
        attach = getattr(importlib.import_module(module_path), "attach_pilot_adapters")
        if module_path in _NO_ADAPTER_PROVIDERS:
            source = inspect.getsource(attach)
            assert ".register(" not in source and "build_excel_adapter" not in source, (
                f"{module_path} 登记为「不造 adapter」却在 attach 里注册 —— 豁免失效"
            )
            continue
        checked += 1
        if not _reaches_resolver(attach):
            offenders.append(module_path)
    assert checked >= 80, f"分母异常：只检查了 {checked} 个 provider"
    assert not offenders, (
        f"这些 provider 不经共享解析器取 representation：{offenders} —— 请求期 pin 管不到它们，"
        "同一 entry 的第二家企业会拿到第一家的冻结身份（R14）"
    )


def test_no_adapter_exemption_is_stale() -> None:
    for module_path in _NO_ADAPTER_PROVIDERS:
        assert module_path in RG._ALLOWED_PROVIDER_MODULES, f"豁免条目已失效: {module_path}"


# ═══════════════════════════════════════════════════════════════════════════
# 6. R15：entry 级注册缓存的指纹不随「保存」变（只随首版发布 / bundle 重发布变）
# ═══════════════════════════════════════════════════════════════════════════


class _FingerprintSession:
    """两条 ORM 查询的替身：① entry_state 指针 ② 指针所指 representation 的 bundle。"""

    def __init__(self, pointers: list[tuple[str, uuid.UUID, uuid.UUID]], bundle_of: dict[uuid.UUID, uuid.UUID]) -> None:
        self.pointers = pointers
        self.bundle_of = bundle_of
        self.calls = 0

    async def execute(self, statement: Any) -> _Result:
        self.calls += 1
        if self.calls == 1:
            return _Result(list(self.pointers))
        return _Result([(rep, bundle) for rep, bundle in self.bundle_of.items()])


async def _fingerprint(pointers: list[tuple[str, uuid.UUID, uuid.UUID]], bundle_of: dict[uuid.UUID, uuid.UUID]) -> tuple[str, int]:
    from types import SimpleNamespace

    from app.routers import wp_sync_router as SR

    session = _FingerprintSession(pointers, bundle_of)
    registry = SimpleNamespace(manifest_entries={ENTRY: {}, OTHER_ENTRY: {}})
    fingerprint = await SR._registration_state_fingerprint(
        SimpleNamespace(session=session, registry=registry)
    )
    return fingerprint, session.calls


class TestRegistrationFingerprint:
    @pytest.mark.asyncio
    async def test_a_new_generation_under_the_same_bundle_keeps_the_fingerprint(self) -> None:
        """保存（新代际、同 bundle）不得让全平台的 entry 级注册冷建（实测 30~38s）。"""
        wp_a, wp_b, bundle = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        rep_a1, rep_a2, rep_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        before, _ = await _fingerprint(
            [(ENTRY, wp_a, rep_a1), (ENTRY, wp_b, rep_b)], {rep_a1: bundle, rep_b: bundle}
        )
        after, _ = await _fingerprint(
            [(ENTRY, wp_a, rep_a2), (ENTRY, wp_b, rep_b)], {rep_a2: bundle, rep_b: bundle}
        )
        assert before == after

    @pytest.mark.asyncio
    async def test_first_publication_on_another_workpaper_changes_it(self) -> None:
        wp_a, wp_c, bundle = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        rep_a, rep_c = uuid.uuid4(), uuid.uuid4()
        before, _ = await _fingerprint([(ENTRY, wp_a, rep_a)], {rep_a: bundle})
        after, _ = await _fingerprint(
            [(ENTRY, wp_a, rep_a), (ENTRY, wp_c, rep_c)], {rep_a: bundle, rep_c: bundle}
        )
        assert before != after, "新供给（首版发布）必须触发 entry 级注册重建"

    @pytest.mark.asyncio
    async def test_a_bundle_republish_changes_it(self) -> None:
        """契约 / 模板重发布换了 bundle ⇒ 必须重建，否则重放会撞 RG-11 stale。"""
        wp_a = uuid.uuid4()
        rep_old, rep_new = uuid.uuid4(), uuid.uuid4()
        before, _ = await _fingerprint([(ENTRY, wp_a, rep_old)], {rep_old: uuid.uuid4()})
        after, _ = await _fingerprint([(ENTRY, wp_a, rep_new)], {rep_new: uuid.uuid4()})
        assert before != after

    @pytest.mark.asyncio
    async def test_no_pointer_means_no_representation_query(self) -> None:
        _, calls = await _fingerprint([], {})
        assert calls == 1, "零指针时不该去查 representation 表"


# ═══════════════════════════════════════════════════════════════════════════
# 7. R16：callback apply 复用同一份 entry 级注册缓存，失败不冒出 apply
# ═══════════════════════════════════════════════════════════════════════════


class TestCallbackApplyUsesTheRegistrationCache:
    def _try_holding_the_binding(self) -> ast.Try:
        fn = _function(_ROUTER, "_apply_durable_incoming")
        for node in ast.walk(fn):
            if isinstance(node, ast.Try) and any(_awaited_bind_calls(stmt) for stmt in node.body):
                return node
        raise AssertionError("_apply_durable_incoming 里找不到包住绑定调用的 try")

    def test_cache_lookup_and_replay_happen_before_the_binding(self) -> None:
        """callback apply 经共享注册入口（ROI-0 缓存 + 冷建锁 + 写回缓存），且在绑定之前。

        原判据要求本函数自己查缓存 / 重放；那份内联冷建不拿锁、不写缓存（启动预热期间回调与
        预热各冷建一遍，实测 95.7 s），spec writeback-followup-issue-closure P4 收进同一入口。
        """
        body = self._try_holding_the_binding().body
        shared_at = next(
            (i for i, stmt in enumerate(body)
             if "_attach_pilot_adapters" in {
                 getattr(n.value.func, "id", None)
                 for n in ast.walk(stmt) if isinstance(n, ast.Await) and isinstance(n.value, ast.Call)
             }),
            None,
        )
        bind_at = next((i for i, stmt in enumerate(body) if _awaited_bind_calls(stmt)), None)
        assert shared_at is not None and bind_at is not None and shared_at < bind_at, (
            "callback apply 没在绑定之前经过共享注册入口 `_attach_pilot_adapters`"
        )
        shared = _function(_ROUTER, "_attach_pilot_adapters")
        names = {
            n.func.id if isinstance(n.func, ast.Name) else n.func.attr
            for n in ast.walk(shared)
            if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute))
        }
        for required in (
            "_registration_state_fingerprint",
            "_replay_cached_registrations",
            "_registration_build_lock",
            "put",
        ):
            assert required in names, (
                f"共享注册入口缺 {required} —— 每次保存都可能冷建 30s+ 的注册"
            )

    def test_registration_failures_stay_inside_the_apply(self) -> None:
        """incoming 已 durable：注册 / 重放抛的域异常只能留在 operation 上，不得冒成 500。"""
        node = self._try_holding_the_binding()
        awaited = {
            sub.value.func.attr if isinstance(sub.value.func, ast.Attribute) else getattr(sub.value.func, "id", "")
            for sub in ast.walk(node)
            if isinstance(sub, ast.Await) and isinstance(sub.value, ast.Call)
        }
        assert "_attach_pilot_adapters" in awaited, (
            "注册不在包住绑定的同一个 try 里 —— 它抛的 SyncDomainError 会穿出 apply"
        )
        handled = {
            elt.id
            for handler in node.handlers
            for elt in (handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type])
            if isinstance(elt, ast.Name)
        }
        assert {"RegistryError", "SyncDomainError"} <= handled


class _AppRowSession:
    """`_apply_durable_incoming` 的查询替身：application 行 + 目标底稿 current representation。

    后者给按 entry 准备（spec oo-return-to-form-dead-end-and-save-speed R2）用：有 representation ⇒
    缓存冷也不整套建。
    """

    def __init__(self, app_row: Any, representation: Any = None) -> None:
        self.app_row = app_row
        self.representation = representation

    async def execute(self, statement: Any) -> Any:
        row, representation = self.app_row, self.representation

        class _One:
            def scalar_one_or_none(self) -> Any:
                return row

            def scalars(self) -> Any:
                return SimpleNamespace(first=lambda: representation)

        return _One()


async def _run_callback_registration(
    monkeypatch: pytest.MonkeyPatch, *, cache_hit: bool, representation: Any = None
) -> dict[str, Any]:
    """真跑 `_apply_durable_incoming` 的注册段：在绑定处截停，观察冷建有没有发生。"""

    from app.routers import wp_sync_router as SR

    calls: list[str] = []

    async def fake_fingerprint(svc: Any) -> str:
        return "R16-FINGERPRINT"

    monkeypatch.setattr(SR, "_registration_state_fingerprint", fake_fingerprint)
    monkeypatch.setattr(SR, "_REGISTRATION_CACHE", type(SR._REGISTRATION_CACHE)(maxsize=8))
    if cache_hit:
        SR._REGISTRATION_CACHE.put(
            "R16-FINGERPRINT", SR._RegistrationSnapshot(registrations=(), adapter_ids=())
        )
    for module_path, label in (
        ("app.services.workpaper_sync.pilot_simple_checklist", "simple"),
        ("app.services.workpaper_sync.pilot_d2_large_json", "d2"),
        ("app.services.workpaper_sync.pilot_h1_grouped_dynamic", "h1"),
        ("app.services.workpaper_sync.pilot_g7_two_level_dynamic", "g7"),
    ):
        async def attach(registry: Any, *, session: Any, _label: str = label) -> tuple[str, ...]:
            calls.append(_label)
            return ()

        monkeypatch.setattr(importlib.import_module(module_path), "attach_pilot_adapters", attach)

    class _Registry:
        manifest_entries: dict[str, Any] = {}

        def registrations(self) -> tuple[Any, ...]:
            return ()

        def register(self, registration: Any) -> None:  # pragma: no cover - 空快照
            calls.append("replay")

        async def register_from_manifest(self, *, session: Any) -> Any:
            calls.append("manifest")
            return SimpleNamespace(registered_adapter_ids=())

    monkeypatch.setattr(SR, "build_production_registry", lambda **_kw: _Registry())

    async def stop_at_binding(*, session: Any, registry: Any, entry_id: str, wp_id: Any) -> Any:
        calls.append(f"bind:{wp_id}")
        raise RG.AdapterNotRegisteredError("R16 探针：在绑定处截停")

    monkeypatch.setattr(SR, "bind_registration_to_target", stop_at_binding)
    # 冷建前的两段线程预热：源码事实（扫前端文件）与模板结构 hash。这里只看顺序，不真算。
    from app.services.workpaper_sync import entry_source_facts, registration_template_warmup

    monkeypatch.setattr(entry_source_facts, "warm_source_fact_caches", lambda: None)
    monkeypatch.setattr(
        registration_template_warmup,
        "warm_template_structure_hashes",
        lambda modules: calls.append("warm") or 0,
    )
    wp_id = uuid.uuid4()
    app_row = SimpleNamespace(entry_id=ENTRY, wp_id=wp_id)
    await SR._apply_durable_incoming(
        _AppRowSession(app_row, representation),
        outcome=SimpleNamespace(application_id=uuid.uuid4(), operation_id=uuid.uuid4()),
    )
    return {"calls": calls, "wp_id": wp_id}


@pytest.mark.asyncio
async def test_callback_apply_skips_the_cold_build_on_a_cache_hit(monkeypatch) -> None:
    got = await _run_callback_registration(monkeypatch, cache_hit=True)
    assert got["calls"] == [f"bind:{got['wp_id']}"], (
        f"缓存命中仍冷建了注册：{got['calls']} —— 每次保存都多等 30s+"
    )


@pytest.mark.asyncio
async def test_callback_apply_still_cold_builds_on_a_cache_miss(monkeypatch) -> None:
    """目标底稿还没有 representation：绑定会回落到 entry 级注册 ⇒ 缓存冷时仍须整套建。"""
    got = await _run_callback_registration(monkeypatch, cache_hit=False)
    # 模板结构 hash 在 attach 之前先在工作线程算（spec writeback-followup-issue-closure P4）
    assert got["calls"] == ["warm", "simple", "d2", "h1", "g7", "manifest", f"bind:{got['wp_id']}"], got


@pytest.mark.asyncio
async def test_callback_apply_skips_the_cold_build_when_the_workpaper_has_a_representation(monkeypatch) -> None:
    """🔴 判据改过（spec oo-return-to-form-dead-end-and-save-speed R2）：原先缓存冷即整套建。保存回调的
    底稿必有 current representation，apply 只按它现绑 ⇒ 不再排在 36~42 s 的整套冷建后面。"""
    got = await _run_callback_registration(monkeypatch, cache_hit=False, representation=uuid.uuid4())
    assert got["calls"] == [f"bind:{got['wp_id']}"], got
