"""K 管理循环复盘修复 — Bug Condition Exploration Test.

Spec: .kiro/specs/k-admin-cycle-post-review-fix/
Property 1: Bug Condition — K 循环弹窗 UI 入口不可达 + 测试盲区
Validates: Requirements 1.1, 1.2, 1.3

CRITICAL — BUGFIX SPEC EXPLORATION TEST:
This test encodes the EXPECTED behavior. It MUST FAIL on the current (unfixed)
code — failure confirms the bug exists. After implementing the fix in Sprint 1
(P0 #1-4), all 4 assertions SHALL pass.

Bug Condition (from bugfix.md / design.md):
  - WorkpaperEditor.vue 中 ExpenseAnalysisDialog / ImpairmentSummaryDialog 未 wired
    （组件文件存在但无 toolbar 按钮 + visible ref + import）
  - 两个 Dialog 0 vitest 覆盖（同类 G/H/I/J Dialog 已有 .spec.ts）
  - prefill_engine 的 `=LEDGER_DETAIL('6601','1月','>=0')` 3-arg 签名从未在
    端到端 fixture 中被验证（K spec 实施时未补 e2e 测试）

Expected counterexamples on UNFIXED code:
  1. WorkpaperEditor.vue 不含 `expenseAnalysisDialogVisible` 字符串
  2. __tests__/ExpenseAnalysisDialog.spec.ts 不存在
  3. __tests__/ImpairmentSummaryDialog.spec.ts 不存在
  4. backend/tests/test_k_prefill_ledger_detail.py 不存在
"""
from __future__ import annotations

from pathlib import Path

import pytest


# --------------------------------------------------------------------------- #
# Path resolution
# --------------------------------------------------------------------------- #

# This test file lives at backend/tests/, repo root is two levels up.
REPO_ROOT = Path(__file__).resolve().parents[2]

WORKPAPER_EDITOR_VUE = (
    REPO_ROOT / "audit-platform" / "frontend" / "src" / "views" / "WorkpaperEditor.vue"
)
WORKPAPER_TESTS_DIR = (
    REPO_ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "__tests__"
)
BACKEND_TESTS_DIR = REPO_ROOT / "backend" / "tests"


# --------------------------------------------------------------------------- #
# Verification items
# --------------------------------------------------------------------------- #


def test_workpaper_editor_contains_expense_analysis_dialog_visible_ref() -> None:
    """验证项 1: WorkpaperEditor.vue 应包含 `expenseAnalysisDialogVisible` ref.

    Bug Condition: ExpenseAnalysisDialog 未 wired 到 WorkpaperEditor.vue，
    用户打开 K8/K9 底稿时无 toolbar 按钮触发入口（用户不可达）。

    Expected after fix (Sprint 1 task 3.1):
      WorkpaperEditor.vue 中存在 `expenseAnalysisDialogVisible` ref 声明，
      用于控制 ExpenseAnalysisDialog 的 visible 状态。
    """
    assert WORKPAPER_EDITOR_VUE.exists(), (
        f"WorkpaperEditor.vue 不存在: {WORKPAPER_EDITOR_VUE}"
    )
    content = WORKPAPER_EDITOR_VUE.read_text(encoding="utf-8")
    assert "expenseAnalysisDialogVisible" in content, (
        "Bug Condition 确认: WorkpaperEditor.vue 不含 `expenseAnalysisDialogVisible` ref. "
        "ExpenseAnalysisDialog 未 wired — K8/K9 底稿无费用分析 toolbar 入口（用户不可达）. "
        "修复方案: Sprint 1 task 3.1 在 WorkpaperEditor.vue 添加 import + visible ref + "
        "toolbar 按钮 + Dialog 组件 + @applied handler（参照 G 循环 FairValueTestDialog 模式）."
    )


def test_expense_analysis_dialog_spec_exists() -> None:
    """验证项 2: ExpenseAnalysisDialog.spec.ts 应存在于 components/workpaper/__tests__/.

    Bug Condition: ExpenseAnalysisDialog 0 vitest 覆盖（同类 FairValueTestDialog /
    DepreciationCalcDialog / PayrollCalcDialog 已有 .spec.ts）。

    Expected after fix (Sprint 1 task 3.2):
      ExpenseAnalysisDialog.spec.ts 存在并覆盖核心交互
      （mount / form 默认值 / isFormValid / buildRequestBody / onAnalyze API /
       onApplyToSheet emit applied / visible 重置）.
    """
    spec_file = WORKPAPER_TESTS_DIR / "ExpenseAnalysisDialog.spec.ts"
    assert spec_file.exists(), (
        f"Bug Condition 确认: {spec_file} 不存在. "
        "ExpenseAnalysisDialog 0 vitest 覆盖 — 与同类 G/H/I/J Dialog 已有 .spec.ts 不一致. "
        "修复方案: Sprint 1 task 3.2 创建 vitest 文件，参照 FairValueTestDialog.spec.ts 模式."
    )


def test_impairment_summary_dialog_spec_exists() -> None:
    """验证项 3: ImpairmentSummaryDialog.spec.ts 应存在于 components/workpaper/__tests__/.

    Bug Condition: ImpairmentSummaryDialog 0 vitest 覆盖。

    Expected after fix (Sprint 1 task 3.3):
      ImpairmentSummaryDialog.spec.ts 存在并覆盖核心交互
      （mount / onFetchSummary API / 4 来源 H1/I3/G14/F2 result 展示 /
       onApplyToSheet emit applied / visible 重置）.
    """
    spec_file = WORKPAPER_TESTS_DIR / "ImpairmentSummaryDialog.spec.ts"
    assert spec_file.exists(), (
        f"Bug Condition 确认: {spec_file} 不存在. "
        "ImpairmentSummaryDialog 0 vitest 覆盖 — K11 减值汇总弹窗无测试覆盖. "
        "修复方案: Sprint 1 task 3.3 创建 vitest 文件，参照 FairValueTestDialog.spec.ts 模式."
    )


def test_k_prefill_ledger_detail_e2e_test_exists() -> None:
    """验证项 4: backend/tests/test_k_prefill_ledger_detail.py 应存在.

    Bug Condition: prefill_engine 的 `=LEDGER_DETAIL('6601','1月','>=0')` 3-arg 签名
    从未在端到端 fixture 中被测试验证（K8-2/K9-2 销售/管理费用月度明细使用此签名）.

    Expected after fix (Sprint 1 task 3.4):
      backend/tests/test_k_prefill_ledger_detail.py 存在，含 fixture 创建 TbLedger 数据 +
      调用 _resolve_ledger_detail_formula(db, project_id, 2025, ['6601','1月','>=0']) +
      断言不抛异常 + 返回 list + 覆盖 3 种 direction（'>=0' / '<0' / '*'）.
    """
    test_file = BACKEND_TESTS_DIR / "test_k_prefill_ledger_detail.py"
    assert test_file.exists(), (
        f"Bug Condition 确认: {test_file} 不存在. "
        "_resolve_ledger_detail_formula 3-arg 签名（account_code, period, direction）"
        "在 K8-2/K9-2 prefill 链路中使用，但从未端到端验证. "
        "修复方案: Sprint 1 task 3.4 创建 e2e fixture 测试，覆盖 6601/6602 + 12 月份 + "
        "3 种 direction 组合."
    )
