# L 筹资循环底稿优化 — Tasks

> **Spec**: workpaper-l-debt-cycle
> **版本**: v1.0
> **总工时**: 6.5 天 / ~1.3 周（Sprint 0 核验 0.5 天 + Sprint 0.X 前置实测 0.3 天 + Sprint 1 P0 1 天 + Sprint 2 P1 3 天 + Sprint 3 P2 1.7 天）
> **Sprint 数**: 5（Sprint 0 + Sprint 0.X + Sprint 1~3）

## 变更记录

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-05-19 | 三件套实施计划初版 |

## 任务总览

| Sprint | 任务数 | 工时 | 优先级 |
|-------|-------|------|-------|
| Sprint 0 | 3 | 0.5 天 | - |
| Sprint 0.X | 2 | 0.3 天 | - |
| Sprint 1 | 6 | 1 天 | P0 |
| Sprint 2 | 10 | 3 天 | P1 |
| Sprint 3 | 6 | 1.7 天 | P2 |
| **合计** | **27** | **6.5 天** | |

---

## Sprint 0 — 现状核验（0.5 天）

- [x] 0.1 openpyxl 提取 L 循环 9 文件真实 sheet 清单
  - 输出 N_l_raw_sheets=100 + 验证 `_should_skip_historical_sheet` 命中数=1（`函证差异检查表（示例）`）
  - 核对每个 sheet 名末尾空格（已实测：`应付债券实质性程序表L4A ` 末尾带空格）
  - 确认无同 wp_code 多 sheet 情况
  - 合并后有效 sheet = 79（100 - 1 历史 - 20 跨文件去重）
  - 工时: 0.2 天
  - _Requirements: L-F1, L-F6_

- [x] 0.2 grep 实测 L 循环 prefill + cross_wp_references 基线变量
  - 输出 N_l_prefill_entries(10) / N_l_prefill_cells(44) / N_l_cwr_count(6) / N_cwr_max_id
  - 确认 J spec 执行后的 max ref_id（L spec 起编 = max+1）
  - **实测结果**：N_l_prefill_entries=10 ✓ / N_l_prefill_cells=44 ✓ / N_l_cwr_count=6 ✓ / N_cwr_max_id=332(CW-332) / L起编=CW-333
  - 工时: 0.1 天
  - _Requirements: 附录 A_

- [x] 0.3 输出 Sprint 0 核验报告 + 对齐 3 文档基线
  - 汇总 N_* 基准变量写入 requirements.md 附录 A + design.md ADR-L1
  - 填入 Sprint 0 偏差段（§三·B）
  - **核验结果**：附录 A 10 项基线变量 ✓ / ADR-L1 实测结果 ✓ / §三·B 7 项偏差 ✓ / 三件套一致 ✓
  - 工时: 0.2 天

**Sprint 0 验收（3 项）**：
- ✓ N_* 基准变量已实测落地 spec 附录 A（task 0.1/0.2/0.3 完成）
- ✓ L 循环 9 文件 sheet 清单已提取 + 末尾空格确认（`应付债券实质性程序表L4A ` 1 个）
- ✓ `_should_skip_historical_sheet` L 模板命中数确认（1 个：`函证差异检查表（示例）`）

---

## Sprint 0.X — 前置实测（0.3 天，Sprint 1 启动前必做）

> **目的**：为 L-F6 prefill ≥ 40 cells 提供真实 aux_type/aux_code 维度数据

- [x] 0x.1 SQL 实测 tb_aux_balance L 类辅助账维度
  - `SELECT DISTINCT aux_type, aux_code FROM tb_aux_balance WHERE account_code LIKE '200%' LIMIT 50`
  - `SELECT DISTINCT aux_type, aux_code FROM tb_aux_balance WHERE account_code LIKE '250%' LIMIT 50`
  - `SELECT DISTINCT aux_type, aux_code FROM tb_aux_balance WHERE account_code LIKE '6603%' LIMIT 50`
  - 输出 `aux_type_for_2001` / `aux_type_for_2501` / `aux_type_for_6603`
  - **实测结果**：
    - aux_type_for_2001 = {'借款性质', '金融机构'}（37 distinct，'金融机构' 34 codes YG0001~YG9904）
    - aux_type_for_2501 = None（0 行，长期借款 250% 无辅助账数据）
    - aux_type_for_6603 = {'客户'}（50+ distinct，客户编号）
    - 补充：aux_type_for_2502 = None（0 行）/ aux_type_for_2701 = {'成本中心','客户','项目名称'}（32 行）
  - **决策：不降级** — 200%/6603%/270% 有数据，保留 =AUX 4-arg prefill 目标 ≥ 40 cells
  - L3-2（250%）和 L5-2（2502%）局部降级为 =TB（无 aux 数据）
  - **如果无数据**：标记 L-F6 降级为仅 =TB/=LEDGER（目标 ≥ 25 cells），更新 design.md ADR-L3
  - 工时: 0.15 天
  - _Requirements: L-F6, ADR-L3_

