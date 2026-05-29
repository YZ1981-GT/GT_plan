# K 管理循环底稿优化 — Tasks

> **Spec**: workpaper-k-admin-cycle
> **版本**: v1.0
> **总工时**: 7 天 / ~1.4 周（Sprint 0 核验 0.4 天 + Sprint 0.X 前置实测 0.3 天 + Sprint 1 P0 1 天 + Sprint 2 P1 3.5 天 + Sprint 3 P2 1.8 天）
> **Sprint 数**: 5

## 变更记录

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-05-19 | 三件套实施计划初版 |

## 任务总览

| Sprint | 任务数 | 工时 | 优先级 |
|-------|-------|------|-------|
| Sprint 0 | 3 | 0.4 天 | - |
| Sprint 0.X | 2 | 0.3 天 | - |
| Sprint 1 | 6 | 1 天 | P0 |
| Sprint 2 | 12 | 3.5 天 | P1 |
| Sprint 3 | 6 | 1.8 天 | P2 |
| **合计** | **29** | **7 天** | |

---

## Sprint 0 — 现状核验（0.4 天）

- [x] 0.1 openpyxl 提取 K 循环 14 文件真实 sheet 清单
  - 输出 N_k_raw_sheets=152 + 验证 `_should_skip_historical_sheet` 命中数=0（K 模板干净）
  - 确认无末尾空格（已实测：0 个）
  - 合并后有效 sheet = 109（152 - 0 - 43 = 109，task 1.1 实测复核 2026-05-19）
  - 工时: 0.2 天
  - _Requirements: K-F1, K-F6_

- [x] 0.2 grep 实测 K 循环 prefill + cross_wp_references 基线变量
  - 输出 N_k_prefill_entries=20 / N_k_prefill_cells=99 / N_k_cwr_count=15 / N_cwr_max_id
  - 确认 J+L spec 执行后的 max ref_id（K spec 起编 = max+1）
  - 工时: 0.1 天
  - _Requirements: 附录 A_

- [x] 0.3 输出 Sprint 0 核验报告 + 对齐 3 文档基线
  - 汇总 N_* 基准变量写入 requirements.md 附录 A + design.md ADR-K1
  - 工时: 0.1 天

**Sprint 0 验收（3 项）**：
- ✓ N_* 基准变量已实测落地（N_k_raw_sheets=152 / N_k_dedup_sheets=109 / N_k_historical_sheets=0 / N_k_cross_file_dups=43）
- ✓ K 循环 14 文件 sheet 清单已提取 + 0 末尾空格确认
- ✓ `_should_skip_historical_sheet` K 模板 0 命中确认

---

## Sprint 0.X — 前置实测（0.3 天，Sprint 1 启动前必做）

- [x] 0x.1 SQL 实测 tb_aux_balance K 类辅助账维度
  - 6601 销售费用：aux_type='客户'（20+ distinct，非预期'费用类别'）→ K8-2 不用 =AUX
  - 6602 管理费用：aux_type='区域2'+'客户'（非预期'费用类别'）→ K9-2 不用 =AUX
  - 1221 其他应收款：aux_type='三方收款标识'+'代收代付类别' → K1-2 可用 =AUX ✅
  - 2241 其他应付款：aux_type='代收代付类别' → K3-2 可用 =AUX ✅
  - **结论**：不降级，目标保持 ≥ 40 cells；K8-2/K9-2 改用 =LEDGER_DETAIL 按月度
  - 工时: 0.15 天
  - _Requirements: K-F6, ADR-K3_

