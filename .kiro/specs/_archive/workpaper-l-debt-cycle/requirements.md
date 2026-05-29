# L 筹资循环底稿优化 — Requirements

> **Spec**: `workpaper-l-debt-cycle`
> **版本**: v1.0
> **依赖前置 spec**：`workpaper-d-sales-cycle` ✅ + `workpaper-h-fixed-assets-cycle` ✅ + `workpaper-j-payroll-cycle` ✅ + `workpaper-k-admin-cycle` ✅
> **基线日期**: 2026-05-19（Sprint 0 实测基线）

## 变更记录

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-05-19 | 三件套需求初版 — Sprint 0 实测基线 + 10 项功能需求 + EARS 范式 + 8 章标准结构 |

---

## 〇、依赖矩阵

| 上游 spec | 状态 | 本 spec 依赖 | Fallback |
|-----------|------|------------|---------|
| `workpaper-d-sales-cycle` | ✅ 53/53 | `_normalize_sheet_name` / `_merge_sheets_dedup` / `_should_skip_historical_sheet` / PBT 模式 / 4-arg AUX 约定 / cross_wp_ref 起编 max+1 模式 | D spec 必须先 commit |
| `workpaper-h-fixed-assets-cycle` | ✅ 全部完成 | H-F11 折旧引擎跨 spec 复用模式 / VR 三角勾稽模式 / consistency_gate 集成 / `_ensure_ipo_loaded(prefix)` 通用化 | H spec 必须先 commit |
| `workpaper-f-purchase-inventory` | ✅ 44/44 | `apply_to_sheet` 写回联动模式 / `require_project_access("edit")` RBAC / cross_wp_references 起编 max+1 | - |
| `workpaper-j-payroll-cycle` | ✅ 全部完成 | J spec 起编 CW-293~312，K spec CW-313~332，L spec 起编 CW-333 | - |
| `global-linkage-bus` | ✅ | LinkageGraphBuilder / stale_engine / cross-ref:updated 事件 | - |

---

## 一、为什么做（业务/技术根因）

### 1.1 业务痛点（7 类核心问题）

1. **借款利息重算无自动引擎**：L1 短期借款 / L3 长期借款的利息测算表（L1-5 / L3-5）需按合同利率 × 本金 × 天数/360 逐笔重算，当前无统一利息计算引擎，靠手工填或 Univer 内置公式分散维护
2. **长短期借款重分类无自动校验**：长期借款到期日 ≤ 1 年部分应重分类为"一年内到期的非流动负债"，当前无 VR 规则校验重分类金额是否正确
3. **应付债券摊余成本计量复杂**：L5 应付债券需按实际利率法计算摊余成本（面值 + 利息调整），当前无计算引擎
4. **财务费用（L8）与各借款利息测算表无自动勾稽**：L8 利息支出应 = L1 利息 + L3 利息 + H9 租赁利息 + L5 债券利息，当前仅有 CW-09/CW-10/CW-14 三条 cross_wp_ref，缺少 L5→L8 等路径
5. **B/C 前置底稿无联动**：C13（债务循环控制测试）与 L1A 程序执行无前置状态驱动
6. **跨循环联动缺失**：L 循环与 H9 租赁负债（已在 H spec 处理）/ M 权益（股利分配）/ N 税费（利息代扣税）联动路径不完整
7. **prefill 仅覆盖审定表层（10 entries / 44 cells）**：明细表 / 利息测算 / 逾期贷款检查 / 债券摊余成本 / 预计负债明细 全部空白

### 1.2 技术根因

1. **prefill_formula_mapping L 类覆盖不足（10 entries / 44 cells）**：仅审定表 + 1 个分析程序有 prefill；明细表 / 利息测算 / 逾期贷款检查 / 债券摊余成本 / 预计负债明细 全部空白
2. **cross_wp_references L 相关仅 6 条**（CW-09 L1→L8 / CW-10 L3→L8 / CW-14 H9→L8 / CW-53 L1→附注 / CW-54 L1→报表 / CW-101 L1→L8 利率），目标新增 ≥ 20 条
3. **`_should_skip_historical_sheet` 对 L 循环模板命中数已确认**（Sprint 0 实测：仅 1 个"（示例）"命中，无需扩展 regex）
4. **L4 租赁负债与 H9 重叠**：wp_account_mapping.json 中 L4 account_codes=['2601'] 与 H9 同科目，需明确边界（L4 审定表 vs H9 明细计量）

### 1.3 本 spec 边界

