# K 管理循环实施后复盘修复 — Bugfix Design

## Overview

K 管理循环 spec（workpaper-k-admin-cycle）UAT 14/14 ✓ 通过，但复盘发现 12 项"形式合规但本质未到位"问题。核心缺陷：`ExpenseAnalysisDialog` / `ImpairmentSummaryDialog` 组件文件存在但 WorkpaperEditor.vue 无 toolbar 入口（用户不可达）、两弹窗 0 vitest、`_resolve_ledger_detail_formula` 3-arg 签名未 e2e 验证。本修复以最小改动补齐 UI 入口 + 测试覆盖 + 分类精度，保持现有 274 K backend + 23 K vitest + 327 prior-cycle 回归全绿。

## Glossary

- **Bug_Condition (C)**: 用户尝试访问 K 循环弹窗功能但 WorkpaperEditor.vue 无 toolbar 按钮入口
- **Property (P)**: K8/K9 底稿显示"📊 费用分析"按钮 + K11 显示"📋 减值汇总"按钮，点击触发对应 Dialog
- **Preservation**: 现有 G/H/I/J 循环 toolbar 按钮 + 10 类 sheet 分组 + VR 三角勾稽 + prefill 解析全部不受影响
- **WorkpaperEditor.vue**: 底稿编辑器主视图，已集成 G/H/I/J 循环 6 个 Dialog 的 toolbar 按钮模式
- **useKAdminCycleSheetGroups**: K 循环 10 类 sheet 分组 composable（`audit-platform/frontend/src/composables/useKAdminCycleSheetGroups.ts`）
- **consistency_gate**: 后端一致性校验引擎（`backend/app/services/consistency_gate.py`），含 `check_k_cycle_triangle_reconciliation`
- **_lookup_impairment_amount**: K11 跨循环减值汇总查询函数，按 namespace + 4 种 fallback key 读取 parsed_data

## Bug Details

### Bug Condition

用户打开 K8/K9/K11 底稿时，`ExpenseAnalysisDialog.vue` 和 `ImpairmentSummaryDialog.vue` 组件文件存在但 WorkpaperEditor.vue 中无 toolbar 按钮触发入口。同时两弹窗 0 vitest 覆盖，`_resolve_ledger_detail_formula` 3-arg 签名从未 e2e 验证。

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type KAdminCycleFeatureAccess
  OUTPUT: boolean
  
  // P0: 弹窗 UI 入口不可达
  IF input.action = 'open_expense_analysis' AND input.wp_code IN ['K8','K9'] THEN
    RETURN TRUE
  END IF
  IF input.action = 'open_impairment_summary' AND input.wp_code = 'K11' THEN
    RETURN TRUE
  END IF
  
  // P0: 弹窗 0 vitest
  IF input.action = 'run_vitest' AND input.component IN ['ExpenseAnalysisDialog','ImpairmentSummaryDialog'] THEN
    RETURN TRUE
  END IF
  
  // P0: LEDGER_DETAIL 3-arg 未 e2e 验证
  IF input.action = 'prefill_resolve' AND input.formula_type = 'LEDGER_DETAIL'
     AND input.args_count = 3 AND input.account_code IN ['6601','6602'] THEN
    RETURN TRUE
  END IF
  
  RETURN FALSE
