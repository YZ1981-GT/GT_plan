"""K 循环取数装配守卫（Task 8 / Task 9）—— 三口径自检 + K6 审定预填。

判据形态说明（为什么不用 grep）：

平台既有教训是「grep 式守卫只查字符串存在」—— 把 `parent_check` 的调用删了、
改成 `if False:`、或换个名字残留在注释里，字符串仍在、守卫仍绿。故本文件的判据是：

- **纯函数真跑**：给共享适配器喂合成 `tb_balance` 行，断言三口径的**数值**与
  三态语义（`found=False` 不产键）；
- **真调 render 的纯函数部分**：K6 的 `build_adjudication_prefill` /
  `build_source_codes` 直接调，断言符号与 `empty_reason` 分层；
- **源码判据只用于「不得再抄一份」这类结构约束**，且先 `_strip_py_comments()`
  并配「剥注释确实生效」的反向自检。

每条守卫都配了反向自检（复现旧缺陷形态必打红），见各 `test_*_self_check`。

spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
      Requirements 4.1~4.6 / Property 12, 13, 14, 15
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.routers.wp_render_strategies import _k6_held_for_sale as k6mod
from app.services.four_table.k_cycle_specs import (
    EMPTY_REASON_NO_ACCOUNT,
    EMPTY_REASON_NOT_IN_PROJECT,
    liability_spec_for,
)
from app.services.four_table.leaf_aggregation import LeafRow
from app.services.four_table.parent_check import (
    SLOT_GROSS,
    SLOT_PROVISION,
    TOLERANCE,
    build_report_line_parent_check,
)
from app.services.four_table.report_line_accounts import ReportLineAccounts

_STRATEGY_DIR = Path(__file__).resolve().parents[2] / "app/routers/wp_render_strategies"

#: Task 9 的四个作业面 + 已有 parent_check 的三个（K3/K5/K7 走本地两口径版，见
#: `test_k357_local_parent_check_is_registered_divergence`）
_TASK9_TARGETS = {
    "K1": "_k1_other_receivables.py",
    "K2": "_k2_other_current_assets.py",
    "K4": "_k4_other_current_liabilities.py",
    "K6": "_k6_held_for_sale.py",
}
_ALREADY_HAD_LOCAL = {
    "K3": "_k3_other_payables.py",
    "K5": "_k5_provisions.py",
    "K7": "_k7_deferred_income.py",
}


# ─────────────────────────────────────────────────────────────────────────────
# 工具
# ─────────────────────────────────────────────────────────────────────────────


def _strip_py_comments(src: str) -> str:
    """剥 docstring 与行注释（防注释里的字面量冒充实现）。"""
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    return re.sub(r"(?m)#.*$", "", src)


def _row(
    code: str,
    closing: float,
    *,
    name: str | None = None,
    direction: str = "",
    opening: float = 0.0,
) -> LeafRow:
    """构造合成 `tb_balance` 行。

    🔴 ``name`` 用 ``None`` 表示「不关心、给个默认名」，用 ``""`` 表示**真的空名**。
    最初写成 ``name: str = ""`` + ``name or f"科目{code}"``，结果 ``name=""`` 被悄悄
    替换成默认名 —— 「跳过无名行」那条守卫因此测不到真空名（夹具缺陷，非生产缺陷）。
    """
    return LeafRow(
        account_code=code,
        account_name=f"科目{code}" if name is None else name,
        opening=opening,
        closing=closing,
        direction=direction,
    )


def _accounts(
    gross: tuple[str, ...] = (),
    provision: tuple[str, ...] = (),
    *,
    gross_standard: tuple[str, ...] | None = None,
    provision_standard: tuple[str, ...] | None = None,
    provision_exact: bool = True,
) -> ReportLineAccounts:
    return ReportLineAccounts(
        gross=list(gross),
        provision=list(provision),
        gross_standard=list(gross_standard if gross_standard is not None else gross),
        provision_standard=list(
            provision_standard if provision_standard is not None else provision
        ),
        provision_exact=provision_exact,
    )


def _trial(**by_code: float) -> list[dict]:
    return [
        {"standard_account_code": c, "unadjusted_amount": v} for c, v in by_code.items()
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Property 13：三态语义（槽 found=False 时不产生该键，不得填 0）
# ─────────────────────────────────────────────────────────────────────────────


def test_slot_without_codes_produces_no_key():
    """无科目的槽**不产生该键** —— 不得填 0（0 会被当成「余额为 0」）。"""
    acc = _accounts(gross=("1221",))  # 只有原值侧，无备抵
    rows = [_row("1221", 100.0), _row("1221.01", 100.0)]
    out = build_report_line_parent_check(acc, rows, _trial())
    assert SLOT_GROSS in out, "原值侧有科目却没产生键"
    assert SLOT_PROVISION not in out, (
        "备抵侧无科目时**不得**产生该键 —— 填 0 会让前端把「没这科目」"
        f"显示成「余额为 0」（实际输出 {out.get(SLOT_PROVISION)!r}）"
    )


def test_both_sides_absent_produces_empty_dict():
    """两侧都无科目 ⇒ 返回空 dict（K4 宁缺勿造的真实形态）。"""
    out = build_report_line_parent_check(_accounts(), [_row("1221", 5.0)], _trial())
    assert out == {}, f"两侧无科目应返回空 dict，实际 {out!r}"


def test_three_state_self_check():
    """反向自检：把空码换成真码后**必须**产生该键（否则上面两条是空转）。"""
    acc = _accounts(gross=("1221",), provision=("1231.03",))
    rows = [_row("1221", 100.0), _row("1231.03", -20.0)]
    out = build_report_line_parent_check(acc, rows, _trial())
    assert SLOT_PROVISION in out, (
        "备抵侧给了真码却没产生键 —— 说明 `found` 判据坏了，"
        "前两条「不产生该键」的断言会因此恒真（空转）"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Property 12 / 14：三口径数值与 contra 方向
# ─────────────────────────────────────────────────────────────────────────────


def test_three_calibres_are_all_reported():
    """三个口径必须并列下发（不静默取其一）。"""
    acc = _accounts(gross=("1221",))
    rows = [_row("1221", 300.0), _row("1221.01", 300.0)]
    got = build_report_line_parent_check(acc, rows, _trial(**{"1221": 300.0}))[SLOT_GROSS]
    for key in ("leaf_sum", "parent", "trial_balance", "diff_parent", "diff_trial"):
        assert key in got, f"缺口径 {key}：三口径退化就查不出 recalc 父子双算"
    assert got["leaf_sum"] == pytest.approx(300.0)
    assert got["parent"] == pytest.approx(300.0)
    assert got["trial_balance"] == pytest.approx(300.0)
    assert got["consistent"] is True


def test_trial_only_discrepancy_is_exposed():
    """**只有 trial 侧**不一致时必须暴露 —— 本地两口径版查不出的那一类。

    形态取自 2026-08-12 K1 真实库实证：``leaf == parent`` 完全成立，而
    ``trial_balance`` 是叶子和的约 2.9 倍（父子双算 / recalc 陈旧）。
    """
    acc = _accounts(gross=("1221",))
    rows = [_row("1221", 88_596_839.09), _row("1221.01", 88_596_839.09)]
    got = build_report_line_parent_check(
        acc, rows, _trial(**{"1221": 258_028_708.86})
    )[SLOT_GROSS]
    assert abs(got["diff_parent"]) <= TOLERANCE, "叶子和与父额本应相等"
    assert got["diff_trial"] == pytest.approx(-169_431_869.77, abs=0.01)
    assert got["consistent"] is False, (
        "leaf==parent 而 trial 差 1.69 亿时必须报不一致 —— 只比对前两个口径会漏"
    )


def test_contra_family_reconciles_by_direction():
    """Property 14：族内 contra 子科目按方向聚合后与父额勾稽成立。

    形态取自 H9 实测：租赁付款额 credit + 未确认融资费用 debit，
    裸求和不平、按方向定符号才平。
    """
    rows = [
        _row("2651", 94_219.84, direction="credit"),
        _row("2651.01", 98_176.48, direction="credit"),
        _row("2651.02", 3_956.64, direction="debit"),
    ]
    got = build_report_line_parent_check(_accounts(gross=("2651",)), rows, _trial())[
        SLOT_GROSS
    ]
    assert abs(got["diff_parent"]) <= TOLERANCE, (
        "contra 族未走方向自校验：裸求和 102,133.12 vs 父额 94,219.84 "
        f"（实际 diff_parent={got['diff_parent']}）"
    )
    assert got["convention"] == "directional", (
        f"应选中「方向定符号」约定，实际 {got['convention']!r}"
    )


def test_contra_self_check_bare_sum_would_fail():
    """反向自检：同一份数据裸求和**必然**不平（证明上一条不是恒真）。"""
    from app.services.four_table.leaf_aggregation import aggregate_leaves, select_leaves

    rows = [
        _row("2651", 94_219.84, direction="credit"),
        _row("2651.01", 98_176.48, direction="credit"),
        _row("2651.02", 3_956.64, direction="debit"),
    ]
    bare = aggregate_leaves(select_leaves(rows), ["2651"])["closing"]
    assert abs(bare - 94_219.84) > TOLERANCE, (
        "裸求和竟然与父额相等 —— 那么上一条 contra 断言无法证明方向自校验生效"
    )


def test_wide_prefix_provision_is_flagged():
    """备抵反解退化为宽前缀时必须标 `wide_prefix_scope`。

    K1 的 `1231-03` 退化成 `1231` 后，三口径覆盖的是 `1231` **全族**
    （含 D1/D2 的坏账）—— `consistent=True` 不代表本循环备抵已勾稽。
    """
    acc = _accounts(gross=("1221",), provision=("1231",), provision_exact=False)
    rows = [_row("1221", 100.0), _row("1231", -30.0), _row("1231.02", -10.0), _row("1231.03", -20.0)]
    out = build_report_line_parent_check(acc, rows, _trial())
    assert out[SLOT_PROVISION].get("wide_prefix_scope") is True, (
        "宽前缀未标记 —— 审计师会把「1231 全族自洽」误读成「本循环备抵已勾稽」"
    )


def test_exact_provision_is_not_flagged():
    """反向自检：精确反解时**不得**标记（否则标记恒真、失去信息量）。"""
    acc = _accounts(gross=("1221",), provision=("1231.03",), provision_exact=True)
    rows = [_row("1221", 100.0), _row("1231.03", -20.0)]
    out = build_report_line_parent_check(acc, rows, _trial())
    assert "wide_prefix_scope" not in out[SLOT_PROVISION], (
        "精确反解也标 wide_prefix_scope ⇒ 该标记恒真、等于没标"
    )


def test_parent_row_missing_degrades_visibly():
    """只喂叶子（不含父行）时 `parent` 恒 0 —— 钉死「必须传全量行」这条约束。

    这条不是要求这种用法，而是把「传错入参会静默退化成两口径」变成可见事实：
    render 若把 `fetch_tb_balance_all` 换回 `fetch_tb_balance_leaves`，症状就是这样。
    """
    acc = _accounts(gross=("1221",))
    leaves_only = [_row("1221.01", 300.0)]  # 缺父行 1221
    got = build_report_line_parent_check(acc, leaves_only, _trial())[SLOT_GROSS]
    assert got["parent"] == pytest.approx(0.0)
    assert got["consistent"] is True, (
        "parent 缺失时共享件按「该侧不参与判定」处理 ⇒ 静默退化成两口径。"
        "这正是 render 必须传全量行的原因"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 9：四个 render 真的接了共享件（结构约束）
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("wp,fn", sorted(_TASK9_TARGETS.items()))
def test_render_wires_shared_parent_check(wp: str, fn: str):
    """四个 render 必须**调用**共享适配器并把结果放进返回字典。"""
    src = _strip_py_comments((_STRATEGY_DIR / fn).read_text(encoding="utf-8"))
    assert re.search(r"build_report_line_parent_check\s*\(", src), (
        f"{wp} 未**调用** build_report_line_parent_check（只 import 不算）"
    )
    assert re.search(r'"parent_check"\s*:', src), f"{wp} 返回字典缺 parent_check 键"


def _parent_check_rows_arg(src: str) -> tuple[str, ast.AST | None]:
    """AST 取「传给 `build_report_line_parent_check` 的行集实参」及其赋值右侧。

    🔴 为什么必须用 AST 而不是字符串判据（2026-08-12 变异检验实测）：
    原守卫只断言源码里同时出现 `fetch_tb_balance_all(` 与 `select_leaves(`。
    把 ``all_rows = await fetch_tb_balance_all(ctx)`` 变异成
    ``all_rows = select_leaves(await fetch_tb_balance_all(ctx))`` 后 —— 三口径的
    ``parent`` 侧当场退化成恒 0，而两个字符串都还在 ⇒ **守卫照样全绿**（GREEN 态）。
    故判据必须落到「那个实参到底是谁的返回值」这个结构事实上。

    Returns:
        ``(实参变量名, 该变量赋值语句的右侧 AST)``；取不到时右侧为 ``None``。
    """
    tree = ast.parse(src)
    arg_name = ""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
        if name != "build_report_line_parent_check":
            continue
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Name):
            arg_name = node.args[1].id
            break
    if not arg_name:
        return "", None
    rhs: ast.AST | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == arg_name:
                    # 取**最后**一次赋值（render 里常先 `all_rows = []` 再条件赋值）
                    if not isinstance(node.value, (ast.List, ast.Tuple)):
                        rhs = node.value
        elif isinstance(node, ast.AnnAssign):
            tgt = node.target
            if isinstance(tgt, ast.Name) and tgt.id == arg_name and node.value is not None:
                if not isinstance(node.value, (ast.List, ast.Tuple)):
                    rhs = node.value
    return arg_name, rhs


@pytest.mark.parametrize("wp,fn", sorted(_TASK9_TARGETS.items()))
def test_render_fetches_all_rows_not_leaves(wp: str, fn: str):
    """必须把**全量**行传给三口径自检 —— 传叶子会让 `parent` 恒 0 且不打红。"""
    src = _strip_py_comments((_STRATEGY_DIR / fn).read_text(encoding="utf-8"))
    assert re.search(r"select_leaves\s*\(", src), (
        f"{wp} 未由全量行派生叶子 ⇒ tb_values 口径会变（零回归被破坏）"
    )

    arg_name, rhs = _parent_check_rows_arg(src)
    assert arg_name, f"{wp}: 未找到 build_report_line_parent_check 的行集实参"
    assert rhs is not None, f"{wp}: 找不到 {arg_name} 的赋值语句"

    calls = {
        (n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", ""))
        for n in ast.walk(rhs)
        if isinstance(n, ast.Call)
    }
    assert any("fetch_tb_balance_all" in c for c in calls), (
        f"{wp}: 传给三口径自检的 {arg_name} 不是 fetch_tb_balance_all 的结果"
        f"（实际调用链 {sorted(calls)}）—— 预筛叶子会让 parent 口径恒 0"
    )
    assert "select_leaves" not in calls, (
        f"{wp}: {arg_name} 被 select_leaves 包过一层 ⇒ 父科目行被筛掉、"
        "`parent` 恒 0，共享件会「该侧不参与判定」静默退化成两口径"
    )


@pytest.mark.parametrize("wp,fn", sorted(_TASK9_TARGETS.items()))
def test_task9_targets_have_no_local_parent_check(wp: str, fn: str):
    """四个作业面**不得**自写本地 `build_parent_check`（禁抄第五份）。"""
    src = (_STRATEGY_DIR / fn).read_text(encoding="utf-8")
    assert not re.search(r"^def build_parent_check\(", src, re.M), (
        f"{wp} 自写了本地 build_parent_check —— 判据必须走 four_table 共享件"
    )


def test_strip_comments_actually_strips():
    """反向自检：剥注释真的生效（否则上面的源码判据会被注释里的字面量骗过）。"""
    sample = '\ndef f():\n    """build_report_line_parent_check( 在 docstring 里"""\n    # build_report_line_parent_check( 在行注释里\n    return 1\n'
    stripped = _strip_py_comments(sample)
    assert "build_report_line_parent_check" not in stripped, (
        "剥注释未生效 ⇒ 源码判据会把注释当实现"
    )
    assert "return 1" in stripped, "剥注释把代码也剥掉了"


def test_k357_local_parent_check_is_registered_divergence():
    """K3/K5/K7 仍是**本地两口径**版 —— 登记为已知分叉，不静默。

    它们早于本 spec 存在、输出扁平 `{prefix, leaf_sum, parent, diff}`（无 trial 侧）。
    实测无任何测试/前端消费方锁死该形状，故可迁移；但迁移不在 Task 9 作业面内，
    此处显式登记，避免下个会话以为「K 循环已全部走共享件」。
    """
    still_local = []
    for wp, fn in sorted(_ALREADY_HAD_LOCAL.items()):
        src = (_STRATEGY_DIR / fn).read_text(encoding="utf-8")
        if re.search(r"^def build_parent_check\(", src, re.M):
            still_local.append(wp)
    assert still_local == ["K3", "K5", "K7"], (
        "K3/K5/K7 的本地 parent_check 状态变了。若已迁移到共享件，"
        "请把它们加进 _TASK9_TARGETS 并删除本条登记；"
        f"当前实际 {still_local}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 8：K6 审定预填与 empty_reason 分层
# ─────────────────────────────────────────────────────────────────────────────


def test_k6_prefill_keeps_asset_sign_and_abs_liability():
    """资产侧保留符号、负债侧取绝对值（与 `build_tb_values` 同口径）。"""
    leaves = [
        _row("1481", 500.0, name="持有待售资产"),
        _row("2245", -300.0, name="持有待售负债"),
    ]
    rows = k6mod.build_adjudication_prefill(
        leaves, _accounts(gross=("1481",)), _accounts(gross=("2245",))
    )
    by_side = {r["side"]: r for r in rows}
    assert by_side["asset"]["closing_balance"] == pytest.approx(500.0)
    assert by_side["liability"]["closing_balance"] == pytest.approx(300.0), (
        "负债侧未取绝对值 —— 审定表按正数列示，负号会让合计对不上"
    )


def test_k6_prefill_skips_zero_and_nameless():
    """宁缺勿造：双零行与无名行跳过。"""
    leaves = [
        _row("1481", 0.0, name="持有待售资产", opening=0.0),
        _row("1481.02", 700.0, name=""),
        _row("1481.03", 900.0, name="真有名字"),
    ]
    rows = k6mod.build_adjudication_prefill(
        leaves, _accounts(gross=("1481",)), _accounts()
    )
    assert [r["code"] for r in rows] == ["1481.03"], (
        f"应只留有名且非零的叶子，实际 {[r['code'] for r in rows]}"
    )


def test_k6_prefill_empty_when_no_account():
    """解析不出科目 ⇒ 返 []（不造「其他」兜底行）。"""
    assert (
        k6mod.build_adjudication_prefill(
            [_row("1481", 100.0, name="x")], _accounts(), _accounts()
        )
        == []
    )


def test_k6_prefill_sorts_asset_first_then_desc():
    """资产侧在前，同侧按期末绝对值降序。"""
    leaves = [
        _row("1481.01", 100.0, name="a"),
        _row("1481.02", 900.0, name="b"),
        _row("2245.01", -500.0, name="c"),
    ]
    rows = k6mod.build_adjudication_prefill(
        leaves, _accounts(gross=("1481",)), _accounts(gross=("2245",))
    )
    assert [r["code"] for r in rows] == ["1481.02", "1481.01", "2245.01"]


def test_k6_empty_reason_is_not_in_project_when_no_leaf_hit():
    """Requirement 4.6：本项目无该科目 ⇒ NOT_IN_PROJECT（不是 NO_ACCOUNT、不是 None）。"""
    got = k6mod.build_source_codes(
        _accounts(gross=("1481",)), _accounts(gross=("2245",)), leaf_hits=0
    )
    assert got["empty_reason"] == EMPTY_REASON_NOT_IN_PROJECT
    assert got["empty_reason"] != EMPTY_REASON_NO_ACCOUNT, (
        "K6 的 has_account 已实证为 True ⇒ 不能再报「标准科目表无此科目」"
    )


def test_k6_empty_reason_none_when_leaf_hit():
    """有命中叶子 ⇒ empty_reason 为 None（余额确为 0 时前端仍显示 0.00）。"""
    got = k6mod.build_source_codes(
        _accounts(gross=("1481",)), _accounts(gross=("2245",)), leaf_hits=3
    )
    assert got["empty_reason"] is None


def test_k6_empty_reason_self_check_old_form_would_fail():
    """反向自检：旧判据（按 `accounts.gross` 非空）会让 empty_reason 永不触发。

    实测 8/8 项目的 K6 负债侧都能解析出 `['2245']`（`account_mapping` 无反解记录时
    resolver 把标准码本身当前缀返回）⇒ 旧判据下 `has_any` 恒真、说明文案永不出现。
    """
    acc_a = _accounts(gross=("1481",))
    acc_l = _accounts(gross=("2245",))
    old_has_any = bool(acc_a.gross or acc_l.gross)
    assert old_has_any is True, "旧判据前提变了，请重新评估本条"
    new = k6mod.build_source_codes(acc_a, acc_l, leaf_hits=0)
    assert new["empty_reason"] is not None, (
        "新判据必须在零叶子命中时给出说明 —— 否则用户只看到 0.00 且无从区分"
    )


def test_k6_uses_declared_liability_spec_not_local_copy():
    """K6 必须用声明真源 `liability_spec_for`，不得自写负债侧规格。"""
    src = _strip_py_comments((_STRATEGY_DIR / "_k6_held_for_sale.py").read_text(encoding="utf-8"))
    assert re.search(r"liability_spec_for\s*\(", src), (
        "K6 未调用 liability_spec_for —— 声明真源会退化成零消费方死代码"
    )
    assert not re.search(r"^def _liability_spec\(", src, re.M), (
        "K6 又自写了 _liability_spec：双真源，且本地版历史上缺 "
        "is_liability/gross_direction/兜底码"
    )


def test_declared_liability_spec_carries_direction_and_fallback():
    """声明真源必须带方向与兜底码（本地版当年缺的正是这三项）。"""
    spec = liability_spec_for(["soe_standalone"])
    assert spec.is_liability is True
    assert spec.gross_direction == "credit"
    assert "2245" in spec.fallback_gross, (
        f"负债侧兜底码丢失（实际 {spec.fallback_gross}）—— "
        "report_config 缺公式的项目会取不到数"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Property 12：余额类循环输出两个键
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "wp,fn", sorted({**_TASK9_TARGETS, **_ALREADY_HAD_LOCAL}.items())
)
def test_balance_cycles_output_both_keys(wp: str, fn: str):
    """七个余额类循环的 render 返回字典都要含 adjudication_prefill 与 parent_check。"""
    src = _strip_py_comments((_STRATEGY_DIR / fn).read_text(encoding="utf-8"))
    for key in ("adjudication_prefill", "parent_check"):
        assert re.search(rf'"{key}"\s*:', src), f"{wp} 返回字典缺 {key}"
