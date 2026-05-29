# K 管理循环实施后复盘修复 — Bugfix Requirements

## Introduction

K 管理循环底稿优化 spec（workpaper-k-admin-cycle）已完成 23/23 tasks + UAT 14/14 ✓，但实施后复盘发现 12 项"形式合规但本质未到位"（formally compliant but substantively incomplete）的问题。这些问题分为 P0（必须修复才能上线）/ P1（应修复）/ P2（可延后）三级，需在 K spec 真正投产前逐项消除。

核心影响：P0 项直接导致用户无法使用已实现的功能（前端弹窗无入口）、测试覆盖存在盲区（0 vitest + prefill e2e 未验证），属于"UAT 标 ✓ 但用户不可达"的典型案例。

## Bug Analysis

### Current Behavior (Defect)

**P0 — 必须修复（用户不可达 / 测试盲区）**

1.1 WHEN 用户打开 K8/K9/K11 底稿时 THEN `ExpenseAnalysisDialog.vue` 和 `ImpairmentSummaryDialog.vue` 组件文件存在但 WorkpaperEditor.vue 中无 toolbar 按钮触发入口，用户无法访问费用分析和减值汇总功能

1.2 WHEN 运行前端 vitest 测试套件时 THEN `ExpenseAnalysisDialog` 和 `ImpairmentSummaryDialog` 两个弹窗组件的测试覆盖率为 0%（与同类 SharePaymentDialog / PayrollCalcDialog / FairValueTestDialog 已有 vitest 测试不一致）

1.3 WHEN prefill_engine 解析 K8-2/K9-2 的 `=LEDGER_DETAIL('6601','1月','>=0')` 公式时 THEN `_resolve_ledger_detail_formula()` 从未在端到端 fixture 中以此签名模式（3-arg: account_code, period, direction）被测试验证

**P1 — 应修复（测试深度不足 / 分类不精确）**

1.4 WHEN VR-K8-01/VR-K9-01/VR-K11-01 三角勾稽规则执行时 THEN 全部 24 个 VR 测试用例均 mock `_get_wp_parsed_data`，无"真实保存 K8 + K8-2 → run_all_checks → 阻断签字"的集成测试路径

1.5 WHEN `_lookup_impairment_amount` 查询 H1/I3/G14/F2 跨循环减值数据时 THEN 函数假设字段名为 `impairment_amount` / `total_impairment` / `ecl_amount` / `impairment_loss`（4 种 fallback），但从未对照 H1-14/I3/G14/F2 实际 `parsed_data` 结构验证这些字段名是否真实存在

1.6 WHEN K0 函证相关 7 个特殊 sheet（`会计提示` / `邮件传真回函可靠性验证K0-7` / `函证差异调节表K0-4` / `跟函函证过程控制K0-3` / `核实被函证单位信息K0-2` / `函证程序舞弊风险评价表K0-8` / `其他应收/付款替代程序K0-5/K0-6`）被分类时 THEN 全部 fallback 到"其他"类，缺少专属"函证辅助"分组语义

1.7 WHEN 费用明细 regex `^明细表K[89]-` 匹配 sheet 名时 THEN 仅命中 K8-2/K9-2 两个 sheet，K10-2~K13-2（其他收益/资产减值/营业外收入/营业外支出明细）逻辑上也属于费用类明细但 fallback 到通用"明细表"

**P2 — 可延后（跨 spec 协调 / 数据质量）**

1.8 WHEN K spec cross_wp_ref CW-313~332 起编时 THEN 基于"J spec 占至 CW-312"假设硬编码，若 L spec 也从 CW-313 起编将产生 ref_id 碰撞（L spec 尚未执行，需在 L Sprint 0 加运行时 max(ref_id) grep 防护）

1.9 WHEN wp_account_mapping.json 中 K 循环编号（K2=销售费用/K8=其他应付款）与模板文件编号（K2=其他流动资产/K8=销售费用）并存时 THEN 无独立 tracking issue 或 spec 跟踪此历史数据质量问题的修正计划

### Expected Behavior (Correct)

**P0 — 必须修复**