- ✅ **本 spec 做**：L0~L8 共 9 主底稿优化（L-F1 至 L-F10）
- ❌ **不做**：H9 租赁负债明细计量（已在 H spec 完成）/ M 权益循环 / 债券评级外部数据库 / LLM 真实接入

---

## 一·B、Sprint 0 实测基线（附录 A）

| 变量 | 实测值 | 来源 |
|------|-------|------|
| `N_l_files` | 9 | `wp_templates/L/` 目录扫描（L0~L8）|
| `N_l_raw_sheets` | 100 | openpyxl 全文件 sheet 累加 |
| `N_l_historical_sheets` | 1 | `函证差异检查表（示例）`（L0 文件，"（示例）"模式命中）|
| `N_l_dedup_sheets` | 79 | 100 raw - 1 历史 - 20 跨文件去重 = 79 有效 |
| `N_l_cross_file_dups` | 20 | 底稿目录(9×→8dup)/GT_Custom(4×→3dup)/附注披露信息核对(上市)(3×→2dup)/附注披露信息(上市)(3×→2dup)/附注披露信息(国企)(3×→2dup)/附注披露信息核对(国企)(2×→1dup)/附注披露(国企)信息(2×→1dup)/附注披露(上市)信息(2×→1dup) = 20 |
| `N_l_trailing_space_sheets` | 1 | `应付债券实质性程序表L4A `（L4 文件，末尾带空格）|
| `N_l_prefill_entries` | 10 | `prefill_formula_mapping.json` 中 wp_code 以 L 开头的 entry |
| `N_l_prefill_cells` | 44 | 同上，全部 cells 累加（L0:2 + L1:5 + L2:5 + L3:5 + L4:5 + L5:5 + L6:5 + L7:5 + L8:5 + L1分析:2）|
| `N_l_cwr_count` | 6 | source_wp=L 或 target wp_code=L 的条目（CW-09/10/14/53/54/101）|
| `N_cwr_max_id_numeric` | 332 | 全仓 ref_id 数值最大值（J 占 CW-293~312 + K 占 CW-313~332）|
| `N_l_cwr_start` | 333 | Sprint 0 task 0.2 实测确认：max=CW-332，L spec 起编 CW-333 |

**当前 L prefill 10 entries 全部仅覆盖审定表 + 1 个分析程序**：

```
L0  审定表L0-1            cells=2  (TB_SUM)
L1  审定表L1-1            cells=5  (TB+ADJ+PREV)
L2  审定表L2-1            cells=5  (TB+ADJ+PREV)
L3  审定表L3-1            cells=5  (TB+ADJ+PREV)
L4  审定表L4-1            cells=5  (TB+ADJ+PREV)
L5  审定表L5-1            cells=5  (TB+ADJ+PREV)
L6  审定表L6-1            cells=5  (TB+ADJ+PREV)
L7  审定表L7-1            cells=5  (TB+ADJ+PREV)
L8  审定表L8-1            cells=5  (TB+ADJ+PREV)
L1  分析程序L1-3          cells=2  (PREV+TB_SUM)
```

**当前 6 条 L 相关 cross_wp_references**：
- CW-09: L1 利息测算→L8 财务费用
- CW-10: L3 利息测算→L8 财务费用
- CW-14: H9 租赁利息→L8 财务费用
- CW-53: L1 审定数→附注 5.13
- CW-54: L1 审定数→报表 BS-020
- CW-101: L1 借款利率→L8 利息重算

---

## 二、关键业务发现（Sprint 0 openpyxl 实测已确认 2026-05-20）

### A. L 循环模板历史遗留情况（已实测确认）
- ✅ L 循环模板干净（2025 修订），仅 1 个"（示例）"历史遗留
- 无"-删除"/ 无"修订前"/ 无"（原）"/ 无 G+数字+删除移至
- 不需要扩展 `_should_skip_historical_sheet` regex

### B. L4 租赁负债与 H9 边界
- wp_account_mapping.json: L4 account_codes=['2601']（租赁负债）
- H9 已在 H spec 完成明细计量（H9-2 租赁负债明细 / H9-3 未确认融资费用）
- **L4 定位**：审定表层汇总 + 与 H9 的 cross_wp_ref 联动（L4 审定数 = H9 审定数）
- 不重复 H9 的明细计量逻辑

