# J 职工薪酬循环底稿优化 — Tasks

> **Spec**: workpaper-j-payroll-cycle
> **版本**: v1.1
> **总工时**: 7.3 天 / ~1.5 周（Sprint 0 核验 0.5 天 + Sprint 0.X 前置实测 0.3 天 + Sprint 1 P0 1 天 + Sprint 2 P1 3.5 天 + Sprint 3 P2 2 天）
> **Sprint 数**: 5（Sprint 0 + Sprint 0.X + Sprint 1~3）

## 变更记录

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-05-19 | 三件套实施计划初版 |
| v1.1 | 2026-05-19 | 复盘修复：Sprint 0.X 独立段落 + 测试矩阵分层 + 任务总览对齐 |

## 任务总览

| Sprint | 任务数 | 工时 | 优先级 |
|-------|-------|------|-------|
| Sprint 0 | 3 | 0.35 天 | - |
| Sprint 0.X | 2 | 0.3 天 | - |
| Sprint 1 | 6 | 1 天 | P0 |
| Sprint 2 | 12 | 3.5 天 | P1 |
| Sprint 3 | 6 | 2 天 | P2 |
| **合计** | **29** | **7.15 天** | |

---

## Sprint 0 — 现状核验（0.5 天）

- [x] 0.1 grep 实测 J 循环 prefill + cross_wp_references 基线变量
  - 输出 N_j_prefill_entries / N_j_prefill_cells / N_j_cwr_count / N_cwr_max_id
  - 工时: 0.1 天
  - _Requirements: 附录 A_

- [x] 0.2 openpyxl 提取 J 循环 3 文件真实 sheet 清单
  - 输出 N_j_raw_sheets(38) + 验证 `_should_skip_historical_sheet` 命中数 = 5
  - **关键实测**：核对 `审定表J1-1 ` / `明细表J1-2 ` 末尾空格（已实测确认有）→ prefill cell sheet 字段必须含空格
  - 确认"J1A-原版/L1A-原"不被过滤（保留）
  - 工时: 0.15 天
  - _Requirements: J-F1, J-F6_

- [x] 0.3 输出 Sprint 0 核验报告 + 对齐 3 文档基线
  - 汇总 N_* 基准变量写入 requirements.md 附录 A
  - 工时: 0.1 天

**Sprint 0 验收（3 项）**：
- ○ N_* 基准变量已实测落地 spec 附录 A
- ○ J 循环 3 文件 38 sheet 清单已提取 + 末尾空格确认
- ○ `_should_skip_historical_sheet` J 模板 5 命中确认

---

## Sprint 0.X — 前置实测（0.3 天，Sprint 1 启动前必做）

> **目的**：为 J-F6 prefill ≥ 40 cells 提供真实 aux_type/aux_code 维度数据，避免重蹈 F-F10/H-F10 占位 AUX 名教训

- [x] 0x.1 SQL 实测 tb_aux_balance J 类辅助账维度
  - `SELECT DISTINCT aux_type, aux_code FROM tb_aux_balance WHERE account_code LIKE '221%' LIMIT 50`
  - `SELECT DISTINCT aux_type, aux_code FROM tb_aux_balance WHERE account_code LIKE '4001%' OR account_code LIKE '4002%' LIMIT 50`（J3 股份支付科目修正）
  - 输出 `aux_type_for_2211` / `aux_codes_sample_2211` / `aux_type_for_4001`
  - **如果无数据**：标记 J-F6 降级为仅 =TB/=LEDGER（目标 ≥ 25 cells），更新 design.md ADR-J3
  - 工时: 0.15 天
  - _Requirements: J-F6, ADR-J3_

- [x] 0x.2 openpyxl 提取 J1-2/J1-6/J1-7 明细表真实表头 + 数据区结构
  - 读 `明细表J1-2 ` 前 15 行表头 → 确认薪酬类别维度（8 类是否成立）
  - 读 `计提情况检查表J1-6` 数据区 → 确认月度行结构
  - 读 `分配情况检查表J1-7` 数据区 → 确认部门/成本中心列结构
  - 填入 design.md ADR-J3 "实测结果"段落（替换 TBD 占位）
  - 工时: 0.15 天
  - _Requirements: J-F6, ADR-J3_

**Sprint 0.X 验收（2 项）**：
- ○ ADR-J3 "实测结果"段落 TBD 全部替换为真实数据
- ○ J-F6 目标已确认（正常 ≥ 40 cells 或降级 ≥ 25 cells）

---

## Sprint 1 — P0 核心（1 天）

### J-F1: 合并去重 + 历史遗留过滤

- [x] 1.1 验证 chain_orchestrator 对 J 循环复用 `_merge_sheets_dedup`
  - 确认 J 循环已注册到 chain 合并流程
  - 写 `test_j_merge_dedup.py` 验证 38→≈29 有效 sheet
  - 验证 5 个"-删除"被过滤 + "原版"sheet 保留
  - 工时: 0.15 天
  - _Requirements: J-F1_

