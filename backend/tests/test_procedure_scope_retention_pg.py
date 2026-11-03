# -*- coding: utf-8 -*-
"""生成保留范围 —— 真实 PostgreSQL 只读对照（spec procedure-trim-generation-delegation-chain 需求 2）。

重药安徽是唯一有粗裁结果的真实项目（23 个科目级程序标为不适用）。用一个独立写法的朴素口径
（「码本身 / 码- 开头 / 码后紧跟字母的程序表」）对整个项目的底稿编码逐个比对：安徽在已裁码下面没有
自带「执行」程序行的子码，两种口径必须完全一致。只读，结尾 rollback；数据处置（恢复 H3、移入回收站）
后照样成立（朴素口径同样按当时的裁剪结果算）。
"""
from __future__ import annotations

import asyncio
import re
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.services.procedure_scope_retention import load_trimmed_scope, plan_generation

pytestmark = pytest.mark.pg_only

ANHUI = UUID("0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49")


def _naive_trimmed(code: str, trimmed_rows: set[str]) -> bool:
    return any(
        code == t or code.startswith(t + "-") or re.fullmatch(re.escape(t) + r"[A-Z]+(-.*)?", code)
        for t in trimmed_rows
    )


@pytest.mark.asyncio
async def test_anhui_scope_matches_naive_reading():
    # 用例自建引擎：应用全局连接池里的连接属于别的用例的事件循环，整套跑时复用会报
    # 「'NoneType' object has no attribute 'send'」（单跑恰好是第一个用连接的，测不出来）
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine) as db:
            try:
                scope = await load_trimmed_scope(db, ANHUI)
                rows = (await db.execute(sa.text(
                    "SELECT COALESCE(wp_code, procedure_code) AS code, status FROM procedure_instances "
                    "WHERE project_id = :p AND is_deleted = false"), {"p": str(ANHUI)})).all()
                codes = [r[0] for r in (await db.execute(sa.text(
                    "SELECT wp_code FROM wp_index WHERE project_id = :p"), {"p": str(ANHUI)})).all()]
                sample = ["G1", "G1-1", "G10", "G10-2", "M4A", "ZZ_NOT_A_CODE"]
                plan = await plan_generation(db, ANHUI, sample, scope=scope)
            finally:
                await db.rollback()
    finally:
        await engine.dispose()

    trimmed_rows = {c for c, s in rows if s in ("skip", "not_applicable")}
    execute_rows = {c for c, s in rows if s == "execute"}
    # 前提：已裁码下面没有自带「执行」程序行的子码（否则朴素口径不适用）
    assert not any(_naive_trimmed(c, trimmed_rows) for c in execute_rows)
    mismatched = sorted(c for c in codes if scope.is_trimmed(c) != _naive_trimmed(c, trimmed_rows))
    assert mismatched == [], mismatched
    assert scope.trimmed_codes == frozenset(trimmed_rows)

    # 编码边界：G10 被裁不影响 G1；程序表跟随科目
    if "G10" in trimmed_rows and "G1" in execute_rows:
        assert not scope.is_trimmed("G1-1") and scope.is_trimmed("G10-2")
        assert "G1" in plan.existing_codes + plan.to_create + plan.in_recycle_codes
        assert "G10-2" in plan.skipped_trimmed_codes
    assert scope.is_trimmed("M4A") == ("M4" in trimmed_rows)
    assert "ZZ_NOT_A_CODE" in plan.to_create


@pytest.mark.asyncio
async def test_plan_generation_serializes_same_project_transactions():
    """plan_generation 取得的项目锁持有到事务结束；第二个生成 / 粗裁事务不能基于旧 scope 并行推进。"""
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    first = AsyncSession(engine)
    second = AsyncSession(engine)
    pending = None
    try:
        await plan_generation(first, ANHUI, ["D2"])
        pending = asyncio.create_task(plan_generation(second, ANHUI, ["D2"]))
        await asyncio.sleep(0.15)
        assert not pending.done(), "同项目第二个 plan_generation 未等待项目级 advisory transaction lock"
        await first.rollback()
        result = await asyncio.wait_for(pending, timeout=3)
        assert result.to_create + result.existing_codes + result.in_recycle_codes + result.skipped_trimmed_codes
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
        await first.rollback()
        await second.rollback()
        await first.close()
        await second.close()
        await engine.dispose()
