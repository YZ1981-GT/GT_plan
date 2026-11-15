"""时效判定（AQF 任务 10 的 W2 判据，后端侧；真 PG）。

W2 的浏览器判据是「录入一笔 AJE → 切回查询页触发自动判定 → 显示已过期与原因「调整分录行数 a → b」
→ 重新查询 → 未变化」。其中**决定正确性的部分**在服务端：采集时记各分量摘要，判定时
`recapture_vector` 重新采集、`compare_vector` 逐分量比较（路由 `_freshness_for_vector` 就是这两步）。
前端只负责显示与 60 秒节流。

本文件在**回滚事务**里造数据，因此能验「行数变了就判 stale、没变就判 current」，且不在共享库留残留
（W2 原判据要往真实项目写 AJE，会污染共享库 —— 这正是它长期无法执行的根因）。

判据：
1. **数据没动 → current**（不是空转：第 2 条证明同一路径会判 stale）。
2. **多一行 → stale**，`changes` 里有原因（design §4.5 的中文原因）。
3. **重新采集后 → current**，且新旧 `vector_hash` 不同（证明摘要确实含行数）。
4. **空向量 → unknown**（不能因为「没东西可比」就报 current）。
5. **作用域隔离**：另一个项目的数据变化不把本项目判成 stale。
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.pg_only

_INSERT_AJE = text("""
    INSERT INTO adjustments (id, project_id, year, company_code, adjustment_no, adjustment_type,
           account_code, account_name, debit_amount, credit_amount, entry_group_id, created_by)
    VALUES (gen_random_uuid(), :pid, :y, 'AQF', :no, 'aje', :code, :name, :amt, 0,
            gen_random_uuid(), :uid)
""")


async def _admin_id(session) -> uuid.UUID:
    row = (await session.execute(text(
        "SELECT id FROM users WHERE username='admin' AND is_deleted=false LIMIT 1"))).first()
    if row is None:
        pytest.fail("共享库没有 admin 账号，造数据需要合法 created_by")
    return row[0]


async def _seed_project(session, suffix: str = "AQF 时效") -> tuple[uuid.UUID, int]:
    from tests.advanced_query_linkage.writable_projects import insert_test_project

    year = 2025
    pid, _name = await insert_test_project(session, name_suffix=suffix, audit_year=year)
    await _add_aje(session, pid, year, no="AJE-1", code="1001", name="库存现金", amt=100)
    await session.flush()
    return pid, year


async def _add_aje(session, pid, year, *, no: str, code: str, name: str, amt: int) -> None:
    await session.execute(_INSERT_AJE, {
        "pid": str(pid), "y": year, "no": no, "code": code, "name": name,
        "amt": amt, "uid": str(await _admin_id(session)),
    })


async def _capture(session, pid, year, *, source="adj_aje"):
    from app.services.custom_query.version_capture import capture_business_vector

    return await capture_business_vector(
        session, source, scope={"project_id": str(pid), "year": year}, acnr_targets=False)


async def _judge(session, vector_dict) -> dict:
    """与路由 `_freshness_for_vector` 同一路径：重新采集 + 比较。"""
    from app.services.custom_query.version_capture import recapture_vector
    from app.services.custom_query.version_compare import compare_vector

    components = vector_dict.get("components") or []
    if not components:
        return {"status": "unknown", "reason": "版本向量为空，无法判定"}
    recaptured = await recapture_vector(session, components)
    return compare_vector(components, recaptured)


async def test_unchanged_is_current_then_one_more_row_is_stale(pg_rollback_session):
    """W2 核心：数据没动判 current；多一行判 stale 且带原因；重新采集后回到 current。"""
    session = pg_rollback_session
    pid, year = await _seed_project(session)

    vector = await _capture(session, pid, year)
    assert vector.vector_hash, "采集到的版本向量为空 ⇒ 后续判定全是 unknown，测不到 stale"
    assert vector.components, "分量清单为空 ⇒ 判定会直接 unknown"

    same = await _judge(session, vector.as_dict())
    assert same["status"] == "current", f"数据未变却判成 {same['status']}：{same}"

    # 模拟 W2 的「录入一笔 AJE」
    await _add_aje(session, pid, year, no="AJE-2", code="1002", name="银行存款", amt=200)
    await session.flush()

    changed = await _judge(session, vector.as_dict())
    assert changed["status"] == "stale", f"多了一行调整分录却判成 {changed['status']}：{changed}"
    changes = changed.get("changes") or []
    assert changes, f"判 stale 却没给原因：{changed}"
    joined = " ".join(str(c.get("reason") or "") for c in changes)
    assert joined.strip(), f"原因全为空：{changes}"

    fresh = await _capture(session, pid, year)
    assert fresh.vector_hash != vector.vector_hash, "数据变了但摘要没变 ⇒ 摘要没含行数"
    after = await _judge(session, fresh.as_dict())
    assert after["status"] == "current", f"重新采集后仍判 {after['status']}：{after}"


async def test_empty_vector_is_unknown_not_current(pg_rollback_session):
    """空向量 ⇒ `unknown`（不能因为「没东西可比」就报 current —— 那是静默假绿）。"""
    result = await _judge(pg_rollback_session, {"components": [], "vector_hash": ""})
    assert result["status"] == "unknown", f"空向量应判 unknown，实得 {result}"
    assert result.get("reason"), "unknown 必须给原因（前端要显示）"


async def test_other_projects_changes_do_not_mark_this_one_stale(pg_rollback_session):
    """作用域隔离：另一个项目多一行，本项目仍判 current。"""
    session = pg_rollback_session
    pid_a, year = await _seed_project(session, "AQF 时效-甲")
    pid_b, _name = await _seed_project(session, "AQF 时效-乙")

    vector_a = await _capture(session, pid_a, year)
    await _add_aje(session, pid_b, year, no="AJE-B1", code="1001", name="库存现金", amt=999)
    await session.flush()

    result = await _judge(session, vector_a.as_dict())
    assert result["status"] == "current", (
        f"乙项目变了却把甲项目判成 {result['status']} —— 作用域没隔离：{result}"
    )