2.1 WHEN 用户打开 K8/K9 底稿时 THEN WorkpaperEditor.vue SHALL 在 K 循环 toolbar 区域显示"📊 费用分析"按钮，点击后触发 `ExpenseAnalysisDialog`（参照 G 循环 FairValueTestDialog 的 toolbar button + visible ref + dialog component + @applied handler 模式）

2.2 WHEN 用户打开 K11 底稿时 THEN WorkpaperEditor.vue SHALL 在 K 循环 toolbar 区域显示"📋 减值汇总"按钮，点击后触发 `ImpairmentSummaryDialog`（同上模式）

2.3 WHEN 运行前端 vitest 测试套件时 THEN `ExpenseAnalysisDialog` 和 `ImpairmentSummaryDialog` SHALL 各有 ≥ 1 个 vitest spec 文件覆盖核心交互（表单提交 / 结果展示 / 采纳写回 / 错误处理）

2.4 WHEN prefill_engine 解析 `=LEDGER_DETAIL('6601','1月','>=0')` 公式时 THEN SHALL 有端到端 fixture 测试验证 `_resolve_ledger_detail_formula()` 对此 3-arg 签名模式正确返回明细行数据（含 account_code='6601' + period='1月' + direction='>=0' 三参数解析）

**P1 — 应修复**

2.5 WHEN VR-K8-01 blocking 校验执行时 THEN SHALL 有 ≥ 1 个集成测试路径覆盖"真实保存 K8 + K8-2 parsed_data → 调用 run_all_checks → VR-K8-01 fail → 阻断签字"全链路（不 mock `_get_wp_parsed_data`）

2.6 WHEN `_lookup_impairment_amount` 查询跨循环减值数据时 THEN SHALL 有对账测试验证 H1-14 实际 `parsed_data.impairment_calcs` / I3 实际 `parsed_data.impairment_calcs` / G14 实际 `parsed_data.ecl_calcs` / F2 实际 `parsed_data.impairment_calcs` 的真实字段名与 `_lookup_impairment_amount` 的 4 种 fallback key 匹配

2.7 WHEN K0 函证相关 7 个特殊 sheet 被分类时 THEN `useKAdminCycleSheetGroups` SHALL 新增第 11 类"函证辅助"分组（id='confirmation_aux', icon='📮', priority 介于检查表和其他之间），将 K0-2~K0-8 + 替代程序 K0-5/K0-6 归入此类

2.8 WHEN 费用明细分类规则匹配 sheet 名时 THEN regex SHALL 扩展为匹配 K8-2/K9-2/K10-2/K11-2/K12-2/K13-2（即 `^明细表K(8|9|1[0-3])-` 或等效关键词匹配），使所有费用类循环的明细表归入"费用明细"类

**P2 — 可延后**

2.9 WHEN L spec Sprint 0 执行 cross_wp_ref 起编时 THEN SHALL 包含运行时 `max(ref_id)` grep 防护逻辑，确保 L 起编 = 实际 max+1 而非硬编码假设值（防止与 K spec CW-313~332 碰撞）

2.10 WHEN wp_account_mapping K 循环编号双轨问题被识别时 THEN SHALL 创建独立 tracking issue 记录修正计划（scope: K0/K1/K6/K9 四个一致 + 其余 10 个需修正），标注"不阻断当前 spec 上线，运行时以模板文件 sheet 名为准"

### Unchanged Behavior (Regression Prevention)

3.1 WHEN G 循环 FairValueTestDialog / ECLCalcDialog / ClassificationCheckDialog toolbar 按钮在 WorkpaperEditor.vue 中触发时 THEN 系统 SHALL CONTINUE TO 正常弹出对应弹窗且 @applied 写回功能不受影响

3.2 WHEN H 循环 DepreciationCalcDialog / AssetImpairmentDialog toolbar 按钮触发时 THEN 系统 SHALL CONTINUE TO 正常工作

3.3 WHEN J 循环 PayrollCalcDialog / SharePaymentDialog toolbar 按钮触发时 THEN 系统 SHALL CONTINUE TO 正常工作

