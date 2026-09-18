r"""Task 20（tb-writeback-explicit-publish-gate）：各循环合成数据端到端链路集成测试。

**降级路径核心交付**（真实 PG 多数循环无对应审定表真实数据 → 用隔离合成项目做实）。

与既有测试的区别（不重复造已有覆盖）：
  - `test_publish_to_tb_writeback_rows.py`（M0/12）：端点级、**mock DB**，验入参契约（writeback_rows
    优先/occurrence 透传/多科目/三分量零回归/400/幂等 token 合成/角色 403）——**不落真实 TB**。
  - `test_cycle_linkage_handlers_integration.py`：handler 级、**mock session**（捕获 SQL 不落库）。
  - `test_d4_publish_e2e_live.py`：**真 HTTP + 真 PG**，但需运行中的后端(9980)，仅 D4-1 balance 三分量路径。

**本文件补的缺口**：**真实 DB、进程内**驱动完整链路
    端点函数 publish_determination_to_tb（真 DB session + admin）
      → 捕获其发出的 WORKPAPER_SAVED EventPayload
      → 真实 handler _on_d_audit_determination_saved 消费该 payload
      → 断言 trial_balance.audited_amount **真被更新**（真实落库，非 mock）。
无需运行中的 HTTP 后端（比 live 测试更易在 CI/离线跑），但仍打真实 PG。

覆盖各循环**口径类别**代表（端点+handler 对所有循环同构，代表覆盖即可，不逐 30+ 组件重复）：
  - balance 单科目   → D2-1(1122)、J1-1(2211)
  - balance 多科目   → E1-1(1001/1002/1012)、K1-1(1221/1231)、H9-1(2701/2801)
  - occurrence 发生额 → F5-1(6401)、K8-1(6601)、N5-1(6801)、G11-1(1511 发生额示意)

验证要点（对应 task 20* 列举）：
  ① 确认发布→TB 的 audited_amount 真被更新；
  ② 重复同 publish_token 幂等不双写（tb_publish_ack ON CONFLICT）；
  ③ 普通保存（无 publish_confirmed）→ TB 不变；
  ④ occurrence 口径行正确落发生额（handler 直读 audited_amount，balance/occurrence 落库口径一致）；
  ⑤ 多科目 writeback_rows 各科目均落库。

隔离铁律：只操作固定 UUID 隔离合成项目（audit_year=2098，与真实 2024/2025 及 D4 e2e 的 2099 均不撞），
         绝不碰任何真实项目/真实金额。测试后 purge。PG 不可达 → 整文件 skip（不假绿）。

关键实现（跨 loop 陷阱规避）：每个 test 的完整场景（seed reset + 调端点 + 跑 handler + 断言）
在 **单一 asyncio.run（单事件循环）** 内跑完，且把 handler 的 async_session_factory monkeypatch
为本 loop 内的 NullPool 工厂——否则 handler 复用 app 共享池（绑在已关闭的 loop）会 "Event loop is closed"。

执行：
    ..\.venv\Scripts\python.exe -m pytest tests/test_publish_to_tb_synthetic_e2e_chain.py -v --tb=short
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

# ─── 隔离合成常量（固定 UUID / audit_year=2098 / 明显测试标识）──────────────────
SYN_PROJECT_ID = uuid.UUID("2b0e2098-0000-4000-8000-000000002098")
SYN_YEAR = 2098
SYN_COMPANY_CODE = "SYN20"
SYN_CLIENT_NAME = "TB回写合成E2E客户（隔离·非真实）"
SYN_PROJECT_NAME = "TB回写-合成端到端测试项目_请勿动_2098"

# 各口径代表科目集（standard_account_code, account_name, account_category, unadjusted, audited初值）
# account_category 用真实 account_category 枚举成员名（asset/liability/equity/revenue/expense）。
SYN_ACCOUNTS: list[tuple[str, str, str, str, str]] = [
    # balance 单科目代表
    ("1122", "应收账款(SYN)", "asset", "800000.00", "0.00"),          # D2
    ("2211", "应付职工薪酬(SYN)", "liability", "300000.00", "0.00"),   # J1
    # balance 多科目代表（E1 货币资金 / K1 应收+坏账 / H9 租赁负债+未确认融资费用）
    ("1001", "库存现金(SYN)", "asset", "5000.00", "0.00"),            # E1
    ("1002", "银行存款(SYN)", "asset", "1200000.00", "0.00"),         # E1
    ("1012", "其他货币资金(SYN)", "asset", "30000.00", "0.00"),        # E1
    ("1221", "其他应收款(SYN)", "asset", "60000.00", "0.00"),          # K1
    ("1231", "坏账准备(SYN)", "asset", "-4000.00", "0.00"),           # K1（负数）
    ("2701", "租赁负债(SYN)", "liability", "450000.00", "0.00"),       # H9
    ("2801", "未确认融资费用(SYN)", "liability", "-22000.00", "0.00"), # H9（负数）
    # occurrence 发生额代表（F5 营业成本 / K8 销售费用 / N5 所得税费用 / G11 投资示意）
    ("6401", "主营业务成本(SYN)", "expense", "0.00", "0.00"),          # F5 occurrence
    ("6601", "销售费用(SYN)", "expense", "0.00", "0.00"),             # K8 occurrence
    ("6801", "所得税费用(SYN)", "expense", "0.00", "0.00"),           # N5 occurrence
    ("1511", "长期股权投资收益类(SYN)", "revenue", "0.00", "0.00"),    # G11 occurrence 示意
]

# wp_code → (working_paper 固定 UUID, sheet_name, [(account_code, audited_amount, amount_kind), ...])
# 覆盖口径类别代表；audited_amount 为可确定性断言的合成值。
# working_paper UUID 用确定性纯 hex 后缀（0001~0009），保幂等 upsert / purge，无非法字符。
_WP: dict[str, tuple[str, str, list[tuple[str, float, str]]]] = {
    # balance 单科目
    "D2-1": ("2b0e2098-0000-4000-8000-000000000001", "审定表D2-1",
             [("1122", 812345.00, "balance")]),
    "J1-1": ("2b0e2098-0000-4000-8000-000000000002", "审定表J1-1",
             [("2211", 305000.00, "balance")]),
    # balance 多科目
    "E1-1": ("2b0e2098-0000-4000-8000-000000000003", "审定表E1-1",
             [("1001", 5100.00, "balance"), ("1002", 1195000.00, "balance"),
              ("1012", 29000.00, "balance")]),
    "K1-1": ("2b0e2098-0000-4000-8000-000000000004", "审定表K1-1",
             [("1221", 58000.00, "balance"), ("1231", -4500.00, "balance")]),
    "H9-1": ("2b0e2098-0000-4000-8000-000000000005", "审定表H9-1",
             [("2701", 440000.00, "balance"), ("2801", -21000.00, "balance")]),
    # occurrence 发生额
    "F5-1": ("2b0e2098-0000-4000-8000-000000000006", "营业务成本审定表F5-1",
             [("6401", 777000.00, "occurrence")]),
    "K8-1": ("2b0e2098-0000-4000-8000-000000000007", "审定表K8-1",
             [("6601", 123456.00, "occurrence")]),
    "N5-1": ("2b0e2098-0000-4000-8000-000000000008", "审定表N5-1",
             [("6801", 88000.00, "occurrence")]),
    "G11-1": ("2b0e2098-0000-4000-8000-000000000009", "审定表G11-1",
              [("1511", 45000.00, "occurrence")]),
}


# ═══════════════════════════════════════════════════════════════════════════════
# 单事件循环执行框架
#   每个 test 把整个场景 async 函数交给 _run(scenario)：在同一 loop 内
#     1. 建一次性 NullPool 引擎/Session 工厂；
#     2. monkeypatch handler 的 async_session_factory 为该工厂（同 loop 连接，不撞已关闭 loop）；
#     3. 执行 scenario（内部用 _make_session() 拿 db）；
#     4. 结束 restore + dispose。
# ═══════════════════════════════════════════════════════════════════════════════
def _asyncpg_url() -> str:
    from app.core.config import settings
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _run(scenario):
    """在单一事件循环内跑 scenario(ctx)。ctx 提供 make_session() + patch 好的 handler 工厂。"""
    async def _outer():
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import NullPool
        from app.services import event_handlers_cycle_linkage as _h

        engine = create_async_engine(_asyncpg_url(), poolclass=NullPool)
        Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        @asynccontextmanager
        async def _factory(*a, **k):
            async with Session() as s:
                yield s

        orig_factory = _h.async_session_factory
        _h.async_session_factory = _factory  # type: ignore[assignment]

        class _Ctx:
            make_session = staticmethod(Session)

        try:
            return await scenario(_Ctx())
        finally:
            _h.async_session_factory = orig_factory  # type: ignore[assignment]
            await engine.dispose()

    return asyncio.run(_outer())


# ─── PG 可达性探测（不可达则整文件 skip，不假绿）───────────────────────────────
def _pg_reachable() -> bool:
    async def _ping(ctx):
        import sqlalchemy as sa
        async with ctx.make_session() as db:
            await db.execute(sa.text("SELECT 1"))
            n = (
                await db.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM users WHERE username='admin' "
                        "AND is_active=true AND is_deleted=false"
                    )
                )
            ).scalar_one()
        return int(n or 0) >= 1

    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        return bool(_run(_ping))
    except Exception:
        return False


_PG_OK = _pg_reachable()

pytestmark = pytest.mark.skipif(
    not _PG_OK,
    reason="需真实 PG 在线（docker audit-postgres）+ admin 用户存在；否则 skip（不假绿）",
)


# ─── seed / purge / 取证（均接受已开 db session）──────────────────────────────
async def _seed(db) -> uuid.UUID:
    """幂等造隔离合成项目 + 各 wp working_paper + 全部合成 TB 行。返回 admin_id。"""
    import sqlalchemy as sa

    admin_id = (
        await db.execute(
            sa.text("SELECT id FROM users WHERE username='admin' AND is_deleted=false LIMIT 1")
        )
    ).scalar_one()

    await db.execute(
        sa.text(
            """
            INSERT INTO projects
                (id, name, client_name, audit_period_start, audit_period_end,
                 audit_year, status, scenario, has_foreign_currency, consol_level,
                 consol_lock, version, is_large_soe, is_deleted, created_at, updated_at)
            VALUES
                (:id, :name, :client, :ps, :pe, :yr, 'execution', 'normal', false, 1,
                 false, 1, false, false, NOW(), NOW())
            ON CONFLICT (id) DO UPDATE SET
                name=EXCLUDED.name, audit_year=EXCLUDED.audit_year,
                audit_period_end=EXCLUDED.audit_period_end, consol_lock=false, is_deleted=false
            """
        ),
        {"id": str(SYN_PROJECT_ID), "name": SYN_PROJECT_NAME, "client": SYN_CLIENT_NAME,
         "ps": date(SYN_YEAR, 1, 1), "pe": date(SYN_YEAR, 12, 31), "yr": SYN_YEAR},
    )

    for code, name, cat, unadj, aud in SYN_ACCOUNTS:
        await db.execute(
            sa.text(
                """
                INSERT INTO trial_balance
                    (id, project_id, year, company_code, standard_account_code, account_name,
                     account_category, unadjusted_amount, rje_adjustment, aje_adjustment,
                     audited_amount, currency_code, is_deleted, created_at, updated_at)
                VALUES
                    (:id, :pid, :yr, :cc, :code, :name, CAST(:cat AS account_category),
                     :unadj, 0, 0, :aud, 'CNY', false, NOW(), NOW())
                ON CONFLICT (project_id, year, company_code, standard_account_code) DO UPDATE SET
                    account_name=EXCLUDED.account_name, unadjusted_amount=EXCLUDED.unadjusted_amount,
                    audited_amount=EXCLUDED.audited_amount, is_deleted=false
                """
            ),
            {"id": str(uuid.uuid4()), "pid": str(SYN_PROJECT_ID), "yr": SYN_YEAR,
             "cc": SYN_COMPANY_CODE, "code": code, "name": name, "cat": cat,
             "unadj": unadj, "aud": aud},
        )

    for wp_code, (wp_id, _sheet, _rows) in _WP.items():
        existing_idx = (
            await db.execute(
                sa.text(
                    "SELECT id FROM wp_index WHERE project_id=:pid AND wp_code=:code "
                    "AND is_deleted=false LIMIT 1"
                ),
                {"pid": str(SYN_PROJECT_ID), "code": wp_code},
            )
        ).scalar_one_or_none()
        if existing_idx is None:
            wp_index_id = str(uuid.uuid4())
            await db.execute(
                sa.text(
                    """
                    INSERT INTO wp_index
                        (id, project_id, wp_code, wp_name, audit_cycle, status, is_deleted,
                         created_at, updated_at)
                    VALUES (:id, :pid, :code, :name, :cyc, 'not_started', false, NOW(), NOW())
                    """
                ),
                {"id": wp_index_id, "pid": str(SYN_PROJECT_ID), "code": wp_code,
                 "name": f"{wp_code}审定表(SYN)", "cyc": wp_code[0]},
            )
        else:
            wp_index_id = str(existing_idx)

        fp = str(Path("storage") / "projects" / str(SYN_PROJECT_ID) / "workpapers" / wp_code[0]
                 / f"{wp_code}.xlsx")
        await db.execute(
            sa.text(
                """
                INSERT INTO working_paper
                    (id, project_id, wp_index_id, file_path, source_type, status, review_status,
                     file_version, content_revision, prefill_stale, is_deleted, created_at, updated_at)
                VALUES
                    (:id, :pid, :widx, :fp, 'template', 'draft', 'not_submitted',
                     1, 0, false, false, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    file_path=EXCLUDED.file_path, wp_index_id=EXCLUDED.wp_index_id, is_deleted=false
                """
            ),
            {"id": wp_id, "pid": str(SYN_PROJECT_ID), "widx": wp_index_id, "fp": fp},
        )

    await db.commit()
    return admin_id


async def _purge(db) -> None:
    import sqlalchemy as sa
    for tbl in ("tb_publish_ack", "working_paper", "wp_index", "trial_balance", "project_users"):
        await db.execute(sa.text(f"DELETE FROM {tbl} WHERE project_id=:pid"),
                         {"pid": str(SYN_PROJECT_ID)})
    await db.execute(sa.text("DELETE FROM projects WHERE id=:pid"), {"pid": str(SYN_PROJECT_ID)})
    await db.commit()


async def _query_audited(db, codes: list[str]) -> dict[str, Decimal]:
    import sqlalchemy as sa
    rows = (
        await db.execute(
            sa.text(
                "SELECT standard_account_code, audited_amount FROM trial_balance "
                "WHERE project_id=:pid AND year=:yr AND is_deleted=false "
                "AND standard_account_code = ANY(:codes)"
            ),
            {"pid": str(SYN_PROJECT_ID), "yr": SYN_YEAR, "codes": codes},
        )
    ).all()
    return {code: amt for code, amt in rows}


async def _ack_count(db, token: str) -> int:
    import sqlalchemy as sa
    return int(
        (
            await db.execute(
                sa.text("SELECT COUNT(*) FROM tb_publish_ack WHERE publish_token=:tk"),
                {"tk": token},
            )
        ).scalar_one()
    )


async def _reset_audited(db, codes: list[str]) -> None:
    import sqlalchemy as sa
    await db.execute(
        sa.text(
            "UPDATE trial_balance SET audited_amount=0 "
            "WHERE project_id=:pid AND year=:yr AND standard_account_code = ANY(:codes)"
        ),
        {"pid": str(SYN_PROJECT_ID), "yr": SYN_YEAR, "codes": codes},
    )
    await db.commit()


# ─── 驱动完整链路：真端点函数 → 捕获 payload → 真 handler → 真 TB 落库 ───────────
async def _publish_via_endpoint(
    db, *, wp_id: str, sheet_name: str, writeback_rows: list[dict],
    admin_id: uuid.UUID, publish_token: str | None = None,
):
    """调真实端点函数 publish_determination_to_tb（真 DB + admin），返回 (resp, captured_payload)。

    endpoint 内部走 event_bus.publish（debounce 异步），monkeypatch 捕获 payload 供 handler 直驱
    （不改端点逻辑，仅拦截发布通道以拿确定性 payload）。
    """
    from unittest.mock import MagicMock
    from app.routers.wp_html_save import PublishToTbRequest, publish_determination_to_tb
    from app.services import event_bus as _eb_mod

    captured: list = []

    async def _capture(payload):
        captured.append(payload)

    orig = _eb_mod.event_bus.publish
    _eb_mod.event_bus.publish = _capture  # type: ignore[assignment]
    try:
        user = MagicMock()
        user.id = admin_id
        user.role = MagicMock(value="admin")
        body_kwargs: dict = {"sheet_name": sheet_name, "writeback_rows": writeback_rows}
        if publish_token is not None:
            body_kwargs["publish_token"] = publish_token
        body = PublishToTbRequest(**body_kwargs)
        resp = await publish_determination_to_tb(
            wp_id=uuid.UUID(wp_id), body=body, db=db, current_user=user,
        )
    finally:
        _eb_mod.event_bus.publish = orig  # type: ignore[assignment]

    assert captured, "端点未发出 WORKPAPER_SAVED payload"
    return resp, captured[0]


async def _run_handler(payload) -> None:
    """真实 handler 消费 payload（用被 patch 的 async_session_factory 打真 DB → 真落库）。

    handler 还会 publish_immediate(TRIAL_BALANCE_UPDATED)，触发下游 handler（报表重算等）。
    本测试聚焦 TB 落库，patch publish_immediate 为 no-op 以隔离下游、保证断言确定性。
    """
    from app.services import event_handlers_cycle_linkage as _h

    async def _noop(_p):
        return None

    orig = _h.event_bus.publish_immediate
    _h.event_bus.publish_immediate = _noop  # type: ignore[assignment]
    try:
        await _h._on_d_audit_determination_saved(payload)
    finally:
        _h.event_bus.publish_immediate = orig  # type: ignore[assignment]


# ═══════════════════════════════════════════════════════════════════════════════
# module 级 fixture：seed 一次（独立 loop），结束 purge（独立 loop）
# ═══════════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def _admin_id():
    async def _do_seed(ctx):
        async with ctx.make_session() as db:
            return await _seed(db)

    aid = _run(_do_seed)
    try:
        yield aid
    finally:
        async def _do_purge(ctx):
            async with ctx.make_session() as db:
                await _purge(db)
        _run(_do_purge)


# ═══════════════════════════════════════════════════════════════════════════════
# 测试（每个用例：单 loop 内 调端点 → 拿 payload → 跑 handler → 断言真 TB 落库）
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "wp_code",
    ["D2-1", "J1-1", "E1-1", "K1-1", "H9-1", "F5-1", "K8-1", "N5-1", "G11-1"],
)
def test_publish_lands_audited_to_tb(_admin_id, wp_code):
    """验证要点①④⑤：确认发布 → 各口径（balance 单/多、occurrence）审定数真落 trial_balance。"""
    wp_id, sheet_name, rows = _WP[wp_code]
    codes = [c for c, _amt, _k in rows]
    expected = {c: Decimal(str(amt)).quantize(Decimal("0.01")) for c, amt, _k in rows}
    token = f"syn-land-{wp_code}-{uuid.uuid4()}"
    occ_codes = [c for c, _a, k in rows if k == "occurrence"]

    async def _scenario(ctx):
        async with ctx.make_session() as db:
            await _reset_audited(db, codes)

        async with ctx.make_session() as db:
            wb = [{"account_code": c, "audited_amount": amt, "amount_kind": k} for c, amt, k in rows]
            resp, payload = await _publish_via_endpoint(
                db, wp_id=wp_id, sheet_name=sheet_name, writeback_rows=wb,
                admin_id=_admin_id, publish_token=token,
            )
        assert resp.published is True
        assert resp.wp_code == wp_code
        # occurrence 语义标注透传（要点④：口径区分）
        if occ_codes:
            assert payload.extra.get("amount_kinds"), "occurrence 应透传 amount_kinds"
            for c in occ_codes:
                assert payload.extra["amount_kinds"][c] == "occurrence"

        # 真 handler 消费 → 真落库
        await _run_handler(payload)

        async with ctx.make_session() as db:
            got = await _query_audited(db, codes)
            ack = await _ack_count(db, token)
        for c in codes:
            assert got.get(c) == expected[c], (
                f"{wp_code} 科目 {c} 期望 audited={expected[c]} 实得 {got.get(c)}（真实 TB 未正确落库）"
            )
        assert ack == 1, f"{wp_code} tb_publish_ack 应恰一条，实得 {ack}"

        # 清本用例 ack（避免污染幂等/其他用例）
        async with ctx.make_session() as db:
            import sqlalchemy as sa
            await db.execute(sa.text("DELETE FROM tb_publish_ack WHERE publish_token=:tk"),
                             {"tk": token})
            await db.commit()

    _run(_scenario)


def test_idempotent_same_token_no_double_write(_admin_id):
    """验证要点②：同 publish_token 重放 → TB 不二次改写、ack 仍一条（tb_publish_ack ON CONFLICT）。"""
    wp_id, sheet_name, _rows = _WP["D2-1"]
    codes = ["1122"]
    token = f"syn-idem-{uuid.uuid4()}"

    async def _scenario(ctx):
        async with ctx.make_session() as db:
            await _reset_audited(db, codes)

        wb = [{"account_code": "1122", "audited_amount": 500000.0, "amount_kind": "balance"}]

        # 第一次发布 + handler → 落 500000
        async with ctx.make_session() as db:
            _r1, payload1 = await _publish_via_endpoint(
                db, wp_id=wp_id, sheet_name=sheet_name, writeback_rows=wb,
                admin_id=_admin_id, publish_token=token,
            )
        await _run_handler(payload1)
        async with ctx.make_session() as db:
            got1 = await _query_audited(db, codes)
        assert got1.get("1122") == Decimal("500000.00")

        # 篡改 TB 为哨兵 999（若二次回写就会变化）
        async with ctx.make_session() as db:
            import sqlalchemy as sa
            await db.execute(
                sa.text(
                    "UPDATE trial_balance SET audited_amount=999 "
                    "WHERE project_id=:pid AND year=:yr AND standard_account_code='1122'"
                ),
                {"pid": str(SYN_PROJECT_ID), "yr": SYN_YEAR},
            )
            await db.commit()

        # 第二次发布同 token + handler → 幂等跳过，不应改回 500000
        async with ctx.make_session() as db:
            _r2, payload2 = await _publish_via_endpoint(
                db, wp_id=wp_id, sheet_name=sheet_name, writeback_rows=wb,
                admin_id=_admin_id, publish_token=token,
            )
        await _run_handler(payload2)
        async with ctx.make_session() as db:
            got2 = await _query_audited(db, codes)
            ack = await _ack_count(db, token)
        assert got2.get("1122") == Decimal("999.00"), (
            f"幂等失败：第二次发布二次回写了 TB（1122={got2.get('1122')}，应保持哨兵 999）"
        )
        assert ack == 1, f"幂等失败：tb_publish_ack 应仍为一条，实得 {ack}"

        async with ctx.make_session() as db:
            import sqlalchemy as sa
            await db.execute(sa.text("DELETE FROM tb_publish_ack WHERE publish_token=:tk"),
                             {"tk": token})
            await db.commit()

    _run(_scenario)


def test_normal_save_without_publish_confirmed_no_op(_admin_id):
    """验证要点③：普通保存（无 publish_confirmed）→ handler no-op，TB 不变。"""
    codes = ["1122"]

    async def _scenario(ctx):
        from app.models.audit_platform_schemas import EventPayload, EventType

        async with ctx.make_session() as db:
            await _reset_audited(db, codes)

        # 与发布同构、但 **不带 publish_confirmed** 的 WORKPAPER_SAVED（普通保存态）
        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=SYN_PROJECT_ID,
            year=SYN_YEAR,
            extra={
                "wp_code": "D2-1",
                "trigger": "normal_save",
                "parsed_data": {"rows": [{"account_code": "1122", "audited_amount": 424242.0}]},
                # 故意不设 publish_confirmed
            },
        )
        await _run_handler(payload)

        async with ctx.make_session() as db:
            got = await _query_audited(db, codes)
        assert got.get("1122") == Decimal("0.00"), (
            f"普通保存不应写 TB，但 1122 变为 {got.get('1122')}（handler 门控失效）"
        )

    _run(_scenario)


def test_non_determination_sheet_no_op(_admin_id):
    """补充：非审定表 wp_code（无 [D-N]{n}-1）→ handler 直接 return，TB 不变。"""
    codes = ["1122"]

    async def _scenario(ctx):
        from app.models.audit_platform_schemas import EventPayload, EventType

        async with ctx.make_session() as db:
            await _reset_audited(db, codes)

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=SYN_PROJECT_ID,
            year=SYN_YEAR,
            extra={
                "wp_code": "D2-2",  # 明细表，非审定表子码
                "trigger": "audit_determination_publish",
                "parsed_data": {"rows": [{"account_code": "1122", "audited_amount": 111111.0}]},
                "publish_confirmed": True,
                "confirmed_by": None,
                "publish_token": f"syn-nondet-{uuid.uuid4()}",
            },
        )
        await _run_handler(payload)

        async with ctx.make_session() as db:
            got = await _query_audited(db, codes)
        assert got.get("1122") == Decimal("0.00"), (
            f"非审定表 sheet 不应写 TB，但 1122 变为 {got.get('1122')}"
        )

    _run(_scenario)
