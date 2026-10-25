"""`WorkpaperMutationAdapter` 真 PostgreSQL 守卫（一次性 schema，结束 DROP）。

🔴 为什么必须真库：修复前适配器 UPSERT 漏写 `project_id`、`updated_at` 传 isoformat 字符串。
- 真库 `checklist_responses.project_id NOT NULL` 无默认：新行与冲突行两种情况都抛
  NotNullViolation（PG 先校验待插入元组的 NOT NULL，再判 ON CONFLICT）；
- asyncpg 对 `timestamptz` 参数严格拒收 str。
两者在 SQLite（弱类型 + 旧测试建表 project_id 可空）上都不暴露。

断言：新行写入 → 冲突行覆盖（content_version 1→2）→ 读回值 / 版本号与 apply 返回的一致（CAS 前提）。
`DATABASE_URL` 非 PostgreSQL 时直接失败不 skip（与 task35 PG 守卫同策略）。
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_DDL = """
CREATE TABLE projects (id UUID PRIMARY KEY);
CREATE TABLE working_paper (id UUID PRIMARY KEY, project_id UUID NOT NULL REFERENCES projects(id));
CREATE TABLE checklist_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    wp_id UUID NOT NULL REFERENCES working_paper(id),
    item_id VARCHAR(64) NOT NULL,
    conclusion TEXT, remark TEXT, wp_ref VARCHAR(100), updated_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    content_version INTEGER NOT NULL DEFAULT 1,
    UNIQUE (wp_id, item_id)
);
"""


async def _scenario() -> dict:
    from app.core.database import engine
    from app.services.formula_runtime.adapters.workpaper import WorkpaperMutationAdapter
    from app.services.formula_runtime.contracts import CanonicalFormulaTarget
    from sqlalchemy.ext.asyncio import AsyncSession

    assert engine.dialect.name == "postgresql", f"需要 PostgreSQL，实际 {engine.dialect.name}"
    schema = f"tmp_wp_adapter_{uuid.uuid4().hex[:10]}"
    pid, wp = uuid.uuid4(), uuid.uuid4()
    out: dict = {}
    async with engine.begin() as conn:
        await conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text(f'SET search_path TO "{schema}"'))
            for stmt in [s.strip() for s in _DDL.split(";") if s.strip()]:
                await conn.execute(sa.text(stmt))
            await conn.execute(sa.text("INSERT INTO projects (id) VALUES (:p)"), {"p": pid})
            await conn.execute(
                sa.text("INSERT INTO working_paper (id, project_id) VALUES (:w, :p)"), {"w": wp, "p": pid},
            )
            session = AsyncSession(bind=conn)
            adapter = WorkpaperMutationAdapter(session)
            target = CanonicalFormulaTarget(
                domain="workpaper", project_id=pid, year=2025,
                addr_id=f"E1/E1-1/E1-adj-tb-amount-ending",
                locator={"wp_id": str(wp), "item": "E1-adj-tb-amount-ending", "cell": "."},
                wp_id=wp,
            )
            for label, value in (("new_row", 100.5), ("conflict_row", 200.25)):
                muts = await adapter.prepare_many([target], {target.addr_id: value})
                applied = await adapter.apply_many(muts)
                row = (await conn.execute(sa.text(
                    "SELECT project_id, remark, content_version FROM checklist_responses "
                    "WHERE wp_id = :w AND item_id = 'E1-adj-tb-amount-ending'"
                ), {"w": wp})).one()
                versions = await adapter.read_versions([target])
                out[label] = {
                    "project_id": row.project_id,
                    "remark": row.remark,
                    "content_version": row.content_version,
                    "applied_version": applied[0].applied_version,
                    "read_version": versions[target.addr_id],
                }
            await session.close()
            await conn.rollback()
    finally:
        async with engine.begin() as conn:
            await conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
    out["pid"] = pid
    return out


def test_adapter_upsert_on_real_postgres():
    snap = asyncio.run(_scenario())
    for label in ("new_row", "conflict_row"):
        s = snap[label]
        assert s["project_id"] == snap["pid"], f"{label}: project_id 未写入"
        assert s["applied_version"] == s["read_version"], (
            f"{label}: apply 返回版本 {s['applied_version']} ≠ 读回版本 {s['read_version']} "
            "⇒ 后续 CAS 必自冲突"
        )
    assert snap["new_row"]["remark"] == "100.5"
    assert snap["new_row"]["content_version"] == 1
    assert snap["conflict_row"]["remark"] == "200.25"
    assert snap["conflict_row"]["content_version"] == 2, "冲突覆盖未推进 content_version"
