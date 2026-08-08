"""Wave 6 / Task 6.1 —— d-cycle-tier-a-writeback-detail-seed 本 spec Property 1–13 生成式 PBT.

spec: .kiro/specs/d-cycle-tier-a-writeback-detail-seed/  (Requirement 7.1 / Property 1–13)

本 spec（P0-1 Tier A 真生效 + P0-2 明细自动 seed）的 13 条 Correctness Properties 此前
**仅由 example-based 集成/单测覆盖**（`test_tier_a_writeback_save.py` / `test_formulas_endpoint_extraction.py`
/ `test_d6_render_tier_a_seed_integration.py` / `test_d1_d2_d3_d5_d7_tier_a_render_seed_integration.py`
/ `test_d4_tier_a_render_seed_integration.py` / `test_d6_2_detail_seed_integration.py` /
`test_evaluator_active_filter.py`）。

⚠️ 注意：同目录 `test_properties_pbt.py` 的生成式 PBT 覆盖的是**前置 spec**
（`d-cycle-four-table-extraction-formulas`）的 Property 1/5/8/10（叶子判定 / 读时收敛优先级
/ 未知锚点拒绝 / 求值幂等），**与本 spec 的 13 条 Property 语义不同**，故不重复。

本文件对本 spec Property 1–13 逐条补**生成式** hypothesis 断言，对随机输入施压
（随机锚点 × 随机求值 / 随机失败注入 / 门控真值表 / 随机 eval_errors 等），锁定不变量：

  * P1  锚点保存跳过 parsed_data + 返回 evaluated_value + 不写 DB
  * P2  非锚点走 parsed_data 零回归
  * P3  求值失败不静默落空
  * P4  口径统一（get_active_filter，同 project/year）
  * P5  GET Tier A 附 value 且单条 fail-open
  * P6  render Tier A transient seed 手工优先 + 写对字段
  * P7  默认预设 render seed = 求值格式化值（等价 tb_amount 口径）
  * P8  明细 seed 手工优先 + 子开关门控（主 ∧ 子 ∧ 空 才 seed）
  * P9  明细 seed 复用既有归集函数不新造
  * P10 灰度关闭零回归
  * P11 独立可回退 + fail-open（任意失败注入不阻断、不 seed）
  * P12 四表库只读 + logic_check/reasonability 不改值
  * P13 seed 全程 transient 不落库

conftest 已注册 `fast` hypothesis profile（max_examples=5、deadline=None、抑制
function_scoped_fixture 健康检查），故可与 monkeypatch（函数级 fixture）+ 同步 `_run`
包装 async 协程共用；每 example 内新建 fake session + 在测试体内重设 monkeypatch，隔离状态。
不触发 conftest 真实 SQLite create_all（不依赖真实 DB fixture）。
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import sqlalchemy as sa
from hypothesis import given
from hypothesis import strategies as st

from app.core.config import settings
from app.models.audit_platform_models import TrialBalance
from app.routers import wp_formula as router_mod
from app.routers.wp_render_strategies import _d6_contract_assets as d6
from app.services import wp_formula_eval_service as eval_mod
from app.services.d_cycle_extraction import prefill as prefill_mod
from app.services.d_cycle_extraction import presets as presets_mod
from app.services.d_cycle_extraction.anchor_registry import is_known_anchor, seed_field
from app.services.d_cycle_extraction.presets import (
    SOURCE_CUSTOM,
    SOURCE_DISABLED,
    SOURCE_PRESET,
)
from app.services.d_cycle_extraction.tier_a_seed import seed_tier_a_reconciliation
from app.services.wp_formula_eval_service import _resolve_tb
from app.services.wp_parsed_data_service import format_cell_display_value


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 生成式策略常量（confirmed 已登记锚点，非臆造）
# ---------------------------------------------------------------------------

# 确认已登记的 D-cycle 锚点（is_known_anchor True）——供 P1/P3/P12 保存路径
_KNOWN_ANCHORS = [
    ("D6", "D6-1-tb-amount"),
    ("D6", "D6-1-note-conclusion"),
    ("D6", "D6-1-note-explanation"),
    ("D6", "D6-2-rows"),
    ("D2", "D2-adj-tb-amount"),
    ("D2", "D2-detail-rows"),
]

# 确认有 seed_field 登记的 TB 核对行锚点（render transient seed 目标）——供 P6/P7/P11/P13
_SEED_ANCHORS = [
    ("D1", "D1-adj-tb-amount"),
    ("D2", "D2-adj-tb-amount"),
    ("D3", "D3-adj-trial-balance-amount"),
    ("D5", "D5-1-tb-amount"),
    ("D6", "D6-1-tb-amount"),
    ("D7", "D7-1-adj-aging-trial-balance-currentAudited"),
    ("D4", "D4-1-adj-tb-6001"),
    ("D4", "D4-1-adj-tb-6051"),
]

_NON_DCYCLE_WP = ["K1", "H1", "F2", "G7", "N1", "M6"]

st_known_anchor = st.sampled_from(_KNOWN_ANCHORS)
st_seed_anchor = st.sampled_from(_SEED_ANCHORS)
st_non_dcycle_wp = st.sampled_from(_NON_DCYCLE_WP)
# 普通网格 cell（∉ 任何登记锚点）：1-2 大写字母 + 1-3 数字
st_grid_cell = st.from_regex(r"[A-Z]{1,2}[1-9][0-9]{0,2}", fullmatch=True)
st_amount = st.decimals(
    min_value=Decimal("-1e9"), max_value=Decimal("1e9"),
    allow_nan=False, allow_infinity=False, places=2,
)


# ===========================================================================
# 保存路径 fakes（P1/P2/P3/P10/P12/P13-save）
# ===========================================================================


class _SaveResult:
    def __init__(self, *, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))


class _SaveSession:
    """记录 execute SQL，用于断言无 DB 写回（Property 13）。"""

    def __init__(self, *, wp, wp_code, user_formulas=None):
        self.wp = wp
        self.wp_code = wp_code
        self.user_formulas = user_formulas or []
        self.committed = False
        self.executed_sql: list[str] = []

    async def execute(self, stmt, params=None):
        s = str(stmt)
        self.executed_sql.append(s)
        sl = s.lower()
        if "from wp_index" in sl:
            return _SaveResult(scalar=self.wp_code)
        if "from wp_formula" in sl:
            return _SaveResult(rows=self.user_formulas)
        if "from working_paper" in sl:
            if "is_deleted" in sl:
                return _SaveResult(scalar=self.wp)
            return _SaveResult(scalar=self.wp.project_id)
        return _SaveResult()

    async def commit(self):
        self.committed = True

    async def rollback(self):
        return None


def _wp():
    return SimpleNamespace(
        id=uuid4(), project_id=uuid4(), wp_index_id=uuid4(),
        is_deleted=False, parsed_data={},
    )


def _saved(target_cell, *, sheet_name="D6-1", wp=None, formula_type="auto_calc",
           expression="TB('1141','期末余额')"):
    return SimpleNamespace(
        id=uuid4(), project_id=(wp.project_id if wp else uuid4()),
        wp_id=(wp.id if wp else uuid4()), sheet_name=sheet_name,
        target_cell=target_cell, expression=expression, category=None,
        description="用户公式", formula_type=formula_type, refs=None,
        issue_description=None, hint_text=None,
        # V104/V100 生命周期与来源字段（_formula_to_dict 下发这三个键）
        lifecycle_state="saved", definition_version=1, formula_source="custom",
        last_computed_at=None,
        created_by=None, created_at=None, updated_at=None,
    )


def _user():
    return SimpleNamespace(id=uuid4(), username="tester")


def _patch_save(monkeypatch, *, saved, evaluated, eval_errors=None):
    """打通 save 路径，返回 write_cell 调用记录。每 example 内调用得新鲜闭包。"""
    monkeypatch.setattr(router_mod, "find_unsupported_formula_functions", lambda expr: [])

    async def _fake_save(*a, **kw):
        return saved, []

    monkeypatch.setattr(router_mod.wp_formula_service, "save", _fake_save)

    async def _fake_eval(db, **kw):
        return evaluated, list(eval_errors or [])

    monkeypatch.setattr(router_mod, "evaluate_wp_formula_expression", _fake_eval)

    write_calls: list[dict] = []

    def _spy_write(wp, *, sheet_name, cell_ref, value):
        write_calls.append({"cell_ref": cell_ref, "value": value})

    monkeypatch.setattr(router_mod, "write_cell_to_parsed_data", _spy_write)

    async def _fake_linkage(*a, **kw):
        return None

    monkeypatch.setattr(
        "app.services.wp_formula_linkage_service.propagate_custom_wp_cell_change",
        _fake_linkage,
    )
    return write_calls


def _body(target_cell, *, sheet_name="D6-1", expression="TB('1141','期末余额')",
          formula_type="auto_calc"):
    return router_mod.FormulaSaveRequest(
        sheet_name=sheet_name, target_cell=target_cell, expression=expression,
        year=2025, formula_type=formula_type,
    )


def _no_db_write(sql_list):
    joined = " ".join(sql_list).lower()
    return (
        "checklist_responses" not in joined
        and "insert into" not in joined
        and "update " not in joined
    )


# ---------------------------------------------------------------------------
# Property 1: 锚点保存跳过 parsed_data + 返回 evaluated_value + 不做 DB 写回
# ---------------------------------------------------------------------------


@given(pair=st_known_anchor, value=st_amount)
def test_pbt_p1_anchor_save_skips_parsed_data_returns_value_no_db(monkeypatch, pair, value):
    """任意 (D-cycle 已登记锚点, 求值)：主开关开 → 跳过 write_cell_to_parsed_data、
    返回 evaluated_value=str(value)、且无任何 DB/checklist_responses 写回。"""
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)
    wp_code, anchor = pair
    assert is_known_anchor(wp_code, anchor)  # 前提：确为已登记锚点
    wp = _wp()
    saved = _saved(anchor, sheet_name=f"{wp_code}-1", wp=wp)
    writes = _patch_save(monkeypatch, saved=saved, evaluated=value)
    db = _SaveSession(wp=wp, wp_code=wp_code, user_formulas=[])

    resp = _run(router_mod.save_formula(
        wp.id, _body(anchor, sheet_name=f"{wp_code}-1"), db=db, user=_user()))

    assert writes == [], "D-cycle 锚点保存必跳过 parsed_data 写（Property 1）"
    assert resp["evaluated_value"] == str(value), "返回 evaluated_value 供即时显示"
    assert _no_db_write(db.executed_sql), "锚点保存不做 DB/checklist_responses 写回（Property 13）"
    assert db.committed is True


# ---------------------------------------------------------------------------
# Property 2: 非锚点走 parsed_data 零回归
# ---------------------------------------------------------------------------


@given(cell=st_grid_cell, value=st_amount)
def test_pbt_p2_grid_cell_writes_parsed_data(monkeypatch, cell, value):
    """任意普通网格 cell（∉ 已知锚点）→ 沿用 write_cell_to_parsed_data（零回归）。"""
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)
    assert not is_known_anchor("D6", cell)  # 前提：非锚点
    wp = _wp()
    saved = _saved(cell, sheet_name="Sheet1", wp=wp)
    writes = _patch_save(monkeypatch, saved=saved, evaluated=value)
    db = _SaveSession(wp=wp, wp_code="D6", user_formulas=[])

    resp = _run(router_mod.save_formula(
        wp.id, _body(cell, sheet_name="Sheet1"), db=db, user=_user()))

    assert len(writes) == 1 and writes[0]["cell_ref"] == cell, "普通网格 cell 写 parsed_data"
    assert resp["evaluated_value"] == str(value)


@given(wp_code=st_non_dcycle_wp, value=st_amount)
def test_pbt_p2_non_dcycle_wp_writes_parsed_data(monkeypatch, wp_code, value):
    """任意非 D-cycle 底稿（K1/H1/...）即便 target 形似锚点也走 parsed_data（零回归）。"""
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)
    wp = _wp()
    target = f"{wp_code}-1-tb-amount"
    saved = _saved(target, sheet_name=f"{wp_code}-1", wp=wp)
    writes = _patch_save(monkeypatch, saved=saved, evaluated=value)
    db = _SaveSession(wp=wp, wp_code=wp_code, user_formulas=[])

    _run(router_mod.save_formula(
        wp.id, _body(target, sheet_name=f"{wp_code}-1"), db=db, user=_user()))

    assert len(writes) == 1, "非 D-cycle 底稿走 parsed_data（base_wp_code 不匹配 D1–D7）"


# ---------------------------------------------------------------------------
# Property 3: 求值失败不静默落空
# ---------------------------------------------------------------------------


@given(
    pair=st_known_anchor,
    errs=st.lists(st.text(min_size=1, max_size=40), min_size=1, max_size=4),
)
def test_pbt_p3_anchor_eval_errors_returns_warnings_no_value(monkeypatch, pair, errs):
    """任意非空 eval_errors + 已登记锚点 → 返回 eval_warnings 且不返回错误/0 的
    evaluated_value（不静默落空），且仍跳过 parsed_data 写。"""
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)
    wp_code, anchor = pair
    wp = _wp()
    saved = _saved(anchor, sheet_name=f"{wp_code}-1", wp=wp)
    writes = _patch_save(monkeypatch, saved=saved, evaluated=Decimal("0"), eval_errors=errs)
    db = _SaveSession(wp=wp, wp_code=wp_code, user_formulas=[])

    resp = _run(router_mod.save_formula(
        wp.id, _body(anchor, sheet_name=f"{wp_code}-1"), db=db, user=_user()))

    assert resp.get("eval_warnings") == errs, "返回 eval_warnings"
    assert "evaluated_value" not in resp, "求值失败不返回错误/0 的 evaluated_value"
    assert writes == [], "锚点求值失败仍不写 parsed_data"


# ---------------------------------------------------------------------------
# Property 4: 口径统一（get_active_filter，同 project/year）
# ---------------------------------------------------------------------------


class _EvalResult:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))


class _EvalSession:
    def __init__(self, rows=None):
        self._rows = rows or []

    async def execute(self, stmt, params=None):
        return _EvalResult(self._rows)


def _tb_eval_row(code, *, audited):
    return SimpleNamespace(
        standard_account_code=code, audited_amount=Decimal(str(audited)),
        opening_balance=Decimal("0"), unadjusted_amount=Decimal("0"),
        rje_adjustment=Decimal("0"), aje_adjustment=Decimal("0"),
    )


@given(
    year=st.integers(min_value=2000, max_value=2100),
    audited=st.decimals(min_value=Decimal("-1e6"), max_value=Decimal("1e6"),
                        allow_nan=False, allow_infinity=False, places=2),
)
def test_pbt_p4_resolve_tb_via_active_filter_same_project_year(monkeypatch, year, audited):
    """任意 (project_id, year)：Tier A 求值经 get_active_filter，以 TrialBalance 表 +
    同 (project_id, year) 调用（与 Tier B 预填 / GET / render seed 同数据集版本口径）。"""
    calls: list[dict] = []

    async def _fake_filter(db, table, project_id, year, **kw):
        calls.append({"table": table, "project_id": project_id, "year": year})
        return sa.true()

    monkeypatch.setattr(eval_mod, "get_active_filter", _fake_filter)
    pid = uuid4()
    sess = _EvalSession([_tb_eval_row("1141", audited=audited)])

    val = _run(_resolve_tb(sess, pid, year, "1141", "期末余额"))

    assert val == Decimal(str(audited))
    assert len(calls) == 1
    assert calls[0]["table"] is TrialBalance.__table__
    assert calls[0]["project_id"] == pid
    assert calls[0]["year"] == year


# ===========================================================================
# GET 路径 fakes（P5 / P10-get）
# ===========================================================================


class _GetSession:
    def __init__(self, *, wp, wp_code, user_formulas=None, project_year=None):
        self.wp = wp
        self.wp_code = wp_code
        self.user_formulas = user_formulas or []
        self.project_year = project_year

    async def execute(self, stmt, params=None):
        s = str(stmt).lower()
        if "from wp_index" in s:
            return _SaveResult(scalar=self.wp_code)
        if "from wp_formula" in s:
            return _SaveResult(rows=self.user_formulas)
        if "from projects" in s:
            return _SaveResult(scalar=self.project_year)
        if "from working_paper" in s:
            if "is_deleted" in s:
                return _SaveResult(scalar=self.wp)
            return _SaveResult(scalar=self.wp.project_id)
        return _SaveResult()

    async def rollback(self):
        return None


def _preset(anchor, *, expression="TB('1141','期末余额')", sheet_name="D6-1"):
    return {
        "wp_code": "D6", "sheet_name": sheet_name, "anchor": anchor,
        "expression": expression, "formula_type": "auto_calc",
        "description": "预设", "source": SOURCE_PRESET, "tier": "A",
    }


def _patch_presets(monkeypatch, bindings):
    def _fake_load(code):
        return [dict(b) for b in bindings] if code == "D6" else []
    monkeypatch.setattr(presets_mod, "load_presets", _fake_load)


# ---------------------------------------------------------------------------
# Property 5: GET Tier A 附 value 且单条 fail-open
# ---------------------------------------------------------------------------


@given(
    fail_flags=st.lists(st.booleans(), min_size=1, max_size=4),
    value=st.integers(min_value=1, max_value=10_000_000),
)
def test_pbt_p5_get_tier_a_value_single_fail_open(monkeypatch, fail_flags, value):
    """任意 N 条 Tier A binding + 随机失败子集 → 失败条 value=None、成功条填值，
    整个 GET 不阻断（单条 fail-open / Property 5）。"""
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)
    # 每条锚点唯一（用 index 拼 note 锚点变体，均为 D6 已登记？——用固定两个已知 + 其余复用
    # tb-amount 表达式区分 fail/success 靠表达式内嵌标记）
    anchors = ["D6-1-tb-amount", "D6-1-note-conclusion", "D6-1-note-explanation", "D6-2-rows"]
    bindings = []
    fail_exprs = set()
    for i, fail in enumerate(fail_flags):
        anchor = anchors[i % len(anchors)]
        # 保证锚点唯一：仅取前 len(anchors) 条
        if i >= len(anchors):
            break
        expr = f"TB('{'9999' if fail else '1141'}','期末余额')"
        if fail:
            fail_exprs.add(expr)
        bindings.append(_preset(anchor, expression=expr))
    _patch_presets(monkeypatch, bindings)

    async def _selective_eval(db, *, project_id, year, expression, **kw):
        if expression in fail_exprs:
            raise RuntimeError("boom")
        return Decimal(str(value)), []

    monkeypatch.setattr(router_mod, "evaluate_wp_formula_expression", _selective_eval)
    wp = _wp()
    db = _GetSession(wp=wp, wp_code="D6", user_formulas=[], project_year=2025)

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    tier_a = {b["anchor"]: b for b in resp["extraction"]["tierA"]}
    for b in bindings:
        got = tier_a[b["anchor"]]["value"]
        if b["expression"] in fail_exprs:
            assert got is None, "失败条 value=None（fail-open）"
        else:
            assert got == value, "成功条填真实求值结果"


# ---------------------------------------------------------------------------
# Property 10: 灰度关闭零回归（GET 无 extraction / 保存仍写 parsed_data）
# ---------------------------------------------------------------------------


@given(pair=st_known_anchor)
def test_pbt_p10_flag_off_get_no_extraction(monkeypatch, pair):
    """主开关关（默认）→ GET 无 extraction 字段（零回归）。"""
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)
    _wp_code, anchor = pair
    _patch_presets(monkeypatch, [_preset(anchor)])
    wp = _wp()
    db = _GetSession(wp=wp, wp_code="D6", user_formulas=[], project_year=2025)
    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))
    assert "extraction" not in resp


@given(pair=st_known_anchor, value=st_amount)
def test_pbt_p10_flag_off_save_writes_parsed_data(monkeypatch, pair, value):
    """主开关关 → 即便 D-cycle 锚点也照写 parsed_data（逐字节零回归）。"""
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)
    wp_code, anchor = pair
    wp = _wp()
    saved = _saved(anchor, sheet_name=f"{wp_code}-1", wp=wp)
    writes = _patch_save(monkeypatch, saved=saved, evaluated=value)
    db = _SaveSession(wp=wp, wp_code=wp_code, user_formulas=[])
    _run(router_mod.save_formula(
        wp.id, _body(anchor, sheet_name=f"{wp_code}-1"), db=db, user=_user()))
    assert len(writes) == 1, "主开关关时 D-cycle 锚点仍写 parsed_data（零回归）"


# ---------------------------------------------------------------------------
# Property 12: 四表库只读 + logic_check / reasonability 不改值
# ---------------------------------------------------------------------------


@given(pair=st_known_anchor, ftype=st.sampled_from(["logic_check", "reasonability"]))
def test_pbt_p12_logic_check_never_writes_value(monkeypatch, pair, ftype):
    """任意 logic_check/reasonability 类型 + 已登记锚点 → 不求值、不写 parsed_data、
    无 evaluated_value（不改值 / R6.4）。"""
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)
    wp_code, anchor = pair
    wp = _wp()
    saved = _saved(anchor, sheet_name=f"{wp_code}-1", wp=wp, formula_type=ftype)
    writes = _patch_save(monkeypatch, saved=saved, evaluated=Decimal("123"))
    db = _SaveSession(wp=wp, wp_code=wp_code, user_formulas=[])

    resp = _run(router_mod.save_formula(
        wp.id, _body(anchor, sheet_name=f"{wp_code}-1", formula_type=ftype),
        db=db, user=_user()))

    assert writes == [], f"{ftype} 不写 parsed_data"
    assert "evaluated_value" not in resp, f"{ftype} 不返回 evaluated_value"


@given(
    fn=st.sampled_from(["AUX", "PREV", "LEDGER", "COUNT_LEDGER"]),
    code=st.from_regex(r"[1-6][0-9]{3}", fullmatch=True),
)
def test_pbt_p12_unsupported_four_table_functions_detected(fn, code):
    """任意不受支持四表库函数（AUX/PREV/序时账）→ find_unsupported 检出（保存端点据此 422，
    不得当 auto_calc 可编辑目标 / R6.3）。"""
    from app.services.wp_formula_eval_service import find_unsupported_formula_functions

    expr = f"{fn}('{code}','x','期末余额')"
    assert find_unsupported_formula_functions(expr), f"{fn} 应被检出为不受支持"


# ===========================================================================
# render Tier A transient seed via 共享助手 seed_tier_a_reconciliation
#   （P6 手工优先+写对字段 / P7 默认预设=求值格式化值 / P11 fail-open）
# ===========================================================================


def _seed_ctx(*, year=2025):
    # helper 只用 ctx.db / wp_id / project_id / year；db 不被真正 execute（resolve/eval 已注入）
    return SimpleNamespace(db=object(), wp_id=uuid4(), project_id=uuid4(), year=year)


def _mk_resolve(binding):
    async def _resolve(db, wp_id, wp_code, project_id):
        return [binding]
    return _resolve


def _mk_eval(value, errs=None, *, raises=False):
    async def _eval(db, *, project_id, year, expression, **kw):
        if raises:
            raise RuntimeError("eval boom")
        return value, list(errs or [])
    return _eval


# ---------------------------------------------------------------------------
# Property 6: render seed 手工优先 + 写对字段（remark|conclusion）
# ---------------------------------------------------------------------------


@given(pair=st_seed_anchor, disabled=st.booleans(), persisted=st.booleans(), value=st_amount)
def test_pbt_p6_render_seed_manual_priority_correct_field(
    monkeypatch, pair, disabled, persisted, value
):
    """任意 (TB 核对行锚点, disabled?, persisted?, value)：
      * disabled → 不 seed（persisted 则保持原值不变）；
      * 非 disabled 且持久层已有非空该字段值 → 手工优先不覆盖；
      * 否则 → seed 写入登记字段（remark|conclusion），另一字段保留。"""
    from hypothesis import assume

    wp_code, anchor = pair
    field = seed_field(wp_code, anchor)
    assume(field is not None)  # 前提：确为已登记 seed 字段的 TB 核对行
    binding = {
        "anchor": anchor, "expression": "TB('x','期末余额')",
        "source": SOURCE_DISABLED if disabled else SOURCE_PRESET, "tier": "A",
    }
    snap: dict = {}
    if persisted:
        snap[anchor] = {field: "999999", "conclusion": "keep", "remark": "999999"}
    _run(seed_tier_a_reconciliation(
        _seed_ctx(), wp_code, snap,
        resolve_effective=_mk_resolve(binding),
        evaluate_wp_formula_expression=_mk_eval(value),
    ))
    if disabled:
        if persisted:
            assert snap[anchor][field] == "999999", "disabled 不覆盖既有值"
        else:
            assert anchor not in snap, "disabled 不 seed"
    elif persisted:
        assert snap[anchor][field] == "999999", "手工优先不覆盖（Property 6 / R3.2）"
    else:
        assert snap[anchor][field] == str(format_cell_display_value(value)), "seed 写对字段"
        # 另一字段被初始化保留（不丢失）
        other = "conclusion" if field == "remark" else "remark"
        assert other in snap[anchor]


# ---------------------------------------------------------------------------
# Property 7: 默认预设 render seed = 求值格式化值（等价 tb_amount 口径）
# ---------------------------------------------------------------------------


@given(pair=st_seed_anchor, value=st_amount)
def test_pbt_p7_default_preset_seed_equals_formatted_eval(monkeypatch, pair, value):
    """默认预设（source=preset，无用户编辑）+ 空持久层 + 求值成功 → seed 值精确等于
    format_cell_display_value(求值结果)（默认预设 TB(code,'期末余额') 求值 = tb_amount 口径）。"""
    from hypothesis import assume

    wp_code, anchor = pair
    field = seed_field(wp_code, anchor)
    assume(field is not None)
    binding = {
        "anchor": anchor, "expression": "TB('x','期末余额')",
        "source": SOURCE_PRESET, "tier": "A",
    }
    snap: dict = {}
    _run(seed_tier_a_reconciliation(
        _seed_ctx(), wp_code, snap,
        resolve_effective=_mk_resolve(binding),
        evaluate_wp_formula_expression=_mk_eval(value),
    ))
    assert snap[anchor][field] == str(format_cell_display_value(value))


# ---------------------------------------------------------------------------
# Property 11: 独立可回退 + fail-open（任意失败注入 → 不 seed、不抛）
# ---------------------------------------------------------------------------


@given(
    pair=st_seed_anchor,
    mode=st.sampled_from(["resolve_raises", "eval_raises", "eval_errors", "year_none"]),
)
def test_pbt_p11_render_seed_fail_open(monkeypatch, pair, mode):
    """任意失败注入（resolve 异常 / 求值异常 / 有 eval_errors / year 缺失）→ 该锚点不 seed，
    且助手不抛（始终 fail-open / Property 11 / R3.4）。"""
    wp_code, anchor = pair
    binding = {
        "anchor": anchor, "expression": "TB('x','期末余额')",
        "source": SOURCE_PRESET, "tier": "A",
    }
    if mode == "resolve_raises":
        async def _resolve(*a, **k):
            raise RuntimeError("resolve boom")
    else:
        _resolve = _mk_resolve(binding)

    if mode == "eval_raises":
        evaluator = _mk_eval(Decimal("1"), raises=True)
    elif mode == "eval_errors":
        evaluator = _mk_eval(Decimal("0"), errs=["dangling ref"])
    else:
        evaluator = _mk_eval(Decimal("1"))

    year = None if mode == "year_none" else 2025
    snap: dict = {}
    # 不得抛异常
    _run(seed_tier_a_reconciliation(
        _seed_ctx(year=year), wp_code, snap,
        resolve_effective=_resolve, evaluate_wp_formula_expression=evaluator,
    ))
    assert anchor not in snap, f"{mode} → fail-open 不 seed"


# ===========================================================================
# P0-2 明细自动 seed via d6.render（P8 门控+手工优先 / P9 复用不新造 / P13 transient）
# ===========================================================================

_DETAIL_ITEM_ID = "D6-2-rows"


class _DetailResult:
    def __init__(self, rows=None, one=None):
        self._rows = rows or []
        self._one = one

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


class _DetailSession:
    def __init__(self, *, checklist_rows=None, aux_rows=None, raise_on_aux=False):
        self.checklist_rows = checklist_rows or []
        self.aux_rows = aux_rows or []
        self.raise_on_aux = raise_on_aux
        self.executed_sql: list[str] = []

    async def execute(self, stmt, params=None):
        s = str(stmt).lower()
        self.executed_sql.append(s)
        if "tb_aux_balance" in s:
            if self.raise_on_aux:
                raise RuntimeError("aux boom")
            return _DetailResult(rows=self.aux_rows)
        if "tb_balance" in s and "trial_balance" not in s:
            return _DetailResult(rows=[])
        if "checklist_responses" in s:
            return _DetailResult(rows=self.checklist_rows)
        if "related_party_registry" in s:
            return _DetailResult(rows=[])
        if "trial_balance" in s:
            return _DetailResult(one=SimpleNamespace(amount=98765.43))
        if "from projects" in s or "projects where" in s:
            return _DetailResult(one=SimpleNamespace(
                client_name="测试客户", audit_year=2025,
                business_category="general", applicable_standards="listed"))
        return _DetailResult()

    async def rollback(self):
        return None


def _aux_row(name, prior, current):
    return SimpleNamespace(aux_name=name, prior_balance=prior, current_balance=current)


def _detail_ctx(db):
    return SimpleNamespace(
        db=db, wp_id=uuid4(), project_id=uuid4(), year=2025,
        business_category="general",
        classification=SimpleNamespace(sheet_name="合同资产明细表D6-2"),
    )


def _isolate_p0_1(monkeypatch):
    async def _empty_resolve(db, wp_id, wp_code, project_id):
        return []

    async def _fake_filter(db, table, project_id, year, **kw):
        return sa.true()

    monkeypatch.setattr(d6, "resolve_effective", _empty_resolve)
    monkeypatch.setattr(prefill_mod, "get_active_filter", _fake_filter)


def _set_gates(monkeypatch, *, main, sub):
    monkeypatch.setattr(d6.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", main)
    monkeypatch.setattr(d6.settings, "D_CYCLE_DETAIL_SEED_ENABLED", sub)


def _checklist_detail_row(remark):
    return SimpleNamespace(item_id=_DETAIL_ITEM_ID, conclusion="", remark=remark)


# ---------------------------------------------------------------------------
# Property 8: 明细 seed 手工优先 + 子开关门控（主 ∧ 子 ∧ 明细空 才 seed）
# ---------------------------------------------------------------------------


@given(main=st.booleans(), sub=st.booleans(), has_rows=st.booleans())
def test_pbt_p8_detail_seed_gating_truth_table(monkeypatch, main, sub, has_rows):
    """真值表：detail_prefill 出现 ⟺ 主开关 ∧ 子开关 ∧ D6-2 明细完全空。"""
    _set_gates(monkeypatch, main=main, sub=sub)
    _isolate_p0_1(monkeypatch)
    aux = [_aux_row("客户甲", 1000.0, 1500.0), _aux_row("客户乙", 0.0, 500.0)]
    checklist = [_checklist_detail_row('[{"rowId":"r1","contractName":"手工"}]')] if has_rows else []
    db = _DetailSession(checklist_rows=checklist, aux_rows=aux)
    result = _run(d6.render(_detail_ctx(db)))
    expected_seed = main and sub and not has_rows
    assert ("detail_prefill" in result) is expected_seed


# ---------------------------------------------------------------------------
# Property 9: 明细 seed 复用既有归集函数不新造第 3 套读取
# ---------------------------------------------------------------------------


@given(n=st.integers(min_value=1, max_value=5))
def test_pbt_p9_detail_seed_reuses_aggregate_function(monkeypatch, n):
    """任意 n 条 aux 归集 → detail seed 调既有 aggregate_d6_detail_rows（复用不新造），
    SQL 命中 tb_aux_balance + 1141，detail_prefill 行数 = n。"""
    _set_gates(monkeypatch, main=True, sub=True)
    _isolate_p0_1(monkeypatch)
    aux = [_aux_row(f"c{i}", float(i), float(i + 1)) for i in range(n)]
    called = {"hit": False}
    orig = d6.aggregate_d6_detail_rows

    async def _spy(db, project_id, **kw):
        called["hit"] = True
        return await orig(db, project_id, **kw)

    monkeypatch.setattr(d6, "aggregate_d6_detail_rows", _spy)
    db = _DetailSession(aux_rows=aux)
    result = _run(d6.render(_detail_ctx(db)))
    assert called["hit"] is True, "必调既有 aggregate_d6_detail_rows（复用不新造 / Property 9）"
    assert len(result["detail_prefill"]) == n
    assert any("tb_aux_balance" in s and "1141" in s for s in db.executed_sql)


# ---------------------------------------------------------------------------
# Property 11 (detail) + Property 13: 明细归集 fail-open + transient 不落库
# ---------------------------------------------------------------------------


@given(raise_on_aux=st.booleans())
def test_pbt_p11_detail_seed_fail_open(monkeypatch, raise_on_aux):
    """归集异常 → 无 detail_prefill 但 render 正常返回（fail-open）；正常 → 有 detail_prefill。"""
    _set_gates(monkeypatch, main=True, sub=True)
    _isolate_p0_1(monkeypatch)
    aux = [_aux_row("甲", 1.0, 2.0)]
    db = _DetailSession(aux_rows=aux, raise_on_aux=raise_on_aux)
    result = _run(d6.render(_detail_ctx(db)))
    assert "project_context" in result, "render 始终正常返回（不阻断）"
    assert ("detail_prefill" in result) is (not raise_on_aux)


@given(n=st.integers(min_value=1, max_value=4))
def test_pbt_p13_detail_seed_transient_no_db_write(monkeypatch, n):
    """任意 n 条明细 seed → 只进返回 detail_prefill，无任何 checklist_responses INSERT/UPDATE。"""
    _set_gates(monkeypatch, main=True, sub=True)
    _isolate_p0_1(monkeypatch)
    aux = [_aux_row(f"c{i}", float(i), float(i + 1)) for i in range(n)]
    db = _DetailSession(aux_rows=aux)
    result = _run(d6.render(_detail_ctx(db)))
    assert "detail_prefill" in result and len(result["detail_prefill"]) == n
    joined = " ".join(db.executed_sql)
    assert "insert into" not in joined and "update " not in joined, (
        "detail transient seed 不得写 checklist_responses/DB（Property 13）"
    )