### C. L8 财务费用是 L 循环汇总枢纽
- L8 利息支出 = L1 短期借款利息 + L3 长期借款利息 + H9 租赁利息 + L5 债券利息
- L8 汇兑损益 = 外币借款汇率变动（独立计算）
- L8 手续费 = 银行手续费（独立科目 6603.03）
- **VR-L8-01 三角勾稽**：L8 利息支出 = Σ(各借款利息测算表汇总)

### D. 利息测算表是 L 循环核心计算底稿
- L1-5 短期借款利息测算 / L3-5 长期借款利息测算
- 公式：利息 = 本金 × 年利率 × 天数 / 360（或 365）
- 需独立利息计算引擎（类比 H-F11 折旧引擎）

### E. 前置底稿：C13 债务循环业务层面控制测试
- 实测确认 `backend/wp_templates/C/C13 债务循环业务层面控制测试.xlsx` 存在
- C13-2 债务循环评价控制偏差 也存在
- B23/B51 类无 L 循环专项底稿（与 H/I/J spec 同款情况）

---

## 三、功能需求（L-F1 至 L-F10）

> 命名规则：`L-F<n>` 与 D/F/H/I/J spec 保持一致；EARS 范式按 H spec v1.2 标准。

### L-F1 多文件合并 + 历史遗留过滤
- **优先级**：P0
- **依赖**：复用 `_merge_sheets_dedup` + `_should_skip_historical_sheet`（D/F spec 已实现，0 改动）
- **User Story**：As a 审计助理，I want L 循环 9 文件合并后自动去除历史遗留 sheet 和跨文件重复 sheet，so that 合并后 sheet 列表干净。
- **Acceptance Criteria（EARS）**：
  1. WHEN L 循环 9 文件合并加载时, THE chain_orchestrator SHALL 调用 `_merge_sheets_dedup` 对全部 raw sheet 执行去重
  2. THE `_should_skip_historical_sheet` SHALL 对 L 循环模板执行过滤（命中数待 Sprint 0 实测确认）
  3. WHEN 跨文件出现同名 sheet（底稿目录 / GT_Custom / 附注披露信息）, THE chain_orchestrator SHALL 按归一化名称去重保留首次出现
  4. THE 系统 SHALL 复用 D spec 已实现的 `_normalize_sheet_name` 函数（0 代码改动）
  5. WHEN 合并完成后, THE chain_orchestrator SHALL 输出 `N_l_dedup_sheets = 79`（实测：100 raw - 1 历史 - 20 跨文件 = 79）
- **量化指标**：合并后有效 sheet 数 = 79；1 个"（示例）"历史遗留过滤；`应付债券实质性程序表L4A ` 末尾带空格（prefill 需注意）

### L-F2 L 循环 sheet 分组（10 类规则）
- **优先级**：P1
- **依赖**：复用 `useDSalesCycleSheetGroups` 模式新建 `useLDebtCycleSheetGroups.ts`
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 按 10 类分组 L 循环 sheet：索引 / 程序表 / 审定表 / 明细表 / 分析程序 / 利息测算 / 逾期贷款检查 / 债券摊余成本 / 附注披露+调整分录 / 其他程序
  2. THE 索引 + 附注披露类 SHALL 设 `defaultHidden=true`，附注披露 SHALL 设 `readonly=true`
  3. WHEN 任意 L 真实 sheet 名输入 10 类规则时, THE 系统 SHALL 命中**恰好 1 类**（PBT 验证）
  4. THE 分组规则 SHALL 覆盖 L0~L8 全部有效 sheet
- **量化指标**：10 类规则覆盖全部有效 sheet；fallback 兜底 0 漏

### L-F3 三角勾稽 VR 规则（≥ 3 条）
- **优先级**：P0
- **依赖**：复用 `consistency_gate.check_*_triangle_reconciliation` 模式
- **User Story**：As a 合伙人，I want 财务费用利息勾稽 / 借款期末余额勾稽自动校验，so that L 类底稿数据异常能及时发现。
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 新增 ≥ 3 条 validation_rules：
     - **VR-L8-01**（blocking, tolerance=1.0）：L8 利息支出 = L1 利息测算汇总 + L3 利息测算汇总 + H9 租赁利息 + L5 债券利息
     - **VR-L1-01**（blocking, tolerance=1.0）：L1 期末 = L1 期初 + 本期新增借款 − 本期偿还借款
     - **VR-L3-01**（warning, tolerance=1.0）：L3 长期借款期末 + 一年内到期重分类 = L3 期初 + 本期新增 − 本期偿还
  2. WHEN VR-L8-01 / VR-L1-01 blocking 校验失败时, THE ConsistencyGatePanel SHALL 阻断 L8 / L1 底稿签字
  3. WHEN VR-L3-01 warning 触发时, THE ConsistencyGatePanel SHALL 显示告警但不阻断签字
  4. **IF** VR-L8-01 涉及的跨循环目标（H9 租赁利息）未保存, **THEN** THE 系统 SHALL skip 不 blocking（汇总类规则时机铁律）
  5. THE VR 规则 SHALL 写入 `backend/data/l_cycle_validation_rules.json`
