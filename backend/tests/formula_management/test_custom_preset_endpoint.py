"""自定义预设写端点契约测试（template-library-formula-preset-custom Wave 2；formula-global-settings-sync R14.3 改存数据库）。

覆盖 Property 2/3/5/6 + 迁库口径：
- P5 权限门控：非编辑角色 POST /presets/custom → 403，零写入
- R14.3 admin 直接写事务所级模板「自定义公式预设」；合伙人提交全局候选（不进预设库，admin 审核后才进）
- 不写代码仓库里的 ``formula_custom_presets.json``；seed 逐字节不变（P2）
- P6 无效引用拦截：悬空引用 → 422 且不落库
- P3 来源标注：GET /presets/page 条目带 is_custom、/presets/inventory 页带 has_custom

full_resolve 引用校验本身由 import-data 测试覆盖，此处 monkeypatch ``validate_single_formula_refs``。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.formula_setting_models import FormulaPublish, FormulaSetting
from app.routers import formula_import_export as router_mod
from app.services.formula_management import preset_library as pl
from app.services.formula_settings.apply_ops import review_candidate
from app.services.formula_settings.custom_presets import refresh_cache
from tests.formula_settings._env import add_user, make_db

URL = "/api/formula-management/presets/custom"


def _payload(target: str = "R1C1", expr: str = "=TB('1001')") -> dict:
    return {"page_key": "note:测试自定义节", "target_cell": target, "expression": expr, "formula_type": "auto_calc",
            "refs": [{"formula_ref": "TB('1001')"}], "description": "自定义测试"}


@pytest_asyncio.fixture
async def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    custom = tmp_path / "formula_custom_presets.json"
    custom.write_text(json.dumps({"presets": []}), encoding="utf-8")
    monkeypatch.setattr(pl, "CUSTOM_PATH", custom)
    pl.set_db_custom_entries([])
    pl.set_db_custom_refresher(None)
    refs = {"dangling": []}

    async def _validate(**kwargs):
        return kwargs.get("refs") or [], refs["dangling"]

    monkeypatch.setattr(router_mod, "validate_single_formula_refs", _validate)
    async with make_db() as factory:
        async with factory() as db:
            users = {n: await add_user(db, n, r) for n, r in (
                ("admin", "admin"), ("partner", "partner"), ("auditor", "auditor"))}
            await db.commit()
        app = FastAPI()
        app.include_router(router_mod.router)
        who = {"u": users["admin"]}

        async def _db():
            async with factory() as s:
                yield s

        async def _user():
            return who["u"]

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = _user
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield {"c": c, "f": factory, "as": lambda n: who.update(u=users[n]), "file": custom, "refs": refs,
                   "users": users}
    pl.set_db_custom_entries([])


async def _count(f, model) -> int:
    async with f() as db:
        return await db.scalar(sa.select(sa.func.count()).select_from(model))


async def _page(c) -> list[dict]:
    r = await c.get("/api/formula-management/presets/page", params={"page_key": "note:测试自定义节"})
    assert r.status_code == 200
    return r.json().get("data", r.json())["presets"]


async def test_non_editor_role_forbidden(env):
    env["as"]("auditor")
    assert (await env["c"].post(URL, json=_payload())).status_code == 403
    assert await _count(env["f"], FormulaSetting) == 0 and await _count(env["f"], FormulaPublish) == 0


async def test_admin_writes_db_not_repo_file(env):
    seed_before, file_before = pl.SEED_PATH.read_bytes(), env["file"].read_bytes()
    r = await env["c"].post(URL, json=_payload())
    data = r.json().get("data", r.json())
    assert r.status_code == 200 and (data["ok"], data["pending_review"], data["inserted"]) == (True, False, 1)
    assert env["file"].read_bytes() == file_before, "不写代码仓库里的 JSON"
    assert pl.SEED_PATH.read_bytes() == seed_before, "写自定义不得改动 seed"
    async with env["f"]() as db:
        (row,) = (await db.execute(sa.select(FormulaSetting).where(FormulaSetting.domain == "preset"))).scalars()
        assert (row.layer, row.slot_key, row.definition["source"]) == ("template", "note:测试自定义节|R1C1", "custom")
    presets = await _page(env["c"])
    assert presets and presets[0]["is_custom"] is True and presets[0]["expression"] == "=TB('1001')"
    again = (await env["c"].post(URL, json=_payload(expr="=TB('1002')"))).json()
    again = again.get("data", again)
    assert (again["inserted"], again["updated"], again["total"]) == (0, 1, 1), "同键幂等覆盖"
    inv = (await env["c"].get("/api/formula-management/presets/inventory")).json()
    inv = inv.get("data", inv)
    assert [p["has_custom"] for p in inv["pages"] if p["page_key"] == "note:测试自定义节"] == [True]


async def test_partner_submits_candidate_then_admin_approves(env):
    env["as"]("partner")
    r = await env["c"].post(URL, json=_payload(target="R9C9"))
    data = r.json().get("data", r.json())
    assert r.status_code == 200 and data["pending_review"] is True and data["candidate"]["status"] == "pending"
    assert await _count(env["f"], FormulaSetting) == 0 and await _page(env["c"]) == [], "候选未审核不进预设库"
    async with env["f"]() as db:
        cand = (await db.execute(sa.select(FormulaPublish))).scalar_one()
        assert (cand.domain, cand.target) == ("preset", "global")
        out = await review_candidate(db, publish_id=cand.id, approve=True, user_id=env["users"]["admin"].id)
        await db.commit()
        assert out["candidate"]["status"] == "published" and out["custom_presets_changed"]
        assert await refresh_cache(db) == 1
    assert [p["target_cell"] for p in await _page(env["c"])] == ["R9C9"]


async def test_dangling_ref_422_not_persisted(env):
    env["refs"]["dangling"] = ["TB('9999')"]
    assert (await env["c"].post(URL, json=_payload())).status_code == 422
    assert await _count(env["f"], FormulaSetting) == 0


@pytest.mark.parametrize("patch", [{"formula_type": "bogus_type"}, {"page_key": ""}, {"expression": ""}])
async def test_invalid_input_400(env, patch):
    assert (await env["c"].post(URL, json={**_payload(), **patch})).status_code == 400


async def test_refresher_schedules_once_per_ttl(monkeypatch):
    """读时补刷：过时效才刷、同时只刷一次；登记后读预设库即触发（不常驻后台循环）。"""
    import asyncio
    import time

    from app.services.formula_settings import custom_presets as cp

    calls: list[int] = []

    async def fake_refresh():
        calls.append(1)
        cp._state["inflight"], cp._state["loaded_at"] = False, time.monotonic()

    monkeypatch.setattr(cp, "_refresh_once", fake_refresh)
    monkeypatch.setitem(cp._state, "loaded_at", float("-inf"))
    monkeypatch.setitem(cp._state, "inflight", False)
    try:
        assert cp.start_refresher() is True
        assert cp.schedule_refresh() is False, "刷新进行中不重复排队"
        await asyncio.sleep(0)
        assert calls == [1]
        pl.build_preset_library()  # 时效内：读库不再触发
        await asyncio.sleep(0)
        assert calls == [1]
        monkeypatch.setitem(cp._state, "loaded_at", float("-inf"))
        pl.build_preset_library()  # 过时效：读库触发后台补刷
        await asyncio.sleep(0)
        assert calls == [1, 1]
    finally:
        pl.set_db_custom_refresher(None)
