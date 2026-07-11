"""RefreshScopeDiscovery 发现服务 + 端点合伙人门禁测试。

公式管理库（formula-management-library）Task 17.1 / 设计 §19（Req 20）。

覆盖：
- ``discover`` 三来源合并去重（模块固定顶层域 + 后端循环常量 CYCLE_NAMES +
  ``wp_index`` 现存 wp_code 循环前缀），按 key 去重、循环粒度产 ``workpaper:{cycle}``。
- ``GET /api/workpapers/refresh-scopes`` 合伙人门禁：非合伙人 403。

用内存 sqlite（参考 test_pbt_p02_precheck.py 的 fixture 口径）。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# sqlite 无原生 JSONB / ARRAY：映射到 JSON / TEXT（与其他 fm 测试一致）。
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.deps import require_role  # noqa: E402
from app.models.workpaper_models import WpIndex, WpStatus  # noqa: E402
from app.services.dashboard_aggregator_service import CYCLE_NAMES  # noqa: E402
from app.services.formula_management.refresh_scope_discovery import (  # noqa: E402
    RefreshScopeDiscovery,
    RefreshScopeItem,
)

PROJECT_ID = uuid.uuid4()
YEAR = 2025

_TEST_TABLES = [WpIndex.__table__]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _make_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(lambda sc: MetaData().create_all(sc, tables=_TEST_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory, engine


def _wp(wp_code: str, *, cycle: str | None = None, deleted: bool = False) -> WpIndex:
    return WpIndex(
        project_id=PROJECT_ID,
        wp_code=wp_code,
        wp_name=f"底稿{wp_code}",
        audit_cycle=cycle,
        status=WpStatus.not_started,
        is_deleted=deleted,
    )


# ─────────────────────────────────────────────────────────────────────────────
# discover：三来源合并去重
# ─────────────────────────────────────────────────────────────────────────────
def test_discover_includes_fixed_top_level_domains():
    """① 模块注册固定顶层域（报表/调整分录/附注）恒在，group=key、cycle=None。"""

    async def _s():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                items = await RefreshScopeDiscovery(db).discover(
                    project_id=PROJECT_ID, year=YEAR
                )
                by_key = {i.key: i for i in items}
                for key, label in (("report", "报表"), ("adjudication", "调整分录"), ("note", "附注")):
                    assert key in by_key, f"缺固定顶层域 {key}"
                    assert by_key[key].label == label
                    assert by_key[key].group == key
                    assert by_key[key].cycle is None
        finally:
            await engine.dispose()

    _run(_s())


def test_discover_includes_registered_cycle_constants_even_without_wp_index():
    """② 后端注册循环常量（CYCLE_NAMES，D~N）即使 wp_index 为空也全部产出。"""

    async def _s():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                items = await RefreshScopeDiscovery(db).discover(
                    project_id=PROJECT_ID, year=YEAR
                )
                wp_keys = {i.key for i in items if i.group == "workpaper"}
                for cyc in CYCLE_NAMES.keys():
                    assert f"workpaper:{cyc}" in wp_keys, f"缺注册循环 {cyc}"
        finally:
            await engine.dispose()

    _run(_s())


def test_discover_derives_cycle_from_wp_index_prefix():
    """③ wp_index 现存 wp_code 循环前缀被派生为 workpaper:{cycle}（A~C 非 CYCLE_NAMES 内也现）。"""

    async def _s():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                # A/B 不在 CYCLE_NAMES(D~N)，仅来自 wp_index 前缀 → 验证 ③ 独立贡献。
                db.add_all([_wp("A1"), _wp("B23-1"), _wp("D2-1")])
                await db.commit()
                items = await RefreshScopeDiscovery(db).discover(
                    project_id=PROJECT_ID, year=YEAR
                )
                wp_keys = {i.key for i in items if i.group == "workpaper"}
                assert "workpaper:A" in wp_keys, "wp_index 前缀 A 应被派生"
                assert "workpaper:B" in wp_keys, "wp_index 前缀 B 应被派生"
                assert "workpaper:D" in wp_keys
        finally:
            await engine.dispose()

    _run(_s())


def test_discover_dedups_by_key_and_ignores_deleted():
    """②③ 并集按 key 去重（D 既在常量又在 wp_index，仅一条）；已删除 wp_code 不计。"""

    async def _s():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                # D 同时来自 CYCLE_NAMES(②) 与多条 wp_index(③) → 去重后仅一条。
                # Z 无效前缀（非 A-N）不产循环项；已删除 wp_code 忽略。
                db.add_all([
                    _wp("D2-1"),
                    _wp("D3-1"),
                    _wp("D4"),
                    _wp("Z9-1"),
                    _wp("E1", deleted=True),  # 已删除：不贡献前缀（但 E 仍来自 CYCLE_NAMES）
                ])
                await db.commit()
                items = await RefreshScopeDiscovery(db).discover(
                    project_id=PROJECT_ID, year=YEAR
                )
                keys = [i.key for i in items]
                # 去重：无重复 key。
                assert len(keys) == len(set(keys)), "范围项 key 必须去重"
                # D 仅一条。
                assert keys.count("workpaper:D") == 1
                # Z 非 A-N 前缀 → 不产循环项。
                assert "workpaper:Z" not in keys
        finally:
            await engine.dispose()

    _run(_s())


def test_discover_cycle_label_and_group_shape():
    """workpaper 项 label 形如"底稿·循环D（销售收入）"、group=workpaper、cycle 填充。"""

    async def _s():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                items = await RefreshScopeDiscovery(db).discover(
                    project_id=PROJECT_ID, year=YEAR
                )
                d_item = next(i for i in items if i.key == "workpaper:D")
                assert d_item.group == "workpaper"
                assert d_item.cycle == "D"
                assert d_item.label.startswith("底稿·循环D")
                # to_dict 完整回显四字段。
                assert d_item.to_dict() == {
                    "key": "workpaper:D",
                    "label": d_item.label,
                    "group": "workpaper",
                    "cycle": "D",
                }
        finally:
            await engine.dispose()

    _run(_s())


def test_discover_items_are_refresh_scope_items():
    """discover 返回类型契约：全为 RefreshScopeItem。"""

    async def _s():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                items = await RefreshScopeDiscovery(db).discover(
                    project_id=PROJECT_ID, year=YEAR
                )
                assert items, "至少含固定顶层域 + 注册循环项"
                assert all(isinstance(i, RefreshScopeItem) for i in items)
        finally:
            await engine.dispose()

    _run(_s())


# ─────────────────────────────────────────────────────────────────────────────
# 端点合伙人门禁：非合伙人 403（复用 require_role，与 /draft-refresh 同）
# ─────────────────────────────────────────────────────────────────────────────
from types import SimpleNamespace  # noqa: E402

_PARTNER_ROLES = ["partner", "signing_partner"]


def _make_user(role: str):
    return SimpleNamespace(role=SimpleNamespace(value=role))


@pytest.mark.parametrize("role", ["auditor", "manager", "assistant", "readonly", "qc", ""])
def test_refresh_scopes_gate_rejects_non_partner(role):
    """非合伙人调 /refresh-scopes → require_role 依赖解析阶段抛 403，先于任何读写。"""
    dependency = require_role(_PARTNER_ROLES)
    with pytest.raises(HTTPException) as exc:
        _run(dependency(current_user=_make_user(role)))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role", _PARTNER_ROLES)
def test_refresh_scopes_gate_allows_partner(role):
    """合伙人 / 签字合伙人放行（返回该用户），端点体方可执行发现逻辑。"""
    dependency = require_role(_PARTNER_ROLES)
    user = _make_user(role)
    assert _run(dependency(current_user=user)) is user
