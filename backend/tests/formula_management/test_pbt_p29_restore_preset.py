# Feature: formula-management-library, Property 29: 自定义覆盖—恢复预设往返
"""属性测试 P29：自定义覆盖—恢复预设往返（round-trip）。

*对任意* 带预设公式的单元，以 ``custom`` 来源覆盖（``is_preset_override`` 语义：
覆盖时记录 ``original_preset``）后再请求"恢复预设"，该单元回退为**原预设公式**
（表达式与原预设逐字相等）且 ``User_Formula`` 覆盖被删除。即：

    restore(override(preset)) == preset  且  覆盖项被删除

被测（**以真实实现为准**，不重写端点）：
  - ``app.routers.wp_user_formulas.update_user_formulas``（PUT /user-formulas）
    —— 覆盖预设：写 ``parsed_data['user_formulas'][cell_key]`` = {formula: 自定义,
    original_preset: 原预设}（``original_preset`` 由预设映射
    ``prefill_formula_mapping.json`` 捕获，这里以桩注入受控预设）。
  - ``app.routers.wp_user_formulas.restore_preset_formula``（DELETE
    /user-formulas/{cell_key}）—— 恢复预设 = **删除覆盖行** → 该 cell 回退到预设，
    响应 ``restored_to_preset`` 即被删除项记录的 ``original_preset``。

真实存储机制：``WorkingPaper.parsed_data['user_formulas']`` 字典，键 ``{sheet}!{cell}``；
覆盖创建条目并捕获 ``original_preset``，恢复即 ``pop`` 该条目回退预设（无独立
User_Formula 表，随底稿 parsed_data JSONB 持久化）。

测试基座：内存 SQLite（``:memory:`` + ``aiosqlite``）+ SQLite 方言 patch 建
``working_paper`` / ``projects`` 表（对齐 test_pbt_p28_source_roundtrip.py /
test_reference_resolver.py）。桩：
  - ``json.load`` → 受控预设映射，使覆盖捕获我们指定的 ``original_preset``
    （注：SQLAlchemy JSON 序列化用 ``json.dumps`` / ``json.loads``，不受 ``json.load``
    桩影响，故该 patch 对持久化无副作用）。
  - ``app.services.audit_log_helper.append_audit_log`` → no-op（审计留痕与 P29
    往返正交，避免污染事务）。
  - ``projects`` 表建但不插行 → PUT 的 Project 查询返回 None → 悬空校验分支跳过。
  - ``app.services.wp_formula_service.validate_refs_via_acnr`` → 返回空 issues。

    🔴 **为什么必须显式 patch 它**（spec formula-management-runtime-closure
    Task 17 / R9.6，2026-08-07）：Wave 3 把用户公式**收敛进 ``wp_formula`` 表**后，
    PUT 路径改走 ``wp_formula_service.save()``，因而**开始继承 ACNR 悬空引用校验**
    —— 这是有意的功能增强（改造前用户公式只落 ``parsed_data``，
    ``FormulaRuntimeCoordinator._load_formulas`` 只读 ``WpFormula`` ⇒
    用户保存的公式永远不被求值）。

    本模块 docstring 原先声称「``projects`` 不插行 ⇒ 悬空校验跳过」，
    该假设**在收敛后失效**：校验不再依赖 ``Project`` 是否存在，而是查 ACNR 地址目录；
    内存 SQLite 基座下 ``build_trial_balance_entries`` 必然报
    ``'str' object has no attribute 'hex'``（``WorkingPaper.project_id`` 在
    SQLite 下读回是 str，而 ``TrialBalance.project_id`` 是 UUID 列）→ fail-open 返空
    entries → 任意 ``TB('0000',…)`` 都被判 ``not_found`` → 整批 422。

    ⇒ 处置遵循「**属性正交**」：P29 的属性是「override→restore 往返保真」，
    与「引用地址是否存在」无关；悬空引用校验行为由
    ``tests/test_formula_save_validation.py`` 的三条测试专门覆盖
    （``test_user_formulas_update_rejects_dangling_refs`` 等）。
    故这里只 patch 校验层、**P29 自身的断言一条不动**（禁放宽/跳过，符合 R9.6）。

Framework: hypothesis（遵循 conftest fast profile，max_examples=5）。

**Validates: Requirements 25.3, 25.4**
"""

