# Feature: formula-management-library, Property 24: 刷新范围项动态发现无遗漏
"""属性测试 P24：刷新范围项动态发现无遗漏。

*对任意* 模块/循环注册来源——即
``cycleDialogRegistry`` 后端等价物 ``dashboard_aggregator_service.CYCLE_NAMES``
的循环集合 ∪ ``wp_index`` 现存 ``wp_code`` 的循环前缀（``re.match(r'([A-N])', wp_code)``）
∪ 固定顶层域（报表 report / 调整分录 adjudication / 附注 note）——
``RefreshScopeDiscovery.discover`` 发现的可刷新项集合**恰好覆盖**全部注册来源派生项
并**按 key 去重**（新增即现、无硬编码遗漏、无重复）。

被测：``app.services.formula_management.refresh_scope_discovery.RefreshScopeDiscovery.discover``
（三来源动态派生 + 按 key 去重；见 service 文档 §19 / Req 20）。

model-based 策略：
- Hypothesis 随机构造一组 ``wp_index`` ``wp_code``（含 A-N 循环前缀、A-N 内但不在
  CYCLE_NAMES 的前缀[如 A/B/C]、超出 A-N 的前缀[如 O-Z 应被忽略]、大小写混合），
  种入内存 SQLite 的 ``wp_index`` 表。
- 以纯 Python 独立重算"期望 key 集合" = 固定顶层域 ∪ CYCLE_NAMES 循环项
  ∪ wp_code 前缀派生循环项，断言 ``discover`` 输出 key 集合逐一相等、且无重复。

内存 SQLite + SQLite 方言 patch 参考同目录 ``test_pbt_p03_idempotent.py`` /
``test_reference_resolver.py`` 的 fixture 模式；Hypothesis 遵循 conftest ``fast``
profile（``max_examples`` 可经 ``HYPOTHESIS_MAX_EXAMPLES`` 覆盖）。

Framework: hypothesis。

**Validates: Requirements 20.1, 20.2, 20.3, 20.4**
"""

from __future__ import annotations

import asyncio
import re
import uuid

from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# SQLite 测试方言：JSONB → JSON 编译（WpIndex.cross_ref_codes 建表所需）；
# PG ARRAY → TEXT 兜底。参考 test_pbt_p03_idempotent.py。
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.workpaper_models import WpIndex  # noqa: E402
from app.services.dashboard_aggregator_service import CYCLE_NAMES  # noqa: E402
from app.services.formula_management.refresh_scope_discovery import (  # noqa: E402
    RefreshScopeDiscovery,
)

PROJECT_ID = uuid.uuid4()
YEAR = 2025

_TEST_TABLES = [WpIndex.__table__]

# discover 的固定顶层域 key（与 service._TOP_LEVEL_DOMAINS 一致）。
_TOP_LEVEL_KEYS = {"report", "adjudication", "note"}

# 与 service 完全一致的循环前缀提取正则（A-N 首字母）。
_CYCLE_PREFIX_RE = re.compile(r"([A-N])")


# ─────────────────────────────────────────────────────────────────────────────
# 事件循环辅助：discover 为协程；每个 example 用独立内存引擎隔离。
# ─────────────────────────────────────────────────────────────────────────────
def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _make_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: MetaData().create_all(sync_conn, tables=_TEST_TABLES)
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory, engine


def _seed_wp_index(wp_codes: list[str]) -> list[WpIndex]:
    """由 wp_code 列表种子 wp_index（全部 is_deleted=False，即注册在册）。"""
    rows: list[WpIndex] = []
    for code in wp_codes:
        rows.append(
            WpIndex(
                project_id=PROJECT_ID,
                wp_code=code,
                wp_name=f"底稿{code}",
                is_deleted=False,
            )
        )
    return rows


def _expected_keys(wp_codes: list[str]) -> set[str]:
    """独立重算期望 key 集合：固定顶层域 ∪ CYCLE_NAMES ∪ wp_code 前缀派生循环项。"""
    cycles: set[str] = {c.upper() for c in CYCLE_NAMES.keys() if c}
    for code in wp_codes:
        if not code:
            continue
        m = _CYCLE_PREFIX_RE.match(str(code).upper())
        if m:
            cycles.add(m.group(1))
    return set(_TOP_LEVEL_KEYS) | {f"workpaper:{c}" for c in cycles}


# ─────────────────────────────────────────────────────────────────────────────
# 智能生成器：约束到 discover 的输入空间（wp_index wp_code 集合）。
# ─────────────────────────────────────────────────────────────────────────────

# 前缀字母：覆盖 A-N（含 CYCLE_NAMES D-N 与其外 A/B/C）、超出 A-N（O-Z 应被忽略）、
# 以及小写（验证 .upper() 归一化）。
_PREFIX = st.sampled_from(
    list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + list("abdfgknosz")
)
# wp_code = 前缀 + 数字尾巴（+ 可选 "-n" 子序号），如 D2 / A1 / S34 / d2-1 / O5。
_WP_CODE = st.builds(
    lambda p, n, sub: f"{p}{n}" + (f"-{sub}" if sub is not None else ""),
    _PREFIX,
    st.integers(min_value=0, max_value=99).map(str),
    st.one_of(st.none(), st.integers(min_value=1, max_value=9)),
)
# wp_code 列表：0..10 条，按 (project_id, wp_code) 唯一约束去重；允许空列表
# （空时仍应发现固定顶层域 + CYCLE_NAMES 全量）。
_WP_CODES = st.lists(_WP_CODE, min_size=0, max_size=10, unique=True)


@given(wp_codes=_WP_CODES)
def test_scope_discovery_covers_all_sources_dedup(wp_codes):
    """P24：discover 输出 key 集合恰等于三来源并集、无遗漏、无重复。

    **Validates: Requirements 20.1, 20.2, 20.3, 20.4**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                if wp_codes:
                    db.add_all(_seed_wp_index(wp_codes))
                    await db.commit()

                items = await RefreshScopeDiscovery(db).discover(
                    project_id=PROJECT_ID, year=YEAR
                )

                keys = [it.key for it in items]

                # ① 按 key 去重：无重复项（Req 20.4）。
                assert len(keys) == len(set(keys)), f"发现结果存在重复 key: {keys}"

                # ② 覆盖全部注册来源派生项且无硬编码遗漏（Req 20.1/20.2/20.3/20.4）。
                assert set(keys) == _expected_keys(wp_codes)

                # ③ 固定顶层域恒在（新增循环不挤掉固定域）。
                assert _TOP_LEVEL_KEYS.issubset(set(keys))

                # ④ CYCLE_NAMES 全部循环恒被发现（后端注册循环常量集合来源②）。
                for c in CYCLE_NAMES:
                    assert f"workpaper:{c.upper()}" in set(keys)

                # ⑤ 结构自洽：workpaper 项 group/cycle 与 key 对应；顶层域 cycle 为 None。
                for it in items:
                    if it.group == "workpaper":
                        assert it.cycle is not None
                        assert it.key == f"workpaper:{it.cycle}"
                    else:
                        assert it.key in _TOP_LEVEL_KEYS
                        assert it.cycle is None
        finally:
            await engine.dispose()

    _run(_scenario())