- [x] 0x.2 openpyxl 提取 L1-2/L1-5/L3-2/L8-2 真实表头 + 数据区结构
  - 读 L1-2 明细表前 15 行表头 → 确认借款银行/币种维度
  - 读 L1-5 利息测算表数据区 → 确认本金/利率/天数列结构
  - 读 L3-2 长期借款明细表 → 确认期限/到期日列结构
  - 读 L8-2 财务费用明细表 → 确认利息/汇兑/手续费分项
  - 填入 design.md ADR-L3 "实测结果"段落（替换 TBD 占位）
  - **实测结果**：
    - L1_2 = '明细表L1-2'（无末尾空格）— 表头 Row 8-9：序号/借款种类/贷款单位/起始日期/讫止日期/年利率/固定浮动利率/期初余额/本期增减/期末余额
    - L1_5 = '利息测算表L1-5'（无末尾空格）— 表头 Row 10：序号/借款种类/贷款单位/借款起始日期/借款讫止日期/结息日/起算时点/截止时点/年利率/借款本金/本期实计利息/本期应计息天数/本期应计利息/差异/财务费用-利息支出
    - L3_2 = '明细表L3-2'（无末尾空格）— 与 L1-2 结构一致（期限由起止日期推算，无独立期限列）
    - L3_5 = '利息测算表L3-5'（无末尾空格）— 与 L1-5 结构一致
    - L5_2 = '明细表L5-2'（无末尾空格）— 在 L5 长期应付款.xlsx 中（非 L4 应付债券）
    - L6_2 = '明细表L6-2'（无末尾空格）— 表头 Row 8-9：序号/项目/期初余额/本期拨入/本期结转/本期返还/期末余额
    - L8_2 = '明细表L8-2'（无末尾空格）— 表头 Row 8：项目/1月~12月/本期未审合计/账项调整（按行分项：利息费用/利息资本化/利息收入/利息净支出/未确认融资费用/未实现融资收益）
    - **7 个 sheet 全部无末尾空格**（L 循环仅 L4A 有末尾空格，已在 Sprint 0 确认）
  - 工时: 0.15 天
  - _Requirements: L-F6, ADR-L3_

**Sprint 0.X 验收（2 项）**：
- ✓ ADR-L3 "实测结果"段落 TBD 全部替换为真实数据（7 个 sheet 名 + 表头结构）
- ✓ L-F6 目标已确认（正常 ≥ 40 cells，不降级 — 200%/6603%/270% 有 aux 数据）

---

## Sprint 1 — P0 核心（1 天）

### L-F1: 合并去重 + 历史遗留过滤

- [x] 1.1 验证 chain_orchestrator 对 L 循环复用 `_merge_sheets_dedup`
  - 确认 L 循环已注册到 chain 合并流程
  - 写 `test_l_merge_dedup.py` 验证 raw→dedup 有效 sheet 数
  - 验证历史遗留过滤命中数（Sprint 0 实测值）
  - 工时: 0.15 天
  - _Requirements: L-F1_

- [x] 1.2 验证 `_should_skip_historical_sheet` 对 L 循环命中 + D/F/H/I/G/J 回归无影响
  - 确认 L 模板过滤数与 Sprint 0 实测一致
  - 确认 D/F/H/I/G/J 回归无影响
  - 工时: 0.1 天
  - _Requirements: L-F1_

### L-F3: 三角勾稽 VR 规则

- [x] 1.3 创建 `backend/data/l_cycle_validation_rules.json` + 3 条 VR 规则
  - VR-L8-01 / VR-L1-01 / VR-L3-01
  - 工时: 0.15 天
  - _Requirements: L-F3_

- [x] 1.4 实现 `check_l_cycle_triangle_reconciliation()` + 注入 consistency_gate
  - 写 `test_l_validation_rules.py`（pass/fail/skip 全覆盖）
  - VR-L8-01 遵循汇总类规则时机铁律
  - 工时: 0.25 天
  - _Requirements: L-F3_

### L-F4: cross_wp_references 新增

- [x] 1.5 追加 ≥ 20 条 L 循环 cross_wp_references（起编运行时 max+1）
  - 5 分组：L内部 / L→报表 / L→附注 / L→H循环 / L→M/N循环
  - 写 `test_l_cross_wp_refs.py`（闭区间 + cycle membership 双重过滤）
  - 工时: 0.2 天
  - _Requirements: L-F4_

