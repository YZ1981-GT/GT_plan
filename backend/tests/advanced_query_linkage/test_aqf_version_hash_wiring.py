"""AQF 版本摘要接线守卫（2026-11-15，任务 10 走查抓到的真实缺陷）。

缺陷形态：`VersionVector` 的字段名是 `vector_hash`，但编排器与构建器都写成 `version_vector.hash`
⇒ `AttributeError` 被 `except Exception` 以 `logger.debug` 静默吞掉，表现为
「`result.version` 有值、`req.version_hash` 恒 None、运行记录永远『未采集到版本向量』」。
它不会让任何查询失败，因此普通回归全绿也看不出来。

三层判据（都取真实运行期值，不读源码文本）：
1. 结构层：`VersionVector` 上没有 `hash` 属性、有 `vector_hash` —— 钉住字段名本身；
2. 接线层：真 PG 跑一次 `execute_business_query`，`result["_version_hash"]` 必须非空且等于
   `result["version"]["vector_hash"]`，`result["run"]["recorded"]` 必须为 True；
3. 反向对照：把版本向量换成空摘要时，运行记录必须如实降级（`recorded=False`），
   证明第 2 条不是「无论怎样都绿」。
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.services.custom_query.version_capture import VersionVector


def test_version_vector_exposes_vector_hash_not_hash():
    """结构层：字段名是 `vector_hash`（`hash` 不存在）。"""
    assert "vector_hash" in set(VersionVector.__dataclass_fields__)
    assert not hasattr(VersionVector, "hash"), (
        "VersionVector 上出现了 `hash` 属性；若这是有意新增的别名，请同时删掉本守卫的反向断言，"
        "否则编排器里写错字段名又会被 except 静默吞掉"
    )


async def _admin_user(db):
    from types import SimpleNamespace

    row = (await db.execute(text(
        "SELECT id, username, role::text FROM users WHERE username='admin' AND is_deleted=false LIMIT 1"
    ))).first()
    if row is None:
        pytest.fail("共享库没有 admin 账号，无法验证运行记录接线")
    return SimpleNamespace(id=row[0], username=row[1], role=row[2])


async def _picked_project(db):
    """按数据能力取一个【测试】项目（不写死 UUID）。"""
    row = (await db.execute(text("""
        SELECT p.id, EXTRACT(YEAR FROM p.audit_period_end)::int
          FROM projects p
         WHERE p.is_deleted = false
           AND p.name LIKE '%测试%'
           AND EXTRACT(YEAR FROM p.audit_period_end) IS NOT NULL
         ORDER BY p.id
         LIMIT 1
    """))).first()
    if row is None:
        pytest.fail("共享库没有「名称含测试且有审计年度」的项目，本用例无法验证真实接线")
    return row[0], row[1]


@pytest.mark.pg_only
async def test_execute_reports_version_hash_and_records_run(pg_rollback_session):
    """接线层：业务视图执行后版本向量非空、运行记录真的写进库。

    注意 `_version_hash` 是**内部键**：`business_execute` 在登记运行记录时 `pop` 掉它，
    所以对外的响应里不该有它（有反而说明内部键泄漏到了前端）。真正要断言的是：
    ① `version.vector_hash` 非空（采集成功）；② `run.recorded is True` 且给了运行编号
    （登记成功 —— 这一条同时钉住两处历史缺陷：`version_vector.hash` 拼错被 except 吞掉、
    `captured_at` 传字符串让 asyncpg 报 DataError）。

    🔴 第三处历史缺陷：登记在 SAVEPOINT 内、**路由必须提交**。`get_db` 只开会话不提交，
    不提交的话响应里 `recorded=true` 而库里 0 行 —— 因此这里直接查库核验。
    """
    from app.routers.custom_query import QueryRequest
    from app.services.custom_query.business_execute import execute_business_query

    db = pg_rollback_session
    user = await _admin_user(db)
    project_id, year = await _picked_project(db)

    body = QueryRequest(project_id=str(project_id), year=int(year), source="adj_aje", limit=5, offset=0)
    result = await execute_business_query(body, user=user, db=db, origin="direct")

    version = result.get("version") or {}
    assert version.get("vector_hash"), "result.version.vector_hash 为空 —— 版本向量未采集"
    run = result.get("run") or {}
    assert run.get("recorded") is True, (
        f"运行记录未写入：{run}。历史缺陷有三处：① 编排器写 `version_vector.hash`（字段名实为 "
        "`vector_hash`）⇒ AttributeError 被 except 静默吞掉；② `query_runs` 的 PG 插入把 "
        "`captured_at` 当 ISO 字符串传 ⇒ asyncpg DataError；③ 登记在 SAVEPOINT 内但路由不提交 "
        "⇒ 响应 recorded=true 而库里 0 行。三者都不会让查询失败。"
    )
    assert run.get("id"), "运行记录已写入但没有运行编号"
    assert "_version_hash" not in result, (
        "内部键 `_version_hash` 泄漏到了响应里：它是登记运行记录用的中间值，"
        "`business_execute` 应当 pop 掉它（N2：既有响应键与类型不变）"
    )


@pytest.mark.pg_only
async def test_run_recording_degrades_when_version_missing(pg_rollback_session, monkeypatch):
    """反向对照：版本摘要为空时必须如实降级（证明上一条不是恒绿）。"""
    from app.services.custom_query.version_capture import VersionVector as VV

    async def _empty_vector(db, source, *, scope, acnr_targets=False):
        return VV(components=(), vector_hash="", weak=False)

    monkeypatch.setattr(
        "app.services.custom_query.version_capture.capture_business_vector", _empty_vector
    )

    from app.routers.custom_query import QueryRequest
    from app.services.custom_query.business_execute import execute_business_query

    db = pg_rollback_session
    user = await _admin_user(db)
    project_id, year = await _picked_project(db)
    body = QueryRequest(project_id=str(project_id), year=int(year), source="adj_aje", limit=5, offset=0)
    result = await execute_business_query(body, user=user, db=db, origin="direct")

    run = result.get("run") or {}
    assert run.get("recorded") is False, f"版本摘要为空却写入了运行记录：{run}"
    assert run.get("reason"), "降级时没给中文原因"