- **量化指标**：≥ 3 条 VR 各至少 1 个 pass / 1 个 fail / 1 个 skip 测试

### L-F4 cross_wp_references 新增 ≥ 20 条
- **优先级**：P0
- **依赖**：复用 F-F7 ref_id 起编模式（基于运行时 max(ref_id)+1）
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 起编基于运行时 `max(ref_id)+1`（J spec 执行完毕后确定具体起编号）
  2. THE 系统 SHALL 按 5 分组新增 ≥ 20 条 cross_wp_references：
     - **L 内部联动**（≥ 5）：L1-5 利息→L8 / L3-5 利息→L8 / L5 债券利息→L8 / L1 短期→L4 重分类 / L3 长期→L4 重分类
     - **L→报表**（≥ 4）：L1→BS-020 / L3→BS-040 / L5→BS-040 / L8→PL 利润表
     - **L→附注**（≥ 4）：L1→附注 5.13 / L3→附注 5.18 / L5→附注 5.19 / L8→附注 5.30
     - **L→H 循环**（≥ 3）：L4→H9 租赁负债 / L8 利息资本化→H2 在建工程 / L3→H1 抵押资产
     - **L→M/N 循环**（≥ 4）：L8 汇兑→M 权益 / L1 利息代扣→N1 税费 / L5 债券利息→N1 代扣税 / L3→M 股利分配
  3. THE 闭区间 SHALL 为 CW-X ~ CW-(X+N-1)，N ≥ 20（X = 运行时 max+1）
  4. WHEN 测试用闭区间过滤时, THE 测试 SHALL 同时按 cycle membership 过滤（source_wp 或 target wp_code 以 L 开头）— 跨 spec 双重过滤铁律
  5. THE severity 比例 SHALL 满足 info < 25%（CWR severity 健康度铁律）
- **量化指标**：N_l_cwr_count 6 → ≥ 26（基线 6 + 新增 ≥ 20）

### L-F5 B/C 类前置状态横幅
- **优先级**：P1
- **依赖**：复用 `usePrerequisiteStatus.ts` 加 L_CYCLE_PREREQUISITES
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 配置 `L_CYCLE_PREREQUISITES = [C13]`（债务循环业务层面控制测试，实测真实编号）
  2. WHEN wp_code 匹配 `^L\d` 正则, THE usePrerequisiteStatus SHALL 加载 C13 前置状态
  3. THE 横幅状态 SHALL 按 ready / partial / blocked 三档展示（参照 F/H/J spec 模式）
  4. **NOTE**：B23/B51 类无 L 循环专项底稿（与 H/I/J spec 同款情况）
- **量化指标**：L1 顶部前置横幅可见，wp_code 路由按 `^L\d` 命中 C13

### L-F6 prefill 扩展 ≥ 40 cells
- **优先级**：P0
- **依赖**：openpyxl 实测真实 sheet 名 + 4-arg AUX 强制约定
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 新增 prefill cells ≥ 40，目标分布：
     - L1-2 短期借款明细表：≥ 8 cell（=AUX 按借款银行/币种维度）
     - L1-5 利息测算表：≥ 6 cell（=LEDGER 按月利息 + =TB 本金）
     - L3-2 长期借款明细表：≥ 8 cell（=AUX 按借款银行/期限维度）
     - L3-5 利息测算表：≥ 6 cell（=LEDGER 按月利息）
     - L5-2 应付债券明细表：≥ 4 cell（=TB 面值/利息调整）
     - L6-2 长期应付款明细表：≥ 4 cell（=TB）
     - L8-2 财务费用明细表：≥ 4 cell（=TB 利息/汇兑/手续费分项）
  2. THE 全部 cell 公式 SHALL 用 4-arg `=AUX(account_code, aux_type, aux_code, column)` 或 =TB / =PREV / =LEDGER
  3. **Sprint 0.X 前置实测要求**（实施前必做）：
     - SQL `SELECT DISTINCT aux_type, aux_code FROM tb_aux_balance WHERE account_code LIKE '200%' OR account_code LIKE '250%' LIMIT 50` 确认真实 aux 维度
     - openpyxl 读 L1-2 / L3-2 / L1-5 / L8-2 真实表头确认列结构
     - **降级方案**：如 tb_aux_balance 无 200%/250% 数据 → prefill 降级为仅 =TB/=LEDGER，目标降为 ≥ 25 cells
  4. THE 全部 sheet 字段 SHALL 与 openpyxl 读出真名完全一致（含末尾空格 / 全角括号），用 `repr(name)` 核对
