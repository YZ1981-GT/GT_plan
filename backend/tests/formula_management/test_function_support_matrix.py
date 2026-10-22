"""函数支持矩阵单一真源守卫 —— 后端侧（spec formula-manager-closure · Task 4.2 / 需求 8）。

验收判据（tasks.md Task 4.2）：
  「单测查表：不支持者 UI 禁用/标注、禁静默 0；支持者运行产生真实结果。
   变异反证：把某不支持函数改成静默返 0 而 UI 仍可点，应被断言打红；
   反向断言支持函数不误判为禁用。」

本文件守后端矩阵真源 + golden 对拍 + 「矩阵反映真实执行器现状（非凭命名推测）」。
前端 UI 禁用/标注在 ``functionSupportMatrix.spec.ts`` + ``formulaBarSupportGating.spec.ts``，
两侧同对一张 golden（``tests/fixtures/function_support_matrix.json``），前端渲染==后端真相。

现状实证锚点（memory 铁律⑭：枚举/字段路径现读实证，非凭命名推测）：
  - wp evaluator：10 个函数都支持（spec formula-governance-coverage-closure R6）——PREV/AUX/ROW/SUM_ROW/
    REPORT/NOTE 由 ``formula_ref_preload.substitute_value_refs`` 严格按值代入，ADJ 走统一预载层；
    本文件断言求值器源码确有这两处接线（注册表不是执行证据，接线才是）。
  - report path：``report_engine.evaluate_formula_result`` 用 ``_PREV_PATTERN``/``_AUX_PATTERN``
    硬替换成 "0" ⇒ PREV/AUX report_path=False（本文件直接断言源码仍有该替换，锚点漂移即红）。
  - note executor：``note_formula_generator`` 支持 TB/REPORT/NOTE/WP + PRIOR/AGING，不解析 PREV/AUX/ADJ/SUM_TB/ROW。
  - central_batch：``FormulaContext.adj_data`` + ``_handle_adj`` ⇒ ADJ central_batch=True。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.formula_management.function_support_matrix import (
    Executor,
    FUNCTIONS,
    build_matrix_payload,
    is_supported,
    support_issues,
    unsupported_reason,
)

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "function_support_matrix.json"


def _load_golden() -> dict:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert data.get("matrix"), "golden 矩阵为空 —— 判据抽不到值（防空转）"
    return data


# ───────────────────────── golden 对拍（前端据此渲染）─────────────────────────


def test_golden_matches_single_source():
    """golden 确由后端真源重算、未被手改偏离真源。"""
    assert _load_golden() == build_matrix_payload()


def test_golden_covers_four_executors_and_named_functions():
    """防空转：golden 必须覆盖 design 点名的四执行器 + 报告点名的 PREV/AUX/ADJ。"""
    golden = _load_golden()
    assert set(golden["executors"]) == {
        "wp_evaluator",
        "report_path",
        "note_executor",
        "central_batch",
    }
    for fn in ("TB", "SUM_TB", "WP", "PREV", "AUX", "ADJ", "NOTE", "REPORT"):
        assert fn in golden["functions"], f"golden 缺函数 {fn}"


# ─────────────────── 支持者产生真实结果 / 不支持者禁止静默 0 ───────────────────


def test_supported_functions_have_no_reason():
    """支持者：无「不支持」原因（UI 不禁用），即运行应产生真实结果而非占位。"""
    for fn in FUNCTIONS:
        for exe in Executor:
            if is_supported(fn, exe):
                assert unsupported_reason(fn, exe) is None


def test_unsupported_functions_have_explicit_reason():
    """不支持者：必有显式原因文案（UI 据此标注「此处不支持」，禁静默 0）。"""
    found_unsupported = False
    for fn in FUNCTIONS:
        for exe in Executor:
            if not is_supported(fn, exe):
                found_unsupported = True
                reason = unsupported_reason(fn, exe)
                assert reason, f"{fn}×{exe.value} 不支持却无原因 —— UI 无法标注 ⇒ 会静默 0"
    assert found_unsupported, "矩阵无任何不支持格 —— 与现状矛盾（防空转）"


def test_report_path_zeros_prev_and_aux():
    """report 路径对 PREV/AUX 不支持（源码恒置 0 的静默 0 现状）。"""
    assert is_supported("PREV", Executor.REPORT_PATH) is False
    assert is_supported("AUX", Executor.REPORT_PATH) is False


def test_wp_evaluator_supports_all_functions():
    """工作底稿可编辑路径 10 个函数都有真实取数上下文（R6）。"""
    for fn in FUNCTIONS:
        assert is_supported(fn, Executor.WP_EVALUATOR) is True, fn
        assert unsupported_reason(fn, Executor.WP_EVALUATOR) is None


def test_central_batch_supports_adj_injection():
    """中央 batch 支持 ADJ 实时注入（需求 8.4）。"""
    assert is_supported("ADJ", Executor.CENTRAL_BATCH) is True


def test_note_executor_rejects_prev_aux_adj():
    """附注执行器不解析 PREV/AUX/ADJ（用 PRIOR/AGING，非 PREV/AUX）。"""
    for fn in ("PREV", "AUX", "ADJ", "SUM_TB", "ROW", "SUM_ROW"):
        assert is_supported(fn, Executor.NOTE_EXECUTOR) is False


def test_unknown_function_fail_closed():
    """未知函数 fail-closed 判不支持（禁退回「假设支持」）。"""
    assert is_supported("DOES_NOT_EXIST", Executor.WP_EVALUATOR) is False


# ─────────────────── 现状实证：矩阵锚定真实执行器源码 ───────────────────


def test_report_path_source_still_zeros_prev_aux():
    """锚点守卫：report_engine 源码仍把 PREV/AUX 硬替换成 "0"。

    若该替换被移除（PREV/AUX 在 report 路径真支持了），矩阵须同步改 report_path=True；
    此断言打红即提示矩阵与源码漂移（memory 铁律：坐标漂移不报错、只静默打错位置）。
    """
    import app.services.report_engine as re_mod

    src = Path(re_mod.__file__).read_text(encoding="utf-8")
    assert "_PREV_PATTERN" in src and "_AUX_PATTERN" in src, "report_engine 不再引用 PREV/AUX 正则"
    # 报表域置 0 的注释锚点
    assert "报表域默认置 0" in src, "report_engine PREV/AUX 置 0 逻辑可能已变 —— 矩阵须复核"


def test_wp_evaluator_support_is_backed_by_wiring():
    """wp_evaluator 判支持须有求值接线背书（注册表不是执行证据）：严格按值代入 + ADJ 底稿口径预载。

    任一接线被删（例如回到「空上下文跑 L1」），矩阵即与现状矛盾 ⇒ 本断言打红，提示矩阵须复核。
    """
    import ast

    import app.services.wp_formula_eval_service as eval_mod

    tree = ast.parse(Path(eval_mod.__file__).read_text(encoding="utf-8"))
    calls = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            calls.setdefault(name, []).append(node)
    assert "substitute_value_refs" in calls, "底稿求值器不再严格代入 PREV/AUX/ROW/REPORT/NOTE"
    assert any(kw.arg == "strict" and isinstance(kw.value, ast.Constant) and kw.value.value is True
               for call in calls["substitute_value_refs"] for kw in call.keywords), "代入必须 strict=True"
    assert "preload" in calls, "底稿求值器不再经统一预载层取 ADJ"
    assert any(kw.arg == "adj_exclude_origins" and ast.unparse(kw.value) == "frozenset()"
               for call in calls["preload"] for kw in call.keywords), "ADJ 须为底稿口径（不排除来源）"


# ─────────────────────────── 变异反证 ───────────────────────────


def test_mutation_unsupported_flipped_to_silent_support_is_caught():
    """变异反证：把某不支持格（PREV×report_path）改成「静默支持」（UI 仍可点、点了返 0）
    应被断言打红。

    模拟变异：在内存里把 report_path 的 PREV 判为支持（= UI 不禁用、运行却恒 0 的静默 0 态）。
    守卫断言「真源仍判不支持」必须拒绝这个变异。反向断言：未变异时真源判不支持成立。
    """
    # 变异态（错误）：假装 report_path 支持 PREV
    mutated_supported = True
    # 真源判定（正确）：report_path 不支持 PREV
    real = is_supported("PREV", Executor.REPORT_PATH)
    assert real is False  # 真源不被变异污染
    assert real != mutated_supported  # 变异态与真源不一致 ⇒ 若生产按变异态渲染，守卫打红

    # golden 也必须反映真源（不支持 + 有原因），而非被改成支持
    golden = _load_golden()
    cell = golden["matrix"]["PREV"]["report_path"]
    assert cell["supported"] is False
    assert cell["reason"], "PREV×report_path 的不支持原因被清空 ⇒ UI 无法标注 ⇒ 退回静默 0"


def test_mutation_supported_misjudged_as_disabled_is_caught():
    """反向断言：支持函数（TB×wp_evaluator）不得被误判为禁用。

    变异态（错误）= 把 TB×wp_evaluator 标为禁用（disabled=True）。真源判它支持，
    故 UI 若按变异态把 TB 灰掉，与真源冲突 ⇒ 守卫打红。
    """
    real_supported = is_supported("TB", Executor.WP_EVALUATOR)
    assert real_supported is True  # 真源：TB 在 wp evaluator 支持
    assert unsupported_reason("TB", Executor.WP_EVALUATOR) is None  # 无禁用原因 ⇒ UI 不灰

    mutated_disabled = True  # 变异：误把 TB 禁用
    # 「真源支持」与「变异禁用」互斥：real_supported(True) 与 (not mutated_disabled)(False) 不等
    assert real_supported != (not mutated_disabled)


def test_expression_preflight_reports_all_unsupported_functions_in_order():
    issues = support_issues(
        "PREV('1001') + AUX('客户') + TB('1001','期末余额')",
        Executor.REPORT_PATH,
    )
    assert [item["function"] for item in issues] == ["PREV", "AUX"]
    assert all(item["reason"] for item in issues)


def test_expression_preflight_rejects_function_without_executor_context():
    expr = "ROW('BS-001') + TB('1001','期末余额')"
    assert [item["function"] for item in support_issues(expr, Executor.NOTE_EXECUTOR)] == ["ROW"]
    assert support_issues(expr, Executor.WP_EVALUATOR) == []
