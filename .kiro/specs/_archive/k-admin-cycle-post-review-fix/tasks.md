# K 管理循环实施后复盘修复 — Implementation Plan

> **Spec**: k-admin-cycle-post-review-fix
> **版本**: v1.0
> **总工时**: ~1.5 天（Sprint 1 P0 ~0.8 天 + Sprint 2 P1 ~0.6 天 + Sprint 3 P2 ~0.1 天）
> **Sprint 数**: 3 + Checkpoint

## 变更记录

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-05-19 | 复盘修复任务清单初版 |

## 任务总览

| Sprint | 任务数 | 工时 | 优先级 |
|-------|-------|------|-------|
| Sprint 1 | 4 | 0.8 天 | P0 必修 |
| Sprint 2 | 6 | 0.6 天 | P1 应修 |
| Sprint 3 | 2 | 0.1 天 | P2 文档 |
| Checkpoint | 1 | - | 回归验证 |
| **合计** | **13** | **~1.5 天** | |

---

## 1. Bug Condition Exploration Test（修复前确认 bug 存在）

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - K 循环弹窗 UI 入口不可达 + 测试盲区
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: 针对确定性 bug，scope 到具体失败 case
  - 验证项 1: grep `WorkpaperEditor.vue` 确认无 `expenseAnalysisDialogVisible` ref（预期：不存在）
  - 验证项 2: 检查 `__tests__/` 目录确认无 `ExpenseAnalysisDialog.spec.ts`（预期：不存在）
  - 验证项 3: 检查 `__tests__/` 目录确认无 `ImpairmentSummaryDialog.spec.ts`（预期：不存在）
  - 验证项 4: grep test 目录确认无 `test_k_prefill_ledger_detail.py`（预期：不存在）
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS（确认 bug 存在 — Dialog 未 wired + 0 vitest + LEDGER_DETAIL 未 e2e）
  - Document counterexamples: WorkpaperEditor.vue 无 K 循环 Dialog import/visible ref/toolbar button
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3_

---

## 2. Preservation Property Tests（修复前确认现有行为基线）

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - 现有循环 toolbar 按钮 + sheet 分组 + VR + prefill 不受影响
  - **IMPORTANT**: Follow observation-first methodology
  - Observe: 现有 K vitest 23 个测试全绿（`vitest --run useKAdminCycleSheetGroups`）
  - Observe: 现有 K backend 274 个测试全绿（`python -m pytest backend/tests/test_k_*.py`）
  - Observe: G/H/I/J Dialog vitest 全绿（FairValueTestDialog / ECLCalcDialog / DepreciationCalcDialog / AssetImpairmentDialog / PayrollCalcDialog / SharePaymentDialog）
  - Observe: Prior-cycle 327 回归全绿（`python -m pytest backend/tests/test_d_*.py backend/tests/test_f_*.py backend/tests/test_h_*.py backend/tests/test_i_*.py backend/tests/test_g_*.py backend/tests/test_j_*.py`）
  - Write property-based test: for all non-bug-condition inputs, existing behavior preserved
  - Verify tests pass on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS（确认现有行为基线正常）
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

---

## 3. Sprint 1 — P0 必修（~0.8 天）