3.4 WHEN `useKAdminCycleSheetGroups` 对现有 10 类规则分类 K 循环 sheet 时 THEN 已有 23 个 vitest 测试 SHALL CONTINUE TO 全部通过（新增"函证辅助"类不影响已归类 sheet 的分类结果）

3.5 WHEN VR-K8-01/VR-K9-01/VR-K11-01 现有 24 个 mock 测试执行时 THEN SHALL CONTINUE TO 全部通过（新增集成测试是补充而非替代）

3.6 WHEN prefill_engine 解析现有 =TB / =AUX / =PREV / =WP / =LEDGER_DETAIL 公式时 THEN 系统 SHALL CONTINUE TO 对 D/F/H/I/G/J/K 全循环已有 835+ cells 正确解析

3.7 WHEN cross_wp_references CW-313~332 的 K 循环 20 条引用被加载时 THEN 系统 SHALL CONTINUE TO 正确解析 ref_id / source_wp / target_wp / severity 字段

3.8 WHEN K 循环 10 类 sheet 分组中"费用明细"类匹配 K8-2/K9-2 时 THEN 系统 SHALL CONTINUE TO 将这两个 sheet 归入"费用明细"类（扩展 regex 是增量覆盖，不改变已有匹配结果）

---

## Bug Condition（结构化伪代码）

### Bug Condition Function

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type KAdminCycleFeatureAccess
  OUTPUT: boolean
  
  // P0: 用户尝试访问 K 循环弹窗功能但无 UI 入口
  IF X.action = 'open_expense_analysis' AND X.wp_code IN ['K8','K9'] THEN
    RETURN TRUE  // ExpenseAnalysisDialog 未 wired
  END IF
  
  IF X.action = 'open_impairment_summary' AND X.wp_code = 'K11' THEN
    RETURN TRUE  // ImpairmentSummaryDialog 未 wired
  END IF
  
  // P0: 前端弹窗 0 vitest
  IF X.action = 'run_vitest' AND X.component IN ['ExpenseAnalysisDialog','ImpairmentSummaryDialog'] THEN
    RETURN TRUE  // 0 测试覆盖
  END IF
  
  // P0: LEDGER_DETAIL 3-arg 签名未 e2e 验证
  IF X.action = 'prefill_resolve' AND X.formula_type = 'LEDGER_DETAIL' AND X.args_count = 3 AND X.account_code IN ['6601','6602'] THEN
    RETURN TRUE  // 从未端到端测试
  END IF
  
  RETURN FALSE
END FUNCTION
```

### Property Specification — Fix Checking

```pascal
// Property: P0 Fix — 弹窗 UI 入口可达
FOR ALL X WHERE isBugCondition(X) AND X.action = 'open_expense_analysis' DO
  result ← WorkpaperEditor.render(wp_code=X.wp_code)
  ASSERT toolbar_contains_button(result, '费用分析')
  ASSERT click_button(result, '费用分析') → ExpenseAnalysisDialog.visible = true
END FOR

// Property: P0 Fix — vitest 覆盖
FOR ALL X WHERE isBugCondition(X) AND X.action = 'run_vitest' DO
  result ← vitest.run(X.component + '.spec.ts')
  ASSERT result.test_count >= 1 AND result.pass_rate = 100%
END FOR

// Property: P0 Fix — LEDGER_DETAIL e2e
FOR ALL X WHERE isBugCondition(X) AND X.action = 'prefill_resolve' DO
  result ← _resolve_ledger_detail_formula(db, project_id, year, [X.account_code, X.period, X.direction])
  ASSERT result IS list AND no_exception(result)
END FOR
```

### Preservation Goal

```pascal
// Property: Preservation — 现有弹窗功能不受影响
FOR ALL X WHERE NOT isBugCondition(X) AND X.action IN ['open_fair_value_test','open_ecl_calc','open_depreciation_calc','open_payroll_calc'] DO
  ASSERT F(X) = F'(X)  // 修复前后行为一致
END FOR

// Property: Preservation — 现有测试全绿
FOR ALL X WHERE NOT isBugCondition(X) AND X.action = 'run_existing_tests' DO
  ASSERT F(X).pass_count = F'(X).pass_count  // 不减少通过数
END FOR
```
