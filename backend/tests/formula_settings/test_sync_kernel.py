"""同步内核：分类与决策逐格 + 性质测试（spec formula-global-settings-sync R3/R4/R5/R7）。"""
from __future__ import annotations

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from app.services.formula_settings.definitions import (
    DISABLED_KEY,
    exec_hash,
    merge_keep_local_desc,
    normalize,
    same_exec,
)
from app.services.formula_settings.sync import (
    Action,
    Category,
    ConflictChoice,
    LocalState,
    ProjectChoice,
    Resolution,
    classify,
    classify_push,
    decide,
    decide_push,
    resolve_pending,
)

D = "report"


def rc(formula: str, desc: str = "") -> dict:
    return {"formula": formula, "formula_category": "auto_calc", "formula_description": desc}


G0, G1, L = rc("TB('1001','期末余额')"), rc("TB('1001','期末余额')+TB('1002','期末余额')"), rc("ROW('BS-001')")


# ── definitions ──

def test_normalize_strips_and_unifies_empty_values():
    a = {"formula": "  TB('1')  ", "aje_formula": None, "formula_category": "auto_calc"}
    b = {"formula": "TB('1')", "aje_formula": "", "rje_formula": None, "formula_category": "auto_calc ",
         "unknown": "ignored"}
    assert normalize(D, a) == normalize(D, b)
    assert exec_hash(D, a) == exec_hash(D, b)
    assert normalize(D, None) is None


def test_description_only_difference_is_not_an_exec_difference():
    assert same_exec(D, rc("A", "说明一"), rc("A", "说明二"))
    assert not same_exec(D, rc("A"), rc("B"))
    assert same_exec(D, None, None) and not same_exec(D, None, rc("A"))


def test_disabled_is_distinct_from_absent_and_from_definitions():
    off = {DISABLED_KEY: True, "formula": "whatever"}
    assert normalize(D, off) == {DISABLED_KEY: "true"}
    assert not same_exec(D, off, None) and not same_exec(D, off, rc("whatever"))


def test_numeric_tolerance_normalizes():
    a = {"left_ref": "ROW('A')", "operator": "=", "right_ref": "ROW('B')", "tolerance": 1}
    b = dict(a, tolerance="1")
    c = dict(a, tolerance=1.0)
    assert same_exec("cross_check", a, b) and same_exec("cross_check", a, c)


def test_merge_keeps_only_locally_edited_descriptions():
    up = rc("NEW", "新说明")
    assert merge_keep_local_desc(D, up, rc("OLD", "旧说明"), rc("OLD", "旧说明"))["formula_description"] == "新说明"
    assert merge_keep_local_desc(D, up, rc("OLD", "我的说明"), rc("OLD", "旧说明"))["formula_description"] == "我的说明"
    assert merge_keep_local_desc(D, None, rc("OLD"), None) is None


# ── 分类逐格 ──

@pytest.mark.parametrize(
    ("local", "frozen", "expected"),
    [
        (None, True, Category.FROZEN),
        (LocalState(L, G0), True, Category.FROZEN),
        (None, False, Category.INHERIT),
        (LocalState(None), False, Category.INHERIT),
        (LocalState(G0, G0, pinned=True), False, Category.PINNED),
        (LocalState(G1, G0), False, Category.SAME),
        (LocalState(G0, G0), False, Category.FOLLOW),
        (LocalState(L, G0), False, Category.CONFLICT),
        (LocalState(L, None), False, Category.CONFLICT),  # 项目独有行遇到新上游
    ],
)
def test_classify_table(local, frozen, expected):
    assert classify(D, new_upstream=G1, local=local, frozen=frozen) is expected


# ── 决策效果逐格 ──

def _decide(category, local, project=ProjectChoice.APPLY, conflict=ConflictChoice.ASK, new=G1):
    return decide(D, category, old_upstream=G0, old_version=3, new_upstream=new, new_version=4,
                  local=local, project_choice=project, conflict_choice=conflict)


def test_inherit_apply_writes_nothing_and_changes_effective():
    e = _decide(Category.INHERIT, None)
    assert (e.action, e.effective_changed) == (Action.NONE, True)


def test_inherit_defer_pins_old_definition_and_asks_project():
    e = _decide(Category.INHERIT, None, ProjectChoice.DEFER)
    assert e.action is Action.PIN and e.pinned and e.pending_reason == "deferred"
    assert same_exec(D, e.local_definition, G0) and e.base_version == 3


def test_follow_apply_moves_to_new_upstream_and_rebases():
    e = _decide(Category.FOLLOW, LocalState(G0, G0, 3))
    assert e.action is Action.SET_LOCAL and same_exec(D, e.local_definition, G1)
    assert (e.base_version, e.effective_changed) == (4, True)


def test_follow_apply_on_upstream_delete_removes_local():
    e = _decide(Category.FOLLOW, LocalState(G0, G0, 3), new=None)
    assert e.action is Action.DELETE_LOCAL and e.effective_changed