- [x] 3. Fix for K 循环弹窗 UI 入口不可达 + 测试盲区

  - [x] 3.1 Wire ExpenseAnalysisDialog + ImpairmentSummaryDialog into WorkpaperEditor.vue
    - Import 两个 Dialog 组件（`ExpenseAnalysisDialog.vue` / `ImpairmentSummaryDialog.vue`）
    - 添加 `expenseAnalysisDialogVisible` / `impairmentSummaryDialogVisible` ref
    - 添加 K8/K9 toolbar 按钮"📊 费用分析"（v-if `isKCycle && /^K[89]/.test(wp_code)`）
    - 添加 K11 toolbar 按钮"📋 减值汇总"（v-if `isKCycle && /^K11/.test(wp_code)`）
    - Wire Dialog 组件（:visible / :project-id / :wp-id / :target-sheet / @update:visible / @applied）
    - 添加 `onExpenseAnalysisApplied` / `onImpairmentSummaryApplied` handler → `refreshWorkpaper()`
    - 参照 G 循环 FairValueTestDialog 完整 wiring 模式
    - _Bug_Condition: isBugCondition(input) where input.action='open_expense_analysis' AND wp_code IN ['K8','K9']_
    - _Expected_Behavior: toolbar 含对应按钮，点击后 Dialog visible=true_
    - _Preservation: G/H/I/J 循环现有 6 个 Dialog toolbar 按钮不受影响_
    - _Requirements: 2.1, 2.2_
    - 验证: `vitest --run WorkpaperEditor` 含 K 循环按钮渲染测试

  - [x] 3.2 Create ExpenseAnalysisDialog.spec.ts vitest
    - 文件: `audit-platform/frontend/src/components/workpaper/__tests__/ExpenseAnalysisDialog.spec.ts`
    - 参照 `FairValueTestDialog.spec.ts` 模式
    - 测试覆盖: mount / form 默认值 / isFormValid / buildRequestBody / onAnalyze API 调用 / onApplyToSheet emit applied / visible=false 时 result 重置
    - _Bug_Condition: isBugCondition(input) where input.action='run_vitest' AND component='ExpenseAnalysisDialog'_
    - _Expected_Behavior: ≥ 1 spec 文件覆盖核心交互_
    - _Requirements: 2.3_
    - 验证: `npx vitest --run src/components/workpaper/__tests__/ExpenseAnalysisDialog.spec.ts`

  - [x] 3.3 Create ImpairmentSummaryDialog.spec.ts vitest
    - 文件: `audit-platform/frontend/src/components/workpaper/__tests__/ImpairmentSummaryDialog.spec.ts`
    - 参照 `FairValueTestDialog.spec.ts` 模式
    - 测试覆盖: mount / onFetchSummary API 调用 / result 展示（4 来源 H1/I3/G14/F2）/ onApplyToSheet emit applied / visible=false 时 result 重置
    - _Bug_Condition: isBugCondition(input) where input.action='run_vitest' AND component='ImpairmentSummaryDialog'_
    - _Expected_Behavior: ≥ 1 spec 文件覆盖核心交互_
    - _Requirements: 2.3_
    - 验证: `npx vitest --run src/components/workpaper/__tests__/ImpairmentSummaryDialog.spec.ts`

  - [x] 3.4 Create test_k_prefill_ledger_detail.py（LEDGER_DETAIL 3-arg e2e fixture）
    - 文件: `backend/tests/test_k_prefill_ledger_detail.py`（新建）
    - pytest fixture 创建 TbLedger 测试数据（account_code='6601', accounting_period=1, debit_amount=500）
    - 调用 `_resolve_ledger_detail_formula(db, project_id, 2025, ['6601','1月','>=0'])`
    - 断言: 不抛异常 + 返回 list + 每行含 voucher_date/voucher_no/summary/debit_amount/credit_amount/counterpart_account
    - 覆盖 3 种 direction: `'>=0'` / `'<0'` / `'*'`
    - _Bug_Condition: isBugCondition(input) where input.action='prefill_resolve' AND formula_type='LEDGER_DETAIL' AND args_count=3_
    - _Expected_Behavior: 不抛异常 + 返回正确结构 list_
    - _Requirements: 2.4_
    - 验证: `python -m pytest backend/tests/test_k_prefill_ledger_detail.py -v`

  - [x] 3.5 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - K 循环弹窗 UI 入口可达 + 测试覆盖
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES（确认 bug 已修复）
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.6 Verify preservation tests still pass
    - **Property 2: Preservation** - 现有循环功能不受影响
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS（确认无回归）
    - Confirm: K vitest 23 + K backend 274 + prior-cycle 327 全绿

---

## 4. Sprint 2 — P1 应修（~0.6 天）

- [x] 4.1 Create test_k_vr_integration.py（真实 DB → run_all_checks → VR-K8-01 结果）
  - 文件: `backend/tests/test_k_vr_integration.py`（新建）
  - 创建真实 WorkingPaper 记录（含 WpIndex wp_code='K8'），parsed_data 含 `k8_total` / `k8_payroll` / `k8_depreciation` / `k8_other`
  - 调用 `check_k_cycle_triangle_reconciliation(project_id, 2025)` 不 mock
  - 断言 VR-K8-01 结果正确（pass/fail 取决于数据是否勾稽）
  - 覆盖 pass case（数据勾稽）+ fail case（数据不勾稽 → blocking）
  - _Requirements: 2.5_
  - 验证: `python -m pytest backend/tests/test_k_vr_integration.py -v`

- [x] 4.2 Create test_k11_schema_verification.py（跨模块 namespace/field name 对账）
  - 文件: `backend/tests/test_k11_schema_verification.py`（新建）
  - Import H/I/G/F 各 router 模块的写回逻辑
  - 验证 H1 写回 `parsed_data.impairment_calcs[sheet].data.impairment_amount` → fallback key 包含 `impairment_amount` ✓
  - 验证 I3 写回 `parsed_data.goodwill_impairment_calcs[sheet].data.total_impairment` → fallback key 包含 `total_impairment` ✓
  - 验证 G14 写回 `parsed_data.ecl_calcs[sheet].ecl_amount` → fallback key 包含 `ecl_amount` ✓
  - 验证 F2 写回 `parsed_data.impairment_calcs[sheet].data.impairment_loss` → fallback key 包含 `impairment_loss` ✓
  - _Requirements: 2.6_
  - 验证: `python -m pytest backend/tests/test_k11_schema_verification.py -v`

