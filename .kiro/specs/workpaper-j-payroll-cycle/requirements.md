# J 职工薪酬循环底稿优化 — Requirements

> **Spec**: `workpaper-j-payroll-cycle`
> **版本**: v1.1
> **依赖前置 spec**：`workpaper-d-sales-cycle` ✅ + `workpaper-h-fixed-assets-cycle` ✅
> **基线日期**: 2026-05-19（Sprint 0 实测基线）

## 变更记录

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-05-19 | 三件套需求初版 — Sprint 0 实测基线 + 10 项功能需求 |
| v1.1 | 2026-05-19 | 对照 H spec v1.2 复盘修复：①P0 矛盾点（"原版"保留 + 末尾空格）②EARS 范式 10 项 ③Sprint 0 偏差段 6 项 ④非功能详化（性能/兼容性/可观测性）⑤成功判据汇总 ⑥UAT 15 项 + P0 6 项门槛 ⑦prefill 分项 ≥ 42 / 降级 ≥ 25 |

---

## 〇、依赖矩阵

| 上游 spec | 状态 | 本 spec 依赖 | Fallback |
|-----------|------|------------|---------|
| `workpaper-d-sales-cycle` | ✅ 53/53 | `_normalize_sheet_name` / `_merge_sheets_dedup` / `_should_skip_historical_sheet` / PBT 模式 / 4-arg AUX 约定 | D spec 必须先 commit |
| `workpaper-h-fixed-assets-cycle` | ✅ 全部完成 | H-F11 折旧引擎跨 spec 复用模式（term 参数）/ `_ensure_ipo_loaded(prefix)` 通用化 / VR 三角勾稽模式 / cross_wp_ref 起编 max+1 模式 | H spec 必须先 commit |
| `workpaper-f-purchase-inventory` | ✅ 44/44 | `apply_to_sheet` 写回联动模式 / `require_project_access("edit")` RBAC / consistency_gate 模式 | - |
| `global-linkage-bus` | ✅ | LinkageGraphBuilder / stale_engine / cross-ref:updated 事件 | - |

---

## 一、为什么做（业务/技术根因）

### 1.1 业务痛点（6 类核心问题）

1. **薪酬计提与实发差异无自动校验**：J1-6 计提情况检查表需逐月核对计提数 vs 实发数，差异超阈值应报警；当前无 VR 规则
2. **薪酬分配到各部门/成本中心无联动**：J1-7 分配情况检查表应与 D5/K8/K9/F2 联动，当前 cross_wp_references 仅 6 条
3. **社保公积金计提合规性无校验**：五险一金计提比例因地区/年度变化，当前无辅助建议能力
4. **辞退福利（J1-10）预计负债确认逻辑复杂**：需满足三条件确认，当前无结构化校验
5. **股份支付（J3）公允价值计量模型缺失**：Black-Scholes 计算无引擎
6. **B/C 前置底稿无联动**：C10 与 J1A 程序执行无前置状态驱动

### 1.2 技术根因

1. **prefill J 类极度欠覆盖（4 entries / 17 cells）**：仅审定表层有 prefill；明细/月度分析/计提检查/分配检查/J2 明细/J3 检查表 全部空白
2. **cross_wp_references J 相关仅 6 条**（CW-04/05/06 薪酬分摊 + CW-49/50 附注/报表 + CW-98 社保→N1），目标新增 ≥ 20 条
3. **J1 模板含 5 个"-删除"历史遗留 sheet**：现行 `_should_skip_historical_sheet` regex 已覆盖（含 `-删除$` + `G\d+.*删除` 模式），0 代码改动
4. **真实 sheet 名末尾含空格**：openpyxl 实测 `审定表J1-1 ` / `明细表J1-2 ` 末尾有空格 — prefill cell 必须用真实带空格的 sheet 名（F-F10 教训）

### 1.3 本 spec 边界

- ✅ **本 spec 做**：J1~J3 共 3 主底稿优化（J-F1 至 J-F10）
- ❌ **不做**：社保地区政策数据库 / 移动端 / LLM 真实接入

---

## 一·B、Sprint 0 实测基线（附录 A）

