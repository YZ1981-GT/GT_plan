"""Wave 1 / Task 2.1 —— P0-1 保存跳过 parsed_data + 返回 evaluated_value（不做 DB 写回）.

spec: .kiro/specs/d-cycle-tier-a-writeback-detail-seed/
      (Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 6.1 / Property 1, 2, 3, 4, 13)

`PUT /api/workpapers/{wp_id}/formulas` auto_calc 分支按 `is_known_anchor(base_wp_code,
target_cell)` 路由：

  * **D-cycle 锚点 + 主灰度开关开** → 跳过 `write_cell_to_parsed_data`（专属组件读
    checklist_responses 而非 parsed_data 网格）+ 求值返回 `evaluated_value` 供前端即时显示
    + **不做任何 checklist_responses/DB 写回**（决策1：render transient seed 才是权威）。
  * **普通网格 cell / 非 D-cycle / 主开关关** → 沿用 `write_cell_to_parsed_data`（逐字节零回归）。

测试用 fake async session（不触发 conftest 真实 SQLite create_all），直接调 router 协程，
绕过 FastAPI Depends。灰度开关经 monkeypatch settings 翻转。锚点合法性由真实
`d_cycle_anchor_registry.json` 判定（`is_known_anchor`，纯文件读，无 DB）。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.core.config import settings
from app.routers import wp_formula as router_mod


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fake async session（PUT 路径：working_paper / wp_index / wp_formula + commit）
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, *, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))


class _FakeSession:
    """记录所有 execute 的 SQL，用于断言无 checklist_responses/DB 写回（Property 13）。"""

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
            return _FakeResult(scalar=self.wp_code)
        if "from wp_formula" in sl:
            return _FakeResult(rows=self.user_formulas)
        if "from working_paper" in sl:
            if "is_deleted" in sl:
                return _FakeResult(scalar=self.wp)
            return _FakeResult(scalar=self.wp.project_id)
        return _FakeResult()

    async def commit(self):
        self.committed = True

    async def rollback(self):
        return None


def _wp():
    return SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        wp_index_id=uuid4(),
        is_deleted=False,
        parsed_data={},
    )


def _saved_formula(target_cell, *, sheet_name="D6-1", wp=None,
                   formula_type="auto_calc", expression="TB('1141','期末余额')"):
    return SimpleNamespace(
        id=uuid4(),
        project_id=(wp.project_id if wp else uuid4()),
        wp_id=(wp.id if wp else uuid4()),
        sheet_name=sheet_name,
        target_cell=target_cell,
        expression=expression,
        category=None,
        description="用户公式",
        formula_type=formula_type,
        refs=None,
        issue_description=None,
        hint_text=None,
        # V104/V100 生命周期与来源字段（_formula_to_dict 会下发这三个键，
        # 缺则 AttributeError；值取 ORM server_default）
        lifecycle_state="saved",
        definition_version=1,
        formula_source="custom",
        last_computed_at=None,
        created_by=None,
        created_at=None,
        updated_at=None,
    )


def _user():
    return SimpleNamespace(id=uuid4(), username="tester")


def _enable(monkeypatch):
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)


def _disable(monkeypatch):
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)


def _patch_save_path(monkeypatch, *, saved, evaluated=123.45, eval_errors=None):
    """打通 PUT save 路径：过函数门 + 求值(spy) + 记录 write_cell 调用 + 静默 linkage。

    Returns dict(write_calls=[...], eval_calls=[...])。
    """
    monkeypatch.setattr(router_mod, "find_unsupported_formula_functions", lambda expr: [])

    async def _fake_save(*a, **kw):
        return saved, []

    monkeypatch.setattr(router_mod.wp_formula_service, "save", _fake_save)

    eval_calls: list[dict] = []

    async def _fake_eval(db, **kw):
        eval_calls.append(dict(kw))
        return evaluated, list(eval_errors or [])

    monkeypatch.setattr(router_mod, "evaluate_wp_formula_expression", _fake_eval)

    write_calls: list[dict] = []

    def _spy_write(wp, *, sheet_name, cell_ref, value):
        write_calls.append({"sheet_name": sheet_name, "cell_ref": cell_ref, "value": value})

    monkeypatch.setattr(router_mod, "write_cell_to_parsed_data", _spy_write)

    linkage_calls: list[dict] = []

    async def _fake_linkage(*a, **kw):
        linkage_calls.append(dict(kw))
        return None

    monkeypatch.setattr(
        "app.services.wp_formula_linkage_service.propagate_custom_wp_cell_change",
        _fake_linkage,
    )
    return {"write": write_calls, "eval": eval_calls, "linkage": linkage_calls}


def _body(target_cell, *, sheet_name="D6-1", expression="TB('1141','期末余额')"):
    return router_mod.FormulaSaveRequest(
        sheet_name=sheet_name, target_cell=target_cell,
        expression=expression, year=2025,
    )


# ---------------------------------------------------------------------------
# Property 1: D-cycle 锚点保存跳过 parsed_data + 返回 evaluated_value + 不做 DB 写回
#   Validates: Requirements 1.1, 1.2
# ---------------------------------------------------------------------------


def test_property1_dcycle_anchor_skips_parsed_data_returns_value(monkeypatch):
    """主开关开 + target_cell ∈ known_anchors(D6) → 跳过 write_cell_to_parsed_data，
    响应返回 evaluated_value（供前端即时显示）。"""
    _enable(monkeypatch)
    wp = _wp()
    saved = _saved_formula("D6-1-tb-amount", wp=wp)
    spies = _patch_save_path(monkeypatch, saved=saved, evaluated=98765.43)
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[])

    resp = _run(router_mod.save_formula(wp.id, _body("D6-1-tb-amount"), db=db, user=_user()))

    assert spies["write"] == [], "D-cycle 锚点应跳过 write_cell_to_parsed_data（Property 1）"
    assert resp["evaluated_value"] == str(98765.43), "应返回 evaluated_value 供前端即时显示"
    # 求值仍执行（用于返回 evaluated_value）
    assert len(spies["eval"]) == 1


def test_property1_sheet_level_wp_code_strips_suffix(monkeypatch):
    """wp_code 为 sheet 级 'D6-1' 时剥离后缀得 base 'D6'，锚点路由仍生效（跳过网格写）。"""
    _enable(monkeypatch)
    wp = _wp()
    saved = _saved_formula("D6-1-tb-amount", wp=wp)
    spies = _patch_save_path(monkeypatch, saved=saved, evaluated=555.0)
    db = _FakeSession(wp=wp, wp_code="D6-1", user_formulas=[])

    resp = _run(router_mod.save_formula(wp.id, _body("D6-1-tb-amount"), db=db, user=_user()))

    assert spies["write"] == [], "sheet 级 wp_code 'D6-1' 剥离后缀 → D6，锚点路由生效"
    assert resp["evaluated_value"] == str(555.0)


def test_property13_dcycle_anchor_no_db_writeback(monkeypatch):
    """Property 13：D-cycle 锚点保存全程 transient——不向 checklist_responses/DB 持久化任何值。

    fake session 记录的所有 execute SQL 中不得含 checklist_responses 的 INSERT/UPDATE
    （仅 working_paper/wp_index/wp_formula 读取 + commit）。
    Validates: Requirements 1.2 / Property 13。
    """
    _enable(monkeypatch)
    wp = _wp()
    saved = _saved_formula("D6-1-tb-amount", wp=wp)
    _patch_save_path(monkeypatch, saved=saved)
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[])

    _run(router_mod.save_formula(wp.id, _body("D6-1-tb-amount"), db=db, user=_user()))

    joined = " ".join(db.executed_sql).lower()
    assert "checklist_responses" not in joined, (
        "决策1：保存不得向 checklist_responses 写回（render transient seed 才是权威）"
    )
    for banned in ("insert into", "update "):
        assert banned not in joined, f"D-cycle 锚点保存不得 {banned!r}（不做 DB 写回）"
    assert db.committed is True


# ---------------------------------------------------------------------------
# Property 2: 非锚点走 parsed_data 零回归
#   Validates: Requirements 1.3, 6.1
# ---------------------------------------------------------------------------


def test_property2_grid_cell_writes_parsed_data(monkeypatch):
    """主开关开但 target_cell 为普通网格 cell（∉ known_anchors）→ 沿用 write_cell_to_parsed_data。"""
    _enable(monkeypatch)
    wp = _wp()
    saved = _saved_formula("B5", sheet_name="Sheet1", wp=wp)
    spies = _patch_save_path(monkeypatch, saved=saved, evaluated=42.0)
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[])

    resp = _run(router_mod.save_formula(
        wp.id, _body("B5", sheet_name="Sheet1"), db=db, user=_user()))

    assert len(spies["write"]) == 1, "普通网格 cell 应写 parsed_data（零回归）"
    assert spies["write"][0]["cell_ref"] == "B5"
    assert resp["evaluated_value"] == str(42.0)


def test_property2_non_dcycle_wp_writes_parsed_data(monkeypatch):
    """非 D-cycle 底稿（wp_code=K1）即便 target_cell 形似锚点也走 parsed_data（零回归）。"""
    _enable(monkeypatch)
    wp = _wp()
    saved = _saved_formula("K1-1-tb-amount", sheet_name="K1-1", wp=wp)
    spies = _patch_save_path(monkeypatch, saved=saved, evaluated=7.0)
    db = _FakeSession(wp=wp, wp_code="K1", user_formulas=[])

    _run(router_mod.save_formula(
        wp.id, _body("K1-1-tb-amount", sheet_name="K1-1"), db=db, user=_user()))

    assert len(spies["write"]) == 1, "非 D-cycle 底稿走 parsed_data（base_wp_code 不匹配 D1–D7）"


def test_property2_flag_off_dcycle_anchor_writes_parsed_data(monkeypatch):
    """主开关关时 D-cycle 锚点仍走 parsed_data（逐字节零回归 / R1.6, R6.1）。"""
    _disable(monkeypatch)
    wp = _wp()
    saved = _saved_formula("D6-1-tb-amount", wp=wp)
    spies = _patch_save_path(monkeypatch, saved=saved, evaluated=1.0)
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[])

    _run(router_mod.save_formula(wp.id, _body("D6-1-tb-amount"), db=db, user=_user()))

    assert len(spies["write"]) == 1, "主开关关时 D-cycle 锚点仍写 parsed_data（零回归）"


# ---------------------------------------------------------------------------
# Property 3: 求值失败不静默落空
#   Validates: Requirements 1.4
# ---------------------------------------------------------------------------


def test_property3_dcycle_anchor_eval_error_returns_warnings_no_value(monkeypatch):
    """D-cycle 锚点求值有 eval_errors → 返回 eval_warnings 且不返回错误/0 的 evaluated_value。"""
    _enable(monkeypatch)
    wp = _wp()
    saved = _saved_formula("D6-1-tb-amount", wp=wp)
    spies = _patch_save_path(
        monkeypatch, saved=saved, evaluated=0.0, eval_errors=["TB('x'): 无法解析"])
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[])

    resp = _run(router_mod.save_formula(wp.id, _body("D6-1-tb-amount"), db=db, user=_user()))

    assert resp.get("eval_warnings") == ["TB('x'): 无法解析"]
    assert "evaluated_value" not in resp, "求值失败不返回错误/0 的 evaluated_value（不静默落空）"
    assert spies["write"] == [], "锚点求值失败仍不写 parsed_data"


def test_property3_grid_cell_eval_error_keeps_value_zero_regression(monkeypatch):
    """非锚点网格 cell 求值有 eval_errors → 逐字节零回归：仍返回 evaluated_value + eval_warnings。"""
    _enable(monkeypatch)
    wp = _wp()
    saved = _saved_formula("B5", sheet_name="Sheet1", wp=wp)
    spies = _patch_save_path(
        monkeypatch, saved=saved, evaluated=0.0, eval_errors=["跨 sheet 引用缺失"])
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[])

    resp = _run(router_mod.save_formula(
        wp.id, _body("B5", sheet_name="Sheet1"), db=db, user=_user()))

    assert resp["evaluated_value"] == str(0.0), "非锚点保留旧行为（返回 evaluated_value）"
    assert resp.get("eval_warnings") == ["跨 sheet 引用缺失"]
    assert len(spies["write"]) == 1


# ---------------------------------------------------------------------------
# Property 4: 口径统一（保存求值经共享评估器 → get_active_filter）
#   Validates: Requirements 1.5, 7.2
# ---------------------------------------------------------------------------


def test_property4_save_evaluates_via_shared_evaluator(monkeypatch):
    """保存求值经共享 evaluate_wp_formula_expression（其 _resolve_tb/_resolve_sum_tb 经
    get_active_filter，由契约守卫 G2 锁定）——锚点与网格两路径都调用它，参数传 project_id/year。"""
    _enable(monkeypatch)
    for target, wp_code in (("D6-1-tb-amount", "D6"), ("B5", "D6")):
        wp = _wp()
        saved = _saved_formula(target, wp=wp)
        spies = _patch_save_path(monkeypatch, saved=saved, evaluated=1.0)
        db = _FakeSession(wp=wp, wp_code=wp_code, user_formulas=[])
        _run(router_mod.save_formula(wp.id, _body(target), db=db, user=_user()))
        assert len(spies["eval"]) == 1, f"{target} 应经共享评估器求值"
        kw = spies["eval"][0]
        assert kw["project_id"] == wp.project_id
        assert kw["year"] == 2025


def test_property12_logic_check_never_writes_value(monkeypatch):
    """Property 12 护栏：logic_check 类型不求值不写回（不写 parsed_data、无 evaluated_value）。"""
    _enable(monkeypatch)
    wp = _wp()
    saved = _saved_formula("D6-1-tb-amount", wp=wp, formula_type="logic_check")
    spies = _patch_save_path(monkeypatch, saved=saved)
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[])

    resp = _run(router_mod.save_formula(wp.id, _body("D6-1-tb-amount"), db=db, user=_user()))

    assert spies["write"] == []
    assert spies["eval"] == [], "logic_check 不求值（不改值 / R6.4）"
    assert "evaluated_value" not in resp