def test_follow_defer_pins_current_local():
    e = _decide(Category.FOLLOW, LocalState(G0, G0, 3), ProjectChoice.DEFER)
    assert e.action is Action.PIN and same_exec(D, e.local_definition, G0) and e.base_version == 3


def test_same_only_rebases():
    e = _decide(Category.SAME, LocalState(G1, G0, 3))
    assert (e.action, e.base_version, e.effective_changed) == (Action.REBASE, 4, False)


@pytest.mark.parametrize(
    ("choice", "action", "changed"),
    [
        (ConflictChoice.ASK, Action.PENDING, False),
        (ConflictChoice.KEEP, Action.REBASE, False),
        (ConflictChoice.ADOPT, Action.SET_LOCAL, True),
    ],
)
def test_conflict_choices(choice, action, changed):
    e = _decide(Category.CONFLICT, LocalState(L, G0, 3), conflict=choice)
    assert (e.action, e.effective_changed) == (action, changed)
    if action is Action.PENDING:
        assert e.pending_reason == "conflict"


def test_conflict_in_deferred_project_always_asks():
    e = _decide(Category.CONFLICT, LocalState(L, G0, 3), ProjectChoice.DEFER, ConflictChoice.ADOPT)
    assert e.action is Action.PENDING


def test_frozen_never_changes_effective():
    assert _decide(Category.FROZEN, LocalState(L, G0)).action is Action.NONE
    pin = _decide(Category.FROZEN, None)
    assert pin.action is Action.PIN and same_exec(D, pin.local_definition, G0) and not pin.pending_reason
    new_slot = decide(D, Category.FROZEN, old_upstream=None, old_version=None, new_upstream=G1,
                      new_version=1, local=None)
    assert new_slot.action is Action.PIN and new_slot.local_definition == {DISABLED_KEY: True}


def test_pinned_updates_pending_only():
    e = _decide(Category.PINNED, LocalState(G0, G0, 3, pinned=True))
    assert (e.action, e.pending_reason) == (Action.PENDING, "deferred")


# ── 项目处理待确认 ──

def test_resolve_adopt_keep_custom():
    local = LocalState(L, G0, 3, pinned=True)
    adopt = resolve_pending(D, Resolution.ADOPT, upstream=G1, upstream_version=4, local=local)
    assert adopt.action is Action.SET_LOCAL and same_exec(D, adopt.local_definition, G1)
    assert (adopt.base_version, adopt.pinned, adopt.effective_changed) == (4, False, True)
    keep = resolve_pending(D, Resolution.KEEP, upstream=G1, upstream_version=4, local=local)
    assert keep.action is Action.SET_LOCAL and same_exec(D, keep.local_definition, L)
    assert (keep.base_version, keep.pinned, keep.effective_changed) == (4, False, False)
    custom = resolve_pending(D, Resolution.CUSTOM, upstream=G1, upstream_version=4, local=local,
                             custom_definition=rc("ROW('X')"))
    assert same_exec(D, custom.local_definition, rc("ROW('X')")) and custom.effective_changed
    with pytest.raises(ValueError, match="手工修改必须提供定义"):
        resolve_pending(D, Resolution.CUSTOM, upstream=G1, upstream_version=4, local=local)


def test_resolve_adopt_when_upstream_deleted_removes_local():
    e = resolve_pending(D, Resolution.ADOPT, upstream=None, upstream_version=5, local=LocalState(L, G0, 3))
    assert e.action is Action.DELETE_LOCAL


# ── 同级推送 ──

@pytest.mark.parametrize(
    ("target_effective", "local", "expected"),
    [
        (L, LocalState(L, G0), Category.SAME),
        (G0, None, Category.INHERIT),
        (G0, LocalState(G0, G0), Category.FOLLOW),
        (rc("ROW('Y')"), LocalState(rc("ROW('Y')"), G0), Category.CONFLICT),
        (G0, LocalState(G0, G0, pinned=True), Category.CONFLICT),
    ],
)
def test_classify_push(target_effective, local, expected):
    assert classify_push(D, source=L, target_effective=target_effective, local=local, frozen=False) is expected


def test_push_keeps_target_upstream_as_base():
    inherit = decide_push(D, Category.INHERIT, source=L, local=None, upstream=G0, upstream_version=3)
    assert inherit.action is Action.SET_LOCAL and same_exec(D, inherit.base_definition, G0)
    assert inherit.base_version == 3
    ask = decide_push(D, Category.CONFLICT, source=L, local=LocalState(rc("Y"), G0, 3), upstream=G0,
                      upstream_version=3)
    assert ask.action is Action.PENDING
    keep = decide_push(D, Category.CONFLICT, source=L, local=LocalState(rc("Y"), G0, 3), upstream=G0,
                       upstream_version=3, conflict_choice=ConflictChoice.KEEP)
    assert keep.action is Action.NONE


# ── 性质：效果作用后的有效定义等于独立模型（不调用被测分类函数）──

_DEFS = st.sampled_from([None, G0, G1, L, rc("ROW('Z')")])


