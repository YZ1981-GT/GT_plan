"""公式推送三态判定 `policy.decide` —— 逐行判定表 + 性质测试。

spec: chain-closure-phase2-formula-push-engine · design §五 · 需求 3.1~3.4

判定表每一行一个用例（`_TABLE`），行序即 design §五 的优先级；另用 hypothesis
（max_examples=5）钉住四条性质：系统/派生值总跟随公式、锁定/人工不被覆盖、
受保护的人工值不被覆盖、写后再判必为 unchanged（幂等）。
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.formula_push.policy import (
    ACTIONS,
    POLICIES,
    STATES,
    TOLERANCE,
    Decision,
    PolicyError,
    apply_user_action,
    as_number,
    decide,
    is_blank,
    values_equal,
)

# ── 判定表（design §五 逐行）──────────────────────────────────────────────
# (编号, 策略, 公式值, 当前值, 上次推送值, 先前状态, 外部模式, 期望动作, 期望状态)
_TABLE = [
    ("S1 系统值=公式值", "system", 100, "100", None, None, None, "unchanged", "auto"),
    ("S2 系统值≠公式值", "system", 100, "90", None, None, None, "write", "auto"),
    ("S3 派生值=公式值", "derived", 5, 5.004, None, None, None, "unchanged", "auto"),
    ("S4 派生值≠公式值", "derived", 5, None, None, None, None, "write", "auto"),
    ("S5 系统值无视锁定", "system", 100, "90", "90", "locked", "locked", "write", "auto"),
    ("S6 派生值应为空·当前非空 ⇒ 写空", "derived", None, "12", None, None, None, "write", "auto"),
    ("S7 派生值应为空·当前已空", "derived", "", None, "12", None, None, "unchanged", "auto"),
    ("E1 可编辑·已锁定", "editable", 100, "90", "80", "locked", None, "keep_locked", "locked"),
    ("E2 可编辑·单元格锁定", "editable", 100, "90", None, None, "locked", "keep_locked", "locked"),
    ("E3 可编辑·单元格人工", "editable", 100, "90", "90", None, "manual", "keep_manual", "manual"),
    ("E4 可编辑·当前=公式值", "editable", 100, "100.00", None, None, None, "unchanged", "auto"),
    ("E5 可编辑·当前为空", "editable", 100, None, None, None, None, "write", "auto"),
    ("E6 可编辑·当前空白串", "editable", 100, "  ", "80", "manual", None, "write", "auto"),
    ("E7 可编辑·当前=上次推送", "editable", 100, "80", "80", "auto", None, "write", "auto"),
    ("E8 可编辑·当前≠上次推送", "editable", 100, "90", "80", "auto", None, "keep_manual", "manual"),
    ("E9 可编辑·首次且不等", "editable", 100, "90", None, None, None, "keep_pending", "pending_confirm"),
    ("E10 可编辑·待确认后仍不等", "editable", 100, "90", None, "pending_confirm", None, "keep_pending", "pending_confirm"),
    ("E11 可编辑·人工改回上次推送值", "editable", 100, "80", "80", "manual", None, "write", "auto"),
    ("E12 可编辑·0 不是空", "editable", 100, "0", None, None, None, "keep_pending", "pending_confirm"),
]


@pytest.mark.parametrize(
    "policy,formula,current,last,prior,external,action,state",
    [row[1:] for row in _TABLE],
    ids=[row[0] for row in _TABLE],
)
def test_decision_table_row(policy, formula, current, last, prior, external, action, state):
    d = decide(
        policy,
        formula_value=formula,
        current_value=current,
        last_pushed_value=last,
        prior_state=prior,
        external_mode=external,
    )
    assert (d.action, d.state) == (action, state)
    assert d.action in ACTIONS and d.state in STATES


def test_decision_table_covers_every_action_and_state():
    """判定表本身不得漏掉任何动作 / 状态（防表格被删行后主用例仍全绿）。"""
    assert {row[7] for row in _TABLE} == set(ACTIONS)
    assert {row[8] for row in _TABLE} == set(STATES)
    assert {row[1] for row in _TABLE} == set(POLICIES)


# ── record_pushed / differs ───────────────────────────────────────────────


def test_unchanged_records_formula_as_pushed():
    """等值即采纳：否则公式下次变化时旧的上次推送值会把一致值误判成人工改动。"""
    d = decide("editable", formula_value=100, current_value="100", last_pushed_value="80")
    assert d == Decision("unchanged", "auto", differs=False, record_pushed=True)


@pytest.mark.parametrize("action_row", [r for r in _TABLE if r[7].startswith("keep_")], ids=lambda r: r[0])
def test_keep_never_records_pushed(action_row):
    _, policy, formula, current, last, prior, external, _, _ = action_row
    d = decide(policy, formula_value=formula, current_value=current,
               last_pushed_value=last, prior_state=prior, external_mode=external)
    assert d.kept and not d.record_pushed and not d.writes


def test_locked_equal_value_reports_no_difference():
    d = decide("editable", formula_value=100, current_value="100", prior_state="locked")
    assert d.action == "keep_locked" and d.differs is False


# ── 比较口径（与前端同口径）─────────────────────────────────────────────


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (0, "0.005", True),           # 差恰为容差（浮点精确 0.005）→ 相等：前端冲突判据是 > 0.005
        (100, "100.005", True),       # 浮点差 0.00499…，同为相等
        (100, "100.0051", False),
        ("1e3", 1000, True),
        (Decimal("1.10"), "1.1", True),
        (None, "", True),             # 两空相等
        (None, "0", False),           # 0 不是空
        ("abc", "abc", True),
        ("abc", "abd", False),
        ("1_000", 1000, False),       # Python float 接受下划线，JS Number 不接受 → 按字符串比
        ("nan", "nan", True),         # 非数值按全等
        (True, 1, False),             # bool 不算数值
    ],
)
def test_values_equal(a, b, expected):
    assert values_equal(a, b) is expected
    assert values_equal(b, a) is expected


def test_blank_and_number_helpers():
    assert is_blank(None) and is_blank("") and is_blank("  ")
    assert not is_blank(0) and not is_blank("0")
    assert as_number(" 12.5 ") == 12.5
    assert as_number("inf") is None and as_number(float("nan")) is None
    assert as_number("1,000") is None
    assert TOLERANCE == 0.005


# ── 入参守卫 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kwargs,fragment",
    [
        ({"policy": "overwrite"}, "未知写入策略"),
        ({"prior_state": "stale"}, "未知目标状态"),
        ({"external_mode": "readonly"}, "未知外部模式"),
        ({"formula_value": None}, "可编辑目标的公式值为空"),
        ({"formula_value": "  "}, "可编辑目标的公式值为空"),
    ],
)
def test_decide_rejects_invalid_input(kwargs, fragment):
    base = {"policy": "editable", "formula_value": 1, "current_value": 1}
    base.update(kwargs)
    policy = base.pop("policy")
    with pytest.raises(PolicyError, match=fragment):
        decide(policy, **base)


# ── 用户动作 ─────────────────────────────────────────────────────────────


def test_user_actions():
    assert apply_user_action("adopt", policy="editable", state="manual") == "auto"
    assert apply_user_action("adopt", policy="editable", state="pending_confirm") == "auto"
    assert apply_user_action("lock", policy="editable", state="auto") == "locked"
    assert apply_user_action("unlock", policy="editable", state="locked") == "pending_confirm"


@pytest.mark.parametrize(
    "action,policy,state,fragment",
    [
        ("lock", "system", "auto", "只由引擎维护"),
        ("lock", "derived", "auto", "只由引擎维护"),
        ("unlock", "editable", "manual", "只有已锁定"),
        ("delete", "editable", "auto", "未知操作"),
        ("lock", "editable", "stale", "未知目标状态"),
    ],
)
def test_user_action_rejections(action, policy, state, fragment):
    with pytest.raises(PolicyError, match=fragment):
        apply_user_action(action, policy=policy, state=state)


# ── 性质测试（max_examples=5）────────────────────────────────────────────

_amounts = st.one_of(
    st.integers(min_value=-10**9, max_value=10**9),
    st.decimals(min_value=-10**6, max_value=10**6, places=2, allow_nan=False, allow_infinity=False),
)
_maybe_value = st.one_of(st.none(), _amounts, _amounts.map(str), st.just(""))
_prior = st.one_of(st.none(), st.sampled_from(STATES))
_external = st.sampled_from([None, "manual", "locked"])


@settings(max_examples=5, deadline=None)
@given(policy=st.sampled_from(["system", "derived"]), formula=_maybe_value, current=_maybe_value,
       last=_maybe_value, prior=_prior, external=_external)
def test_prop_engine_owned_always_follows_formula(policy, formula, current, last, prior, external):
    """系统 / 派生值总跟随公式值（公式值为空 ⇒ 目标应为空），不看锁定与上次推送值。"""
    d = decide(policy, formula_value=formula, current_value=current,
               last_pushed_value=last, prior_state=prior, external_mode=external)
    assert d.state == "auto" and d.record_pushed
    assert d.writes is (not values_equal(current, formula))


@settings(max_examples=5, deadline=None)
@given(formula=_amounts, current=_maybe_value, last=_maybe_value, prior=_prior,
       external=st.sampled_from(["manual", "locked"]))
def test_prop_editable_external_mode_never_written(formula, current, last, prior, external):
    d = decide("editable", formula_value=formula, current_value=current,
               last_pushed_value=last, prior_state=prior, external_mode=external)
    assert not d.writes and d.kept


@settings(max_examples=5, deadline=None)
@given(formula=_amounts, current=_amounts, last=_maybe_value,
       prior=st.one_of(st.none(), st.sampled_from(["auto", "manual", "pending_confirm"])))
def test_prop_protected_manual_value_never_overwritten(formula, current, last, prior):
    """非空、≠ 公式值、且 ≠ 上次推送值（或从未推送）的当前值 = 来源不明或人工值，绝不写。"""
    if values_equal(current, formula):
        return
    if last is not None and values_equal(current, last):
        return
    d = decide("editable", formula_value=formula, current_value=current,
               last_pushed_value=last, prior_state=prior)
    assert not d.writes
    assert d.action in {"keep_manual", "keep_pending"}


@settings(max_examples=5, deadline=None)
@given(policy=st.sampled_from(POLICIES), formula=_amounts, current=_maybe_value,
       last=_maybe_value, prior=st.one_of(st.none(), st.sampled_from(["auto", "manual", "pending_confirm"])))
def test_prop_write_then_decide_again_is_unchanged(policy, formula, current, last, prior):
    """写入后按写入结果再判一次必为 unchanged/auto（引擎不会反复写同一值）。"""
    first = decide(policy, formula_value=formula, current_value=current,
                   last_pushed_value=last, prior_state=prior)
    if not first.writes:
        return
    second = decide(policy, formula_value=formula, current_value=formula,
                    last_pushed_value=formula if first.record_pushed else last,
                    prior_state=first.state)
    assert (second.action, second.state) == ("unchanged", "auto")


def test_blank_formula_clears_only_engine_owned_targets():
    """「目标应为空」只对引擎独占目标生效；可编辑目标来源缺失必须由调用方跳过。"""
    assert decide("derived", formula_value=None, current_value="5").writes
    assert decide("system", formula_value="", current_value="5").writes
    assert decide("derived", formula_value=None, current_value=None).action == "unchanged"
    with pytest.raises(PolicyError):
        decide("editable", formula_value=None, current_value="5")