| 变量 | 实测值 | 来源 |
|------|-------|------|
| `N_j_files` | 3 | `wp_templates/J/` 目录 |
| `N_j_raw_sheets` | 38 | openpyxl 全文件 sheet 累加 |
| `N_j_historical_sheets` | 5 | `-删除` 模式命中 |
| `N_j_old_template_sheets` | 2 | `J1A-原版` + `L1A-原`（修改模板前旧版，保留不过滤）|
| `N_j_prefill_entries` | 4 | J1审定+J2审定+J3审定+J1分析 |
| `N_j_prefill_cells` | 17 | 5+5+5+2 |
| `N_j_cwr_count` | 7 | CW-04/05/06/49/50/68/98 |
| `N_cwr_max_id_numeric` | 292 | 起编 **CW-293** |

---

## 二、关键业务发现

### A. J 循环模板含"-删除"历史遗留（5 个 sheet）
- 现行 `_should_skip_historical_sheet` 已支持"-删除"模式，**0 代码改动**

### B. J1A 程序表"原版"（修改模板前旧版，保留）
- `应付职工薪酬实质性程序表 J1A-原版` + `长期应付职工薪酬实质性程序表 L2A`（L1A-原）
- 这些是致同修改模板前的旧版本，**不属于历史遗留**，保留在 sheet 列表中供参考

### C. J3 股份支付含 IPO 专项 sheet（非删除版，应保留）

### D. J 循环无同 wp_code 多 sheet 问题（删除版过滤后无冲突）

### E. 前置底稿：C10 薪酬循环控制测试

---

## 三、功能需求（J-F1 至 J-F10）

> 命名规则：`J-F<n>` 与 D/F/H spec 保持一致；每项需求标注「优先级」「依赖」。EARS 范式按 H spec v1.2 标准（WHEN/IF/WHILE/THE...SHALL）。

### J-F1 多文件合并 + 历史遗留过滤
- **优先级**：P0
- **依赖**：复用 `_merge_sheets_dedup` + `_should_skip_historical_sheet`（D/F spec 已实现，0 改动）
- **User Story**：As a 审计助理，I want J 循环 3 文件合并后自动去除"-删除"历史 sheet 和跨文件重复 sheet，so that 合并后 sheet 列表干净。
- **Acceptance Criteria（EARS）**：
  1. WHEN J 循环 3 文件合并加载时, THE chain_orchestrator SHALL 调用 `_merge_sheets_dedup` 对全部 38 raw sheet 执行去重
  2. THE `_should_skip_historical_sheet` SHALL 命中 5 个"-删除"sheet（实测：股份支付检查表J1-10-删除 / J1-11-删除 / J1-12-删除 / IPO企业股权激励工具-删除 / 首发业务解答二-删除）
  3. THE 系统 SHALL **保留** `应付职工薪酬实质性程序表 J1A-原版` 和 `应付职工薪酬实质性程序表 L1A-原` 两个 sheet（修改模板前旧版本，不过滤）
  4. WHEN 跨文件出现同名 sheet（底稿目录 / 附注披露信息（上市公司）/ 附注披露信息（国有企业））, THE chain_orchestrator SHALL 按归一化名称去重保留首次出现
  5. WHEN 合并完成后, THE chain_orchestrator SHALL 输出 `N_j_dedup_sheets = 29`（38 raw - 5 删除 - 4 跨文件 = 29 实测）
- **量化指标**：合并后有效 sheet 数 = 29；5 个"-删除"全部过滤；2 个"原版"sheet 保留

### J-F2 J 循环 sheet 分组（8 类规则）
- **优先级**：P1
- **依赖**：复用 `useDSalesCycleSheetGroups` 模式新建 `useJPayrollSheetGroups.ts`
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 按 8 类分组 J 循环 sheet：索引 / 程序表 / 审定表 / 明细表 / 分析程序 / 检查表 / IPO专项 / 附注披露+调整分录
  2. THE 索引 + 附注披露类 SHALL 设 `defaultHidden=true`，附注披露 SHALL 设 `readonly=true`
  3. THE J3 IPO 专项 sheet（`IPO企业薪酬审计提示`，非"-删除"版）SHALL 归入 IPO 专项类
  4. WHEN 任意 J 真实 sheet 名输入 8 类规则时, THE 系统 SHALL 命中**恰好 1 类**（PBT-P3 验证）
- **量化指标**：8 类规则覆盖 29 个有效 sheet 全部；fallback 兜底 0 漏

