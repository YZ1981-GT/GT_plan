"""H9 族内 contra 子科目不得双算 —— 取数与三口径自检双侧守卫。

**缺陷背景（2026-08-06 真实库实测，项目 `c8621493`）**

`tb_balance` 的 `2651 租赁负债` 家族::

    2651              租赁负债                     credit   94,219.84   ← 父行
    2651.01           租赁负债_租赁付款额          credit   98,176.48
    2651.02           租赁负债_未确认融资费用      debit     3,956.64   ← 族内 contra
    2651.99           一年内到期的租赁负债         credit      NULL

裸 `aggregate_leaves` 忽略 `closing_direction` ⇒ 98,176.48 + 3,956.64 = **102,133.12**，
与父额差 **7,913.28（= 2 × 3,956.64）** ⇒ 审定表「与试算平衡表核对」显示假差异。

两处都要修：

1. ``_h9_lease_liabilities.build_h9_tb_values`` → 改用 ``resolve_leaf_totals``
   （两种符号约定各算一遍，取与父额勾稽成立的那一种）。
2. ``four_table.parent_check.build_parent_check`` → 裸求和与父额不平时才试方向约定，
   且仅当它能让勾稽成立才采用 ⇒ **原本已平的调用方输出逐字不变**（零回归）。

spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/ Task 18
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.routers.wp_render_strategies._h9_lease_liabilities import build_h9_tb_values
from app.services.four_table.leaf_aggregation import (
    CONVENTION_AS_STORED,
    CONVENTION_DIRECTIONAL,
    LeafRow,
    aggregate_leaves,
    select_leaves,
    to_leaf_rows,
)
from app.services.four_table.parent_check import build_parent_check

_BACKEND = Path(__file__).resolve().parents[2]
_H9_RENDER = _BACKEND / "app" / "routers" / "wp_render_strategies" / "_h9_lease_liabilities.py"
_PARENT_CHECK = _BACKEND / "app" / "services" / "four_table" / "parent_check.py"


def _strip_comments(src: str) -> str:
    """剥 Python 注释与 docstring —— 本守卫的说明文字里会写出被禁的反例。"""
    out = re.sub(r'"""[\s\S]*?"""', "", src)
    out = re.sub(r"'''[\s\S]*?'''", "", out)
    return re.sub(r"(?m)#.*$", "", out)


def _func_body(src: str, name: str) -> str:
    """按缩进截取顶层函数体。

    🔴 两个已踩过的坑（memory 已登记）：

    1. 缩进正则用 ``[ \\t]*`` 不用 ``\\s*`` —— 后者在 ``re.M`` 下含换行，会从前面的空行
       开始匹配，``indent`` 被算成换行数。
    2. **多行签名必须先用圆括号配对跳过参数列表** —— ``) -> dict[str, float]:`` 那一行
       缩进为 0，按「缩进 <= def 的缩进即结束」会让函数体截成**只有签名首行**，
       于是「函数体内含某调用」这类断言恒假（本守卫首轮即因此打红 2 条）。
    """
    m = re.search(rf"(?m)^([ \t]*)def {re.escape(name)}\s*\(", src)
    assert m, f"未找到函数 {name}（判据失效）"
    indent = len(m.group(1))
    tail = src[m.start() :]
    # 圆括号配对跳过参数列表，再找签名结束的冒号
    depth = 0
    i = tail.index("(")
    while i < len(tail):
        ch = tail[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    colon = tail.index(":", i)
    lines = tail[colon + 1 :].splitlines()
    body: list[str] = []
    for line in lines:
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        body.append(line)
    assert body, f"函数 {name} 体截取为空（判据失效）"
    return "\n".join(body)


def test_func_body_helper_handles_multiline_signature():
    """反向自检：多行签名 + 返回类型注解的函数体必须被完整截出。"""
    fixture = (
        "def foo(\n"
        "    a: int,\n"
        "    b,\n"
        ") -> dict[str, float]:\n"
        "    marker_inside_body()\n"
        "    return {}\n"
        "\n"
        "def bar():\n"
        "    neighbor_must_not_leak()\n"
    )
    body = _func_body(fixture, "foo")
    assert "marker_inside_body" in body
    assert "neighbor_must_not_leak" not in body


# ─────────────────────────────────────────────────────────────────────────────
# 真实数据形态的替身（逐字取自 c8621493 / 2025）
# ─────────────────────────────────────────────────────────────────────────────

_REAL_ROWS = [
    {
        "account_code": "2651",
        "account_name": "租赁负债",
        "opening_balance": None,
        "closing_balance": 94219.84,
        "debit_amount": 0.0,
        "credit_amount": 94219.84,
        "closing_direction": "credit",
        "opening_direction": "credit",
    },
    {
        "account_code": "2651.01",
        "account_name": "租赁负债_租赁付款额",
        "opening_balance": None,
        "closing_balance": 98176.48,
        "debit_amount": 0.0,
        "credit_amount": 98176.48,
        "closing_direction": "credit",
        "opening_direction": "credit",
    },
    {
        "account_code": "2651.02",
        "account_name": "租赁负债_未确认融资费用",
        "opening_balance": None,
        "closing_balance": 3956.64,
        "debit_amount": 3956.64,
        "credit_amount": 0.0,
        "closing_direction": "debit",
        "opening_direction": "debit",
    },
    {
        "account_code": "2651.99",
        "account_name": "租赁负债_一年内到期的租赁负债",
        "opening_balance": None,
        "closing_balance": None,
        "debit_amount": None,
        "credit_amount": None,
        "closing_direction": "credit",
        "opening_direction": "credit",
    },
]

#: 父额（真源判据）
_PARENT_CLOSING = 94219.84
#: 裸求和（旧实现的错值）
_NAIVE_SUM = 102133.12


def _slot(codes, standard_codes, *, found=True):
    return SimpleNamespace(
        found=found, codes=list(codes), standard_codes=list(standard_codes)
    )


def _accounts(slots: dict):
    return SimpleNamespace(slots=slots)


class TestNaiveSumIsWrongOnRealData:
    """反向自检：旧实现（裸求和）在真实数据上确实产出错值 —— 证明扫描面非空。"""

    def test_naive_aggregate_leaves_overstates_by_twice_contra(self):
        leaves = select_leaves(to_leaf_rows(_REAL_ROWS))
        agg = aggregate_leaves(leaves, ["2651"])
        assert abs(agg["closing"] - _NAIVE_SUM) < 0.01, (
            "替身数据未复现旧口径错值（应为 %.2f，实得 %.2f）" % (_NAIVE_SUM, agg["closing"])
        )
        assert abs(agg["closing"] - _PARENT_CLOSING) > 7000.0, "裸求和竟与父额相符，替身失真"

    def test_gap_equals_twice_the_contra_leaf(self):
        gap = _NAIVE_SUM - _PARENT_CLOSING
        assert abs(gap - 2 * 3956.64) < 0.01, "差额不等于 2 倍 contra 叶子额，判据依据不成立"


class TestBuildH9TbValuesUsesDirectionalResolution:
    """`build_h9_tb_values` 必须与父额勾稽成立。"""

    def test_gross_closing_equals_parent(self):
        accounts = _accounts({"gross": _slot(["2651"], ["2601"])})
        out = build_h9_tb_values(accounts, _REAL_ROWS, [])
        got = out["lease_liability_unadjusted_closing"]
        assert abs(got - _PARENT_CLOSING) < 0.01, (
            "H9 gross 期末应为父额 %.2f，实得 %.2f（疑似退回裸 aggregate_leaves）"
            % (_PARENT_CLOSING, got)
        )
        assert abs(got - _NAIVE_SUM) > 7000.0, "取到了裸求和错值"

    def test_legacy_alias_carries_same_value(self):
        accounts = _accounts({"gross": _slot(["2651"], ["2601"])})
        out = build_h9_tb_values(accounts, _REAL_ROWS, [])
        assert out["lease_2205_closing"] == out["lease_liability_unadjusted_closing"]

    def test_slot_not_found_produces_no_keys(self):
        accounts = _accounts({"gross": _slot([], [], found=False)})
        out = build_h9_tb_values(accounts, _REAL_ROWS, [])
        assert not any(k.startswith("lease_liability") for k in out), "found=False 仍产出键"

    def test_source_uses_resolve_leaf_totals_not_bare_aggregate(self):
        src = _strip_comments(_H9_RENDER.read_text(encoding="utf-8"))
        body = _func_body(src, "build_h9_tb_values")
        assert "resolve_leaf_totals" in body, "build_h9_tb_values 未使用 resolve_leaf_totals"
        assert "aggregate_leaves" not in body, (
            "build_h9_tb_values 仍在使用裸 aggregate_leaves（忽略 closing_direction）"
        )


class TestParentCheckFallsBackToDirectional:
    """`build_parent_check` 的方向回退：只在裸求和不平时启用。"""

    def test_gross_slot_becomes_consistent(self):
        accounts = _accounts(
            {
                "gross": _slot(["2651"], ["2601"]),
                "unearned_finance": _slot(["2651.02"], ["2602"]),
            }
        )
        pc = build_parent_check(accounts, _REAL_ROWS, [], ["gross", "unearned_finance"])
        gross = pc["gross"]
        assert abs(gross["leaf_sum"] - _PARENT_CLOSING) < 0.01
        assert abs(gross["diff_parent"]) < 0.01, "diff_parent 未归零"
        assert gross["consistent"] is True
        assert gross["convention"] == CONVENTION_DIRECTIONAL, (
            "gross 槽应识别为方向约定，实得 %r" % gross["convention"]
        )

    def test_slot_without_contra_stays_as_stored(self):
        """零回归证据：本就已平的槽必须仍走原样求和。"""
        accounts = _accounts({"unearned_finance": _slot(["2651.02"], ["2602"])})
        pc = build_parent_check(accounts, _REAL_ROWS, [], ["unearned_finance"])
        slot = pc["unearned_finance"]
        assert slot["convention"] == CONVENTION_AS_STORED, (
            "无 contra 子科目的槽被误判为方向约定 ⇒ 存在回归风险"
        )
        assert abs(slot["leaf_sum"] - 3956.64) < 0.01

    def test_directional_not_used_when_it_does_not_reconcile(self):
        """方向约定也不平时不得采用 —— 差额必须如实暴露。"""
        rows = [
            dict(_REAL_ROWS[0], closing_balance=1.0),  # 父额篡改成 1.00
            _REAL_ROWS[1],
            _REAL_ROWS[2],
            _REAL_ROWS[3],
        ]
        accounts = _accounts({"gross": _slot(["2651"], ["2601"])})
        pc = build_parent_check(accounts, rows, [], ["gross"])
        slot = pc["gross"]
        assert slot["convention"] == CONVENTION_AS_STORED, (
            "方向约定同样不平时不得采用（应保留裸求和并暴露差额）"
        )
        assert abs(slot["leaf_sum"] - _NAIVE_SUM) < 0.01
        assert slot["consistent"] is False

    def test_occurrence_mode_untouched(self):
        """损益类（`occurrence=True`）不走方向回退 —— 发生额无方向语义。"""
        accounts = _accounts({"gross": _slot(["2651"], ["2601"])})
        pc = build_parent_check(accounts, _REAL_ROWS, [], ["gross"], occurrence=True)
        assert pc["gross"]["convention"] == CONVENTION_AS_STORED

    def test_parent_missing_keeps_as_stored(self):
        """父行缺失（无参照物）时不做无依据的翻转。"""
        rows = [_REAL_ROWS[1], _REAL_ROWS[2], _REAL_ROWS[3]]  # 去掉父行
        accounts = _accounts({"gross": _slot(["2651"], ["2601"])})
        pc = build_parent_check(accounts, rows, [], ["gross"])
        slot = pc["gross"]
        assert slot["parent"] == 0.0
        assert slot["convention"] == CONVENTION_AS_STORED

    def test_source_guards_the_fallback_condition(self):
        """源码级：方向回退必须**带条件**（不得无条件改口径）。"""
        src = _strip_comments(_PARENT_CHECK.read_text(encoding="utf-8"))
        body = _func_body(src, "build_parent_check")
        assert "_directional_leaf_sum" in body, "未接入方向回退"
        assert re.search(
            r"if\s+not\s+occurrence\s+and\s+parent\s*!=\s*0\.0\s+and\s+abs\(\s*leaf_sum\s*-\s*parent\s*\)\s*>\s*TOLERANCE\s*:",
            body,
        ), "方向回退的门控条件形态不符（应仅在裸求和不平时尝试）"


class TestConventionKeyExposed:
    """`convention` 必须下发给前端 —— 审计 UI 需要逻辑追溯能力。"""

    @pytest.mark.parametrize("slot_key", ["gross", "unearned_finance"])
    def test_every_slot_carries_convention(self, slot_key):
        accounts = _accounts(
            {
                "gross": _slot(["2651"], ["2601"]),
                "unearned_finance": _slot(["2651.02"], ["2602"]),
            }
        )
        pc = build_parent_check(accounts, _REAL_ROWS, [], ["gross", "unearned_finance"])
        assert "convention" in pc[slot_key]
        assert pc[slot_key]["convention"] in (
            CONVENTION_AS_STORED,
            CONVENTION_DIRECTIONAL,
        )
