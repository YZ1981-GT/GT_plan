"""底稿短链定位端点 ``GET /api/acnr/workpapers/{wp_id}/locate``（spec acnr-foundation-defect-closure T16 / RV7.5-01）。

ACNR 产出的跳转路由是 ``/workpapers/{wp_id}?sheet=…``，前端只有 ``/projects/{pid}/workpapers/{wp_id}/edit``；
短链页凭本端点按底稿 id 查出所属项目后重定向。经 HTTP 真发请求（权限世界：真实成员行、生产门禁、生产注册；
只 override 当前用户与会话）。

- 未登录 401；非成员 403（且不回 project_id）；readonly 成员 / admin 200（project_id / wp_id / wp_code）；
- 不存在、或传的是 ``wp_index.id``（两者不同，附件管理曾因此恒 404）→ 404；
- 底稿在回收站 → 410 + 中文「底稿已移入回收站」；底稿所属项目整体在回收站（底稿行不标删）→ 410 +
  「底稿所属项目已移入回收站」（RV7.6-01）；两者都在鉴权通过后才区分，非成员照样 403。
"""
from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType
from app.routers import acnr as acnr_module
from tests.authz_world import sqlite_world

ASSERT_GATE = "app.deps.assert_project_permission"


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch, extra_tables=(WpIndex.__table__, WorkingPaper.__table__)) as w:
        yield w


@pytest.fixture(autouse=True)
def wp_gate_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """2026-11-25 端点在项目级鉴权之后补接了 wp 可见性门 ``enforce_wp_gate``。

    SQLite 权限世界缺可见性域的表（委派 / epoch），门在这里无法按生产口径判定，故替身为放行并
    记录调用；门本身的判定由 wp_visibility 的测试覆盖。接线与拒绝路径见文件末两条用例。
    """
    from app.routers import _wp_gate

    calls: list[dict] = []

    async def allow(_db, _user, **kw):
        calls.append(kw)

    monkeypatch.setattr(_wp_gate, "enforce_wp_gate", allow)
    return calls


async def _workpaper(world, *, deleted: bool = False) -> tuple[WorkingPaper, WpIndex]:
    idx = WpIndex(project_id=world.target.id, wp_code="E1", wp_name="货币资金")
    world.db.add(idx)
    await world.db.flush()
    wp = WorkingPaper(project_id=world.target.id, wp_index_id=idx.id, file_path="x.xlsx",
                      source_type=WpSourceType.template, is_deleted=deleted)
    world.db.add(wp)
    await world.db.flush()
    return wp, idx


def _url(wp_id) -> str:
    return f"/api/acnr/workpapers/{wp_id}/locate"


async def test_anonymous_is_401(world):
    wp, _ = await _workpaper(world)
    async with world.client(acnr_module.router, user=None) as client:
        resp = await client.get(_url(wp.id))
    assert resp.status_code == 401, resp.text


async def test_non_member_is_403_without_project_id(world):
    wp, _ = await _workpaper(world)
    user = (await world.non_member()).user
    async with world.client(acnr_module.router, user=user) as client:
        resp = await client.get(_url(wp.id))
    assert resp.status_code == 403, resp.text
    assert str(world.target.id) not in resp.text
    client.assert_passed(ASSERT_GATE, times=1)


@pytest.mark.parametrize("identity", ["readonly_member", "edit_member", "admin_non_member"])
async def test_member_gets_project_id(world, identity: str):
    wp, _ = await _workpaper(world)
    user = (await world.identity(identity)).user
    async with world.client(acnr_module.router, user=user) as client:
        resp = await client.get(_url(wp.id))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"wp_id": str(wp.id), "project_id": str(world.target.id), "wp_code": "E1"}
    client.assert_passed(ASSERT_GATE, times=1)


async def test_unknown_id_is_404(world):
    await _workpaper(world)
    user = (await world.readonly_member()).user
    async with world.client(acnr_module.router, user=user) as client:
        resp = await client.get(_url(uuid.uuid4()))
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"]["message"] == "底稿不存在"


async def test_wp_index_id_is_not_a_workpaper_id(world):
    """传 wp_index.id（不是 working_paper.id）→ 404，不按索引误命中。"""
    _, idx = await _workpaper(world)
    user = (await world.readonly_member()).user
    async with world.client(acnr_module.router, user=user) as client:
        resp = await client.get(_url(idx.id))
    assert resp.status_code == 404, resp.text