### J-F3 三角勾稽 VR 规则（3 条）
- **优先级**：P0
- **依赖**：复用 `consistency_gate.check_*_triangle_reconciliation` 模式（H spec 已实现 4 条 VR-H1/H8）
- **User Story**：As a 合伙人，I want 应付职工薪酬期末/计提/实发/分配勾稽自动校验，so that 薪酬数据异常能及时发现。
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 新增 3 条 validation_rules：
     - **VR-J1-01**（blocking, tolerance=1.0）：J1 期末 = J1 期初 + 本期计提（J1-6 汇总）− 本期实发（J1-7 汇总）
     - **VR-J1-02**（warning, tolerance=0.05）：J1 薪酬费用率年度波动 < 5%（与上年对比）
     - **VR-J1-03**（blocking, tolerance=1.0）：J1 分配合计 = D5 营业成本薪酬 + K8 管理费用薪酬 + K9 销售费用薪酬 + F2 生产成本薪酬
  2. WHEN VR-J1-01 / VR-J1-03 blocking 校验失败时, THE ConsistencyGatePanel SHALL 阻断 J1 底稿签字
  3. WHEN VR-J1-02 warning 触发时, THE ConsistencyGatePanel SHALL 显示告警但不阻断签字
  4. **IF** VR-J1-03 涉及的跨循环目标（D5/K8/K9/F2）全部未保存, **THEN** THE 系统 SHALL skip 不 blocking（汇总类规则时机铁律）
  5. THE VR 规则 SHALL 写入 `backend/data/j_cycle_validation_rules.json`，由 `consistency_gate_service.check_j_cycle_triangle_reconciliation()` 注入主流程
- **量化指标**：3 条 VR 各至少 1 个 pass / 1 个 fail / 1 个 skip 测试；阻断签字 e2e 测试通过

### J-F4 cross_wp_references 新增 ≥ 20 条
- **优先级**：P0
- **依赖**：复用 F-F7 ref_id 起编模式（基于运行时 max(ref_id)+1）
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 起编 **CW-293**（基于 Sprint 0 实测 max(ref_id)=292，G spec 已占至 CW-292）
  2. THE 系统 SHALL 按 5 分组新增 ≥ 20 条 cross_wp_references：
     - **J 内部联动**（≥ 4）：J1-6 计提→J1-1 审定 / J1-7 分配→J1-1 / J2 长期转短期→J1 / J3 费用确认→J1
     - **J→费用循环**（≥ 5）：J1-7→D5 营业成本 / →K8 管理费用 / →K9 销售费用 / →F2 生产成本 / →H1-13 折旧分配中薪酬部分
     - **J→报表**（≥ 4）：J1→BS-030 / J2→BS-040 / J3→所有者权益变动表 / J1→利润表薪酬费用
     - **J→附注**（≥ 4）：J1→附注 5.12 / J2→附注 5.20 / J3→附注 X 股份支付 / J1→附注薪酬政策
     - **J→N 税费**（≥ 3）：J1 社保→N1 / J1 个税代扣→N1 / J1 住房公积金→N1
  3. THE 闭区间 SHALL 为 CW-293 ~ CW-(293+N-1)，N ≥ 20
  4. WHEN 测试用闭区间过滤时, THE 测试 SHALL 同时按 cycle membership 过滤（source_wp 或 target wp_code 以 J 开头）— 跨 spec 双重过滤铁律
  5. THE info / warning / blocking severity 比例 SHALL 满足 info < 25%（CWR severity 健康度铁律）
- **量化指标**：N_j_cwr_count 6 → ≥ 26（基线 6 + 新增 ≥ 20）

### J-F5 B/C 类前置状态横幅
- **优先级**：P1
- **依赖**：复用 `usePrerequisiteStatus.ts` 加 J_CYCLE_PREREQUISITES
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 配置 `J_CYCLE_PREREQUISITES = [C10]`（薪酬循环控制测试，实测真实编号）
  2. WHEN wp_code 匹配 `^J\d` 正则, THE usePrerequisiteStatus SHALL 加载 C10 前置状态
  3. THE 横幅状态 SHALL 按 ready / partial / blocked 三档展示（参照 F/H spec 模式）
  4. **NOTE**：致同模板 B23 类无 J 业务专项 / B51 类仅 -3 货币 + -5 收入（无 J 资产舞弊专项），与 H spec 同款情况
- **量化指标**：J1 顶部前置横幅可见，wp_code 路由按 `^J\d` 命中 C10