- [x] 0x.2 openpyxl 提取 K8-2/K9-2/K1-2/K3-2/K5-2 真实表头 + 数据区结构
  - K8-2 `明细表K8-2`：Row 11 表头 项目/1月~12月，Row 12+ 费用类别分项
  - K9-2 `明细表K9-2`：Row 10 表头 项目/1月~12月，Row 11+ 费用类别分项
  - K1-2 `明细表K1-2`：Row 10 表头 序号/债务人名称/关联方类型/款项性质/期初...
  - K3-2 `明细表K3-2`：Row 8 表头 债权人名称/公司代码/关联方类型/款项性质/期初...
  - K5-2 `明细表 K5-2`（**K5 和 -2 之间有空格**）：Row 11 表头 项目类别/计提原因/未审数
  - 已填入 design.md ADR-K3 "实测结果"段落
  - 工时: 0.15 天
  - _Requirements: K-F6, ADR-K3_

**Sprint 0.X 验收（2 项）**：
- ✓ ADR-K3 "实测结果"段落已填入真实数据（aux_type + sheet 名 + 表头结构）
- ✓ K-F6 目标确认：≥ 40 cells（不降级，K1-2/K3-2 用 =AUX，K8-2/K9-2 用 =LEDGER_DETAIL）

---

## Sprint 1 — P0 核心（1 天）

### K-F1: 合并去重

- [x] 1.1 验证 chain_orchestrator 对 K 循环复用 `_merge_sheets_dedup`
  - 确认 K 循环已注册到 chain 合并流程
  - 写 `test_k_merge_dedup.py` 验证 152→109 有效 sheet
  - 验证 0 历史遗留 + 43 跨文件去重
  - 工时: 0.15 天
  - _Requirements: K-F1_

- [x] 1.2 验证 `_should_skip_historical_sheet` 对 K 循环 0 命中 + D/F/H/I/G/J/L 回归无影响
  - 工时: 0.1 天
  - _Requirements: K-F1_

### K-F3: 三角勾稽 VR 规则

- [x] 1.3 创建 `backend/data/k_cycle_validation_rules.json` + 3 条 VR 规则
  - VR-K8-01 / VR-K9-01 / VR-K11-01
  - 工时: 0.15 天
  - _Requirements: K-F3_

- [x] 1.4 实现 `check_k_cycle_triangle_reconciliation()` + 注入 consistency_gate
  - 写 `test_k_validation_rules.py`（pass/fail/skip 全覆盖）
  - VR-K11-01 遵循汇总类规则时机铁律
  - 工时: 0.25 天
  - _Requirements: K-F3_

### K-F4: cross_wp_references 新增

- [x] 1.5 追加 ≥ 20 条 K 循环 cross_wp_references（起编运行时 max+1）
  - 5 分组：K内部 / K→跨循环来源 / K→报表 / K→附注 / K→其他循环
  - 写 `test_k_cross_wp_refs.py`（闭区间 + cycle membership 双重过滤）
  - 工时: 0.2 天
  - _Requirements: K-F4_

### K-F6: prefill 扩展

- [x] 1.6 追加 ≥ 40 cells prefill（基于 Sprint 0.X aux 实测结果）
  - K8-2(≥10, =LEDGER_DETAIL 按月度) / K9-2(≥10, =LEDGER_DETAIL 按月度) / K1-2(≥6, =AUX('1221','三方收款标识',code,col)) / K3-2(≥6, =AUX('2241','代收代付类别',code,col)) / K5-2(≥4, =TB, **sheet 名含空格**) / K8-3(≥4, =PREV+TB)
  - 写 `test_k_prefill_extension.py`
  - 工时: 0.15 天
  - _Requirements: K-F6_

---

## Sprint 2 — P1 主体（3.5 天）

### K-F2: sheet 分组

- [x] 2.1 新建 `useKAdminCycleSheetGroups.ts` composable（10 类规则）
  - 索引/程序表/审定表/明细表/分析程序/检查表/费用明细/往来款检查/附注+调整/其他
  - 工时: 0.2 天
  - _Requirements: K-F2_

- [x] 2.2 写 `test_k_sheet_groups.py` + vitest 前端测试
  - 工时: 0.15 天
  - _Requirements: K-F2_

### K-F5: 前置状态横幅

