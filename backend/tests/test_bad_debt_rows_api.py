# Feature: workpaper-bad-debt-nested-structure — Task 10.3 API 集成测试
"""坏账准备明细表 D2-3 嵌套子表 Router API 集成测试（in-process ASGI）。

参照 test_wp_template_files_lazy_load.py 的 in-process httpx.ASGITransport 模式：
- 最小 FastAPI app，仅 include bad_debt_rows.router
- in-process 内存 SQLite，仅建 bad_debt_detail_rows 表
- 单一持久 session override get_db；fake admin user override get_current_user

覆盖端点与状态码：
- GET  /provision-methods                → 200（4 枚举 + 中文 label）
- GET  ``（tree）                        → 200
- POST /parents                          → 201 / 409（重复枚举）
- POST /{parent_id}/children             → 201
- PUT  /{row_id}                         → 200 / 409（乐观锁）/ 400（父行有子行）/ 404
- DELETE /{row_id}                       → 400（删最后一个父行）
- POST /serialize                        → 200
- POST /deserialize                      → 200 / 422（校验失败）
- GET  /aje-suggestion                   → 200

Validates: Requirements 1.4, 8.2, 8.3, 8.5, 10.5
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.bad_debt_models import BadDebtDetailRow
from app.models.workpaper_models import WorkingPaper


@pytest_asyncio.fixture
async def client():
    """最小 FastAPI app + in-process 内存 SQLite + 单一持久 session。

    返回 (AsyncClient, wp_id)；每个测试拿到全新隔离的 DB。
    """
    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers.bad_debt_rows import router as bad_debt_rows_router

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[BadDebtDetailRow.__table__, WorkingPaper.__table__],
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = factory()

    app = FastAPI()
    app.include_router(bad_debt_rows_router)

    async def override_get_db():
        yield session

    class _FakeUser:
        id = uuid.uuid4()
        username = "admin"

        class _Role:
            value = "admin"

        role = _Role()

    async def override_user():
        return _FakeUser()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_user

    wp_id = uuid.uuid4()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, wp_id

    app.dependency_overrides.clear()
    await session.close()
    await engine.dispose()


def _base(wp_id: uuid.UUID) -> str:
    return f"/api/workpapers/{wp_id}/bad-debt-rows"



# ─────────────────────────────────────────────────────────────────────────────
# 用例 1：provision-methods 枚举 + 中文 label
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_provision_methods_returns_four_enums_with_labels(client):
    c, wp_id = client
    resp = await c.get(f"{_base(wp_id)}/provision-methods")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    values = {it["value"] for it in items}
    assert values == {"INDIVIDUAL", "CREDIT_RISK_AGING", "CREDIT_RISK_OTHER", "OTHER"}
    label_by_value = {it["value"]: it["label"] for it in items}
    assert label_by_value["INDIVIDUAL"] == "按单项评估计提"


# ─────────────────────────────────────────────────────────────────────────────
# 用例 2：空树 → 200，parents 为空
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_tree_empty(client):
    c, wp_id = client
    resp = await c.get(_base(wp_id))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["parents"] == []
    assert body["wp_index_id"] == str(wp_id)


# ─────────────────────────────────────────────────────────────────────────────
# 用例 3：全链路 建父行→建2子行→tree 合计→serialize→deserialize→再 tree 合计
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_chain_create_serialize_deserialize(client):
    c, wp_id = client
    base = _base(wp_id)

    # 建父行（INDIVIDUAL）→ 201
    pr = await c.post(
        f"{base}/parents",
        json={"provision_method": "INDIVIDUAL", "row_label": "按单项评估计提"},
    )
    assert pr.status_code == 201, pr.text
    parent_id = pr.json()["id"]

    # 建 2 子行（amount_n 100 / 50）→ 201
    for label, amt in (("甲公司", "100.00"), ("乙公司", "50.00")):
        cr = await c.post(
            f"{base}/{parent_id}/children",
            json={"row_label": label, "amount_n": amt},
        )
        assert cr.status_code == 201, cr.text

    # get_tree → 父行 + summary amount_n == "150.00"
    tree = await c.get(base)
    assert tree.status_code == 200, tree.text
    tbody = tree.json()
    assert len(tbody["parents"]) == 1
    assert tbody["parents"][0]["amounts"]["amount_n"] == "150.00"
    assert tbody["summary"]["amounts"]["amount_n"] == "150.00"

    # serialize → 200
    ser = await c.post(f"{base}/serialize")
    assert ser.status_code == 200, ser.text
    snapshot = ser.json()
    assert snapshot["parents"], "serialize 应含父行"

    # deserialize（回放快照）→ 200
    de = await c.post(f"{base}/deserialize", json=snapshot)
    assert de.status_code == 200, de.text

    # 再 get_tree → summary amount_n 仍 "150.00"
    tree2 = await c.get(base)
    assert tree2.status_code == 200, tree2.text
    assert tree2.json()["summary"]["amounts"]["amount_n"] == "150.00"


# ─────────────────────────────────────────────────────────────────────────────
# 用例 4：重复 provision_method → 409
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_duplicate_provision_method_conflict(client):
    c, wp_id = client
    base = _base(wp_id)
    body = {"provision_method": "INDIVIDUAL", "row_label": "按单项评估计提"}
    first = await c.post(f"{base}/parents", json=body)
    assert first.status_code == 201, first.text
    dup = await c.post(f"{base}/parents", json=body)
    assert dup.status_code == 409, dup.text


# ─────────────────────────────────────────────────────────────────────────────
# 用例 5：乐观锁 → 409
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_optimistic_lock_conflict(client):
    c, wp_id = client
    base = _base(wp_id)
    pr = await c.post(
        f"{base}/parents",
        json={"provision_method": "INDIVIDUAL", "row_label": "单项"},
    )
    assert pr.status_code == 201, pr.text
    parent_id = pr.json()["id"]

    # PUT version=1（无子行，可编辑金额）→ 成功
    ok = await c.put(
        f"{base}/{parent_id}",
        json={"version": 1, "amounts": {"amount_n": "100.00"}},
    )
    assert ok.status_code == 200, ok.text

    # 再用 stale version=1 → 409
    stale = await c.put(
        f"{base}/{parent_id}",
        json={"version": 1, "amounts": {"amount_n": "200.00"}},
    )
    assert stale.status_code == 409, stale.text


# ─────────────────────────────────────────────────────────────────────────────
# 用例 6：删最后一个父行 → 400
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_last_parent_rejected(client):
    c, wp_id = client
    base = _base(wp_id)
    pr = await c.post(
        f"{base}/parents",
        json={"provision_method": "INDIVIDUAL", "row_label": "单项"},
    )
    assert pr.status_code == 201, pr.text
    parent_id = pr.json()["id"]

    resp = await c.delete(f"{base}/{parent_id}")
    assert resp.status_code == 400, resp.text


# ─────────────────────────────────────────────────────────────────────────────
# 用例 7：父行有子行编辑金额 → 400
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_edit_parent_amount_with_children_rejected(client):
    c, wp_id = client
    base = _base(wp_id)
    pr = await c.post(
        f"{base}/parents",
        json={"provision_method": "INDIVIDUAL", "row_label": "单项"},
    )
    assert pr.status_code == 201, pr.text
    parent_id = pr.json()["id"]

    cr = await c.post(
        f"{base}/{parent_id}/children",
        json={"row_label": "甲公司", "amount_n": "100.00"},
    )
    assert cr.status_code == 201, cr.text

    # 从 tree 取父行当前 version（建子行后父行汇总可能变更）
    tree = await c.get(base)
    parent = tree.json()["parents"][0]
    parent_version = parent["version"]

    # 父行有子行 → 编辑金额 → 400
    resp = await c.put(
        f"{base}/{parent_id}",
        json={"version": parent_version, "amounts": {"amount_n": "999.00"}},
    )
    assert resp.status_code == 400, resp.text


# ─────────────────────────────────────────────────────────────────────────────
# 用例 8：更新不存在的行 → 404
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_nonexistent_row_404(client):
    c, wp_id = client
    base = _base(wp_id)
    random_id = uuid.uuid4()
    resp = await c.put(
        f"{base}/{random_id}",
        json={"version": 1, "amounts": {"amount_n": "100.00"}},
    )
    assert resp.status_code == 404, resp.text


# ─────────────────────────────────────────────────────────────────────────────
# 用例 9：deserialize 非法 payload → 422
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deserialize_invalid_payload_422(client):
    c, wp_id = client
    base = _base(wp_id)
    resp = await c.post(f"{base}/deserialize", json={"parents": [{"bad": "x"}]})
    assert resp.status_code == 422, resp.text


# ─────────────────────────────────────────────────────────────────────────────
# 用例 10：aje-suggestion → 200，补提差额 50.00
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aje_suggestion_provision(client):
    c, wp_id = client
    base = _base(wp_id)
    # 建无子行父行
    pr = await c.post(
        f"{base}/parents",
        json={"provision_method": "INDIVIDUAL", "row_label": "单项"},
    )
    assert pr.status_code == 201, pr.text
    parent_id = pr.json()["id"]

    # PUT version=1 amounts={amount_n:150, amount_k:100}
    upd = await c.put(
        f"{base}/{parent_id}",
        json={"version": 1, "amounts": {"amount_n": "150.00", "amount_k": "100.00"}},
    )
    assert upd.status_code == 200, upd.text

    # GET aje-suggestion → 200，amount == "50.00"，direction == "PROVISION"
    sug = await c.get(f"{base}/aje-suggestion")
    assert sug.status_code == 200, sug.text
    body = sug.json()
    assert body is not None, "存在差额应生成建议"
    assert body["amount"] == "50.00"
    assert body["direction"] == "PROVISION"


# ─────────────────────────────────────────────────────────────────────────────
# 用例 N：resolve_wp_index_id 归一（working_paper.id ↔ wp_index_id 兼容）
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_wp_index_id_from_working_paper():
    """传 working_paper.id → 解析为其 wp_index_id。"""
    from app.services.bad_debt_nested_table_service import resolve_wp_index_id

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[BadDebtDetailRow.__table__, WorkingPaper.__table__],
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = factory()

    wp_index_id = uuid.uuid4()
    working_paper_id = uuid.uuid4()
    session.add(
        WorkingPaper(
            id=working_paper_id,
            project_id=uuid.uuid4(),
            wp_index_id=wp_index_id,
            file_path="",
            source_type="template",
            status="draft",
            review_status="not_submitted",
        )
    )
    await session.commit()

    resolved = await resolve_wp_index_id(session, working_paper_id)
    assert resolved == wp_index_id

    await session.close()
    await engine.dispose()


@pytest.mark.asyncio
async def test_resolve_wp_index_id_fallback_unknown_id():
    """传未知 id（本身即 wp_index_id，无对应 working_paper）→ 原值返回。"""
    from app.services.bad_debt_nested_table_service import resolve_wp_index_id

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[BadDebtDetailRow.__table__, WorkingPaper.__table__],
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = factory()

    unknown_id = uuid.uuid4()
    resolved = await resolve_wp_index_id(session, unknown_id)
    assert resolved == unknown_id

    await session.close()
    await engine.dispose()