- **量化指标**：N_l_prefill_cells 44 → ≥ 84（新增 ≥ 40，降级目标 ≥ 69）

### L-F7 利息自动测算引擎
- **优先级**：P1（核心增量，独立于 LLM 可测试）
- **依赖**：新建 `wp_l_interest_calc` 路由
- **User Story**：As a 审计助理，I want 输入"本金/年利率/起息日/到期日/计息基准"后系统自动计算利息，so that 我不需要手工填利息测算表。
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 提供 endpoint `POST /api/projects/{pid}/workpapers/{wid}/l/interest-calc`（L1/L3 共用，通过请求体 `wp_code: 'L1' | 'L3'` 区分写回目标）
  2. THE endpoint SHALL 接受 `principal / annual_rate / start_date / end_date / day_count_basis('ACT/360' | 'ACT/365' | '30/360') / compound_frequency('simple' | 'monthly' | 'quarterly')` 输入
  3. THE endpoint SHALL 返回 `interest_amount / daily_interest / period_days / calculation_detail` 输出
  4. THE endpoint SHALL 使用 `Depends(require_project_access("edit"))` RBAC 校验
  5. WHEN 请求 body 含 `apply_to_sheet: str` 字段时, THE 系统 SHALL 把计算结果写回 `working_paper.parsed_data.interest_calcs[sheet]`
  6. **业务正确性约束**：简单利息 = 本金 × 年利率 × 天数 / day_count_basis；复利按频率复合
- **量化指标**：3 种计息基准 × 3 种复利频率 = 9 组合至少各 1 个测试 + 写回联动 + RBAC

### L-F8 应付债券摊余成本引擎（stub）
- **优先级**：P2
- **依赖**：新建 `wp_l_bond_amortization` 路由
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 提供 endpoint `POST /api/projects/{pid}/workpapers/{wid}/l5/bond-amortization`
  2. THE endpoint SHALL 接受 `face_value / issue_price / coupon_rate / effective_rate / term_years / payment_frequency` 输入
  3. THE endpoint SHALL 实现实际利率法：每期利息费用 = 期初摊余成本 × 实际利率；每期摊销 = 利息费用 − 票面利息
  4. THE endpoint SHALL 返回 `amortization_schedule[] / total_interest_expense / final_carrying_amount / is_llm_stub`
  5. THE `is_llm_stub` 字段 SHALL 由 `settings.WP_AI_SERVICE_ENABLED` 驱动（stub 标志铁律）
  6. WHEN face_value=0 OR effective_rate=0 OR term_years=0 时, THE endpoint SHALL 返回 HTTP 400
  7. THE endpoint SHALL 支持 `apply_to_sheet` 写回
- **量化指标**：摊余成本收敛性测试（最终 carrying_amount = face_value ± 0.01）+ 边界 case + RBAC

### L-F9 L1A 审计导航图
- **优先级**：P2
- **依赖**：复用 WorkpaperAuditNav 组件 + `resolveProcedureSheetKey` 加 L 循环路由
- **Acceptance Criteria（EARS）**：
  1. THE `resolveProcedureSheetKey` SHALL 加 `L1→l1a` / `L3→l3a` / `L5→l5a` / `L8→l8a` 路由
  2. WHEN 用户首次打开 L1 底稿, THE 系统 SHALL 默认展开审计导航图（与 H/J spec 同模式）
- **量化指标**：vitest 验证 sheetKey 路由 4/4 正确

### L-F10 IPO 专项触发器（占位实现）
- **优先级**：P2
- **依赖**：复用 `_ensure_ipo_loaded(prefix='L1')`
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 在 `_IPO_CONFIG` 注册 `'L1'` 入口，`codes=[]`（占位）
  2. WHEN 调用 `_ensure_ipo_loaded(prefix='L1')` 时, THE 函数 SHALL 不抛异常，返回 `{prefix:'L1', added_codes:[], skipped_existing:[], errors:[]}`
  3. THE D/F/H/I/G/J 既有 IPO 触发器 SHALL 不受影响（回归保留）
  4. **TD-L6**（新增技术债）：用户后续提供 L 循环 IPO 应对类专属模板后再立 spec 接入触发器