- [x] 2.3 配置 K_CYCLE_PREREQUISITES = [C11] + `^K\d` 路由
  - 扩展 usePrerequisiteStatus 加 K 循环分支
  - 工时: 0.15 天
  - _Requirements: K-F5_

- [x] 2.4 vitest 验证 K8 前置横幅 C11 状态
  - 工时: 0.1 天
  - _Requirements: K-F5_

### K-F7: 费用分析引擎

- [x] 2.5 新建 `backend/app/api/endpoints/wp_k_expense_analysis.py` 路由
  - POST endpoint + RBAC + 3 维度分析 + apply_to_sheet 写回
  - is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动
  - 工时: 0.4 天
  - _Requirements: K-F7, ADR-K4_

- [x] 2.6 写 `test_k_expense_analysis.py`（3 维度 + 写回 + RBAC + 边界）
  - 工时: 0.25 天
  - _Requirements: K-F7_

- [x] 2.7 新建 `ExpenseAnalysisDialog.vue` 前端弹窗
  - 输入表单 + 同比/环比/预算差异结果展示 + 采纳写回按钮
  - 工时: 0.3 天
  - _Requirements: K-F7_

### K-F9: 审计导航图

- [x] 2.8 resolveProcedureSheetKey 加 K8→k8a / K9→k9a / K1→k1a / K5→k5a
  - 工时: 0.1 天
  - _Requirements: K-F9_

### PBT

- [x] 2.9 PBT-P1: Sheet 名归一化幂等性（100 examples）
  - 工时: 0.15 天

- [x] 2.10 PBT-P2: VR-K8-01 费用勾稽正确性（200 + 9 boundary）
  - drift ∈ [-2,2]，passes ↔ |drift| < tolerance
  - 工时: 0.2 天

- [x] 2.11 PBT-P3: K 循环 10 类 sheet 分组完备性（200 examples）
  - 工时: 0.15 天

- [x] 2.12 PBT-P4: cross_wp_ref ref_id 全局唯一（50 examples）
  - 闭区间 + cycle membership
  - 工时: 0.1 天

---

## Sprint 3 — P2 打磨（1.8 天）

### K-F8: K11 资产减值损失汇总引擎

- [x] 3.1 新建 `backend/app/api/endpoints/wp_k_impairment_summary.py` 路由
  - 跨循环汇总（H/I/G/F 减值数据）+ apply_to_sheet + RBAC
  - is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动
  - 工时: 0.35 天
  - _Requirements: K-F8, ADR-K5_

- [x] 3.2 写 `test_k_impairment_summary.py`（汇总逻辑 + 来源缺失处理 + 写回 + is_llm_stub）
  - 工时: 0.2 天
  - _Requirements: K-F8_

- [x] 3.3 新建 `ImpairmentSummaryDialog.vue` 前端弹窗
  - 工时: 0.25 天
  - _Requirements: K-F8_

### K-F10: IPO 占位

- [x] 3.4 `_IPO_CONFIG['K8']` 注册 codes=[] + 单测
  - 验证 D/F/H/I/G/J/L 既有 IPO 触发器回归
  - 工时: 0.1 天
  - _Requirements: K-F10_

### PBT（optional）

- [x]* 3.5 PBT-P5: 费用分析同比单调性（200 examples）
  - current↑ → yoy_change↑（其他参数固定）
  - 工时: 0.2 天

### 回归 + UAT

- [x] 3.6 全量回归测试 + UAT 验收
  - D/F/H/I/G/J/L 循环回归无影响
  - 14 项 UAT 验收
  - 工时: 0.3 天

---

## 已知缺口

| 项 | 决策 | 原因 |
|----|------|------|
| PBT-P5 费用分析单调性 | optional，视工时决定 | 3 维度计算已有单测覆盖 |
| K8/K9 费用率行业对比数据库 | 不做 | 外部数据源，独立 spec |
| LLM 真实接入 | stub | 待 wp_ai_service 升级 |
| K11 汇总来源底稿未保存时 | sources_missing 列表记录，不阻断 | 汇总类时机铁律 |

