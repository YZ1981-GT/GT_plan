"""模板集生成底稿保留用户裁剪结果（spec formula-fetch-and-wp-generation-defect-closure R4）。

缺陷：生成前的裁剪弹窗把选中编码作为 ``selected_templates`` 发给 ``POST /working-papers/generate``，而请求模型
没有这个字段 ⇒ pydantic 静默丢弃 ⇒ 用户去掉的底稿照样整套生成。前端单测只断言「请求里带了这个字段」，
后端从没收过它 —— 典型的单侧假绿。本文件：

* 纯函数 ``select_generation_codes`` 的取交集 / 不传 / 空选 / 未知编码；
* 真实路由 + SQLite 真 ORM：只生成选中的、回报不在模板集里的、未登记字段 422；
* 跨语言契约：前端两处生成调用的请求体键 ⊆ 后端请求模型字段；前端读的回执键 ⊆ 后端真实回执键。
"""
from __future__ import annotations

import re
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401  全量注册（生成路径会查程序裁剪等表）
from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.audit_platform_models import AccountCategory, TrialBalance  # noqa: E402
from app.models.base import Base, ProjectStatus, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.workpaper_models import WpIndex  # noqa: E402
from app.routers import wp_template  # noqa: E402
from app.services import wp_template_init_service  # noqa: E402
from app.services.template_engine import TemplateEngine, select_generation_codes  # noqa: E402

_FRONTEND = Path(__file__).resolve().parents[2] / "audit-platform" / "frontend" / "src"
_GEN_URL = "/api/projects/{pid}/working-papers/generate"
_CODES_URL = "/api/projects/{pid}/working-papers/generate-from-codes"


# ── 纯函数 ──────────────────────────────────────────────────────────────────


def test_select_none_means_whole_set_in_order_without_duplicates():
    assert select_generation_codes(["E1", "D2", "E1", "", "H1"], None) == (["E1", "D2", "H1"], [])


def test_select_intersects_in_set_order_and_reports_unknown():
    codes, ignored = select_generation_codes(["E1", "D2", "H1"], ["H1", " E1 ", "ZZ9", "H1", None, ""])
    assert codes == ["E1", "H1"], "按模板集顺序、选中编码去空白后比较"
    assert ignored == ["ZZ9"]


def test_select_empty_list_generates_nothing():
    assert select_generation_codes(["E1", "D2"], []) == ([], [])


# ── 真实路由 ────────────────────────────────────────────────────────────────


