"""单测 — 附注权威源收敛：execute_note_formulas 合并消费 _formulas ∪ _user_formulas.

Spec:    .kiro/specs/formula-manager-closure/ Task 4.1（ADR-FMC-04）
Design:  ADR-FMC-04「后果」默认合并口径 + §9 单元可测「附注合并键冲突」

覆盖合并默认口径（ADR-FMC-04）：
- execute_note_formulas 合并消费 _formulas（模板预设）∪ _user_formulas（用户集）。
- 同一目标单元格键（"row:col"）冲突时**用户集优先**覆盖模板预设。
- 对合并去重后的集合**统一重算拓扑排序**（不是两套各自排序后拼接），
  不产生两次回填 / 排序抖动。
- 变异反证：去掉用户集合并（纯 _formulas）应使「覆盖」样本断言打红；
  本测试用 _merge_formula_sets 直接断言合并口径，并用 execute 端到端对拍。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.note_formula_generator import (
    _merge_formula_sets,
    _topological_sort_formulas,
    _user_formula_to_def,
    execute_note_formulas,
)


# ===========================================================================
# _merge_formula_sets — 纯合并口径（无 DB）
# ===========================================================================


def test_merge_user_set_overrides_template_on_same_key():
    """同键冲突：用户集公式覆盖模板预设（用户集优先）."""
    template = {
        "2:0": {"type": "vertical_sum", "expression": "SUM(0:1, 0)",
                "description": "模板合计", "category": "auto_calc", "source": "check_presets"},
    }
    user = [
        {"target": "2:0", "formula": "SUM(0:1, 0) * 2", "description": "用户自定义",
         "category": "auto_calc", "source": "user"},
    ]
    merged = _merge_formula_sets(template, user)
    # 同键只有一条（去重），且是用户版本
    assert len(merged) == 1
    assert merged["2:0"]["expression"] == "SUM(0:1, 0) * 2"
    assert merged["2:0"]["description"] == "用户自定义"


def test_merge_union_disjoint_keys():
    """不冲突键：模板集与用户集并集都保留."""
    template = {
        "2:0": {"type": "vertical_sum", "expression": "SUM(0:1, 0)",
                "description": "模板", "category": "auto_calc", "source": "check_presets"},
    }
    user = [
        {"target": "2:1", "formula": "SUM(0:1, 1)", "description": "用户列2",
         "category": "auto_calc", "source": "user"},
    ]
    merged = _merge_formula_sets(template, user)
    assert set(merged.keys()) == {"2:0", "2:1"}
    assert merged["2:0"]["description"] == "模板"
    assert merged["2:1"]["description"] == "用户列2"


def test_merge_none_user_set_is_template_only():
    """用户集为 None → 等价于只有模板集（浅拷贝，不污染原 dict）."""
    template = {"2:0": {"type": "vertical_sum", "expression": "SUM(0:1, 0)"}}
    merged = _merge_formula_sets(template, None)
    assert merged == template
    assert merged is not template  # 浅拷贝，避免回写污染


def test_merge_skips_invalid_user_records():
    """用户集中无合法 target / 无表达式的记录被跳过（不进合并集）."""
    template = {"2:0": {"type": "vertical_sum", "expression": "SUM(0:1, 0)"}}
    user = [
        {"target": "", "formula": "SUM(0:1, 0)"},          # 无 target
        {"target": "合计行", "formula": "SUM(0:1, 0)"},     # 非 row:col
        {"target": "3:0", "formula": "   "},                # 空表达式
        {"target": "3:0", "formula": "SUM(0:2, 0)", "source": "user"},  # 合法
    ]
    merged = _merge_formula_sets(template, user)
    assert set(merged.keys()) == {"2:0", "3:0"}
    assert merged["3:0"]["expression"] == "SUM(0:2, 0)"


def test_merge_topo_recomputed_over_union_single_pass():
    """拓扑对合并集统一重算：用户新增的被引用行参与排序，合计行排在其后.

    用户集在 1:0 新增一条明细公式，模板合计 2:0 引用 0..1 行（含 1:0）。
    合并后统一拓扑：1:0 必须排在 2:0 之前（被引用先算），且每键只出现一次
    （无两套各自排序后拼接的重复）。
    """
    template = {
        "2:0": {"type": "vertical_sum", "expression": "SUM(0:1, 0)"},
    }
    user = [
        {"target": "1:0", "formula": "SUM(5:6, 0)", "type": "vertical_sum", "source": "user"},
    ]
    merged = _merge_formula_sets(template, user)
    rows = [{}, {}, {}]
    order = _topological_sort_formulas(merged, rows)
    # 每键恰一次（无重复 → 无两次回填）
    assert order.count("1:0") == 1
    assert order.count("2:0") == 1
    assert sorted(order) == ["1:0", "2:0"]
    # 被引用行先于引用方
    assert order.index("1:0") < order.index("2:0")


def test_user_formula_to_def_shape():
    """_user_formula_to_def 把用户集记录归一化为 _formulas 条目形态."""
    rec = {"target": "2:0", "formula": "SUM(0:1,0)", "description": "d",
           "category": "logic_check", "source": "user", "type": "vertical_sum"}
    conv = _user_formula_to_def(rec)
    assert conv is not None
    key, fdef = conv
    assert key == "2:0"
    assert fdef["expression"] == "SUM(0:1,0)"
    assert fdef["type"] == "vertical_sum"
    assert fdef["category"] == "logic_check"
    assert fdef["source"] == "user"
    # 非法记录
    assert _user_formula_to_def({"target": "x", "formula": "SUM(0:1,0)"}) is None
    assert _user_formula_to_def({"target": "2:0", "formula": ""}) is None


# ===========================================================================
# execute_note_formulas — 端到端合并消费（mock DB）
# ===========================================================================


def _empty_scalars_result() -> MagicMock:
    result = MagicMock()
    result.all = MagicMock(return_value=[])
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=[])
    result.scalars = MagicMock(return_value=scalars)
    return result


def _make_db(note) -> MagicMock:
    note_query_result = MagicMock()
    note_query_result.scalar_one_or_none = MagicMock(return_value=note)
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[
        note_query_result,
        _empty_scalars_result(),   # report
        _empty_scalars_result(),   # tb
        _empty_scalars_result(),   # wp
        _empty_scalars_result(),   # notes (当年)
        _empty_scalars_result(),   # prior notes
        MagicMock(all=lambda: []),  # aging ledger
    ])
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _make_note(template_formulas: dict, user_formulas: list | None) -> SimpleNamespace:
    td = {
        "headers": ["项目", "期末"],
        "rows": [
            {"label": "明细1", "values": [10.0]},
            {"label": "明细2", "values": [20.0]},
            {"label": "合计", "values": [None], "is_total": True},
        ],
        "_formulas": template_formulas,
        "_check_presets": ["sub_item"],
    }
    if user_formulas is not None:
        td["_user_formulas"] = user_formulas
    return SimpleNamespace(
        project_id=uuid4(), year=2025, note_section="五、1", table_data=td,
    )


@pytest.mark.asyncio
async def test_execute_consumes_user_formula_override():
    """端到端：用户集覆盖同键模板预设，execute 用用户表达式回填.

    模板 2:0 = SUM(0:1,0) = 30；用户 2:0 = SUM(0:0,0) = 10（只加第一行）。
    合并后用户集优先 → 合计行回填 10（不是 30）。
    """
    note = _make_note(
        template_formulas={"2:0": {"type": "vertical_sum", "expression": "SUM(0:1, 0)"}},
        user_formulas=[{"target": "2:0", "formula": "SUM(0:0, 0)",
                        "type": "vertical_sum", "source": "user"}],
    )
    db = _make_db(note)
    with patch("sqlalchemy.orm.attributes.flag_modified", lambda *_a, **_kw: None):
        result = await execute_note_formulas(db, note.project_id, note.year, note.note_section)

    assert result["updated"] >= 1
    # 用户集优先：合计 = 只有明细1 = 10（若未合并用户集则会是模板的 30）
    assert note.table_data["rows"][2]["values"][0] == 10.0


@pytest.mark.asyncio
async def test_execute_without_user_set_uses_template():
    """变异反证基线：无用户集时用模板预设回填（合计=30）.

    与上一例对拍：同一模板，去掉用户集后结果回到 30，
    证明「10」确实来自用户集合并（去掉合并即打红覆盖样本）。
    """
    note = _make_note(
        template_formulas={"2:0": {"type": "vertical_sum", "expression": "SUM(0:1, 0)"}},
        user_formulas=None,
    )
    db = _make_db(note)
    with patch("sqlalchemy.orm.attributes.flag_modified", lambda *_a, **_kw: None):
        result = await execute_note_formulas(db, note.project_id, note.year, note.note_section)

    assert result["updated"] >= 1
    assert note.table_data["rows"][2]["values"][0] == 30.0


@pytest.mark.asyncio
async def test_execute_user_only_formula_executes():
    """用户集新增一条模板没有的公式键，execute 也应执行并回填."""
    note = _make_note(
        template_formulas={},  # 模板无公式
        user_formulas=[{"target": "2:0", "formula": "SUM(0:1, 0)",
                        "type": "vertical_sum", "source": "user"}],
    )
    db = _make_db(note)
    with patch("sqlalchemy.orm.attributes.flag_modified", lambda *_a, **_kw: None):
        result = await execute_note_formulas(db, note.project_id, note.year, note.note_section)

    assert result["updated"] >= 1
    assert note.table_data["rows"][2]["values"][0] == 30.0
