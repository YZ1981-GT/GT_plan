"""地址库接口的项目鉴权（spec formula-fetch-followup-defect-closure R4.1）。

原状：读库的五个端点只挂 ``get_current_user`` ⇒ 任意登录用户按任意 ``project_id`` 读出该项目的试算表科目、报表行、
附注章节、底稿单元格目录；任何人都能清空全平台的地址缓存。现行：搜索 / 统计 / 解析走 ``require_project_access("readonly")``，
校验 / 失效缓存在函数首句 ``assert_project_permission(..., "readonly")``；清空全部项目缓存只许管理员；
``jump`` / ``parse`` 只做字符串换算、不读库，保持仅登录。

经 HTTP 真发请求（权限世界：真实成员行、生产门禁、生产注册；只 override 当前用户与会话），业务层换成计数桩：
放行 = 200、桩恰 1 次且拿到的是请求里的项目；拒绝 = 403 / 401 / 422 且桩 0 次。
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from app.routers import address_registry as router_module
from app.services import address_registry as svc
from tests.authz_world import TARGET_PROJECT_ID, sqlite_world

GATE = "app.deps.assert_project_permission"
PID = str(TARGET_PROJECT_ID)

#: 端点 → (方法, 路径, 请求参数, 被桩的业务方法, 桩返回值, 项目在桩参数里的位置, 放行时响应须含的键值)
_ENDPOINTS: dict[str, tuple] = {
    "search": ("GET", "/api/address-registry", {"params": {"project_id": PID, "year": 2025}},
               "match", [], 1, {"total": 0, "items": []}),
    "stats": ("GET", "/api/address-registry/stats", {"params": {"project_id": PID, "year": 2025}},
              "get_stats", {"total": 7}, 1, {"total": 7}),
    "resolve": ("GET", "/api/address-registry/resolve",
                {"params": {"project_id": PID, "year": 2025, "uri": "tb://1001#期末余额"}},
                "resolve", None, 1, {"found": False}),
    "validate": ("POST", "/api/address-registry/validate",
                 {"json": {"project_id": PID, "year": 2025, "formula": "TB('1001','期末余额')"}},
                 "validate_formula_refs", [], 1, {"valid": True}),
    "invalidate": ("POST", "/api/address-registry/invalidate", {"json": {"project_id": PID, "year": 2025}},
                   "invalidate_async", None, 0, {"ok": True}),
}
#: 该放行的身份：只读成员是下限；复核级（质控 / EQCR）与编辑级成员、非成员管理员都要能用公式选址
_ALLOWED = ("readonly_member", "review_member", "edit_member", "admin_non_member")


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch) as w:
        yield w


def _stub(world, attr: str, returns):
    """桩在类上（单例实例上若残留同名实例属性会挡住类级替换，先拿掉；用例结束 monkeypatch 还原）。"""
    if attr in vars(svc.address_registry):
        world.monkeypatch.delattr(svc.address_registry, attr)
    return world.stub(svc.AddressRegistryService, attr, returns=returns)


async def _call(world, user, key: str, **override):
    method, path, kwargs, attr, returns, _, _ = _ENDPOINTS[key]
    stub = _stub(world, attr, returns)
    async with world.client(router_module.router, user=user) as client:
        response = await client.request(method, path, **{**kwargs, **override})
    return response, stub, client


@pytest.mark.parametrize("identity", _ALLOWED)
@pytest.mark.parametrize("key", sorted(_ENDPOINTS))
async def test_allowed_identity_reaches_business_with_its_project(world, key: str, identity: str):
    user = (await world.identity(identity)).user
    response, stub, client = await _call(world, user, key)
    assert response.status_code == 200, response.text
    body = response.json()
    expected = _ENDPOINTS[key][6]
    assert {k: body[k] for k in expected} == expected
    ((args, _kwargs),) = stub.calls
    assert args[_ENDPOINTS[key][5]] == PID
    client.assert_passed(GATE, times=1)


@pytest.mark.parametrize("key", sorted(_ENDPOINTS))
async def test_non_member_is_403_before_business(world, key: str):
    user = (await world.non_member()).user  # 在另一项目是 edit 级成员，本项目不是
    response, stub, client = await _call(world, user, key)
    assert response.status_code == 403, response.text
    assert response.json() == {"detail": "权限不足"}
    assert stub.count == 0
    client.assert_passed(GATE, times=1)


@pytest.mark.parametrize("key", sorted(_ENDPOINTS))
async def test_anonymous_is_401(world, key: str):
    response, stub, client = await _call(world, None, key)
    assert response.status_code == 401, response.text
    assert stub.count == 0
    client.assert_passed(GATE, times=0)


@pytest.mark.parametrize("key", ["validate", "invalidate"])
@pytest.mark.parametrize("project_id", [None, "", "p1"])
async def test_body_project_id_is_required_uuid(world, key: str, project_id):
    """请求体里的项目缺失 / 空 / 非 UUID 一律 422（原先缺项目时校验照常跑、失效缓存返回 ok=false 的 200）。"""
    user = (await world.edit_member()).user
    body = {k: v for k, v in _ENDPOINTS[key][2]["json"].items() if k != "project_id"}
    if project_id is not None:
        body["project_id"] = project_id
    response, stub, client = await _call(world, user, key, json=body)
    assert response.status_code == 422, response.text
    assert response.json() == {"detail": "project_id 必填且须为 UUID"}
    assert stub.count == 0
    client.assert_passed(GATE, times=0)


@pytest.mark.parametrize("key", ["search", "stats", "resolve"])
async def test_query_project_id_must_be_uuid(world, key: str):
    user = (await world.edit_member()).user
    params = {**_ENDPOINTS[key][2]["params"], "project_id": "p1"}
    response, stub, _client = await _call(world, user, key, params=params)
    assert response.status_code == 422, response.text
    assert stub.count == 0


async def test_invalidate_all_is_admin_only(world):
    """清空全部项目的地址缓存：编辑级成员 403（两种失效都没发生）；管理员放行且只清全部、不再按项目清。"""
    member = (await world.edit_member()).user
    admin = (await world.admin_non_member()).user
    for user, status in ((member, 403), (admin, 200)):
        clear_all = _stub(world, "invalidate_all_async", None)
        response, by_project, _client = await _call(world, user, "invalidate", json={"project_id": PID, "all": True})
        assert response.status_code == status, response.text
        if status == 403:
            assert response.json() == {"detail": "清空全部项目的地址缓存只许管理员"}
            assert (clear_all.count, by_project.count) == (0, 0)
        else:
            assert response.json() == {"ok": True, "scope": "all"}
            assert (clear_all.count, by_project.count) == (1, 0)


async def test_jump_and_parse_stay_identity_only(world):
    """只做字符串换算、不读库：非成员也能用（不经项目门禁），未登录仍 401。"""
    outsider = (await world.non_member()).user
    async with world.client(router_module.router, user=outsider) as client:
        jump = await client.post("/api/address-registry/jump", json={"formula_ref": "TB('1001','期末余额')",
                                                                    "project_id": PID, "year": 2025})
        assert jump.status_code == 200, jump.text
        assert jump.json()["uri"] and PID in jump.json()["route"]
        client.assert_passed(GATE, times=0)
        parsed = await client.get("/api/address-registry/parse", params={"formula_ref": "TB('1001','期末余额')"})
        assert parsed.status_code == 200 and parsed.json()["uri"], parsed.text
        client.assert_passed(GATE, times=0)
    async with world.client(router_module.router, user=None) as client:
        for method, path in (("POST", "/api/address-registry/jump"), ("GET", "/api/address-registry/parse")):
            response = await client.request(method, path, **({"json": {}} if method == "POST" else {}))
            assert response.status_code == 401, (path, response.text)