### J-F6 prefill 扩展 ≥ 40 cells
- **优先级**：P0
- **依赖**：openpyxl 实测真实 sheet 名（**ADR-J3 铁律：禁止臆造，含末尾空格**）+ 4-arg AUX 强制约定
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 新增 prefill cells ≥ 40，目标分布：
     - `明细表J1-2 `（**末尾带空格**）：≥ 8 cell
     - `月度分析表J1-4`：≥ 6 cell（=TB + =PREV）
     - `计提情况检查表J1-6`：≥ 8 cell（=LEDGER 按月计提）
     - `分配情况检查表J1-7`：≥ 6 cell（=AUX 部门维度，待 Sprint 0.X 实测）
     - `明细表J2-2`：≥ 4 cell
     - `股份支付检查表J3-2`：≥ 4 cell
  2. THE 全部 cell 公式 SHALL 用 4-arg `=AUX(account_code, aux_type, aux_code, column)` 或 =TB / =PREV / =LEDGER（3-arg AUX 调用 prefill_engine 直接 return None）
  3. **Sprint 0.X 前置实测要求**（实施前必做）：
     - SQL `SELECT DISTINCT aux_type, aux_code FROM tb_aux_balance WHERE account_code LIKE '221%' LIMIT 50` 确认真实 aux 维度
     - openpyxl 读 `明细表J1-2 ` / `计提情况检查表J1-6` / `分配情况检查表J1-7` 真实表头确认资产/费用类别维度
     - **降级方案**：如 tb_aux_balance 无 221% 数据 → prefill 降级为仅 =TB/=LEDGER，目标降为 ≥ 25 cells
  4. THE 全部 sheet 字段 SHALL 与 openpyxl 读出真名完全一致（含末尾空格 / 全角括号），用 `repr(name)` 核对避免肉眼漏看
- **量化指标**：N_j_prefill_cells 17 → ≥ 57（新增 ≥ 40，降级目标 ≥ 42）

### J-F7 薪酬计提自动测算引擎
- **优先级**：P1（核心增量，独立于 LLM 可测试）
- **依赖**：新建 `wp_j_payroll_calc` 路由
- **User Story**：As a 审计助理，I want 输入"员工数 / 月均工资 / 社保比例 / 公积金比例"后系统自动计算月度计提明细，so that 我不需要手工填计提情况检查表。
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 提供 endpoint `POST /api/projects/{pid}/workpapers/{wid}/j1/payroll-calc`
  2. THE endpoint SHALL 接受 `employee_count / avg_monthly_salary / social_insurance_rates(养老/医疗/失业/工伤/生育) / housing_fund_rate / welfare_rate / education_rate / union_rate / months` 输入
  3. THE endpoint SHALL 返回 `monthly_breakdown[]` + `annual_summary` 输出
  4. THE endpoint SHALL 使用 `Depends(require_project_access("edit"))` RBAC 校验
  5. WHEN 请求 body 含 `apply_to_sheet: str` 字段时, THE 系统 SHALL 把计算结果写回 `working_paper.parsed_data.payroll_calcs[sheet]`（参照 H-F11 apply_to_sheet 模式）
  6. **业务正确性约束**：年度合计 = 12 × 月度合计 ± 1（取整误差容忍）；社保 5 项比例之和应 < 0.5（合理性边界）
- **量化指标**：每种参数组合至少 3 个边界 case 单元测试 + 写回联动测试 + RBAC 测试

### J-F8 股份支付公允价值计算（Black-Scholes stub）
- **优先级**：P2
- **依赖**：新建 `wp_j_share_payment` 路由 + `SharePaymentDialog.vue`
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 提供 endpoint `POST /api/projects/{pid}/workpapers/{wid}/j3/share-payment-calc`
  2. THE endpoint SHALL 接受 `stock_price / exercise_price / risk_free_rate / volatility / time_to_maturity / dividend_yield / grant_quantity / vesting_period` 输入
  3. THE endpoint SHALL 实现 Black-Scholes 公式：`C = S·e^(-qT)·N(d1) − K·e^(-rT)·N(d2)`（含股息率 q）
  4. THE endpoint SHALL 返回 `option_value / total_fair_value / annual_expense_schedule[] / is_llm_stub`
  5. THE `is_llm_stub` 字段 SHALL 由 `settings.WP_AI_SERVICE_ENABLED` 驱动（未配置 → True；配置后 → False）— stub 标志铁律
  6. WHEN σ=0 OR T=0 OR S<=0 OR K<=0 时, THE endpoint SHALL 返回 HTTP 400 + 错误信息
  7. THE endpoint SHALL 使用 `Depends(require_project_access("edit"))` RBAC + 支持 `apply_to_sheet` 写回