async def test_recycle_bin_is_410_with_chinese_reason(world):
    wp, _ = await _workpaper(world, deleted=True)
    user = (await world.readonly_member()).user
    async with world.client(acnr_module.router, user=user) as client:
        resp = await client.get(_url(wp.id))
    assert resp.status_code == 410, resp.text
    detail = resp.json()["detail"]
    assert detail["error_code"] == "WORKPAPER_IN_RECYCLE_BIN"
    assert detail["message"] == "底稿已移入回收站"


async def test_project_recycle_bin_is_410_after_authorization(world):
    """项目整体移入回收站时底稿行不标删：定位端点另看项目，给中文原因（RV7.6-01）。"""
    wp, _ = await _workpaper(world)
    world.target.is_deleted = True
    await world.db.flush()
    user = (await world.readonly_member()).user
    async with world.client(acnr_module.router, user=user) as client:
        resp = await client.get(_url(wp.id))
    assert resp.status_code == 410, resp.text
    detail = resp.json()["detail"]
    assert detail["error_code"] == "PROJECT_IN_RECYCLE_BIN"
    assert detail["message"] == "底稿所属项目已移入回收站"
    client.assert_passed(ASSERT_GATE, times=1)


async def test_project_recycle_bin_still_403_for_non_member(world):
    """项目在回收站同样只在鉴权通过后才区分：非成员拿不到「项目在不在回收站」。"""
    wp, _ = await _workpaper(world)
    world.target.is_deleted = True
    await world.db.flush()
    user = (await world.non_member()).user
    async with world.client(acnr_module.router, user=user) as client:
        resp = await client.get(_url(wp.id))
    assert resp.status_code == 403, resp.text
    assert "回收站" not in resp.text


async def test_recycle_bin_still_403_for_non_member(world):
    """回收站状态只在鉴权通过后才区分：非成员拿不到「在不在回收站」。"""
    wp, _ = await _workpaper(world, deleted=True)
    user = (await world.non_member()).user
    async with world.client(acnr_module.router, user=user) as client:
        resp = await client.get(_url(wp.id))
    assert resp.status_code == 403, resp.text


def test_locate_calls_project_gate_with_readonly():
    """AST 钉子：函数体真实调用 ``assert_project_permission(..., "readonly")``（docstring / 注释不算）。

    该端点路径只有 ``{wp_id}``、不带 ``{project_id}``，两个鉴权基线扫描器都不覆盖它（路径含对象 id 的端点被
    请求体维显式排除），故在此单独钉住。
    """
    tree = ast.parse(Path(acnr_module.__file__).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "acnr_locate_workpaper")
    calls = [c for c in ast.walk(fn) if isinstance(c, ast.Call)
             and getattr(c.func, "id", getattr(c.func, "attr", None)) == "assert_project_permission"]
    assert calls, "定位端点没有调用 assert_project_permission"
    assert any(isinstance(a, ast.Constant) and a.value == "readonly" for c in calls for a in c.args)


async def test_member_also_passes_the_wp_visibility_gate(world, wp_gate_calls):
    """项目级 readonly 之外必须过 wp 可见性门（read_detail，与编辑页同口径）。"""
    wp, _ = await _workpaper(world)
    user = (await world.readonly_member()).user
    async with world.client(acnr_module.router, user=user) as client:
        resp = await client.get(_url(wp.id))
    assert resp.status_code == 200, resp.text
    assert len(wp_gate_calls) == 1, wp_gate_calls
    call = wp_gate_calls[0]
    assert call["wp_id"] == wp.id and call["project_id"] == world.target.id
    assert (call["entrypoint"], call["action"], call["method"]) == ("workpaper.detail", "read_detail", "GET")


async def test_wp_gate_denial_is_404_without_project_id(world, monkeypatch):
    """成员但对该底稿不可见（未委派等）⇒ 404，且不回 project_id / wp_code。"""
    from app.routers import _wp_gate
    from app.services.wp_visibility.denial import ExternalNotFound

    async def deny(_db, _user, **_kw):
        raise ExternalNotFound()

    monkeypatch.setattr(_wp_gate, "enforce_wp_gate", deny)
    wp, _ = await _workpaper(world)
    user = (await world.readonly_member()).user
    async with world.client(acnr_module.router, user=user) as client:
        resp = await client.get(_url(wp.id))
    assert resp.status_code == 404, resp.text
    assert str(world.target.id) not in resp.text and "E1" not in resp.text