from __future__ import annotations

import asyncio
import json
import types
import uuid
from unittest.mock import AsyncMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# SQLite 测试方言：UUID → uuid 编译；JSONB → JSON 编译（建表所需）。
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid
if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models.core import Project  # noqa: E402
from app.models.workpaper_models import (  # noqa: E402
    WorkingPaper,
    WpFormula,
    WpSourceType,
)
from app.routers.wp_user_formulas import (  # noqa: E402
    BatchUserFormulasRequest,
    list_user_formulas,
    restore_preset_formula,
    update_user_formulas,
)


# ─────────────────────────────────────────────────────────────────────────────
# 测试基座：端点为协程；每个 example 用独立内存引擎隔离。
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
        # working_paper：_load_wp 依赖；projects：PUT 悬空校验分支的 Project 查询依赖
        # （建表但不插行 → 查询返回 None → 校验跳过，无需真实 ACNR）。
        await conn.run_sync(
            lambda sc: WorkingPaper.__table__.create(sc, checkfirst=True)
        )
        await conn.run_sync(
            lambda sc: Project.__table__.create(sc, checkfirst=True)
        )
        # wp_formula：Wave 3 存储收敛后 PUT 会往该表 upsert（见模块 docstring）。
        # 不建表则报 `no such table: wp_formula` —— 这是**真实依赖**，
        # 不是可以绕开的细节：用户公式的权威存储已从 parsed_data 迁到此表。
        await conn.run_sync(
            lambda sc: WpFormula.__table__.create(sc, checkfirst=True)
        )
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory, engine


async def _insert_wp(db: AsyncSession, *, project_id: uuid.UUID) -> uuid.UUID:
    """落一条最小 WorkingPaper（parsed_data 为空 → 该 cell 初始解析到预设）。"""
    wp_id = uuid.uuid4()
    db.add(
        WorkingPaper(
            id=wp_id,
            project_id=project_id,
            wp_index_id=uuid.uuid4(),
            file_path="test.xlsx",
            source_type=WpSourceType.template,
        )
    )
    await db.commit()
    return wp_id


async def _read_user_formulas(db: AsyncSession, wp_id: uuid.UUID) -> dict:
    """经 **GET 端点**读回 user_formulas 覆盖字典。

    🔴 **为什么不再直读 `parsed_data['user_formulas']`**（spec
    formula-management-runtime-closure Task 17 / R9.6，2026-08-07）：

    Wave 3 把用户公式**收敛进 `wp_formula` 表**后，`parsed_data['user_formulas']`
    只保留 `{cell_key: {"original_preset": ...}}` 溯源元数据（表侧无该列），
    **公式本体不再回写那里**（回写就成了双写 = 双真源，Wave 3 的收敛守卫
    `test_user_formula_storage_convergence` 会正当地打红）。

    于是直读 parsed_data 会拿到缺 `formula` 键的条目 → `KeyError: 'formula'`。
    这**不是 P29 属性被破坏**，而是本 helper 读错了容器：它读的是**实现细节**，
    而 P29 要验的往返保真发生在**对外契约**上。

    ⇒ 改为调用 `list_user_formulas`（GET /user-formulas）——
    R9.4 要求该端点响应形状逐字不变，正是「override→restore 往返」的观测面：
    它按「表优先、遗留键补 `original_preset`」合并，同时给出 `formula` 与
    `original_preset` 两个字段。**P29 自身的断言一条未动**（禁放宽/跳过）。
    """
    resp = await list_user_formulas(
        wp_id, db=db, _user=types.SimpleNamespace(id=uuid.uuid4())
    )
    return dict(resp.get("user_formulas") or {})


# ─────────────────────────────────────────────────────────────────────────────
# 智能生成器：约束到 user-formulas 输入空间。
#   cell_key 必须匹配端点校验 ^[^!]+![A-Z]+\d+$；公式须为受支持类型（TB，2 参）。
# ─────────────────────────────────────────────────────────────────────────────
_SHEET = st.text(
    alphabet="审定表明细现金Sheet0123ABC", min_size=1, max_size=8
).filter(lambda s: "!" not in s and s.strip() != "")

_COL = st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=2)
_ROW = st.integers(min_value=1, max_value=999)
_ACCOUNT = st.text(alphabet="0123456789", min_size=4, max_size=4)
_COLUMN_NAME = st.sampled_from(["期末余额", "期初余额", "本期发生额"])