- **量化指标**：BS 公式 4 单调性测试（S↑→C↑ / K↑→C↓ / σ↑→C↑ / T↑→C↑）+ 边界 case + 写回联动 + RBAC

### J-F9 J1A 审计导航图
- **优先级**：P2
- **依赖**：复用 WorkpaperAuditNav 组件 + `resolveProcedureSheetKey` 加 J 循环路由
- **Acceptance Criteria（EARS）**：
  1. THE `resolveProcedureSheetKey` SHALL 加 `J1→j1a` / `J2→j2a` / `J3→j3a` 路由
  2. WHEN 用户首次打开 J1 底稿, THE 系统 SHALL 默认展开审计导航图（与 H-F13 同模式）
- **量化指标**：vitest 验证 sheetKey 路由 3/3 正确（含 ⚠ partial 限定：procedure_status 数据需项目首次填写后才不全 pending，与 F-F18/H-F13 同款限制）

### J-F10 IPO 专项触发器（占位实现）
- **优先级**：P2
- **依赖**：复用 `_ensure_ipo_loaded(prefix='J1')`
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 在 `_IPO_CONFIG` 注册 `'J1'` 入口，`codes=[]`（占位）
  2. WHEN 调用 `_ensure_ipo_loaded(prefix='J1')` 时, THE 函数 SHALL 不抛异常，返回 `{prefix:'J1', added_codes:[], skipped_existing:[], errors:[]}`
  3. THE J3 现有 IPO 专项 sheet（`IPO企业薪酬审计提示`）SHALL 保留为常驻 sheet（非 IPO 触发加载）
  4. THE D/F/H/I/G 既有 IPO 触发器 SHALL 不受影响（回归保留）
  5. **TD-J6**（新增技术债）：用户后续提供 J 循环 IPO 应对类专属模板后再立 spec 接入触发器
- **量化指标**：单测验证 `_IPO_CONFIG['J1']` 注册 + empty result + D/F/H/I/G 既有 IPO 触发器测试全过

---

## 三·B、Sprint 0 关键偏差发现

实测 vs 起草前假设对比（**spec 起草偏差归零原则**：所有偏差必须明确标注 + 修正方案）：

| # | 起草前假设 | Sprint 0 实测 | 偏差影响 | 修正方案 |
|---|----------|--------------|---------|---------|
| 1 | J 循环 38 sheet 中 5 个"-删除" + 2 个"原版"都需过滤 → 有效 sheet ≈ 30 | "原版"是修改模板前旧版本，**用户确认保留不过滤**；实测 38 raw - 5 删除 - 4 跨文件去重 = **29** 有效 sheet | J-F1 简化（不需扩展 regex 覆盖"-原版/-原"后缀）+ UAT #1 数字从 30 改 29 | requirements §1.2/二.B + tasks 0.2/1.2 已对齐；删除原"扩展 regex"任务 |
| 2 | 真实 sheet 名整洁，prefill cell 直接按 wp_code 标注（如 `审定表J1-1`）即可 | openpyxl 实测发现 `审定表J1-1 ` / `明细表J1-2 ` **末尾带空格** | prefill cell sheet 字段必须包含真实空格，否则 prefill_engine 匹配落空（F-F10 同款教训） | ADR-J3 强制铁律 + tasks 0.2 用 `repr(name)` 核对 |
| 3 | J3 含 2 个 IPO 专项 sheet（IPO企业薪酬审计提示 + IPO企业股权激励工具） | IPO企业股权激励工具是"-删除"版（已过滤），仅 `IPO企业薪酬审计提示` 1 个有效 IPO sheet | J-F2 IPO 专项分组覆盖数从 2 改 1 | requirements §二.C 已澄清 |
| 4 | tb_aux_balance 221% 有完整 8 类薪酬维度（工资/奖金/津贴/社保/公积金/福利费/教育经费/工会经费） | **未实测**，待 Sprint 0.X 跑 SQL 确认 | prefill ≥ 40 cells 目标可能降级到 ≥ 25 cells（仅 =TB/=LEDGER）— 与 H/I/G spec 同款降级风险 | ADR-J3 加降级方案 + UAT 加降级目标行 |
| 5 | J 循环前置底稿应有 B23-X 业务控制 + B51-X 资产舞弊（参照 D/F 模式）| B23 类**仅 B23-15 信息处理 + B23-XX-5 通用模板**；B51 类**仅 -3 货币 + -5 收入**（无 J 业务/舞弊专项）；C 类有 **C10 薪酬循环控制** | J-F5 前置清单从"B23-?+C-?+B51-?"改为实测真实 [C10] 单条 | requirements §J-F5 + 二.E 已对齐 |
| 6 | J3 股份支付现有 prefill 用 `2211` 应付职工薪酬科目（与 J1 同）| prefill_formula_mapping.json 实测 J3 account_codes=`['2211']`，但 J3 股份支付应该用 `4001` 资本公积-股份支付科目；现有数据是问题（非 spec 问题），实施时一并修正 | J-F6 J3-2 prefill 应使用 4001 / 4002 而非 2211 | ADR-J3 备注 + Sprint 0.X 加 SQL 实测 4001 维度 |

