"""D4「发布到试算表」后端 API 级端到端实测（P0-3b · spec d4-dual-mode-formula-governance）。

打**真实运行的后端**（127.0.0.1:9980）+ **真实 PG**，端到端验证显式发布链路：
    POST /api/workpapers/{wp_id}/audit-determination/publish-to-tb

前置（须先跑）：
  1. 后端已运行（start-dev.bat，9980）+ PG 在线。
  2. seed 隔离测试项目：
        ../.venv/Scripts/python.exe scripts/e2e/seed_d4_publish_e2e.py
     造出 project=d4e2e000-…-d401（audit_year=2099）、TB 6001/6051（audited 初值 0）、
     wp_index D4-1、working_paper wp_id=d4e2e000-…-d403。

不满足前置 → 整文件 skip（不假绿）。**只操作隔离测试项目 d4e2e…，绝不碰真实项目/真实金额。**

覆盖：
  - test_publish_happy_path        发布成功 → response.published=True + TB audited == 三者和 + tb_publish_ack 一条
  - test_publish_idempotent        同 token 再发一次 → TB 不二次变化、ack 仍一条
  - test_publish_400_no_audit_rows 无 audit_rows → 400，TB 不变
  - test_publish_400_non_det_sheet 非审定表 sheet → 400，TB 不变

执行：
    python -m pytest backend/tests/test_d4_publish_e2e_live.py -v --tb=short
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from decimal import Decimal

import pytest

# ─── seed 常量（与 scripts/e2e/seed_d4_publish_e2e.py 对齐）───────────────────────
TEST_PROJECT_ID = "d4e2e000-0000-4000-8000-00000000d401"
TEST_WP_ID = "d4e2e000-0000-4000-8000-00000000d403"
TEST_YEAR = 2099
TEST_SHEET_NAME = "审定表D4-1"
import os as _os
BASE = _os.environ.get("D4_E2E_BASE", "http://127.0.0.1:9980")
_DEBOUNCE_WAIT = 2.0  # event_bus.publish debounce=500ms + dispatch/commit 余量


async def _run_sql(fn):
    """在**独立引擎 + NullPool** 上跑一段异步 SQL 并 dispose。

    关键：本测试用多次 asyncio.run（每次新事件循环），若复用 app.core.database 的
    共享连接池会撞 "Event loop is closed"（池里 asyncpg 连接绑在首个已关闭的 loop）。
    每次用一次性 NullPool 引擎彻底规避跨 loop 复用连接。
    """
    import sqlalchemy as sa  # noqa: F401
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, poolclass=NullPool)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as db:
            return await fn(db)
    finally:
        await engine.dispose()

# ─── 环境探测（后端在线 + seed 数据存在 + httpx 可用；否则 skip）─────────────────
try:
    sys.path.insert(0, "backend")
    import httpx  # noqa: E402
    from app.core.config import settings  # noqa: E402

    _DB_URL = bool(settings.DATABASE_URL)
except Exception:
    _DB_URL = False
    httpx = None  # type: ignore


def _backend_up() -> bool:
    if not _DB_URL or httpx is None:
        return False
    try:
        r = httpx.get(f"{BASE}/api/health", timeout=5.0)
        return r.status_code == 200
    except Exception:
        return False


def _seed_present() -> bool:
    """检查隔离测试项目 + TB 行是否已 seed（未 seed 则 skip 而非造数）。"""
    async def _check(db) -> bool:
        import sqlalchemy as sa
        n = (
            await db.execute(
                sa.text(
                    "SELECT COUNT(*) FROM trial_balance "
                    "WHERE project_id = :pid AND year = :yr AND is_deleted = false"
                ),
                {"pid": TEST_PROJECT_ID, "yr": TEST_YEAR},
            )
        ).scalar_one()
        return int(n or 0) >= 2
    try:
        return asyncio.run(_run_sql(_check))
    except Exception:
        return False


_BACKEND_UP = _backend_up()
_SEED_OK = _seed_present() if _BACKEND_UP else False

pytestmark = pytest.mark.skipif(
    not (_BACKEND_UP and _SEED_OK),
    reason=(
        "需真实后端(9980)在线 + 已 seed 隔离测试项目"
        "（跑 scripts/e2e/seed_d4_publish_e2e.py）"
    ),
)


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════════════════════════

def _login() -> str:
    r = httpx.post(
        f"{BASE}/api/auth/login",
        json={"username": "admin", "password": "admin123"},
        timeout=30.0,
    )
    r.raise_for_status()
    body = r.json()
    return body["data"]["access_token"]


def _audit_rows() -> list[dict]:
    """两行可回写审定行 + 一行小计（应被跳过）。

    6001: audited = 1000000 + 5000(adj) + 0(reclass) = 1005000
    6051: audited = 200000 + 0 + (-3000)(reclass) = 197000
    """
    return [
        {"id": "r1", "account_code": "6001", "current_unadjusted": 1000000,
         "adj_amount": 5000, "reclass_amount": 0},
        {"id": "r2", "account_code": "6051", "current_unadjusted": 200000,
         "adj_amount": 0, "reclass_amount": -3000},
        {"id": "r3", "isSection": True, "account_code": None},  # 小计行，须跳过
    ]


_EXPECTED = {"6001": Decimal("1005000.00"), "6051": Decimal("197000.00")}


def _post_publish(token: str, *, sheet_name=TEST_SHEET_NAME, audit_rows=None,
                  publish_token=None) -> httpx.Response:
    payload: dict = {
        "sheet_name": sheet_name,
        "html_data": {"audit_rows": audit_rows if audit_rows is not None else _audit_rows()},
    }
    if publish_token is not None:
        payload["publish_token"] = publish_token
    return httpx.post(
        f"{BASE}/api/workpapers/{TEST_WP_ID}/audit-determination/publish-to-tb",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )


def _query_tb() -> dict[str, Decimal]:
    async def _q(db) -> dict[str, Decimal]:
        import sqlalchemy as sa
        rows = (
            await db.execute(
                sa.text(
                    "SELECT standard_account_code, audited_amount FROM trial_balance "
                    "WHERE project_id = :pid AND year = :yr AND is_deleted = false"
                ),
                {"pid": TEST_PROJECT_ID, "yr": TEST_YEAR},
            )
        ).all()
        return {code: amt for code, amt in rows}
    return asyncio.run(_run_sql(_q))


def _query_ack(token: str) -> list[dict]:
    async def _q(db) -> list[dict]:
        import sqlalchemy as sa
        rows = (
            await db.execute(
                sa.text(
                    "SELECT publish_token, accounts_updated FROM tb_publish_ack "
                    "WHERE publish_token = :tk"
                ),
                {"tk": token},
            )
        ).mappings().all()
        return [dict(r) for r in rows]
    return asyncio.run(_run_sql(_q))


def _reset_tb_audited() -> None:
    """把测试 TB 行 audited_amount 归零（测试前置，保证断言可复现）。"""
    async def _r(db) -> None:
        import sqlalchemy as sa
        await db.execute(
            sa.text(
                "UPDATE trial_balance SET audited_amount = 0 "
                "WHERE project_id = :pid AND year = :yr"
            ),
            {"pid": TEST_PROJECT_ID, "yr": TEST_YEAR},
        )
        await db.commit()
    asyncio.run(_run_sql(_r))


def _bump_6001(value: int) -> None:
    """把 6001 的 audited_amount 设为可检测哨兵值（幂等测试用）。"""
    async def _b(db) -> None:
        import sqlalchemy as sa
        await db.execute(
            sa.text(
                "UPDATE trial_balance SET audited_amount = :v "
                "WHERE project_id = :pid AND year = :yr AND standard_account_code = '6001'"
            ),
            {"v": value, "pid": TEST_PROJECT_ID, "yr": TEST_YEAR},
        )
        await db.commit()
    asyncio.run(_run_sql(_b))


def _purge_ack(token: str) -> None:
    async def _p(db) -> None:
        import sqlalchemy as sa
        await db.execute(
            sa.text("DELETE FROM tb_publish_ack WHERE publish_token = :tk"),
            {"tk": token},
        )
        await db.commit()
    asyncio.run(_run_sql(_p))


# ═══════════════════════════════════════════════════════════════════════════════
# 测试
# ═══════════════════════════════════════════════════════════════════════════════

def test_publish_happy_path():
    """发布成功 → published=True；TB audited == 三者和；tb_publish_ack 一条。"""
    token = _login()
    ptok = f"e2e-happy-{uuid.uuid4()}"
    _purge_ack(ptok)
    _reset_tb_audited()

    resp = _post_publish(token, publish_token=ptok)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    data = body.get("data", body)  # ResponseWrapperMiddleware 信封
    assert data["published"] is True
    assert data["wp_code"] == "D4-1"
    assert data["publish_token"] == ptok

    # handler 经 debounce 异步回写 → 等 dispatch 落库
    import time
    time.sleep(_DEBOUNCE_WAIT)

    tb = _query_tb()
    assert tb.get("6001") == _EXPECTED["6001"], f"6001 expected {_EXPECTED['6001']} got {tb.get('6001')}"
    assert tb.get("6051") == _EXPECTED["6051"], f"6051 expected {_EXPECTED['6051']} got {tb.get('6051')}"

    ack = _query_ack(ptok)
    assert len(ack) == 1, f"tb_publish_ack 应恰有一条，实得 {len(ack)}"
    assert ack[0]["accounts_updated"] == 2

    _purge_ack(ptok)


def test_publish_idempotent():
    """同 publish_token 再发一次 → TB 不二次变化、ack 仍一条（幂等）。"""
    token = _login()
    ptok = f"e2e-idem-{uuid.uuid4()}"
    _purge_ack(ptok)
    _reset_tb_audited()

    import time
    # 第一次发布
    r1 = _post_publish(token, publish_token=ptok)
    assert r1.status_code == 200, r1.text
    time.sleep(_DEBOUNCE_WAIT)
    tb1 = _query_tb()
    assert tb1.get("6001") == _EXPECTED["6001"]

    # 篡改 TB 制造"若二次回写就会变化"的可检测差异（幂等则应保持不变）
    _bump_6001(999)

    # 第二次发布（同 token）→ 幂等跳过，不应把 6001 改回 1005000
    r2 = _post_publish(token, publish_token=ptok)
    assert r2.status_code == 200, r2.text
    time.sleep(_DEBOUNCE_WAIT)
    tb2 = _query_tb()
    assert tb2.get("6001") == Decimal("999.00"), (
        f"幂等失败：第二次发布二次回写了 TB（6001={tb2.get('6001')}，应保持 999）"
    )

    ack = _query_ack(ptok)
    assert len(ack) == 1, f"幂等失败：tb_publish_ack 应仍为一条，实得 {len(ack)}"

    _purge_ack(ptok)
    _reset_tb_audited()


def test_publish_400_no_audit_rows():
    """无 audit_rows → 400，TB 不变。"""
    token = _login()
    _reset_tb_audited()
    resp = _post_publish(token, audit_rows=[])
    assert resp.status_code == 400, resp.text
    import time
    time.sleep(0.5)
    tb = _query_tb()
    assert tb.get("6001") == Decimal("0.00")
    assert tb.get("6051") == Decimal("0.00")


def test_publish_400_non_determination_sheet():
    """非审定表 sheet（无 [D-N]n-1 子码）→ 400，TB 不变。"""
    token = _login()
    _reset_tb_audited()
    resp = _post_publish(token, sheet_name="D4-2 明细表")
    assert resp.status_code == 400, resp.text
    import time
    time.sleep(0.5)
    tb = _query_tb()
    assert tb.get("6001") == Decimal("0.00")
    assert tb.get("6051") == Decimal("0.00")
