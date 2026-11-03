"""试算表父子不符告警到达用户可见结果（spec formula-hub-integrity-closure 需求 4.3；ADR-FHIC-03 / 19）。

- **推送**：真推送引擎 ``formula_push.engine.run``（经 ``run_and_commit``）+ 真 D1 binding 取数（``load_tb_audited`` 读
  SQLite 真 ORM 试算表行），父 ``1231-01`` = 100、子 40 + 50 ⇒ ``TB('1231-01')`` 取 90，运行结果 ``warnings``（接口摘要与
  落库的 ``formula_push_run.detail``）含科目码「1231-01」与差额「10.00」。
- **中央 execute 与 debug**（任务 12）：``POST /api/formula/execute`` / ``/batch-execute`` / ``/api/formula/debug`` 真发请求
  （夹具与装配见 ``_central_world.py``：只替换 ``get_current_user`` / ``get_db``），父 ``1231`` = 100、子 40 + 50 ⇒
  ``TB('1231','审定数')`` 取 90，三个响应的 ``warnings`` 含「1231」与「10.00」；父行改为 90 后不再告警。
- **报表行结果**（任务 16）：全量生成（夹具见 ``_report_compute_world``，SQLite 真 ORM）父 ``1231`` = 100、子 40 + 50 ⇒
  ``TB('1231','期末余额')`` 行值 90，行结果 ``warnings`` 与覆盖率统计的行告警含「1231」与「10.00」；父行改为 90 后不再告警。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.models.audit_platform_models import AccountCategory, TrialBalance
from tests._formula_push_env import YEAR, make_env
from tests.formula_hub._central_world import Row, post_batch, post_debug, post_execute, sqlite_endpoint
from tests.formula_hub._report_compute_world import LEAF, run_path, set_tb, sqlite_world

D1_TARGET = "D1/D1-1/D1-adj-tb-amount"
#: (码, 期末审定数)：D1 = TB('1121') − TB('1231-01')；1231-01 父 100 ≠ 子 40 + 50
_TB_ROWS = (("1121", "500"), ("1231-01", "100"), ("1231-01-01", "40"), ("1231-01-02", "50"))


@pytest_asyncio.fixture
async def env(monkeypatch):
    async with make_env(monkeypatch, extra_tables=(TrialBalance.__table__,)) as e:
        idx, wp = uuid.uuid4(), uuid.uuid4()
        async with e.factory() as db:
            await db.execute(sa.text("INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, 'D1')"),
                             {"i": str(idx), "p": str(e.pid)})
            await db.execute(sa.text("INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"),
                             {"w": str(wp), "p": str(e.pid), "i": str(idx)})
            for code, audited in _TB_ROWS:
                db.add(TrialBalance(project_id=e.pid, year=YEAR, company_code="001", standard_account_code=code,
                                    account_name=code, account_category=AccountCategory.asset,
                                    audited_amount=Decimal(audited), opening_balance=Decimal("0")))
            await db.commit()

        async def fake_template_type(db, project_id):  # 附注模板类型与本用例无关（无附注行，附注阶段按缺章跳过）
            return "listed"

        monkeypatch.setattr("app.services.formula_push.bindings.tier_a._load_template_type", fake_template_type)
        yield e


def _leaf_warning(texts):
    return [t for t in texts if "1231-01" in t and "10.00" in t]


@pytest.mark.asyncio
async def test_push_run_result_carries_leaf_warning(env):
    """推送运行结果：值按叶子（500 − 90 = 410），告警进接口摘要与落库运行记录。"""
    result = await env.push(codes=("D1",))
    item = next(i for i in result.items if i.addr_id == D1_TARGET)
    assert item.formula == pytest.approx(410.0), item
    assert _leaf_warning(result.summary()["warnings"]), result.summary()["warnings"]
    (run,) = await env.runs()
    assert _leaf_warning(run.detail["warnings"]), run.detail["warnings"]


@pytest.mark.asyncio
async def test_push_run_without_mismatch_has_no_leaf_warning(env):
    """对照：父行改为 90（= 40 + 50）后值不变、不再告警（告警只因父子不符而来）。"""
    async with env.factory() as db:
        await db.execute(sa.text("UPDATE trial_balance SET audited_amount = 90 WHERE standard_account_code = '1231-01'"))
        await db.commit()
    result = await env.push(codes=("D1",))
    item = next(i for i in result.items if i.addr_id == D1_TARGET)
    assert item.formula == pytest.approx(410.0)
    assert not [t for t in result.summary()["warnings"] if "1231-01" in t]


# ─── 中央 execute 与 debug（任务 12） ─────────────────────────────────────────

_CENTRAL_FORMULA = "TB('1231','审定数')"


def _central_rows(parent: int) -> dict[str, tuple[Row, ...]]:
    """父 1231 = ``parent``、子 40 + 50（审定 = 未审）。"""
    return {"leaf": tuple(Row(code, Decimal(v), Decimal(v)) for code, v in
                          (("1231", parent), ("1231-01", 40), ("1231-02", 50)))}


def _central_leaf_warning(texts):
    return [t for t in texts if "1231" in t and "10.00" in t]


def _central_responses(parent: int) -> dict[str, dict]:
    with sqlite_endpoint(_central_rows(parent), tag="fh_task12_warn") as (client, world):
        pid = world.projects["leaf"]
        (batched,) = post_batch(client, pid, [_CENTRAL_FORMULA])
        return {"execute": post_execute(client, pid, _CENTRAL_FORMULA), "batch": batched,
                "debug": post_debug(client, pid, _CENTRAL_FORMULA)}


def test_central_execute_and_debug_carry_leaf_warning():
    """父 100 ≠ 子 40 + 50：三个端点值都是 90、``ok``，``warnings`` 含科目码与差额。"""
    got = _central_responses(100)
    for kind in ("execute", "batch"):
        assert (got[kind]["value"], got[kind]["ok"], got[kind]["state"]) == (90.0, True, "ok"), got[kind]
    assert (Decimal(got["debug"]["value"]), got["debug"]["ok"]) == (Decimal(90), True), got["debug"]
    for kind, body in got.items():
        assert _central_leaf_warning(body["warnings"]), (kind, body["warnings"])


def test_central_execute_and_debug_without_mismatch_have_no_leaf_warning():
    """对照：父行改为 90（= 40 + 50）后值不变、三个端点都不再有 1231 的告警。"""
    got = _central_responses(90)
    for kind in ("execute", "batch"):
        assert (got[kind]["value"], got[kind]["ok"]) == (90.0, True), got[kind]
    assert Decimal(got["debug"]["value"]) == Decimal(90), got["debug"]
    for kind, body in got.items():
        assert not [t for t in body["warnings"] if "1231" in t], (kind, body["warnings"])


# ─── 报表行结果（任务 16） ─────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("parent, warned", [(100, True), (90, False)])
async def test_report_row_result_carries_leaf_warning(parent, warned):
    """全量生成的报表行结果：值按叶子 90（不论父行金额）；父 100 ≠ 子 40 + 50 时行 ``warnings`` 与覆盖率行告警含科目码与差额。"""
    async with sqlite_world(tag="fh_t16_leaf") as world:
        await set_tb(world, "1231", parent)
        result = await run_path(world, "full")
    row = next(r for r in result["balance_sheet"] if r["row_code"] == LEAF)
    assert (Decimal(row["current_period_amount"]), row["formula_error"]) == (Decimal(90), None), row
    coverage = [w["message"] for w in result["coverage_stats"]["by_type"]["balance_sheet"].get("warnings", [])
                if w["row_code"] == LEAF]
    assert bool(_central_leaf_warning(row["warnings"])) is warned, row["warnings"]
    assert bool(_central_leaf_warning(coverage)) is warned, coverage