- [x] 1.2 验证 `_should_skip_historical_sheet` 对 J 循环 5 个"-删除"命中 + 其余不误过滤
  - 确认"J1A-原版/L1A-原"不被过滤（修改模板前旧版本，保留）
  - 确认 D/F/H/I/G 回归无影响
  - 工时: 0.1 天
  - _Requirements: J-F1_

### J-F3: 三角勾稽 VR 规则

- [x] 1.3 创建 `backend/data/j_cycle_validation_rules.json` + 3 条 VR 规则
  - VR-J1-01 / VR-J1-02 / VR-J1-03
  - 工时: 0.15 天
  - _Requirements: J-F3_

- [x] 1.4 实现 `check_j_cycle_triangle_reconciliation()` + 注入 consistency_gate
  - 写 `test_j_validation_rules.py`（pass/fail/skip 全覆盖）
  - VR-J1-03 遵循汇总类规则时机铁律
  - 工时: 0.25 天
  - _Requirements: J-F3_

### J-F4: cross_wp_references 新增

- [x] 1.5 追加 ≥ 20 条 J 循环 cross_wp_references（起编 CW-293）
  - 5 分组：J内部 / J→费用 / J→报表 / J→附注 / J→N税费
  - 写 `test_j_cross_wp_refs.py`（闭区间 + cycle membership 双重过滤）
  - 工时: 0.2 天
  - _Requirements: J-F4_

### J-F6: prefill 扩展

- [x] 1.6 追加 ≥ 40 cells prefill（基于 Sprint 0.X aux 实测结果）
  - J1-2(≥8) / J1-4(≥6) / J1-6(≥8) / J1-7(≥6) / J2-2(≥4) / J3-2(≥4)
  - 全部 4-arg AUX 或 TB/PREV/LEDGER
  - 写 `test_j_prefill_extension.py`
  - 工时: 0.15 天
  - _Requirements: J-F6_

---

## Sprint 2 — P1 主体（3.5 天）

### J-F2: sheet 分组

- [x] 2.1 新建 `useJPayrollSheetGroups.ts` composable（8 类规则）
  - 索引/程序表/审定表/明细表/分析程序/检查表/IPO专项/附注+调整
  - 工时: 0.2 天
  - _Requirements: J-F2_

- [x] 2.2 写 `test_j_sheet_groups.py` + vitest 前端测试
  - 8 类规则全覆盖 J 循环有效 sheet
  - 工时: 0.15 天
  - _Requirements: J-F2_

### J-F5: 前置状态横幅

- [x] 2.3 配置 J_CYCLE_PREREQUISITES = [C10] + `^J\d` 路由
  - 扩展 usePrerequisiteStatus 加 J 循环分支
  - 工时: 0.15 天
  - _Requirements: J-F5_

- [x] 2.4 vitest 验证 J1 前置横幅 C10 状态
  - 工时: 0.1 天
  - _Requirements: J-F5_

### J-F7: 薪酬计提引擎

- [x] 2.5 新建 `backend/app/api/endpoints/wp_j_payroll_calc.py` 路由
  - POST endpoint + RBAC + apply_to_sheet 写回
  - 工时: 0.4 天
  - _Requirements: J-F7, ADR-J4_

- [x] 2.6 写 `test_j_payroll_calc.py`（计提公式 + 写回 + RBAC + 边界）
  - 工时: 0.25 天
  - _Requirements: J-F7_

- [x] 2.7 新建 `PayrollCalcDialog.vue` 前端弹窗
  - 输入表单 + 结果展示 + 采纳写回按钮
  - 工时: 0.3 天
  - _Requirements: J-F7_

### J-F9: 审计导航图

- [x] 2.8 resolveProcedureSheetKey 加 J1→j1a / J2→j2a / J3→j3a
  - 工时: 0.1 天
  - _Requirements: J-F9_

### PBT

- [x] 2.9 PBT-P1: Sheet 名归一化幂等性（100 examples）
  - 工时: 0.15 天

- [x] 2.10 PBT-P2: VR-J1-01 三角勾稽正确性（200 + 9 boundary）
  - drift ∈ [-2,2]，passes ↔ |drift| < tolerance
  - 工时: 0.2 天

- [x] 2.11 PBT-P3: J 循环 8 类 sheet 分组完备性（200 examples）
  - 工时: 0.15 天

- [x] 2.12 PBT-P4: cross_wp_ref ref_id 全局唯一（50 examples）
  - 闭区间 CW-293~N + cycle membership
  - 工时: 0.1 天

---

## Sprint 3 — P2 打磨（2 天）

### J-F8: 股份支付 Black-Scholes

- [x] 3.1 新建 `backend/app/api/endpoints/wp_j_share_payment.py` 路由
  - BS 公式 + 费用摊销 + apply_to_sheet + RBAC
  - is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动
  - 工时: 0.4 天
  - _Requirements: J-F8, ADR-J5_

- [x] 3.2 写 `test_j_share_payment.py`（BS 公式验证 + 单调性 + 边界 + 写回）
  - 工时: 0.25 天
  - _Requirements: J-F8_

- [x] 3.3 新建 `SharePaymentDialog.vue` 前端弹窗
  - 工时: 0.25 天
  - _Requirements: J-F8_