def _effective_after(effect, local: LocalState | None, new):
    """把效果作用到「项目层 + 上游」上，求项目的有效定义（停用 ≡ 没有定义）。"""
    from app.services.formula_settings.definitions import is_effectively_disabled

    has_local = local is not None and local.definition is not None
    if effect.action in (Action.SET_LOCAL, Action.PIN):
        got = effect.local_definition
        return None if is_effectively_disabled(D, got) else got
    if effect.action is Action.DELETE_LOCAL:
        return new
    return local.definition if has_local else new


def _model(old, new, local: LocalState | None, frozen, project, conflict):
    """需求原文推导的期望有效定义。"""
    has_local = local is not None and local.definition is not None
    before = local.definition if has_local else old
    if frozen or project is ProjectChoice.DEFER:
        return before
    if not has_local:
        return new
    if local.pinned:
        return before
    if same_exec(D, local.definition, new):
        return before
    if same_exec(D, local.definition, local.base_definition):
        return new
    return new if conflict is ConflictChoice.ADOPT else before


@settings(max_examples=5, deadline=None)
@given(old=_DEFS, new=_DEFS, local_def=_DEFS, base=_DEFS, pinned=st.booleans(), frozen=st.booleans(),
       project=st.sampled_from(list(ProjectChoice)), conflict=st.sampled_from(list(ConflictChoice)))
@example(old=G0, new=G1, local_def=L, base=G0, pinned=False, frozen=False,
         project=ProjectChoice.APPLY, conflict=ConflictChoice.ASK)
@example(old=G0, new=G1, local_def=G0, base=G0, pinned=False, frozen=False,
         project=ProjectChoice.APPLY, conflict=ConflictChoice.ASK)
@example(old=G0, new=None, local_def=None, base=None, pinned=False, frozen=True,
         project=ProjectChoice.APPLY, conflict=ConflictChoice.ADOPT)
# hypothesis 找到的反例：归档项目遇到全新公式位 ⇒ 固定为「停用」，有效定义仍为空
@example(old=None, new=G1, local_def=None, base=None, pinned=False, frozen=True,
         project=ProjectChoice.APPLY, conflict=ConflictChoice.ASK)
def test_effect_matches_model(old, new, local_def, base, pinned, frozen, project, conflict):
    local = LocalState(local_def, base, 3, pinned) if local_def is not None else None
    category = classify(D, new_upstream=new, local=local, frozen=frozen)
    effect = decide(D, category, old_upstream=old, old_version=3, new_upstream=new, new_version=4,
                    local=local, project_choice=project, conflict_choice=conflict)
    got = _effective_after(effect, local, new)
    want = _model(old, new, local, frozen, project, conflict)
    assert same_exec(D, got, want), (category, effect)
    # 本项目改过的公式（≠ 基线）只有在明确选择「采用新全局」时才会被改写
    modified = local is not None and not same_exec(D, local.definition, local.base_definition)
    if modified and not (conflict is ConflictChoice.ADOPT and project is ProjectChoice.APPLY):
        assert same_exec(D, got, local.definition)


# ── 物化（上游为订阅模板）与报表域「停用 ≡ 执行字段全空」──

def test_materialize_writes_new_template_slot_for_inherit():
    e = decide(D, Category.INHERIT, old_upstream=G0, old_version=1, new_upstream=G1, new_version=2,
               local=None, materialize=True)
    assert e.action is Action.SET_LOCAL and same_exec(D, e.local_definition, G1) and e.base_version == 2
    assert e.effective_changed
    none = decide(D, Category.INHERIT, old_upstream=G0, old_version=1, new_upstream=None, new_version=2,
                  local=None, materialize=True)
    assert none.action is Action.NONE
    deferred = decide(D, Category.INHERIT, old_upstream=G0, old_version=1, new_upstream=G1, new_version=2,
                      local=None, materialize=True, project_choice=ProjectChoice.DEFER)
    assert deferred.action is Action.PIN


def test_same_rebase_lets_unmodified_descriptions_follow():
    e = decide(D, Category.SAME, old_upstream=G0, old_version=1, new_upstream=rc("A", "新"), new_version=2,
               local=LocalState(rc("A", "旧"), rc("B", "旧"), 1))
    assert e.action is Action.REBASE and e.local_definition["formula_description"] == "新"
    mine = decide(D, Category.SAME, old_upstream=G0, old_version=1, new_upstream=rc("A", "新"), new_version=2,
                  local=LocalState(rc("A", "我的"), rc("B", "旧"), 1))
    assert mine.local_definition["formula_description"] == "我的"


def test_report_disabled_equals_empty_but_other_domains_do_not():
    from app.services.formula_settings.definitions import is_effectively_disabled

    off = {DISABLED_KEY: True}
    assert same_exec("report", off, {"formula": None, "aje_formula": ""})
    assert not same_exec("tb_detail", off, {"formula": ""})
    assert is_effectively_disabled("report", {"formula": "  "}) and not is_effectively_disabled("report", None)
    assert is_effectively_disabled("note", off) and not is_effectively_disabled("note", {"formula": ""})