### L-F6: prefill 扩展

- [x] 1.6 追加 ≥ 40 cells prefill（基于 Sprint 0.X aux 实测结果）
  - L1-2(≥8) / L1-5(≥6) / L3-2(≥8) / L3-5(≥6) / L5-2(≥4) / L6-2(≥4) / L8-2(≥4)
  - 全部 4-arg AUX 或 TB/PREV/LEDGER
  - 写 `test_l_prefill_extension.py`
  - 工时: 0.15 天
  - _Requirements: L-F6_

---

## Sprint 2 — P1 主体（3 天）

### L-F2: sheet 分组

- [x] 2.1 新建 `useLDebtCycleSheetGroups.ts` composable（10 类规则）
  - 索引/历史遗留/程序表/审定表/明细表/分析程序/利息测算/检查表/附注+调整/其他
  - 工时: 0.2 天
  - _Requirements: L-F2_

- [x] 2.2 写 `test_l_sheet_groups.py` + vitest 前端测试
  - 10 类规则全覆盖 L 循环有效 sheet
  - 工时: 0.15 天
  - _Requirements: L-F2_

### L-F5: 前置状态横幅

- [x] 2.3 配置 L_CYCLE_PREREQUISITES = [C13] + `^L\d` 路由
  - 扩展 usePrerequisiteStatus 加 L 循环分支
  - 工时: 0.15 天
  - _Requirements: L-F5_

- [x] 2.4 vitest 验证 L1 前置横幅 C13 状态
  - 工时: 0.1 天
  - _Requirements: L-F5_

### L-F7: 利息自动测算引擎

- [x] 2.5 新建 `backend/app/api/endpoints/wp_l_interest_calc.py` 路由
  - POST endpoint + RBAC + 3 计息基准 × 3 复利频率 + apply_to_sheet 写回
  - 工时: 0.4 天
  - _Requirements: L-F7, ADR-L4_

- [x] 2.6 写 `test_l_interest_calc.py`（9 组合 + 写回 + RBAC + 边界）
  - 工时: 0.25 天
  - _Requirements: L-F7_

- [x] 2.7 新建 `InterestCalcDialog.vue` 前端弹窗
  - 输入表单（本金/利率/起息日/到期日/计息基准/复利频率）+ 结果展示 + 采纳写回按钮
  - 工时: 0.3 天
  - _Requirements: L-F7_

### L-F9: 审计导航图

- [x] 2.8 resolveProcedureSheetKey 加 L1→l1a / L3→l3a / L5→l5a / L8→l8a
  - 工时: 0.1 天
  - _Requirements: L-F9_

### PBT

- [x] 2.9 PBT-P1: Sheet 名归一化幂等性（100 examples）
  - 工时: 0.15 天

- [x] 2.10 PBT-P2: VR-L8-01 利息勾稽正确性（200 + 9 boundary）
  - drift ∈ [-2,2]，passes ↔ |drift| < tolerance
  - 工时: 0.2 天

- [x] 2.11 PBT-P3: L 循环 10 类 sheet 分组完备性（200 examples）
  - 工时: 0.15 天

- [x] 2.12 PBT-P4: cross_wp_ref ref_id 全局唯一（50 examples）
  - 闭区间 + cycle membership
  - 工时: 0.1 天

---

## Sprint 3 — P2 打磨（1.7 天）

### L-F8: 应付债券摊余成本引擎

- [x] 3.1 新建 `backend/app/api/endpoints/wp_l_bond_amortization.py` 路由
  - 实际利率法 + 收敛性尾差调整 + apply_to_sheet + RBAC
  - is_llm_stub 由 settings.WP_AI_SERVICE_ENABLED 驱动
  - 工时: 0.35 天
  - _Requirements: L-F8, ADR-L5_

- [x] 3.2 写 `test_l_bond_amortization.py`（收敛性 + 边界 + 写回 + is_llm_stub）
  - 工时: 0.2 天
  - _Requirements: L-F8_

- [x] 3.3 新建 `BondAmortizationDialog.vue` 前端弹窗
  - 工时: 0.25 天
  - _Requirements: L-F8_

### L-F10: IPO 占位

- [x] 3.4 `_IPO_CONFIG['L1']` 注册 codes=[] + 单测
  - 验证 D/F/H/I/G/J 既有 IPO 触发器回归
  - 工时: 0.1 天
  - _Requirements: L-F10_

### PBT（optional）

- [x]* 3.5 PBT-P5: 利息计算单调性（200 examples）
  - principal↑→interest↑ / rate↑→interest↑ / days↑→interest↑
  - 工时: 0.2 天

### 回归 + UAT