**关键修正后的实施基线**：
```python
# 真实基线（替代起草假设）
N_j_files = 3                     # ✅
N_j_raw_sheets = 38               # ✅
N_j_historical_sheets = 5         # ✅ 全部 "-删除" 后缀
N_j_old_template_sheets = 2       # ✅ J1A-原版 + L1A-原（保留不过滤）
N_j_dedup_sheets = 29             # ✅ 实测：38 - 5 - 4 = 29
N_j_cross_file_dups = 4           # ✅ 底稿目录×2 + 附注披露上市×1 + 国企×1
N_j_prefill_entries = 4           # ✅
N_j_prefill_cells = 17            # ✅
N_j_cwr_count = 6                 # ✅
N_cwr_max_id_numeric = 292        # ✅ 起编 CW-293
N_j_ipo_sheets = 1                # ❌ 偏差：假设 2，实测 1（IPO企业薪酬审计提示）
N_j_b51_dedicated = 0             # ❌ 偏差：B51 仅 -3/-5
N_j_b23_dedicated = 0             # ❌ 偏差：B23 仅 -15/-XX-5
N_j_c_prerequisites = 1           # ✅ 实测仅 C10
N_j_sheet_with_trailing_space = 2 # ❌ 偏差：审定表J1-1 / 明细表J1-2 末尾带空格
```

---

## 四、非功能需求

### 4.1 性能

| 指标 | 目标 | 参照 |
|------|------|------|
| chain 生成 J 循环 3 主底稿 | < 15s（J 循环仅 3 文件 38 sheet，远小于 H 的 11 文件 187）| H spec < 60s 基线 |
| J1 单底稿打开（含 23 sheet）| < 5s | F spec F2 同基线 |
| J 循环 sheet 分组导航切换 | < 200ms | F/H spec |
| J-F3 VR 三角勾稽校验（3 条规则）| < 500ms | H spec VR-H1 |
| J-F4 cross_wp_ref stale 传播 | < 500ms | E1 spec |
| J-F7 薪酬计提引擎单次计算（12 月度序列）| < 100ms（纯算法，无 DB IO）| H-F11 折旧引擎 |
| J-F7 月度序列写回 parsed_data | < 1s | H-F11 apply_to_sheet |
| J-F8 Black-Scholes 单次计算 | < 50ms（数学库 norm.cdf）| 新增 |

### 4.2 兼容性 / 回归白名单

**必须不破坏的现有循环**（每项需对应回归测试）：
- ✅ D 销售循环（53 task + 20 UAT pass）— 不影响 `_normalize_sheet_name` / `_should_skip_historical_sheet` / `_ensure_d4_ipo_loaded` 现有行为
- ✅ E1 货币资金循环（91 task pass）— 不影响 useUniverSheetNav / scenarioFilter / WorkpaperAuditNav
- ✅ F 采购存货循环（44 task + UAT 上线）— 不影响 `_ensure_ipo_loaded(prefix='F2')` / F-F8 反向回填 / F-F11 valuation-sample / F-F12 impairment-analysis
- ✅ H 固定资产循环（H spec 上线）— 不影响 H-F11 depreciation-calc / H-F12 impairment-analysis / MEASUREMENT_MODEL_FILTER / 4 种折旧方法引擎（J-F7 薪酬计提是独立引擎，不复用折旧引擎）
- ✅ I 无形资产循环（I spec 上线）— 不影响 I-F2 amortization 引擎（J spec 不复用 term 参数模式，因 J-F7 薪酬计提与折旧/摊销公式结构不同）
- ✅ G 投资循环（G spec 上线）— 不影响 fair_value/ECL/classification 三 router