END FUNCTION
```

### Examples

- 用户打开 K8 销售费用底稿 → toolbar 无"📊 费用分析"按钮 → 无法触发 ExpenseAnalysisDialog（预期：按钮可见可点击）
- 用户打开 K11 资产减值底稿 → toolbar 无"📋 减值汇总"按钮 → 无法触发 ImpairmentSummaryDialog（预期：按钮可见可点击）
- 运行 `vitest --run` → ExpenseAnalysisDialog.spec.ts 不存在 → 0 覆盖（预期：≥ 1 spec 文件覆盖核心交互）
- 调用 `_resolve_ledger_detail_formula(db, pid, 2025, ['6601','1月','>=0'])` → 从未在 fixture 中验证（预期：有 e2e 测试确认不抛异常 + 返回正确结构）

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- G 循环 FairValueTestDialog / ECLCalcDialog / ClassificationCheckDialog toolbar 按钮正常弹出 + @applied 写回
- H 循环 DepreciationCalcDialog / AssetImpairmentDialog toolbar 按钮正常工作
- J 循环 PayrollCalcDialog / SharePaymentDialog toolbar 按钮正常工作
- `useKAdminCycleSheetGroups` 现有 10 类规则对已归类 sheet 的分类结果不变（23 vitest 全绿）
- VR-K8-01/VR-K9-01/VR-K11-01 现有 24 个 mock 测试全绿
- prefill_engine 对 =TB / =AUX / =PREV / =WP / =LEDGER_DETAIL 全循环 835+ cells 正确解析
- cross_wp_references CW-313~332 的 K 循环 20 条引用正确解析

**Scope:**
所有不涉及 K 循环 toolbar 按钮新增 / sheet 分组规则扩展 / regex 扩展的输入完全不受影响。

## Hypothesized Root Cause

1. **Dialog 未 wired（P0 #1-2）**: WorkpaperEditor.vue 在 K spec 实施时创建了 `ExpenseAnalysisDialog.vue` / `ImpairmentSummaryDialog.vue` 组件文件，但遗漏了 toolbar 按钮 + visible ref + import + v-if 条件渲染的集成步骤（对比 G 循环 FairValueTestDialog 完整 wiring 模式）

2. **0 vitest（P0 #3）**: K spec tasks 未包含弹窗 vitest task（与 G/H/I/J 循环每个 Dialog 都有 .spec.ts 不一致）

3. **LEDGER_DETAIL e2e 缺失（P0 #4）**: K8-2/K9-2 prefill 使用 `=LEDGER_DETAIL('6601','1月','>=0')` 3-arg 签名，但 prefill_engine 测试仅覆盖 E1 循环的 LEDGER_DETAIL 调用，未覆盖 K 循环特定参数组合

4. **VR 全 mock（P1 #5）**: 24 个 VR 测试全部 mock `_get_wp_parsed_data`，缺少真实 DB 记录 → run_all_checks → 阻断签字的集成路径

5. **K11 schema 未对账（P1 #6）**: `_lookup_impairment_amount` 的 4 种 fallback key（`impairment_amount` / `total_impairment` / `impairment_loss` / `ecl_amount`）从未对照 H/I/G/F 实际写回代码验证字段名匹配

6. **函证辅助分组缺失（P1 #7）**: K0 函证相关 7 个 sheet 全部 fallback 到"其他"类，缺少专属语义分组

7. **费用明细 regex 过窄（P1 #8）**: `^明细表K[89]-` 仅匹配 K8-2/K9-2，K10-2~K13-2 逻辑上也属费用类明细但 fallback 到通用"明细表"

## Correctness Properties

Property 1: Bug Condition - K 循环弹窗 UI 入口可达

_For any_ K 循环底稿（wp_code 匹配 K8/K9/K11），WorkpaperEditor.vue 渲染后 toolbar 区域 SHALL 包含对应按钮（K8/K9→"📊 费用分析"，K11→"📋 减值汇总"），点击后对应 Dialog visible 变为 true。

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation - 现有循环 toolbar 按钮不受影响

_For any_ 非 K 循环弹窗触发输入（G/H/I/J 循环 toolbar 按钮点击），修复后 SHALL 产生与修复前完全相同的行为，保持所有现有 Dialog 的 visible/applied/write-back 功能不变。

**Validates: Requirements 3.1, 3.2, 3.3**

Property 3: Bug Condition - LEDGER_DETAIL 3-arg 签名正确解析

_For any_ `=LEDGER_DETAIL(account_code, period, direction)` 公式调用（account_code ∈ ['6601','6602']，period ∈ ['1月'...'12月']，direction ∈ ['>=0','<0','*']），`_resolve_ledger_detail_formula` SHALL 不抛异常且返回 list 类型结果。

**Validates: Requirements 2.4**

Property 4: Preservation - Sheet 分组扩展不破坏已有分类

_For any_ 已被现有 10 类规则正确分类的 sheet 名，新增"函证辅助"类 + 费用明细 regex 扩展后 SHALL 产生相同分类结果（K8-2/K9-2 仍归"费用明细"，K1-2/K3-2 仍归"明细表"）。

**Validates: Requirements 3.4, 3.8**

## Fix Implementation

### Changes Required

**P0 #1-2: Dialog wiring（WorkpaperEditor.vue）**

**File**: `audit-platform/frontend/src/views/WorkpaperEditor.vue`

**Specific Changes**:
1. **Import 两个 Dialog 组件**:
   ```typescript
   import ExpenseAnalysisDialog from '@/components/workpaper/ExpenseAnalysisDialog.vue'
   import ImpairmentSummaryDialog from '@/components/workpaper/ImpairmentSummaryDialog.vue'
   ```

2. **添加 visible ref**:
   ```typescript
   const expenseAnalysisDialogVisible = ref(false)
   const impairmentSummaryDialogVisible = ref(false)
   ```

3. **添加 toolbar 按钮**（在 amortizationCalcSection 按钮之后）:
   ```html
   <!-- K-admin-cycle-post-review-fix P0 #1: K8/K9 费用分析按钮 -->
   <div v-if="isKCycle && /^K[89]/.test((wpDetail?.wp_code || '').toUpperCase())" class="gt-expense-analysis-trigger">
     <el-button size="small" type="primary" plain @click="expenseAnalysisDialogVisible = true">
       📊 费用分析
     </el-button>
   </div>
   <!-- K-admin-cycle-post-review-fix P0 #2: K11 减值汇总按钮 -->
   <div v-if="isKCycle && /^K11/.test((wpDetail?.wp_code || '').toUpperCase())" class="gt-impairment-summary-trigger">
     <el-button size="small" type="primary" plain @click="impairmentSummaryDialogVisible = true">
       📋 减值汇总
     </el-button>
   </div>
   ```

4. **Wire Dialog 组件**（在现有 Dialog 组件区域之后）:
   ```html
   <ExpenseAnalysisDialog
     v-if="wpDetail && isKCycle"
     :visible="expenseAnalysisDialogVisible"
     :project-id="projectId"
     :wp-id="wpId"
     :target-sheet="sheetNav.activeSheetId.value || ''"
     @update:visible="expenseAnalysisDialogVisible = $event"
     @applied="onExpenseAnalysisApplied"
   />
   <ImpairmentSummaryDialog
     v-if="wpDetail && isKCycle"
     :visible="impairmentSummaryDialogVisible"
     :project-id="projectId"
     :wp-id="wpId"
     :target-sheet="sheetNav.activeSheetId.value || ''"
     @update:visible="impairmentSummaryDialogVisible = $event"
     @applied="onImpairmentSummaryApplied"
   />
   ```

5. **添加 @applied handler**:
   ```typescript
   function onExpenseAnalysisApplied(sheet: string) {
     refreshWorkpaper()
   }
   function onImpairmentSummaryApplied(sheet: string) {
     refreshWorkpaper()
   }
   ```

---

**P0 #3: Dialog vitest**

**File**: `audit-platform/frontend/src/components/workpaper/__tests__/ExpenseAnalysisDialog.spec.ts`
**File**: `audit-platform/frontend/src/components/workpaper/__tests__/ImpairmentSummaryDialog.spec.ts`

**Pattern**: 参照 `FairValueTestDialog.spec.ts`（mock api.post → mount → 验证 form 默认值 / isFormValid / buildRequestBody / onAnalyze API 调用 / onApplyToSheet emit applied / visible=false 时 result 重置）

---

**P0 #4: LEDGER_DETAIL e2e fixture**

**File**: `backend/tests/test_k_prefill_ledger_detail.py`（新建）

**Specific Changes**:
- pytest fixture 创建 TbLedger 测试数据（account_code='6601', accounting_period=1, debit_amount=500）
- 调用 `_resolve_ledger_detail_formula(db, project_id, 2025, ['6601','1月','>=0'])`
- 断言：不抛异常 + 返回 list + 每行含 voucher_date/voucher_no/summary/debit_amount/credit_amount/counterpart_account
- 覆盖 3 种 direction：`'>=0'` / `'<0'` / `'*'`

---

**P1 #5: VR e2e 集成测试**

**File**: `backend/tests/test_k_vr_integration.py`（新建）

**Specific Changes**:
- 创建真实 WorkingPaper 记录（含 WpIndex wp_code='K8'），parsed_data 含 `k8_total` / `k8_payroll` / `k8_depreciation` / `k8_other`
- 调用 `check_k_cycle_triangle_reconciliation(project_id, 2025)` 不 mock
- 断言 VR-K8-01 结果正确（pass/fail 取决于数据是否勾稽）

---

**P1 #6: K11 schema 对账测试**

**File**: `backend/tests/test_k11_schema_verification.py`（新建）

**Specific Changes**:
- Import H/I/G/F 各 router 模块的写回逻辑
- 验证 H1 写回 `parsed_data.impairment_calcs[sheet].data.impairment_amount` → `_lookup_impairment_amount` 的 fallback key 包含 `impairment_amount` ✓
- 验证 I3 写回 `parsed_data.goodwill_impairment_calcs[sheet].data.total_impairment` → fallback key 包含 `total_impairment` ✓
- 验证 G14 写回 `parsed_data.ecl_calcs[sheet].ecl_amount` → fallback key 包含 `ecl_amount` ✓
- 验证 F2 写回 `parsed_data.impairment_calcs[sheet].data.impairment_loss` → fallback key 包含 `impairment_loss` ✓

---

**P1 #7: 函证辅助分组**

**File**: `audit-platform/frontend/src/composables/useKAdminCycleSheetGroups.ts`

**Specific Changes**:
- 在 `check_table`（priority=7）之后、`disclosure_adj`（priority=8）之前插入新规则：
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
- 将 `disclosure_adj` priority 改为 8（不变）、`other` priority 改为 9（不变）
- 实际用 priority=7.5 插入无需 renumber（浮点 priority 排序正确）

---

**P1 #8: 费用明细 regex 扩展**

**File**: `audit-platform/frontend/src/composables/useKAdminCycleSheetGroups.ts`

**Specific Changes**:
- 将 `expense_detail` 规则的 match 从 `/^明细表K[89]-/` 改为 `/^明细表K(8|9|1[0-3])-/`
- 覆盖 K8-2/K9-2/K10-2/K11-2/K12-2/K13-2

---

**P2 #9: L spec Sprint 0 max(ref_id) grep 防护**

**变更类型**: 文档注记（在 L spec requirements.md Sprint 0 段落添加说明）

---

**P2 #10: wp_account_mapping tracking issue**

**变更类型**: 创建 tracking issue 文本（scope: K0/K1/K6/K9 四个一致 + 其余 10 个需修正）

## Testing Strategy

### Validation Approach

测试策略分两阶段：先在未修复代码上确认 bug 存在（exploratory），再验证修复正确性 + 保持现有行为不变。

### Exploratory Bug Condition Checking

**Goal**: 在未修复代码上确认 bug 存在，验证根因分析正确。

**Test Plan**: 检查 WorkpaperEditor.vue 源码确认无 K 循环 toolbar 按钮；检查 `__tests__/` 目录确认无 ExpenseAnalysisDialog.spec.ts / ImpairmentSummaryDialog.spec.ts；检查 test 目录确认无 LEDGER_DETAIL 3-arg K 循环 fixture。

**Test Cases**:
1. **Dialog 入口缺失**: grep WorkpaperEditor.vue 确认无 `expenseAnalysisDialogVisible` ref（will fail on unfixed code）
2. **0 vitest**: ls `__tests__/` 确认无 ExpenseAnalysisDialog.spec.ts（will fail on unfixed code）
3. **LEDGER_DETAIL 未覆盖**: grep test 目录确认无 `'6601','1月','>=0'` 测试签名（will fail on unfixed code）
4. **函证辅助分组缺失**: 调用 `classifyKSheet('函证差异调节表K0-4')` 返回"其他"而非"函证辅助"（will fail on unfixed code）

**Expected Counterexamples**:
- WorkpaperEditor.vue 无 K 循环 Dialog import / visible ref / toolbar button
- 可能原因：K spec task 清单遗漏 Dialog wiring 步骤

### Fix Checking

**Goal**: 验证修复后所有 bug condition 输入产生正确行为。

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := fixedSystem(input)
  ASSERT expectedBehavior(result)
END FOR
```