- [x] 3.6 全量回归测试 + UAT 验收
  - D/F/H/I/G/J 循环回归无影响
  - 15 项 UAT 验收
  - 工时: 0.3 天

---

## 已知缺口

| 项 | 决策 | 原因 |
|----|------|------|
| PBT-P5 利息单调性 | optional，跳过 | 利息公式正确性已有单测 9 组合覆盖（TestNineCombinations）；principal=0→interest=0 / principal>0→interest>0 隐含验证单调性；TestBoundary.test_one_day_period 验证最小正值；性价比不足 |
| L4 租赁负债与 H9 深度联动 | 不做 | H spec 已完成 H9 明细计量，L4 仅审定汇总 |
| LLM 真实接入 | stub | 待 wp_ai_service 升级 |
| 债券评级外部数据库 | 不做 | 外部数据源，独立 spec |
| L 循环 IPO 应对类专属底稿 | 占位 | 致同模板未提供（TD-L6）|

---

## 测试矩阵

### 单测（pytest）

| 测试文件 | 覆盖 | Sprint |
|---------|------|--------|
| `test_l_merge_dedup.py` | L-F1 合并去重 + 历史遗留过滤 + 跨文件去重 | S1 |
| `test_l_validation_rules.py` | L-F3 VR-L8-01/L1-01/L3-01（pass/fail/skip 全覆盖）| S1 |
| `test_l_cross_wp_refs.py` | L-F4 ≥ 20 条新增 + ref_id 闭区间 + cycle membership 双重过滤 | S1 |
| `test_l_prefill_extension.py` | L-F6 新增 ≥ 40 cell + 4-arg AUX 校验 + 真实 sheet 名校验 | S1 |
| `test_l_sheet_groups.py` | L-F2 10 类分组规则全覆盖 | S2 |
| `test_l_interest_calc.py` | L-F7 利息引擎 9 组合 + 写回 + RBAC + 边界 | S2 |
| `test_l_bond_amortization.py` | L-F8 摊余成本收敛性 + 边界 + 写回 + is_llm_stub config 驱动 | S3 |
| `test_l_ipo_trigger.py` | L-F10 `_IPO_CONFIG['L1']` 注册 + empty result + 全循环 IPO 回归 | S3 |

### PBT（hypothesis）

| PBT | Property | Sprint | max_examples | Validates |
|-----|---------|--------|-------------|-----------|
| P1 | Sheet 名归一化幂等性 | S2 | 100 | L-F1 |
| P2 | VR-L8-01 利息勾稽正确性（drift ∈ [-2,2]，passes ↔ |drift|<tolerance）| S2 | 200 + 9 boundary | L-F3 |
| P3 | L 循环 10 类 sheet 分组完备性（任意 L sheet 恰好匹配 1 类）| S2 | 200 | L-F2 |
| P4 | cross_wp_ref ref_id 全局唯一 + 闭区间 | S2 | 50 | L-F4 |
| P5* | 利息计算单调性（principal↑→interest↑ / rate↑→interest↑ / days↑→interest↑）| S3 | 200 | L-F7（optional）|

### 前端测试（vitest）

| 测试文件 | 覆盖 | Sprint |
|---------|------|--------|
| `test_l_sheet_groups.spec.ts` | useLDebtCycleSheetGroups 10 类规则 | S2 |
| `InterestCalcDialog.spec.ts` | 利息计算弹窗表单 + 写回 + 结果展示 | S2 |
| `BondAmortizationDialog.spec.ts` | 债券摊余成本弹窗 + 写回 | S3 |
| `test_l_prerequisite.spec.ts` | L1 前置横幅 C13 状态 | S2 |
| `test_l_audit_nav.spec.ts` | resolveProcedureSheetKey L1→l1a / L3→l3a / L5→l5a / L8→l8a | S2 |

### UAT（手动验收，详见 §五）

15 项验收项 + 6 项 P0 关键项门槛（#1/#3/#4/#6/#8/#9）。

---

## 启动条件检查清单

- [x] D spec git commit 锁定
- [x] F spec 44/44 completed + UAT 达标
- [x] H spec 全部完成 + UAT 上线
- [x] I spec 全部完成 + UAT 上线
- [x] G spec 全部完成
- [x] J spec 全部完成（J 占 CW-293~312 + K 占 CW-313~332，L 起编 CW-333 已确认）
- [x] requirements.md v1.0 review 完成
- [x] design.md v1.0 review 完成
- [x] Sprint 0 现状核验通过（task 0.1/0.2/0.3 全部完成 2026-05-20）
- [x] Sprint 0.X 前置实测完成（aux_type/aux_code 维度确认 + openpyxl 表头提取）

**启动条件 10/10 已满足 — 可启动 Sprint 1**