---

## 测试矩阵

### 单测（pytest）

| 测试文件 | 覆盖 | Sprint |
|---------|------|--------|
| `test_k_merge_dedup.py` | K-F1 合并去重（152→114）+ 0 历史遗留 + 跨文件去重 | S1 |
| `test_k_validation_rules.py` | K-F3 VR-K8-01/K9-01/K11-01（pass/fail/skip 全覆盖）| S1 |
| `test_k_cross_wp_refs.py` | K-F4 ≥ 20 条新增 + ref_id 闭区间 + cycle membership 双重过滤 | S1 |
| `test_k_prefill_extension.py` | K-F6 新增 ≥ 40 cell + 4-arg AUX 校验 + 真实 sheet 名校验 | S1 |
| `test_k_sheet_groups.py` | K-F2 10 类分组规则全覆盖 | S2 |
| `test_k_expense_analysis.py` | K-F7 费用分析 3 维度 + 写回 + RBAC + 边界 | S2 |
| `test_k_impairment_summary.py` | K-F8 减值汇总 + 来源缺失处理 + 写回 + is_llm_stub | S3 |
| `test_k_ipo_trigger.py` | K-F10 注册 + empty result + 全循环 IPO 回归 | S3 |

### PBT（hypothesis）

| PBT | Property | Sprint | max_examples | Validates |
|-----|---------|--------|-------------|-----------|
| P1 | Sheet 名归一化幂等性 | S2 | 100 | K-F1 |
| P2 | VR-K8-01 费用勾稽正确性（drift ∈ [-2,2]）| S2 | 200 + 9 boundary | K-F3 |
| P3 | K 循环 10 类 sheet 分组完备性 | S2 | 200 | K-F2 |
| P4 | cross_wp_ref ref_id 全局唯一 + 闭区间 | S2 | 50 | K-F4 |
| P5* | 费用分析同比单调性 | S3 | 200 | K-F7（optional）|

### 前端测试（vitest）

| 测试文件 | 覆盖 | Sprint |
|---------|------|--------|
| `test_k_sheet_groups.spec.ts` | useKAdminCycleSheetGroups 10 类规则 | S2 |
| `test_k_prerequisite.spec.ts` | K8 前置横幅 C11 状态 | S2 |
| `test_k_audit_nav.spec.ts` | resolveProcedureSheetKey K8→k8a / K9→k9a / K1→k1a / K5→k5a | S2 |
| `ExpenseAnalysisDialog.spec.ts` | 费用分析弹窗 + 写回 | S2 |
| `ImpairmentSummaryDialog.spec.ts` | 减值汇总弹窗 + 写回 | S3 |

### UAT（手动验收，详见 §五）

14 项验收项 + 6 项 P0 关键项门槛（#1/#3/#4/#6/#8/#9）。

---

## 启动条件检查清单

- [x] D spec git commit 锁定
- [x] F spec 44/44 completed + UAT 达标
- [x] H spec 全部完成 + UAT 上线
- [x] I spec 全部完成 + UAT 上线
- [x] G spec 全部完成
- [x] J spec 全部完成（K spec cross_wp_ref 起编依赖 J 执行后的 max ref_id）
- [x] L spec 全部完成（K spec cross_wp_ref 起编依赖 L 执行后的 max ref_id）
- [x] Sprint 0 现状核验通过（N_k_raw_sheets=152 / N_k_dedup_sheets=109 / N_k_historical_sheets=0 / N_k_cross_file_dups=43）
- [x] Sprint 0.X 前置实测完成（aux_type 实测：6601='客户'/6602='区域2'/1221='三方收款标识'/2241='代收代付类别'；K5-2 sheet 名含空格）

**启动条件 7/9 已满足 — 待 J+L spec 执行完毕后启动 Sprint 1**
