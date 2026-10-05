"""公式推送端点：TestClient 真发请求（任务 12 · 需求 1.1 / 1.4 / 2.3）。

只 override ``get_current_user``（随请求切换身份）与 ``get_db``（SQLite 内存库）——
``require_project_access`` 是依赖工厂，每次调用返回新函数，override 工厂本身会静默失效；
这里让真实的项目权限判定（project_users 查询）照常执行，无权限用户走真 403。
取数层同引擎测试：``E1Binding.load_sources`` 换成固定源，其余全走真实代码。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import PermissionLevel, ProjectUserRole, UserRole
from app.models.core import ProjectUser, User
from app.routers.formula_push import router
from app.services.formula_push.bindings import get_binding, supported_wp_codes
from tests._formula_push_env import CASH_OPENING, YEAR, base_entries, make_env


@pytest_asyncio.fixture
async def env(monkeypatch):
    async with make_env(monkeypatch, extra_tables=(User.__table__, ProjectUser.__table__)) as e:
        yield e


class _Actor:
    def __init__(self, role: UserRole):
        self.id = uuid.uuid4()
        self.role = role
        self.username = f"u-{self.id.hex[:4]}"
        self.email = f"{self.username}@example.com"
        self.is_active = True


@pytest_asyncio.fixture
async def api(env):
    editor, reader, outsider = _Actor(UserRole.auditor), _Actor(UserRole.auditor), _Actor(UserRole.auditor)
    async with env.factory() as db:
        for actor, level in ((editor, PermissionLevel.edit), (reader, PermissionLevel.readonly)):
            db.add(ProjectUser(project_id=env.pid, user_id=actor.id, role=ProjectUserRole.auditor,
                               permission_level=level))
        await db.commit()
    app = FastAPI()
    app.include_router(router)
    who = {"actor": editor}

    async def _db():
        async with env.factory() as s:
            yield s

    async def _user():
        return who["actor"]

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield {
            "client": client, "env": env, "base": f"/api/projects/{env.pid}/formula-push",
            "as": lambda name: who.update(actor={"editor": editor, "reader": reader, "outsider": outsider}[name]),
        }



@pytest.mark.asyncio
async def test_rules_listing_is_readonly_and_chinese(api):
    c, base = api["client"], api["base"]
    api["as"]("reader")
    r = await c.get(f"{base}/rules", params={"wp_code": "E1"})
    assert r.status_code == 200, r.text
    payload = r.json()
    assert "E1" in payload["supported_wp_codes"] and "K1" in payload["supported_wp_codes"]
    assert len(payload["supported_wp_codes"]) == 20  # E1 + K1 + 18 Tier A
    rules = payload["rules"]
    assert len(rules) == 30 and {x["wp_code"] for x in rules} == {"E1"}  # wp_code 过滤只返回 E1 的 30 条
    tb = next(x for x in rules if x["rule_id"] == "E1.tb_amount.ending")
    assert tb["formula"].startswith("TB('1001','期末余额')") and "试算" in tb["description"]
    assert all(x["description"] and x["formula"] for x in rules), "面板每条规则都要有中文说明与算式"


@pytest.mark.asyncio
async def test_bindings_listing_is_readonly_and_returns_registry_shape(api):
    c, base = api["client"], api["base"]
    api["as"]("reader")
    r = await c.get(f"{base}/bindings")
    assert r.status_code == 200, r.text
    assert r.json() == {
        "supported_wp_codes": list(supported_wp_codes()),
        "bindings": [
            {"wp_code": code, "account_prefixes": list(get_binding(code).account_prefixes)}
            for code in supported_wp_codes()
        ],
    }


@pytest.mark.asyncio
async def test_bindings_listing_tracks_temporary_registry_registration_and_revoke(api):
    from app.services.formula_push.bindings import register_binding

    from tests._formula_push_binding import DummyPushBinding

    class FakeBinding(DummyPushBinding):
        wp_code = "Z9"
        account_prefixes = ("9901",)

    c, base = api["client"], api["base"]
    api["as"]("reader")
    revoke = register_binding("Z9", FakeBinding)
    try:
        r = await c.get(f"{base}/bindings")
        assert r.status_code == 200
        codes_with_z9 = r.json()["supported_wp_codes"]
        assert "Z9" in codes_with_z9
        assert len(codes_with_z9) == 21  # 20 permanent + Z9
        assert r.json()["bindings"][-1] == {"wp_code": "Z9", "account_prefixes": ["9901"]}
    finally:
        revoke()

    r = await c.get(f"{base}/bindings")
    assert r.status_code == 200
    codes_after = r.json()["supported_wp_codes"]
    assert "Z9" not in codes_after
    assert len(codes_after) == 20


@pytest.mark.asyncio
async def test_run_and_state_endpoints(api):
    c, base, env = api["client"], api["base"], api["env"]
    await env.seed_entries(base_entries())
    r = await c.post(f"{base}/run", json={"year": YEAR})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["written_count"] == 20 and body["kept_count"] == 2 and body["run_id"]
    assert (await env.entries())["E1-adj-tb-amount-ending"] == "606.73"

    api["as"]("reader")
    latest = (await c.get(f"{base}/latest", params={"year": YEAR})).json()
    assert latest["run"]["run_id"] == body["run_id"] and latest["run"]["trigger"] == "manual"
    assert latest["state_counts"]["pending_confirm"] == 2
    pending = (await c.get(f"{base}/states", params={"year": YEAR, "state": "pending_confirm"})).json()["states"]
    row = next(s for s in pending if s["addr_id"] == CASH_OPENING)
    assert (row["current_value"], row["formula_value"], row["differs"]) == (200.0, 286.73, True)
    assert (await c.get(f"{base}/states", params={"year": YEAR, "state": "bogus"})).status_code == 400


@pytest.mark.asyncio
async def test_dry_run_endpoint_leaves_no_trace(api):
    c, base, env = api["client"], api["base"], api["env"]
    await env.seed_entries(base_entries())
    before = await env.entries()
    r = await c.post(f"{base}/run", json={"year": YEAR, "dry_run": True})
    assert r.status_code == 200 and r.json()["dry_run"] is True and r.json()["run_id"] is None
    assert r.json()["written_count"] == 20
    assert await env.entries() == before and await env.runs() == []


@pytest.mark.asyncio
async def test_adopt_and_lock_endpoints(api):
    c, base, env = api["client"], api["base"], api["env"]
    await env.seed_entries(base_entries())
    await c.post(f"{base}/run", json={"year": YEAR})
    r = await c.post(f"{base}/states/adopt", json={"year": YEAR, "addr_ids": [CASH_OPENING]})
    assert r.status_code == 200, r.text
    assert [i["action"] for i in r.json()["items"]] == ["write"]
    r = await c.post(f"{base}/states/lock", json={"year": YEAR, "addr_ids": [CASH_OPENING], "locked": True})
    assert r.status_code == 200 and r.json()["states"][0]["state"] == "locked"
    # 派生值 / 系统值不能锁定；没有推送记录的目标不能采用 —— 400 且中文原因
    r = await c.post(f"{base}/states/lock", json={"year": YEAR, "addr_ids": ["E1/E1-1/E1-adj-total-1001"],
                                                   "locked": True})
    assert r.status_code == 400 and "不能采用或锁定" in r.json()["detail"]
    r = await c.post(f"{base}/states/adopt", json={"year": YEAR, "addr_ids": ["E1/E1-9/不存在"]})
    assert r.status_code == 400 and "尚无推送记录" in r.json()["detail"]
    assert (await env.states())[CASH_OPENING].state == "locked", "失败的锁定请求不得改动其它目标"


@pytest.mark.asyncio
async def test_run_for_non_audit_year_is_400(api):
    r = await api["client"].post(f"{api['base']}/run", json={"year": YEAR - 1})
    assert r.status_code == 400 and "审计年度" in r.json()["detail"]



WRITE_CALLS = [
    ("post", "/run", {"year": YEAR}),
    ("post", "/states/adopt", {"year": YEAR, "addr_ids": [CASH_OPENING]}),
    ("post", "/states/lock", {"year": YEAR, "addr_ids": [CASH_OPENING], "locked": True}),
]
READ_CALLS = [
    ("get", "/bindings", None),
    ("get", "/rules", None),
    ("get", f"/latest?year={YEAR}", None),
    ("get", f"/states?year={YEAR}", None),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method, path, body", WRITE_CALLS)
async def test_write_endpoints_require_project_edit(api, method, path, body):
    """只读成员 / 非项目成员调写端点 ⇒ 真 403，且不产生任何写入。"""
    c, base, env = api["client"], api["base"], api["env"]
    await env.seed_entries(base_entries())
    before = await env.entries()
    for who in ("reader", "outsider"):
        api["as"](who)
        r = await getattr(c, method)(f"{base}{path}", json=body)
        assert r.status_code == 403, (who, r.status_code, r.text)
    assert await env.entries() == before and await env.runs() == [] and await env.states() == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("method, path, body", READ_CALLS)
async def test_read_endpoints_require_project_membership(api, method, path, body):
    c, base = api["client"], api["base"]
    api["as"]("outsider")
    assert (await getattr(c, method)(f"{base}{path}")).status_code == 403
    api["as"]("reader")
    assert (await getattr(c, method)(f"{base}{path}")).status_code == 200


def test_every_route_declares_project_access_dependency():
    """纯 AST：每个端点签名都以 require_project_access(...) 为依赖（docstring / 注释不算）；写端点必须 edit。"""
    import ast
    import inspect

    import app.routers.formula_push as mod

    tree = ast.parse(inspect.getsource(mod))
    routes: dict[str, str] = {}
    for fn in (n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)):
        verbs = [d.func.attr for d in fn.decorator_list
                 if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ("get", "post")]
        if not verbs:
            continue
        levels = [
            d.args[0].args[0].value
            for d in fn.args.defaults + fn.args.kw_defaults
            if isinstance(d, ast.Call) and getattr(d.func, "id", None) == "Depends" and d.args
            and isinstance(d.args[0], ast.Call) and getattr(d.args[0].func, "id", None) == "require_project_access"
        ]
        assert levels, f"{fn.name} 未挂 require_project_access"
        routes[fn.name] = levels[0]
        assert levels[0] == ("edit" if verbs[0] == "post" else "readonly"), (fn.name, levels)
    assert set(routes) == {"list_bindings", "list_rules", "run_push", "latest", "states", "adopt", "lock"}


def test_router_is_registered():
    from fastapi import FastAPI

    from app.router_registry.report import register_report_routers

    app = FastAPI()
    register_report_routers(app)
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/projects/{project_id}/formula-push/run" in paths
    assert "/api/projects/{project_id}/formula-push/states/adopt" in paths


# ── Task 9：按 wp_code / wp_codes 隔离 ──────────────────────────────────────


@pytest.mark.asyncio
async def test_wp_codes_selective_run_only_pushes_specified_code(api):
    """wp_codes=['E1'] 只推 E1；wp_codes=['K1']（未注册）不推任何底稿；wp_codes=[] 返回 400。"""
    c, base, env = api["client"], api["base"], api["env"]
    await env.seed_entries(base_entries())
    # 只推 E1
    r = await c.post(f"{base}/run", json={"year": YEAR, "wp_codes": ["E1"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["written_count"] == 20
    assert (await env.entries())["E1-adj-tb-amount-ending"] == "606.73"

    # 只推 K1（未注册）——不应改动 E1 的已有条目
    before = await env.entries()
    r = await c.post(f"{base}/run", json={"year": YEAR, "wp_codes": ["K1"]})
    assert r.status_code == 200
    assert r.json()["written_count"] == 0
    assert await env.entries() == before

    # 空列表 → 400
    r = await c.post(f"{base}/run", json={"year": YEAR, "wp_codes": []})
    assert r.status_code == 400 and "空列表" in r.json()["detail"]

    # 空字符串元素被过滤后为空 → 400
    r = await c.post(f"{base}/run", json={"year": YEAR, "wp_codes": ["", "  "]})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_latest_and_states_filter_by_wp_code(api):
    """按 wp_code 过滤时，states 只返回该 code 前缀的行；latest 返回涉及该 code 的运行。"""
    c, base, env = api["client"], api["base"], api["env"]
    await env.seed_entries(base_entries())
    await c.post(f"{base}/run", json={"year": YEAR})

    # 不带 wp_code：全量
    all_states = (await c.get(f"{base}/states", params={"year": YEAR})).json()["states"]
    all_count = len(all_states)
    assert all_count > 0

    # 带 wp_code=E1：只有 E1 前缀的状态
    e1_states = (await c.get(f"{base}/states", params={"year": YEAR, "wp_code": "E1"})).json()["states"]
    assert len(e1_states) == all_count  # 当前只有 E1
    assert all(s["rule_id"].startswith("E1.") for s in e1_states)

    # 带 wp_code=K1：无状态
    k1_states = (await c.get(f"{base}/states", params={"year": YEAR, "wp_code": "K1"})).json()["states"]
    assert k1_states == []

    # latest 带 wp_code=E1：能找到运行
    e1_latest = (await c.get(f"{base}/latest", params={"year": YEAR, "wp_code": "E1"})).json()
    assert e1_latest["run"] is not None
    assert e1_latest["state_counts"].get("pending_confirm", 0) >= 0
    # detail.wp 只含 E1
    wp_list = e1_latest["run"]["detail"].get("wp") or []
    assert all(wp.get("wp_code") == "E1" for wp in wp_list)
    # detail.items 只含 E1 前缀
    items = e1_latest["run"]["detail"].get("items") or []
    assert all(it.get("rule_id", "").startswith("E1.") for it in items)

    # latest 带 wp_code=K1：无运行
    k1_latest = (await c.get(f"{base}/latest", params={"year": YEAR, "wp_code": "K1"})).json()
    assert k1_latest["run"] is None
    assert k1_latest["state_counts"] == {}


@pytest.mark.asyncio
async def test_run_with_wp_codes_preserves_permission_checks(api):
    """wp_codes 参数不绕过权限：reader 403、outsider 403。"""
    c, base, env = api["client"], api["base"], api["env"]
    await env.seed_entries(base_entries())
    for who in ("reader", "outsider"):
        api["as"](who)
        r = await c.post(f"{base}/run", json={"year": YEAR, "wp_codes": ["E1"]})
        assert r.status_code == 403, (who, r.status_code)


@pytest.mark.asyncio
async def test_read_endpoints_with_wp_code_preserve_permission_checks(api):
    """wp_code 参数不绕过权限：outsider 403。"""
    c, base = api["client"], api["base"]
    api["as"]("outsider")
    for path in (f"/latest?year={YEAR}&wp_code=E1", f"/states?year={YEAR}&wp_code=E1"):
        r = await c.get(f"{base}{path}")
        assert r.status_code == 403, (path, r.status_code)


@pytest.mark.asyncio
async def test_two_binding_isolation_wp_codes_and_states(api, monkeypatch):
    """双 binding 隔离：wp_codes=['E1'] 只推 E1，Z9 的条目/状态不受影响。"""
    import sqlalchemy as sa

    from app.services.formula_push import engine as push
    from app.services.formula_push.bindings import register_binding
    from app.services.formula_push.bindings.e1 import WorkpaperTarget
    from app.services.formula_push.rules import PushRule, PushSource, PushTarget

    c, base, env = api["client"], api["base"], api["env"]
    await env.seed_entries(base_entries())

    # ── 注册 Z9 dummy binding + 造底稿/条目 ──
    z9_wp_id = uuid.uuid4()
    z9_idx = uuid.uuid4()
    async with env.factory() as db:
        await db.execute(sa.text("INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, 'Z9')"),
                         {"i": str(z9_idx), "p": str(env.pid)})
        await db.execute(sa.text("INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"),
                         {"w": str(z9_wp_id), "p": str(env.pid), "i": str(z9_idx)})
        await db.execute(sa.text(
            "INSERT INTO checklist_responses (id, project_id, wp_id, item_id, remark, updated_at) "
            "VALUES (:id, :p, :w, 'Z9-value', 'z9-old', '2026-09-01 08:00:00.000000+00:00')"
        ), {"id": str(uuid.uuid4()), "p": str(env.pid), "w": str(z9_wp_id)})
        await db.commit()

    from types import SimpleNamespace

    class Z9Binding:
        wp_code = "Z9"
        account_prefixes = ("9901",)
        derivations = frozenset()
        four_table_slots = frozenset()
        tb_columns = frozenset({"期末余额"})
        paper_codes = ("Z9",)

        async def load_sources(self, db, project_id, year, wp_id):
            return SimpleNamespace(warnings=[], template_type=None)

        def workpaper_targets(self, rule, entries, sources):
            return [WorkpaperTarget(
                rule_id=rule.rule_id, policy=rule.policy,
                addr_id=f"Z9/Z9/Z9-value", item_id="Z9-value",
                formula_value="z9-new", current_value=entries.get("Z9-value"),
            )], []

        def apply(self, entries, target, value):
            changed = entries.get(target.item_id) != str(value)
            entries[target.item_id] = str(value)
            return changed

        def note_rows(self, entries, template_type, rule):
            return []

        def entry_warnings(self, entries):
            return []

    revoke = register_binding("Z9", Z9Binding)
    try:
        z9_rule = PushRule(
            rule_id="Z9.value", page_key="workpaper:Z9", stage="source", policy="system",
            target=PushTarget(domain="workpaper", wp_code="Z9", sheet_code="Z9", item_id="Z9-value", fields=("value",)),
            source=PushSource(kind="derivation", name="fake", formula_text="Z9 测试值"),
            triggers=("manual",), description="Z9 隔离测试",
        )
        real_load = push.load_push_rules
        def patched_rules():
            return real_load() + (z9_rule,)
        monkeypatch.setattr(push, "load_push_rules", patched_rules)

        # 全量推送：E1 + Z9 都推
        r = await c.post(f"{base}/run", json={"year": YEAR})
        assert r.status_code == 200
        body = r.json()
        assert body["written_count"] > 20, "E1(20) + Z9(1) = 21+"

        # Z9 条目已改
        async with env.factory() as db:
            z9_remark = (await db.execute(sa.text(
                "SELECT remark FROM checklist_responses WHERE wp_id = :w AND item_id = 'Z9-value'"
            ), {"w": str(z9_wp_id)})).scalar_one()
        assert z9_remark == "z9-new"

        # 选择性推 wp_codes=['E1']：Z9 的条目不应被再次改动
        async with env.factory() as db:
            await db.execute(sa.text(
                "UPDATE checklist_responses SET remark = 'z9-user-edit' WHERE wp_id = :w AND item_id = 'Z9-value'"
            ), {"w": str(z9_wp_id)})
            await db.commit()
        r = await c.post(f"{base}/run", json={"year": YEAR, "wp_codes": ["E1"]})
        assert r.status_code == 200
        async with env.factory() as db:
            z9_after = (await db.execute(sa.text(
                "SELECT remark FROM checklist_responses WHERE wp_id = :w AND item_id = 'Z9-value'"
            ), {"w": str(z9_wp_id)})).scalar_one()
        assert z9_after == "z9-user-edit", "wp_codes=['E1'] 不得改动 Z9 的条目"

        # states 按 wp_code 过滤
        e1_states = (await c.get(f"{base}/states", params={"year": YEAR, "wp_code": "E1"})).json()["states"]
        z9_states = (await c.get(f"{base}/states", params={"year": YEAR, "wp_code": "Z9"})).json()["states"]
        assert all(s["rule_id"].startswith("E1.") for s in e1_states)
        assert all(s["rule_id"].startswith("Z9.") for s in z9_states)
        assert len(z9_states) == 1

        # state_counts 按 wp_code 过滤：Z9 只有 1 个 auto 状态
        all_counts = (await c.get(f"{base}/latest", params={"year": YEAR})).json()["state_counts"]
        z9_counts = (await c.get(f"{base}/latest", params={"year": YEAR, "wp_code": "Z9"})).json()["state_counts"]
        e1_counts = (await c.get(f"{base}/latest", params={"year": YEAR, "wp_code": "E1"})).json()["state_counts"]
        assert sum(z9_counts.values()) == 1, f"Z9 只有 1 条状态，实际 {z9_counts}"
        assert sum(e1_counts.values()) + sum(z9_counts.values()) == sum(all_counts.values()), (
            "E1 + Z9 状态数 = 全量状态数"
        )

        # latest 按 wp_code 裁剪 detail
        e1_latest = (await c.get(f"{base}/latest", params={"year": YEAR, "wp_code": "E1"})).json()
        assert e1_latest["run"] is not None
        detail_items = e1_latest["run"]["detail"].get("items") or []
        assert all(it.get("rule_id", "").startswith("E1.") for it in detail_items), "latest detail.items 不应含 Z9"
        z9_latest = (await c.get(f"{base}/latest", params={"year": YEAR, "wp_code": "Z9"})).json()
        assert z9_latest["run"] is not None
        z9_items = z9_latest["run"]["detail"].get("items") or []
        assert all(it.get("rule_id", "").startswith("Z9.") for it in z9_items)

    finally:
        revoke()