**具体验证**:
- P0 #1-2: vitest mount WorkpaperEditor（mock wpDetail.wp_code='K8'）→ 断言 toolbar 含"📊 费用分析"按钮
- P0 #3: `vitest --run ExpenseAnalysisDialog.spec.ts ImpairmentSummaryDialog.spec.ts` → 全绿
- P0 #4: `pytest test_k_prefill_ledger_detail.py` → 全绿
- P1 #5: `pytest test_k_vr_integration.py` → 全绿
- P1 #6: `pytest test_k11_schema_verification.py` → 全绿
- P1 #7: `classifyKSheet('函证差异调节表K0-4')` → category='函证辅助'
- P1 #8: `classifyKSheet('明细表K10-2')` → category='费用明细'

### Preservation Checking

**Goal**: 验证修复不影响现有行为。

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalSystem(input) = fixedSystem(input)
END FOR
```

**Testing Approach**: 运行现有测试套件确认全绿。

**Test Cases**:
1. **现有 K vitest 全绿**: `vitest --run` 含 useKAdminCycleSheetGroups 23 个测试 → 全绿（新增"函证辅助"类不影响已归类 sheet）
2. **现有 K backend 全绿**: `pytest backend/tests/test_k_*.py` 274 个测试 → 全绿
3. **Prior-cycle 回归全绿**: `pytest backend/tests/test_d_*.py test_f_*.py test_h_*.py test_i_*.py test_g_*.py test_j_*.py` 327 个测试 → 全绿
4. **G/H/I/J Dialog 不受影响**: 现有 FairValueTestDialog.spec.ts / ECLCalcDialog.spec.ts / DepreciationCalcDialog.spec.ts / AssetImpairmentDialog.spec.ts 全绿

### Unit Tests

- ExpenseAnalysisDialog.spec.ts: mount / form 默认值 / isFormValid / buildRequestBody / onAnalyze API / onApplyToSheet emit / visible 重置
- ImpairmentSummaryDialog.spec.ts: mount / onFetchSummary API / result 展示 / onApplyToSheet emit / visible 重置
- test_k_prefill_ledger_detail.py: 3-arg 签名解析 / period 过滤 / amount_filter 过滤 / 空数据返回 []
- test_k11_schema_verification.py: 4 来源 namespace + field name 对账

### Property-Based Tests

- 无新增 PBT（现有 PBT-P1~P5 已覆盖 sheet 分组完备性 + VR 三角勾稽 + YoY 单调性）
- 新增"函证辅助"类 + regex 扩展后运行现有 PBT-P3（sheet group completeness 200 examples）确认不破坏

### Integration Tests

- test_k_vr_integration.py: 真实 DB 记录 → run_all_checks → VR-K8-01 结果正确
- test_k11_schema_verification.py: 跨模块 import 验证 namespace/field 对齐