- **量化指标**：单测验证 `_IPO_CONFIG['L1']` 注册 + empty result + D/F/H/I/G/J 既有 IPO 触发器测试全过

---

## 三·B、Sprint 0 关键偏差发现（2026-05-19 openpyxl 实测）

| # | 起草前假设 | Sprint 0 实测 | 偏差影响 | 修正方案 |
|---|----------|--------------|---------|---------|
| 1 | L 循环 9 文件可能含"-删除"等历史遗留 | ✅ 仅 1 个"（示例）"命中（`函证差异检查表（示例）` in L0），无"-删除"/无"修订前"/无"（原）" | 无偏差（L 模板干净） | 不需扩展 `_should_skip_historical_sheet` |
| 2 | L1-2/L3-2 明细表 sheet 名无末尾空格 | ✅ 仅 `应付债券实质性程序表L4A ` 末尾带空格（L4 文件） | prefill sheet 字段需含真实空格 | 已确认 1 个 trailing space |
| 3 | tb_aux_balance 200%/250% 有辅助账数据 | 待 Sprint 0.X 实测 | 影响 L-F6 prefill 目标 | 降级方案已备 |
| 4 | L 循环无同 wp_code 多 sheet 问题 | ✅ 无同 wp_code 多 sheet | 无偏差 | 不需 H-F1b 分支选择器 |
| 5 | 跨文件去重 = 19 | ⚠ 实测 = 20（8 类去重目标，比预估多 1 个附注披露变体） | dedup_sheets = 79（非 80） | 已修正三件套基线 |
| 6 | C13 前置底稿存在且可用 | ✅ 已确认 | 无偏差 | C13 + C13-2 均存在 |
| 7 | cross_wp_ref 起编基于 J spec max CW-312 | ⚠ Sprint 0 实测 max=CW-332（K spec 占 CW-313~332） | L 起编 = CW-333（非原假设 CW-313） | L spec 起编必须运行时 `max(ref_id)` grep 确认实际 max+1，禁止硬编码假设值 |

---

## 四、非功能需求

### 4.1 性能

| 指标 | 目标 | 参照 |
|------|------|------|
| chain 生成 L 循环 9 主底稿 | < 30s（L 循环 9 文件，规模介于 J(3) 和 H(11) 之间）| H spec < 60s / J spec < 15s |
| L1 单底稿打开 | < 5s | F spec F2 同基线 |
| L 循环 sheet 分组导航切换 | < 200ms | F/H/J spec |
| L-F3 VR 三角勾稽校验（≥ 3 条规则）| < 500ms | H spec VR-H1 |
| L-F4 cross_wp_ref stale 传播 | < 500ms | E1 spec |
| L-F7 利息引擎单次计算 | < 100ms（纯算法，无 DB IO）| H-F11 折旧引擎 |
| L-F8 债券摊余成本计算（20 期序列）| < 200ms | 新增 |

### 4.2 兼容性 / 回归白名单

**必须不破坏的现有循环**：
- ✅ D 销售循环（53 task + 20 UAT pass）
- ✅ E1 货币资金循环（91 task pass）
- ✅ F 采购存货循环（44 task + UAT 上线）
- ✅ H 固定资产循环（全部完成 + UAT 上线）— 特别注意 H9 租赁负债与 L4 边界
- ✅ I 无形资产循环（全部完成 + UAT 上线）
- ✅ G 投资循环（全部完成）
- ✅ J 职工薪酬循环（全部完成 + UAT 达标，L spec 不修改 J 相关代码）

**关键兼容性约束**：
- THE L spec SHALL NOT 修改 `_normalize_sheet_name` 函数签名或行为
- THE L spec SHALL NOT 修改 `_should_skip_historical_sheet` 现有 4 模式
- THE L spec SHALL NOT 修改 `_ensure_ipo_loaded(prefix)` 通用接口（仅追加 `_IPO_CONFIG['L1']` 注册）
- THE L spec SHALL NOT 修改 H9 租赁负债相关逻辑（H spec 已完成）
- THE L spec SHALL NOT 引入新 vue 依赖
- WHEN 修改 `usePrerequisiteStatus.ts` 路由时, THE L spec SHALL 仅追加 `^L\d` 命中分支
- WHEN 新增 cross_wp_references 时, THE L spec SHALL 起编基于运行时 max(ref_id)+1（禁止硬编码）
- WHEN 新增 prefill cells 时, THE L spec SHALL 用 `(wp_code, sheet)` 作幂等保护 key