### J-F10: IPO 占位

- [x] 3.4 `_IPO_CONFIG['J1']` 注册 codes=[] + 单测
  - 验证 D/F/H/I/G 既有 IPO 触发器回归
  - 工时: 0.1 天
  - _Requirements: J-F10_

### PBT（optional）

- [x]* 3.5 PBT-P5: Black-Scholes 单调性（200 examples）
  - S↑→C↑ / K↑→C↓ / σ↑→C↑ / T↑→C↑
  - 工时: 0.2 天

### 回归 + UAT

- [x] 3.6 全量回归测试 + UAT 验收
  - D/F/H/I/G 循环回归无影响
  - 13 项 UAT 验收
  - 工时: 0.3 天

---

## 已知缺口

| 项 | 决策 | 原因 |
|----|------|------|
| PBT-P5 BS 单调性 | optional，视工时决定 | 公式正确性已有单测覆盖 |
| 社保地区政策数据库 | 不做 | 外部数据源，独立 spec |
| LLM 真实接入 | stub | 待 wp_ai_service 升级 |
| J3 科目修正 2211→4001/4002 | Sprint 1 task 1.6 一并修正 | 现有 prefill 数据错位 |
| J1-2/J1-1 末尾空格 | 已标注铁律 | prefill sheet 字段必须含真实空格 |

---

## 测试矩阵

### 单测（pytest）

| 测试文件 | 覆盖 | Sprint |
|---------|------|--------|
| `test_j_merge_dedup.py` | J-F1 合并去重（38→29 sheet）+ 5 删除命中 + 原版保留 + 跨文件去重 | S1 |
| `test_j_validation_rules.py` | J-F3 VR-J1-01/02/03（pass/fail/skip 全覆盖）+ 跨循环 skip 逻辑 | S1 |
| `test_j_cross_wp_refs.py` | J-F4 ≥ 20 条新增 + ref_id 闭区间 CW-293~N + cycle membership 双重过滤 | S1 |
| `test_j_prefill_extension.py` | J-F6 新增 ≥ 40 cell + 4-arg AUX 校验 + 真实 sheet 名（含空格）校验 | S1 |
| `test_j_sheet_groups.py` | J-F2 8 类分组规则全覆盖 29 sheet | S2 |
| `test_j_payroll_calc.py` | J-F7 薪酬计提引擎（多参数组合 + 写回 + RBAC + 边界）| S2 |
| `test_j_share_payment.py` | J-F8 BS 公式验证 + 单调性 + 边界 + 写回 + is_llm_stub config 驱动 | S3 |
| `test_j_ipo_trigger.py` | J-F10 `_IPO_CONFIG['J1']` 注册 + empty result + D/F/H/I/G 回归 | S3 |

### PBT（hypothesis）

| PBT | Property | Sprint | max_examples | Validates |
|-----|---------|--------|-------------|-----------|
| P1 | Sheet 名归一化幂等性 | S2 | 100 | J-F1 |
| P2 | VR-J1-01 三角勾稽正确性（drift ∈ [-2,2]，passes ↔ |drift|<tolerance）| S2 | 200 + 9 boundary | J-F3 |
| P3 | J 循环 8 类 sheet 分组完备性（任意 J sheet 恰好匹配 1 类）| S2 | 200 | J-F2 |
| P4 | cross_wp_ref ref_id 全局唯一 + 闭区间 | S2 | 50 | J-F4 |
| P5* | Black-Scholes 单调性（S↑→C↑ / K↑→C↓ / σ↑→C↑ / T↑→C↑）| S3 | 200 | J-F8（optional）|

### 前端测试（vitest）

| 测试文件 | 覆盖 | Sprint |
|---------|------|--------|
| `test_j_sheet_groups.spec.ts` | useJPayrollSheetGroups 8 类规则 | S2 |
| `PayrollCalcDialog.spec.ts` | 薪酬计提弹窗表单 + 写回 + 结果展示 | S2 |
| `SharePaymentDialog.spec.ts` | BS 弹窗表单 + 写回 | S3 |
| `test_j_prerequisite.spec.ts` | J1 前置横幅 C10 状态 | S2 |
| `test_j_audit_nav.spec.ts` | resolveProcedureSheetKey J1→j1a / J2→j2a / J3→j3a | S2 |

### UAT（手动验收，详见 §五）

15 项验收项 + 6 项 P0 关键项门槛（#1/#3/#4/#6/#8/#9）。

---

## 启动条件检查清单

- [x] D spec git commit 锁定（J spec 依赖 D spec 代码）
- [x] F spec 44/44 completed + UAT 达标
- [x] H spec 全部完成 + UAT 上线
- [x] I spec 全部完成 + UAT 上线
- [x] G spec 全部完成
- [x] requirements.md v1.1 review 完成
- [x] design.md v1.0 review 完成
- [x] Sprint 0 现状核验通过
- [x] Sprint 0.X 前置实测完成（aux_type/aux_code 维度确认）

**启动条件 7/9 已满足 — 待 Sprint 0 + Sprint 0.X 完成后启动 Sprint 1**
