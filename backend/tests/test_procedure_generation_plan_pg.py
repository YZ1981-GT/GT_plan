"""生成计划与生成接口逐码一致 —— 真实 PostgreSQL 只读对照（spec trim-generation-plan-linkage R1.2）。

对每个有程序行的真实项目、按「标准年审」模板集（没有则全部模板编码）算生成计划，再把计划里的全部编码交给
生成接口的分流 ``plan_generation``：计划说「将生成 / 业务分类不生成」的，分流必须判为新建（业务分类只在弹窗
默认不勾，生成接口不看它）；「已裁剪 / 在回收站 / 已生成」三类必须一一对应。只读，结尾 rollback。
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.services.procedure_generation_plan import build_generation_plan
from app.services.procedure_scope_retention import plan_generation
from tests.contracts._contract_schemas import assert_valid

pytestmark = pytest.mark.pg_only


async def test_plan_matches_plan_generation_on_real_projects():
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)  # 自建引擎（见 test_procedure_scope_retention_pg）
    compared = 0
    try:
        async with AsyncSession(engine) as db:
            try:
                projects = [r[0] for r in (await db.execute(sa.text(
                    "SELECT p.id FROM projects p WHERE p.is_deleted = false AND EXISTS ("
                    "SELECT 1 FROM procedure_instances pi WHERE pi.project_id = p.id AND pi.is_deleted = false)"
                ))).all()]
                set_id = (await db.execute(sa.text(
                    "SELECT id FROM wp_template_set WHERE set_name = '标准年审' LIMIT 1"))).scalar_one_or_none()
                for pid in projects:
                    plan = await build_generation_plan(db, pid, set_id)
                    assert_valid("generation-plan-view", plan, "/$defs/plan")
                    by_state: dict[str, list[str]] = {}
                    for cycle in plan["cycles"]:
                        for item in cycle["items"]:
                            by_state.setdefault(item["state"], []).append(item["wp_code"])
                    codes = [c for v in by_state.values() for c in v]
                    gen = await plan_generation(db, pid, codes)
                    assert sorted(by_state.get("to_create", []) + by_state.get("category_excluded", [])) == sorted(
                        gen.to_create), pid
                    assert sorted(by_state.get("trimmed", [])) == sorted(gen.skipped_trimmed_codes), pid
                    assert sorted(by_state.get("in_recycle", [])) == sorted(gen.in_recycle_codes), pid
                    assert sorted(by_state.get("existing", [])) == sorted(gen.existing_codes), pid
                    compared += 1
            finally:
                await db.rollback()
    finally:
        await engine.dispose()
    assert compared >= 1, "真库里至少要有一个有程序行的项目，否则这条对照没有比任何东西"