@st.composite
def _override_case(draw):
    """抽一条覆盖案例：cell_key + 原预设公式 + 自定义覆盖公式（保证二者不同）。"""
    sheet = draw(_SHEET)
    cell = f"{draw(_COL)}{draw(_ROW)}"
    cell_key = f"{sheet}!{cell}"

    preset_acct = draw(_ACCOUNT)
    preset_col = draw(_COLUMN_NAME)
    preset_formula = f"=TB('{preset_acct}','{preset_col}')"

    # 自定义覆盖公式：与预设不同（不同科目或不同列）。
    custom_acct = draw(_ACCOUNT)
    custom_col = draw(_COLUMN_NAME)
    custom_formula = f"=TB('{custom_acct}','{custom_col}')"

    # 保证 custom != preset（否则往返平凡成立，削弱属性强度）。
    if custom_formula == preset_formula:
        custom_formula = f"=SUM_TB('{custom_acct}','{custom_col}')"

    return {
        "sheet": sheet,
        "cell": cell,
        "cell_key": cell_key,
        "preset_formula": preset_formula,
        "custom_formula": custom_formula,
    }


@given(_override_case())
@settings(max_examples=5)
def test_restore_preset_roundtrip(case):
    """P29：override(preset) 记 original_preset → restore 删覆盖回退原预设。

    restore(override(preset)) == preset 且 User_Formula 覆盖被删除。

    **Validates: Requirements 25.3, 25.4**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                project_id = uuid.uuid4()
                wp_id = await _insert_wp(db, project_id=project_id)
                user = types.SimpleNamespace(id=uuid.uuid4())

                cell_key = case["cell_key"]
                preset_formula = case["preset_formula"]
                custom_formula = case["custom_formula"]

                # 受控预设映射：使覆盖时 original_preset 捕获到我们指定的原预设。
                # 结构对齐 update_user_formulas 中 preset_lookup 的解析口径。
                fake_mapping = {
                    "mappings": [
                        {
                            "sheet": case["sheet"],
                            "cells": [
                                {
                                    "cell_ref": case["cell"],
                                    "formula": preset_formula,
                                }
                            ],
                        }
                    ]
                }

                # ── ① override(preset)：以 custom 来源覆盖预设 ──
                with patch.object(
                    json, "load", return_value=fake_mapping
                ), patch(
                    "app.services.audit_log_helper.append_audit_log",
                    new_callable=AsyncMock,
                ), patch(
                    # 见模块 docstring「属性正交」说明：只关掉 ACNR 悬空引用校验，
                    # P29 的往返断言不变（校验行为由 test_formula_save_validation.py 覆盖）
                    "app.services.wp_formula_service.validate_refs_via_acnr",
                    new_callable=AsyncMock,
                    return_value=[],
                ):
                    put_resp = await update_user_formulas(
                        wp_id,
                        BatchUserFormulasRequest(
                            formulas={cell_key: custom_formula}
                        ),
                        db=db,
                        user=user,
                    )

                assert put_resp["updated"] == 1
                assert put_resp["deleted"] == 0

                # 覆盖后：条目存在，formula=自定义，original_preset=原预设。
                after_override = await _read_user_formulas(db, wp_id)
                assert cell_key in after_override
                assert after_override[cell_key]["formula"] == custom_formula
                assert after_override[cell_key]["original_preset"] == preset_formula

                # ── ② restore：请求恢复预设（删除覆盖行）──
                with patch(
                    "app.services.audit_log_helper.append_audit_log",
                    new_callable=AsyncMock,
                ):
                    del_resp = await restore_preset_formula(
                        wp_id, cell_key, db=db, _user=user
                    )

                # round-trip：恢复到的预设逐字等于原预设（restore(override(preset))==preset）。
                assert del_resp["status"] == "restored"
                assert del_resp["restored_to_preset"] == preset_formula

                # User_Formula 覆盖被删除：cell 不再有覆盖条目 → 回退预设解析。
                after_restore = await _read_user_formulas(db, wp_id)
                assert cell_key not in after_restore
        finally:
            await engine.dispose()

    _run(_scenario())


if __name__ == "__main__":  # pragma: no cover
    import pytest

    pytest.main([__file__, "-v"])