**关键兼容性约束**：
- THE J spec SHALL NOT 修改 `_normalize_sheet_name` 函数签名或行为（D/F spec 已实施 + 锁定）
- THE J spec SHALL NOT 修改 `_should_skip_historical_sheet` 现有 4 模式（J 实测仅"-删除"模式命中，0 扩展）
- THE J spec SHALL NOT 修改 `_ensure_ipo_loaded(prefix)` 通用接口（仅追加 `_IPO_CONFIG['J1']` 注册，codes=[]）
- THE J spec SHALL NOT 修改 H-F11 / I-F2 折旧/摊销引擎（J-F7 薪酬计提独立 router，不引入 term 参数）
- THE J spec SHALL NOT 引入新 vue 依赖（复用 E1 + D + F + H 已有组件）
- WHEN 修改 `usePrerequisiteStatus.ts` 路由时, THE J spec SHALL 仅追加 `^J\d` 命中分支（不影响 D/E/F/H/I/G 现有路由）
- WHEN 新增 cross_wp_references 时, THE J spec SHALL 起编 CW-293（基于运行时 max(ref_id)+1，禁止硬编码）
- WHEN 新增 prefill cells 时, THE J spec SHALL 用 `(wp_code, sheet)` 作幂等保护 key（参照 F-F10 一次性脚本铁律）

### 4.3 可观测性

- J-F1 合并去重日志记录 `chain_executions.merge_dedup_summary`（去重前/后 sheet 数）（D/F spec 已实现）
- J-F3 VR-J1-01/02/03 校验结果写入 `validation_rule_results` 表（复用 D/F/H 已有架构）
- J-F4 stale 传播写 `linkage_audit_log`（global-linkage-bus 已有）
- J-F7 薪酬计提引擎计算日志写 `wp_calculation_log`（输入参数 + 月度序列摘要 + apply_to_sheet 命中）
- J-F8 Black-Scholes stub 调用日志写 `wp_ai_call_log`（与 F-F12/H-F12 同表，含 is_llm_stub 字段）
- J-F5 前置状态查询日志写 `prerequisite_status_log`（复用 F/H spec 模式）

兼容性总体声明：不影响 D/E/F/G/H/I 循环；不修改 `_normalize_sheet_name` / `_should_skip_historical_sheet` / `_ensure_ipo_loaded` / 折旧/摊销引擎现有行为。

---

## 五、UAT 验收清单

| # | 验收项 | 需求 | P | Status |
|---|-------|------|---|--------|
| 1 | 合并后有效 sheet = 29，5 个"-删除"被过滤，2 个"原版"保留 | J-F1 | P0 | ○ |
| 2 | J 循环 sheet 列表按 8 类分组 + 折叠展开 | J-F2 | P1 | ○ |
| 3 | VR-J1-01 blocking 阻断 J1 签字 | J-F3 | P0 | ○ |
| 4 | VR-J1-03 薪酬分配勾稽 blocking + 跨循环 skip 逻辑 | J-F3 | P0 | ○ |
| 5 | VR-J1-02 薪酬费用率波动 warning（不阻断）| J-F3 | P1 | ○ |
| 6 | cross_wp_ref J 循环条目 ≥ 26（基线 6 + 新增 ≥ 20，闭区间 CW-293~N）| J-F4 | P0 | ○ |
| 7 | J1 顶部前置横幅显示 C10 状态 | J-F5 | P1 | ○ |
| 8 | `明细表J1-2 ` prefill ≥ 8 cell（4-arg AUX，含末尾空格）| J-F6 | P0 | ○ |
| 9 | `计提情况检查表J1-6` prefill ≥ 10 cell（=LEDGER 按月）| J-F6 | P0 | ○ |
| 10 | `分配情况检查表J1-7` prefill ≥ 8 cell（=AUX 部门维度）| J-F6 | P1 | ○ |
| 11 | J3-2 prefill ≥ 4 cell（科目修正为 4001/4002 资本公积-股份支付）| J-F6 | P1 | ○ |
| 12 | 薪酬计提引擎 4 种参数组合 + apply_to_sheet 写回 + RBAC | J-F7 | P1 | ○ |
| 13 | Black-Scholes 公式 + is_llm_stub config 驱动 + 写回 | J-F8 | P2 | ○ |
| 14 | J1/J2/J3 审计导航图 sheetKey=j1a/j2a/j3a 路由 | J-F9 | P2 | ○（**预期 ⚠ partial**：组件 ✓ + 路由 ✓，procedure_status seed 数据待项目首次填写后才不全 pending，与 F-F18/H-F13 同款限制）|
| 15 | `_IPO_CONFIG['J1']` 注册 codes=[] + D/F/H/I/G IPO 触发器回归全过 | J-F10 | P2 | ○ |