### 4.3 可观测性

- L-F1 合并去重日志记录 `chain_executions.merge_dedup_summary`（D/F spec 已实现）
- L-F3 VR-L8-01/L1-01/L3-01 校验结果写入 `validation_rule_results` 表
- L-F4 stale 传播写 `linkage_audit_log`
- L-F7 利息引擎计算日志写 `wp_calculation_log`（principal + rate + days + result）
- L-F8 债券摊余成本 stub 调用日志写 `wp_ai_call_log`（含 is_llm_stub 字段）
- L-F5 前置状态查询日志写 `prerequisite_status_log`

---

## 五、UAT 验收清单

| # | 验收项 | 需求 | P | Status |
|---|-------|------|---|--------|
| 1 | 9 文件合并后有效 sheet = 79，1 个"（示例）"历史遗留过滤 + 20 跨文件去重 | L-F1 | P0 | ○ |
| 2 | L 循环 sheet 列表按 10 类分组 + 折叠展开 | L-F2 | P1 | ○ |
| 3 | VR-L8-01 blocking 阻断 L8 签字（利息勾稽）| L-F3 | P0 | ○ |
| 4 | VR-L1-01 blocking 阻断 L1 签字（借款余额勾稽）| L-F3 | P0 | ○ |
| 5 | VR-L3-01 warning 长期借款重分类提示 | L-F3 | P1 | ○ |
| 6 | cross_wp_ref L 循环条目 ≥ 26（基线 6 + 新增 ≥ 20）| L-F4 | P0 | ○ |
| 7 | L1 顶部前置横幅显示 C13 状态 | L-F5 | P1 | ○ |
| 8 | L1-2 短期借款明细表 prefill ≥ 8 cell | L-F6 | P0 | ○ |
| 9 | L1-5 利息测算表 prefill ≥ 6 cell | L-F6 | P0 | ○ |
| 10 | L3-2 长期借款明细表 prefill ≥ 8 cell | L-F6 | P1 | ○ |
| 11 | L8-2 财务费用明细表 prefill ≥ 4 cell | L-F6 | P1 | ○ |
| 12 | 利息引擎 3 种计息基准 × 写回 + RBAC | L-F7 | P1 | ○ |
| 13 | 债券摊余成本引擎 + is_llm_stub config 驱动 + 写回 | L-F8 | P2 | ○ |
| 14 | L1/L3/L5/L8 审计导航图 sheetKey 路由 | L-F9 | P2 | ○（**预期 ⚠ partial**）|
| 15 | `_IPO_CONFIG['L1']` 注册 codes=[] + D/F/H/I/G/J IPO 回归全过 | L-F10 | P2 | ○ |

**上线门槛**：
- ≥ 12 项 ✓ pass + **P0 关键项**（#1, #3, #4, #6, #8, #9）必须**全部** ✓ pass
- P0 共 6 项，与 J spec 同量级

---

## 五·B、成功判据汇总

| 类别 | 验收项 | 量化指标 |
|------|-------|---------|
| **合并去重（P0）** | L-F1 9 文件合并 | raw → `N_l_dedup_sheets`（Sprint 0 实测）|
| **导航体验（P1）** | L-F2 sheet 分组 | 10 类规则全覆盖 L 循环有效 sheet |
| | L-F5 前置横幅 | C13 状态可视 |
| **勾稽联动（P0）** | L-F3 三角勾稽 | ≥ 3 条 VR + VR-L8-01/L1-01 blocking 阻断签字 |
| | L-F4 cross_wp_ref | ≥ 20 条新增（运行时 max+1 起编，目标 N_l_cwr ≥ 26）|
| **数据覆盖（P0）** | L-F6 prefill | 44 → ≥ 84 cell（新增 ≥ 40，降级目标 ≥ 69）|
| **智能辅助（P1/P2）** | L-F7 利息引擎 | 3 计息基准 × 3 复利频率 + apply_to_sheet 写回 + RBAC |
| | L-F8 债券摊余成本 | 实际利率法 + is_llm_stub config 驱动 + 收敛性验证 |
| **导航/触发（P2）** | L-F9 审计导航图 | sheetKey=l1a/l3a/l5a/l8a 路由 |
| | L-F10 IPO 占位 | `_IPO_CONFIG['L1']` 注册 + 占位 codes=[] + 全循环 IPO 回归 |

---

## 六、测试矩阵