- [x] 4.3 Add "函证辅助" category to useKAdminCycleSheetGroups.ts（priority=7.5）
  - 文件: `audit-platform/frontend/src/composables/useKAdminCycleSheetGroups.ts`
  - 在 `check_table`（priority=7）之后、`disclosure_adj`（priority=8）之前插入新规则:
    ```typescript
    {
      id: 'confirmation_aux',
      category: '函证辅助',
      icon: '📮',
      color: '#00695c',
      priority: 7.5,
      match: (s) => /K0[-]?\d/.test(s) && /函证|替代程序|回函|核实|舞弊风险|差异调节|过程控制|会计提示/.test(s),
    }
    ```
  - 覆盖 K0-2~K0-8 + 替代程序 K0-5/K0-6 归入"函证辅助"类
  - _Requirements: 2.7_

- [x] 4.4 Expand expense_detail regex from `^明细表K[89]-` to `^明细表K(8|9|1[0-3])-`
  - 文件: `audit-platform/frontend/src/composables/useKAdminCycleSheetGroups.ts`
  - 将 `expense_detail` 规则的 match regex 扩展覆盖 K8-2/K9-2/K10-2/K11-2/K12-2/K13-2
  - 确保 K1-2/K3-2/K5-2 仍归通用"明细表"（不受影响）
  - _Requirements: 2.8_

- [x] 4.5 Update vitest for sheet groups（add 函证辅助 + expanded regex test cases）
  - 新增测试: `classifyKSheet('函证差异调节表K0-4')` → category='函证辅助'
  - 新增测试: `classifyKSheet('核实被函证单位信息K0-2')` → category='函证辅助'
  - 新增测试: `classifyKSheet('明细表K10-2')` → category='费用明细'
  - 新增测试: `classifyKSheet('明细表K13-2')` → category='费用明细'
  - 确认现有 23 个测试仍全绿（K8-2/K9-2 仍归"费用明细"，K1-2/K3-2 仍归"明细表"）
  - _Requirements: 2.7, 2.8, 3.4, 3.8_
  - 验证: `npx vitest --run useKAdminCycleSheetGroups`

- [x] 4.6 Update backend test_k_sheet_groups.py（sync Python mirror rules）
  - 同步 Python 端 sheet 分组规则（如有 mirror）
  - 新增"函证辅助"分类 + 费用明细 regex 扩展对应测试
  - 确认现有 K backend 测试全绿
  - _Requirements: 2.7, 2.8_
  - 验证: `python -m pytest backend/tests/test_k_sheet_groups.py -v`

---

## 5. Sprint 3 — P2 文档（~0.1 天）

- [x] 5.1 Add max(ref_id) grep guard note to L spec requirements
  - 在 L spec requirements.md Sprint 0 段落添加说明:
    > K spec 占至 CW-332，L spec 起编必须运行时 `max(ref_id)` grep 确认实际 max+1，禁止硬编码假设值
  - 防止 L spec 与 K spec CW-313~332 碰撞
  - _Requirements: 2.9_

- [x] 5.2 Create wp_account_mapping tracking issue text
  - 创建 tracking issue 文本记录 K 循环编号双轨修正计划
  - Scope: K0/K1/K6/K9 四个一致 + 其余 10 个需修正
  - 标注"不阻断当前 spec 上线，运行时以模板文件 sheet 名为准"
  - _Requirements: 2.10_

---

## 6. Checkpoint — 全量回归验证

- [x] 6. Checkpoint - Ensure all tests pass
  - 运行 K backend 全量: `python -m pytest backend/tests/test_k_*.py`（274 + 新增测试）
  - 运行 K PBT 全量: 87 PBT tests 全绿
  - 运行 K vitest 全量: `npx vitest --run`（含新增 ExpenseAnalysisDialog + ImpairmentSummaryDialog + sheet groups 扩展）
  - 运行 prior-cycle 回归: `python -m pytest backend/tests/test_d_*.py backend/tests/test_f_*.py backend/tests/test_h_*.py backend/tests/test_i_*.py backend/tests/test_g_*.py backend/tests/test_j_*.py`（327 tests）
  - 确认总计: 274 K backend + 87 PBT + vitest + 327 prior-cycle 全绿
  - Ensure all tests pass, ask the user if questions arise.