**上线门槛**：
- ≥ 12 项 ✓ pass + **P0 关键项**（#1, #3, #4, #6, #8, #9）必须**全部** ✓ pass
- 实测 P0 共 6 项（vs H spec 8 项），权重低于 H 因 J 循环架构改动较少（无 measurement_model / 无多 sheet 路由 / 无跨表强联动反向回填）

---

## 五·B、成功判据汇总

| 类别 | 验收项 | 量化指标 |
|------|-------|---------|
| **合并去重（P0）** | J-F1 3 文件合并 | 38 → 29 sheet（实测，5 删除 + 4 跨文件去重）|
| **导航体验（P1）** | J-F2 sheet 分组 | 8 类规则全覆盖 J 循环 29 个有效 sheet（PBT-P3 验证恰好 1 类）|
| | J-F5 前置横幅 | C10 状态可视（实测真实编号）|
| **勾稽联动（P0）** | J-F3 三角勾稽 | 3 条 VR + VR-J1-01/03 blocking 阻断签字 + VR-J1-03 跨循环 skip 逻辑 |
| | J-F4 cross_wp_ref | ≥ 20 条新增（起编 CW-293，目标 N_j_cwr ≥ 26）+ info severity < 25% |
| **数据覆盖（P0）** | J-F6 prefill | 17 → ≥ 57 cell（新增 ≥ 40，含 4-arg AUX 真实维度 + 末尾空格 sheet 名 + J3 科目修正 4001/4002）；降级目标 ≥ 25 cells（如 tb_aux_balance 无 221% 数据）|
| **智能辅助（P1/P2）** | J-F7 薪酬计提引擎 | 12 月度序列 + 5 险一金 + apply_to_sheet 写回 + RBAC + 边界 case |
| | J-F8 BS 公式 | 4 单调性测试 + is_llm_stub config 驱动 + 写回（与 F-F12/H-F12 同 stub 模式）|
| **导航/触发（P2）** | J-F9 审计导航图 | sheetKey=j1a/j2a/j3a 路由 + 程序状态展示 |
| | J-F10 IPO 占位 | `_IPO_CONFIG['J1']` 注册 + 占位 codes=[] + D/F/H/I/G IPO 回归 |

---

## 六、测试矩阵

| 测试文件 | 覆盖 |
|---------|------|
| `test_j_merge_dedup.py` | J-F1 |
| `test_j_sheet_groups.py` | J-F2 |
| `test_j_validation_rules.py` | J-F3 |
| `test_j_cross_wp_refs.py` | J-F4 |
| `test_j_prefill_extension.py` | J-F6 |
| `test_j_payroll_calc.py` | J-F7 |
| `test_j_share_payment.py` | J-F8 |
| `test_j_ipo_trigger.py` | J-F10 |

PBT：P1 归一化幂等(100) / P2 VR-J1-01 勾稽(200+9) / P3 分组完备(200) / P4 ref_id 唯一(50)

---

## 七、术语表

| 术语 | 定义 |
|------|------|
| J 循环 | 职工薪酬循环（J1/J2/J3，3 文件 38 sheet）|
| J1A | 应付职工薪酬实质性程序表 |
| J1-6 | 计提情况检查表 |
| J1-7 | 分配情况检查表 |
| J3 | 股份支付 |
| C10 | 薪酬循环控制测试（前置）|
| Black-Scholes | 期权定价模型 |
| 设定受益计划 | 企业承担精算风险的退休福利（J2）|
| 设定提存计划 | 企业仅承担缴费义务（五险一金）|
