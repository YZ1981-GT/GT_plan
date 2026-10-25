"""断点 2：入库后自动科目映射的结果必须可见（不再「只记日志 + 空试算表」）。

🔴 缺陷（2026-09-29 现扫）：
- ``_auto_map_on_dataset_activated`` 整体 ``except Exception: logger.warning``：映射失败时用户侧只看到
  「导入成功」，试算表为空，没有任何提示或重试入口。
- 真库「四川物流_2025」项目：813 个余额科目、0 客户科目、0 映射、试算表 171 行未审数全 0 ——
  数据集 06-16 激活而自动映射 handler 07-26 才上线，属存量项目**从未映射**；页面同样无提示。
  事务内 dry-run 证实重新映射即可自愈（749 条映射、未审数非零 30 行）。
- 顺带根治同链路猜年份：``_generate_client_accounts_from_balance`` 原为 ``year or 2025``，
  2024 项目点「一键映射」不传 year 时按 2025 查余额表 → 0 客户科目 → 0 映射。

判据：
1. 结果分类（纯函数）四态全覆盖，阈值与试算表页引导步骤同口径（80%）
2. handler 真跑（SQLite 真库 + 真 auto_match）后结果落 ``validation_summary.auto_map``，
   且不覆盖 summary 里的既有键
3. 失败 / 空映射推 ``sync.failed`` SSE 且带重试端点；成功不推
4. 手动「重新映射」端点回写结果（红色提示在修好后能消失）
5. ``/datasets/active`` 端点把 auto_map 透出给前端
6. 年度解析：无 active 数据集时回退项目审计年度，不猜 2025
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.models.base import Base, UserRole  # noqa: E402
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.dataset_models  # noqa: E402, F401
from app.models.audit_platform_models import AccountMapping, TbBalance  # noqa: E402
from app.models.audit_platform_schemas import EventPayload, EventType  # noqa: E402
from app.models.core import Project, ProjectStatus, ProjectType, User  # noqa: E402
from app.models.dataset_models import DatasetStatus, LedgerDataset  # noqa: E402
from app.services.event_bus import event_bus  # noqa: E402
from app.services.event_handlers._impl import (  # noqa: E402
    AUTO_MAP_ATTENTION_RATE,
    _auto_map_on_dataset_activated,
    classify_auto_map_outcome,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. 分类纯函数
# ─────────────────────────────────────────────────────────────────────────────


def _r(total: int, rate: float, saved: int = 0):
    return SimpleNamespace(total_client=total, completion_rate=rate, saved_count=saved,
                           unmatched_count=max(total - saved, 0))


@pytest.mark.parametrize("result,error,expected", [
    (None, RuntimeError("boom"), "failed"),
    (_r(0, 0.0), None, "empty"),
    (_r(100, AUTO_MAP_ATTENTION_RATE - 0.1, 79), None, "low_coverage"),
    (_r(100, AUTO_MAP_ATTENTION_RATE, 80), None, "ok"),
    (_r(813, 92.13, 749), None, "ok"),
])
def test_classify_four_states(result, error, expected):
    out = classify_auto_map_outcome(result, error)
    assert out["status"] == expected
    assert out["message"], "每个状态都必须有中文说明（前端直接展示）"


def test_threshold_matches_trial_balance_setup_step():
    """阈值必须与前端试算表引导步骤「映射率 < 80 停在第 2 步」同口径，否则两处提示自相矛盾。"""
    from pathlib import Path

    vue = (Path(__file__).resolve().parents[2] / "audit-platform" / "frontend" / "src"
           / "views" / "TrialBalance.vue").read_text(encoding="utf-8")
    assert "mappingRate < 80" in vue
    assert AUTO_MAP_ATTENTION_RATE == 80.0


# ─────────────────────────────────────────────────────────────────────────────
# 2~5. 真库链路
# ─────────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    pid, ds_id = uuid.uuid4(), uuid.uuid4()
    async with factory() as db:
        db.add(Project(id=pid, name="自动映射可见性_2024", client_name="测试客户",
                       project_type=ProjectType.annual, status=ProjectStatus.execution,
                       audit_year=2024))
        db.add(LedgerDataset(id=ds_id, project_id=pid, year=2024, status=DatasetStatus.active,
                             validation_summary={"warnings": 3}))
        for code, name, bal in [("1001", "库存现金", "120"), ("1002", "银行存款", "48000"),
                                ("2202", "应付账款", "-2500")]:
            db.add(TbBalance(id=uuid.uuid4(), project_id=pid, year=2024, dataset_id=ds_id,
                             company_code="001", account_code=code, account_name=name,
                             closing_balance=Decimal(bal), currency_code="CNY", is_deleted=False))
        await db.commit()

    sse: list[EventPayload] = []

    async def _capture(p: EventPayload) -> None:
        sse.append(p)

    with patch("app.core.database.async_session", factory), \
         patch.object(event_bus, "_notify_sse", _capture), \
         patch("app.services.mapping_service._publish_mapping_changed", _noop):
        yield SimpleNamespace(factory=factory, pid=pid, ds_id=ds_id, sse=sse)
    await engine.dispose()


async def _noop(*_a, **_kw):
    return None


async def _auto_map_summary(factory, ds_id):
    async with factory() as db:
        ds = await db.get(LedgerDataset, ds_id)
        return dict(ds.validation_summary or {})


def _activated(pid, ds_id, year=2024) -> EventPayload:
    return EventPayload(event_type=EventType.LEDGER_DATASET_ACTIVATED, project_id=pid,
                        year=year, extra={"dataset_id": str(ds_id)})


@pytest.mark.asyncio
async def test_success_is_recorded_and_existing_summary_kept(env):
    await _auto_map_on_dataset_activated(_activated(env.pid, env.ds_id))
    summary = await _auto_map_summary(env.factory, env.ds_id)
    assert summary.get("warnings") == 3, "不得覆盖 validation_summary 里的既有键"
    am = summary.get("auto_map")
    assert am and am["status"] in ("ok", "low_coverage"), am
    assert am["total_client"] == 3 and am["year"] == 2024 and am["trigger"] == "dataset_activated"
    async with env.factory() as db:
        n = len((await db.execute(select(AccountMapping).where(
            AccountMapping.project_id == env.pid))).scalars().all())
    assert n > 0, "handler 应真的建出映射（本测试不 mock auto_match）"
    assert not [p for p in env.sse if p.event_type == EventType.SYNC_FAILED], "成功不应推失败"


@pytest.mark.asyncio
async def test_failure_is_recorded_and_pushed_to_sse(env):
    async def _boom(*_a, **_kw):
        raise RuntimeError("映射服务炸了")

    with patch("app.services.mapping_service.auto_match", _boom):
        await _auto_map_on_dataset_activated(_activated(env.pid, env.ds_id))

    am = (await _auto_map_summary(env.factory, env.ds_id)).get("auto_map")
    assert am["status"] == "failed" and "映射服务炸了" in am["message"]
    fails = [p for p in env.sse if p.event_type == EventType.SYNC_FAILED]
    assert len(fails) == 1
    extra = fails[0].extra or {}
    assert extra["source_event"] == EventType.LEDGER_DATASET_ACTIVATED.value
    assert extra["retry_endpoint"] == f"/api/projects/{env.pid}/mapping/auto-match"


@pytest.mark.asyncio
async def test_empty_mapping_is_treated_as_failure(env):
    """没读到客户科目 = 静默空试算表的形态，必须和异常一样推失败。"""
    async def _empty(*_a, **_kw):
        return _r(0, 0.0)

    with patch("app.services.mapping_service.auto_match", _empty):
        await _auto_map_on_dataset_activated(_activated(env.pid, env.ds_id))
    assert (await _auto_map_summary(env.factory, env.ds_id))["auto_map"]["status"] == "empty"
    assert [p for p in env.sse if p.event_type == EventType.SYNC_FAILED]


@pytest.mark.asyncio
async def test_manual_rematch_endpoint_overwrites_failed_state_and_active_endpoint_exposes_it(env):
    """先落一条 failed，再走手动「重新映射」端点 → 状态被覆盖；/datasets/active 透出最新状态。"""
    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers.ledger_datasets import router as ds_router
    from app.routers.mapping import router as mapping_router

    async def _boom(*_a, **_kw):
        raise RuntimeError("x")

    with patch("app.services.mapping_service.auto_match", _boom):
        await _auto_map_on_dataset_activated(_activated(env.pid, env.ds_id))
    assert (await _auto_map_summary(env.factory, env.ds_id))["auto_map"]["status"] == "failed"

    admin = User(id=uuid.uuid4(), username="adm", email="adm@t.local", hashed_password="x",
                 role=UserRole.admin, is_active=True)
    app = FastAPI()
    app.include_router(mapping_router)
    app.include_router(ds_router)

    async def _db():
        async with env.factory() as s:
            yield s

    async def _user():
        return admin

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        r = await client.post(f"/api/projects/{env.pid}/mapping/auto-match", json={"year": 2024})
        assert r.status_code == 200, r.text
        active = await client.get(f"/api/projects/{env.pid}/ledger-import/datasets/active",
                                  params={"year": 2024})
    assert active.status_code == 200, active.text
    am = active.json()["auto_map"]
    assert am["status"] in ("ok", "low_coverage") and am["trigger"] == "manual"


# ─────────────────────────────────────────────────────────────────────────────
# 6. 年度解析：不猜 2025
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_year_falls_back_to_project_audit_year(env):
    from app.services.mapping_service import _resolve_event_year

    async with env.factory() as db:
        ds = await db.get(LedgerDataset, env.ds_id)
        ds.status = DatasetStatus.superseded  # 模拟「无 active 数据集」
        await db.commit()
        assert await _resolve_event_year(env.pid, db) == 2024, "应回退项目审计年度而不是 None/2025"
        assert await _resolve_event_year(env.pid, db, 2023) == 2023, "显式年度优先"
        assert await _resolve_event_year(uuid.uuid4(), db) is None


def test_no_year_or_2025_guess_left_in_mapping_service():
    import ast
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "app" / "services" / "mapping_service.py"
           ).read_text(encoding="utf-8")
    guesses = [
        n.lineno for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.BoolOp) and isinstance(n.op, ast.Or)
        and isinstance(n.values[0], ast.Name) and n.values[0].id == "year"
        and any(isinstance(v, ast.Constant) and v.value == 2025 for v in n.values[1:])
    ]
    assert not guesses, f"mapping_service 仍有 `year or 2025` 猜年份：行 {guesses}"