@pytest.fixture
async def world(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(wp_template_init_service, "STORAGE_DIR", tmp_path / "wp_storage")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        user = User(id=uuid.uuid4(), username="gen_sel", email="gen_sel@example.com", hashed_password="x",
                    role=UserRole.auditor, is_active=True)
        pid = uuid.uuid4()
        db.add(user)
        db.add(Project(id=pid, name="【测试】裁剪生成", client_name="【测试】裁剪生成", status=ProjectStatus.execution,
                       template_type="soe", report_scope="standalone", audit_year=2025))
        await db.flush()
        db.add(TrialBalance(project_id=pid, year=2025, company_code="001", standard_account_code="1001",
                            account_name="库存现金", account_category=AccountCategory.asset,
                            unadjusted_amount=Decimal("1"), audited_amount=Decimal("1")))
        ts = await TemplateEngine().create_template_set(
            db=db, set_name="【测试】裁剪集", template_codes=["E1", "D2", "H1"])
        await db.commit()

        api = FastAPI()
        api.include_router(wp_template.router)

        async def _db():
            yield db

        async def _user() -> User:
            return user

        api.dependency_overrides[get_db] = _db
        api.dependency_overrides[get_current_user] = _user
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://gen") as http:
            yield {"http": http, "db": db, "pid": pid, "set_id": str(ts.id)}
    await engine.dispose()


async def _codes(world) -> list[str]:
    rows = (await world["db"].execute(
        sa.select(WpIndex.wp_code).where(WpIndex.project_id == world["pid"]).order_by(WpIndex.wp_code)
    )).scalars().all()
    return list(rows)


async def _post(world, body: dict):
    return await world["http"].post(_GEN_URL.format(pid=world["pid"]), json=body)


async def test_generate_only_selected_and_report_ignored(world):
    r = await _post(world, {"template_set_id": world["set_id"], "year": 2025,
                            "selected_templates": ["H1", "E1", "ZZ9"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 2 and body["count"] == 2
    assert body["ignored_codes"] == ["ZZ9"]
    assert "ZZ9" in body["message"] and "未生成" in body["message"]
    assert await _codes(world) == ["E1", "H1"], "裁剪掉的 D2 不应生成"


async def test_generate_without_selection_keeps_whole_set(world):
    r = await _post(world, {"template_set_id": world["set_id"], "year": 2025})
    assert r.status_code == 200, r.text
    assert r.json()["ignored_codes"] == []
    assert await _codes(world) == ["D2", "E1", "H1"]


async def test_generate_with_empty_selection_creates_nothing(world):
    r = await _post(world, {"template_set_id": world["set_id"], "year": 2025, "selected_templates": []})
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 0
    assert await _codes(world) == []


async def test_unknown_request_field_is_rejected(world):
    r = await _post(world, {"template_set_id": world["set_id"], "year": 2025, "selected": ["E1"]})
    assert r.status_code == 422
    assert await _codes(world) == []


# ── 跨语言契约 ──────────────────────────────────────────────────────────────

#: 前端发起生成的全部调用点（grep `working-papers/generate` 全前端得出；新增调用点须登记）
_CALLERS = ("views/WorkpaperList.vue", "composables/useWorkpaperGenerate.ts")
_CALL_RE = re.compile(r"/working-papers/(generate(?:-from-codes)?)`\s*,\s*\{")
_MODELS = {
    "generate": wp_template.GenerateWorkpapersRequest,
    "generate-from-codes": wp_template.GenerateFromCodesRequest,
}


def _post_bodies(text: str) -> list[tuple[str, set[str]]]:
    """取 ``api.post(`…/working-papers/generate…`, { … })`` 的请求体键（支持 ``year,`` 简写）。"""
    found = []
    for m in _CALL_RE.finditer(text):
        start = m.end() - 1
        depth = 0
        for end in range(start, len(text)):
            depth += {"{": 1, "}": -1}.get(text[end], 0)
            if depth == 0:
                break
        inner = text[start + 1:end]
        assert "{" not in inner and "[" not in inner, f"请求体出现嵌套结构，解析器需要升级：{inner!r}"
        keys = set()
        for part in inner.split(","):
            key = part.split(":", 1)[0].strip()
            if key:
                assert re.fullmatch(r"\w+", key), f"无法识别的请求体键：{part!r}"
                keys.add(key)
        found.append((m.group(1), keys))
    return found


def test_frontend_request_bodies_match_backend_models():
    seen: dict[str, set[str]] = {}
    for rel in _CALLERS:
        bodies = _post_bodies((_FRONTEND / rel).read_text(encoding="utf-8"))
        assert bodies, f"{rel} 里找不到生成调用 —— 调用点改了写法或已删除，请同步本清单"
        for endpoint, keys in bodies:
            fields = set(_MODELS[endpoint].model_fields)
            assert keys <= fields, f"{rel} 发往 {endpoint} 的 {sorted(keys - fields)} 后端模型没有（会被 422）"
            seen.setdefault(endpoint, set()).update(keys)
    assert "selected_templates" in seen["generate"], "裁剪结果没有发给后端"
    assert seen.keys() == _MODELS.keys(), "两个生成接口都应有前端调用点"


def test_frontend_callers_list_is_complete():
    """全前端 grep 出的调用点必须都在 _CALLERS 里（防新增调用点绕开上面的契约）。"""
    hits = sorted(
        str(p.relative_to(_FRONTEND)).replace("\\", "/")
        for p in _FRONTEND.rglob("*")
        if p.suffix in {".ts", ".vue"} and "__tests__" not in p.parts and ".spec." not in p.name
        and _CALL_RE.search(p.read_text(encoding="utf-8", errors="ignore"))
    )
    assert hits == sorted(_CALLERS)


async def test_frontend_reads_only_keys_backend_returns(world):
    """前端回执提示读的键 ⊆ 两个生成接口真实回执的键（键名漂移即红）。"""
    gen = (await _post(world, {"template_set_id": world["set_id"], "year": 2025,
                               "selected_templates": ["E1", "ZZ9"]})).json()
    codes = (await world["http"].post(_CODES_URL.format(pid=world["pid"]),
                                      json={"wp_codes": ["H1", "ZZ8"], "year": 2025})).json()
    returned = set(gen) | set(codes)
    helper = (_FRONTEND / "utils" / "workpaperGenerateResult.ts").read_text(encoding="utf-8")
    read = set(re.findall(r"result\?\.(\w+)", helper))
    assert {"created", "count", "ignored_codes", "blank_codes", "failures"} <= read, read
    assert read <= returned, f"前端读了后端不返回的键 {sorted(read - returned)}"
    assert gen["ignored_codes"] == ["ZZ9"] and codes["blank_codes"] == ["ZZ8"]