### 6.1 单测（pytest）

| 测试文件 | 覆盖 |
|---------|------|
| `test_l_merge_dedup.py` | L-F1 9 文件合并去重 + 历史遗留过滤 + 跨文件去重 |
| `test_l_sheet_groups.py` | L-F2 10 类分组规则全覆盖 |
| `test_l_validation_rules.py` | L-F3 VR-L8-01/L1-01/L3-01（pass/fail/skip 全覆盖）|
| `test_l_cross_wp_refs.py` | L-F4 ≥ 20 条新增 + ref_id 闭区间 + cycle membership 双重过滤 |
| `test_l_prefill_extension.py` | L-F6 新增 ≥ 40 cell + 4-arg AUX 校验 + 真实 sheet 名校验 |
| `test_l_interest_calc.py` | L-F7 利息引擎 9 组合 + 写回 + RBAC + 边界 |
| `test_l_bond_amortization.py` | L-F8 摊余成本收敛性 + 边界 + 写回 + is_llm_stub |
| `test_l_ipo_trigger.py` | L-F10 `_IPO_CONFIG['L1']` 注册 + empty result + 全循环 IPO 回归 |

### 6.2 PBT（hypothesis）

| PBT | Property | Sprint | max_examples | Validates |
|-----|---------|--------|-------------|-----------|
| P1 | Sheet 名归一化幂等性 | S1 | 100 | L-F1 |
| P2 | VR-L8-01 利息勾稽正确性（drift ∈ [-2,2]，passes ↔ |drift|<tolerance）| S2 | 200 + 9 boundary | L-F3 |
| P3 | L 循环 10 类 sheet 分组完备性（任意 L sheet 恰好匹配 1 类）| S2 | 200 | L-F2 |
| P4 | cross_wp_ref ref_id 全局唯一 + 闭区间 | S2 | 50 | L-F4 |
| P5* | 利息计算单调性（principal↑→interest↑ / rate↑→interest↑ / days↑→interest↑）| S3 | 200 | L-F7（optional）|

### 6.3 前端测试（vitest）

| 测试文件 | 覆盖 |
|---------|------|
| `test_l_sheet_groups.spec.ts` | useLDebtCycleSheetGroups 10 类规则 |
| `test_l_prerequisite.spec.ts` | L1 前置横幅 C13 状态 |
| `test_l_audit_nav.spec.ts` | resolveProcedureSheetKey L1→l1a / L3→l3a / L5→l5a / L8→l8a |
| `InterestCalcDialog.spec.ts` | 利息计算弹窗表单 + 写回 |
| `BondAmortizationDialog.spec.ts` | 债券摊余成本弹窗 + 写回 |

### 6.4 UAT（手动验收，详见 §五）

15 项验收项 + 6 项 P0 关键项门槛。

---

## 七、术语表

| 术语 | 定义 |
|------|------|
| **L 循环** | 筹资循环（L0 函证 / L1 短期借款 / L2 应付利息 / L3 长期借款 / L4 应付债券（原租赁负债审定）/ L5 应付债券 / L6 长期应付款 / L7 其他非流动负债（预计负债）/ L8 财务费用，共 9 文件）|
| **L1A** | 短期借款实质性程序表（L1 总控台）|
| **L1-5** | 短期借款利息测算表 |
| **L3-5** | 长期借款利息测算表 |
| **L8** | 财务费用（利息支出 + 汇兑损益 + 手续费，L 循环汇总枢纽）|
| **C13** | 债务循环业务层面控制测试（L 循环前置底稿）|
| **计息基准（day_count_basis）** | ACT/360（实际天数/360）/ ACT/365（实际天数/365）/ 30/360（每月 30 天/360）|
| **实际利率法** | 应付债券摊余成本计量方法：每期利息费用 = 期初摊余成本 × 实际利率 |
| **摊余成本** | 面值 ± 利息调整（溢价/折价摊销后的账面价值）|
| **一年内到期重分类** | 长期借款到期日 ≤ 1 年部分重分类为流动负债 |
| **三角勾稽（L 循环版）** | L8 利息支出 = Σ(L1+L3+H9+L5 利息测算)；L1 期末 = 期初 + 新增 − 偿还 |
| **VR-L8-01** | L8 财务费用利息支出与各借款利息测算表汇总的勾稽规则（blocking）|
| **VR-L1-01** | L1 短期借款期末余额勾稽（blocking）|
| **VR-L3-01** | L3 长期借款期末 + 重分类勾稽（warning）|
