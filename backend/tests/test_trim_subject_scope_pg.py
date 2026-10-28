# -*- coding: utf-8 -*-
"""科目有无数据判定 —— 真实 PostgreSQL 只读回归（spec procedure-trim-generation-delegation-chain 需求 1）。

重药安徽（2006 版码作标准码）H3 投资性房地产 1521 审定 7,689,744.44 曾被判「无数据」自动裁剪；
宜宾临港店（标准码映射进平台标准表：实收资本 3001、4001 是生产成本）验证另一种科目表写法。

用例自建引擎、结束即释放：应用全局连接池里的连接绑定创建它的事件循环，跨用例复用会撞
「Event loop is closed」/「'NoneType' object has no attribute 'send'」（用了全局池的用例还会把坏连接留给后面
的用例）。只读，结尾 rollback。
"""
from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.services.procedure_trim_scope import resolve_subject_data_availability

pytestmark = pytest.mark.pg_only

ANHUI = UUID("0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49")
HEPING_2024 = UUID("f064f5e4-69f2-4c7e-9c6d-c899c18d650b")


def _located(ev: dict) -> set[str]:
    return {c for s in ev["slots"] for c in s["standard_codes"]}


@pytest.mark.asyncio
async def test_real_projects_both_chart_dialects():
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine) as db:
            try:
                anhui = await resolve_subject_data_availability(db, ANHUI, 2025)
                heping = await resolve_subject_data_availability(db, HEPING_2024, 2024)
            finally:
                await db.rollback()
    finally:
        await engine.dispose()

    # 重药安徽（2006 版码作标准码）：H3 有数据（曾被误裁），按名称定位到 1521
    assert anhui["tb_empty"] is False
    assert "H3" in anhui["subject_with_data"]
    assert anhui["evidence"]["H3"]["closing"] >= 7689744.44
    assert "1521" in _located(anhui["evidence"]["H3"])
    for code in ("H1", "F2", "F4", "M2"):  # 有余额的科目不得落到无数据（F2：库存商品 1.59 亿）
        assert code in anhui["subject_with_data"], code

    # 和平药房 2024（标准码映射进平台标准表）：使用权资产在 1641、其他综合收益在 3102。
    # 旧码表把 H8 写成 1901、M9 写成 4103，两张底稿都会被判无数据。
    assert heping["tb_empty"] is False
    assert "H8" in heping["subject_with_data"]
    assert "1641" in _located(heping["evidence"]["H8"])
    assert "M9" in heping["subject_with_data"]
    assert "3102" in _located(heping["evidence"]["M9"])
