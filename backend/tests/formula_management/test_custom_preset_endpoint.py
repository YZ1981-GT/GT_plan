"""自定义预设写端点契约测试（template-library-formula-preset-custom Wave 2）。

覆盖 Property 2/3/5/6：
- P5 权限门控：非编辑角色 POST /presets/custom → 403
- P6 无效引用拦截：悬空引用 → 422 且不落库（custom 文件不变）
- P2 自定义不写基线：写入后 seed 逐字节不变
- P3 来源标注：GET /presets/page 条目带 is_custom、/presets/inventory 页带 has_custom

full_resolve 引用校验本身由 import-data 测试覆盖，此处 monkeypatch
``validate_single_formula_refs`` 隔离端点契约（权限/落库/来源标注）。

Requirements: 3.1, 3.2, 3.4, 4.1, 4.3, 5.1, 6.1
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.routers import formula_import_export as router_mod
from app.services.formula_management import preset_library as pl


class _Role:
    def __init__(self, value: str):
        self.value = value


class _FakeUser:
    def __init__(self, role: str):
        self.role = _Role(role)
        self.id = "u-test"


def _build_app(role: str, tmp_custom: Path):
    from fastapi import FastAPI

    from app.core.database import get_db
    from app.deps import get_current_user

    app = FastAPI()
    app.include_router(router_mod.router)

    async def _override_db():
        yield None

    def _override_user():
        return _FakeUser(role)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


@pytest.fixture
def tmp_custom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "formula_custom_presets.json"
    p.write_text(
        json.dumps({"description": "t", "version": "t", "presets": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(pl, "CUSTOM_PATH", p)
    return p


def _valid_payload() -> dict:
    return {
        "page_key": "note:测试自定义节",
        "target_cell": "R1C1",
        "expression": "=TB('1001')",
        "formula_type": "auto_calc",
        "refs": [{"formula_ref": "TB('1001')"}],
        "description": "自定义测试",
    }


# ── P5: 权限门控 ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_non_editor_role_forbidden(tmp_custom: Path, monkeypatch):
    async def _ok_validate(**kwargs):
        return kwargs.get("refs") or [], []

    monkeypatch.setattr(router_mod, "validate_single_formula_refs", _ok_validate)
    app = _build_app("assistant", tmp_custom)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/formula-management/presets/custom", json=_valid_payload())
    assert r.status_code == 403
    # 未落库
    saved = json.loads(tmp_custom.read_text(encoding="utf-8"))
    assert saved["presets"] == []


@pytest.mark.asyncio
async def test_editor_role_allowed_persists(tmp_custom: Path, monkeypatch):
    async def _ok_validate(**kwargs):
        return kwargs.get("refs") or [], []

    monkeypatch.setattr(router_mod, "validate_single_formula_refs", _ok_validate)
    app = _build_app("partner", tmp_custom)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/formula-management/presets/custom", json=_valid_payload())
    assert r.status_code == 200
    body = r.json()
    # ResponseWrapper 可能包裹；容错取 data
    data = body.get("data", body)
    assert data["ok"] is True and data["inserted"] == 1
    saved = json.loads(tmp_custom.read_text(encoding="utf-8"))
    assert len(saved["presets"]) == 1
    assert saved["presets"][0]["source"] == "custom"


# ── P6: 悬空引用 → 422 且不落库 ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_dangling_ref_422_not_persisted(tmp_custom: Path, monkeypatch):
    async def _dangling_validate(**kwargs):
        return kwargs.get("refs") or [], ["TB('9999')"]

    monkeypatch.setattr(router_mod, "validate_single_formula_refs", _dangling_validate)
    app = _build_app("admin", tmp_custom)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/formula-management/presets/custom", json=_valid_payload())
    assert r.status_code == 422
    saved = json.loads(tmp_custom.read_text(encoding="utf-8"))
    assert saved["presets"] == [], "悬空引用不得落库"


# ── P2: 自定义不写基线 seed ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_seed_untouched_after_custom_write(tmp_custom: Path, monkeypatch):
    async def _ok_validate(**kwargs):
        return kwargs.get("refs") or [], []

    monkeypatch.setattr(router_mod, "validate_single_formula_refs", _ok_validate)
    seed_before = pl.SEED_PATH.read_bytes()
    app = _build_app("admin", tmp_custom)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/formula-management/presets/custom", json=_valid_payload())
    assert r.status_code == 200
    assert pl.SEED_PATH.read_bytes() == seed_before, "写自定义不得改动 seed"


# ── 无效输入 400 ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_invalid_formula_type_400(tmp_custom: Path):
    app = _build_app("admin", tmp_custom)
    payload = _valid_payload()
    payload["formula_type"] = "bogus_type"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/formula-management/presets/custom", json=payload)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_missing_page_key_400(tmp_custom: Path):
    app = _build_app("admin", tmp_custom)
    payload = _valid_payload()
    payload["page_key"] = ""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/formula-management/presets/custom", json=payload)
    assert r.status_code == 400


# ── P3: 来源标注（GET /presets/page 带 is_custom，/inventory 带 has_custom） ──
@pytest.mark.asyncio
async def test_get_page_entries_have_is_custom(tmp_custom: Path, monkeypatch):
    # 写一条 custom 到隔离文件，再查该页
    pl.upsert_custom_presets(
        [
            pl.PresetEntry(
                page_key="note:来源标注测试节",
                target_cell="R2C2",
                expression="=TB('1002')",
                formula_type="auto_calc",
                refs=[],
                source="custom",
                description="",
            )
        ]
    )
    app = _build_app("assistant", tmp_custom)  # 只读浏览允许任意角色
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get(
            "/api/formula-management/presets/page",
            params={"page_key": "note:来源标注测试节"},
        )
    assert r.status_code == 200
    data = r.json().get("data", r.json())
    assert data["presetted"] is True
    assert data["presets"], "该页应有自定义预设"
    assert all("is_custom" in p for p in data["presets"])
    assert data["presets"][0]["is_custom"] is True


@pytest.mark.asyncio
async def test_get_inventory_pages_have_has_custom(tmp_custom: Path):
    pl.upsert_custom_presets(
        [
            pl.PresetEntry(
                page_key="note:inv测试节",
                target_cell="R3C3",
                expression="=TB('1003')",
                formula_type="auto_calc",
                refs=[],
                source="custom",
                description="",
            )
        ]
    )
    app = _build_app("assistant", tmp_custom)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/formula-management/presets/inventory")
    assert r.status_code == 200
    data = r.json().get("data", r.json())
    assert data["pages"], "应有登记页"
    assert all("has_custom" in p for p in data["pages"])
    inv = [p for p in data["pages"] if p["page_key"] == "note:inv测试节"]
    assert inv and inv[0]["has_custom"] is True
