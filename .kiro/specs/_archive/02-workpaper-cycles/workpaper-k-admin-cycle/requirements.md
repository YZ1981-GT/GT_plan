# K 管理循环底稿优化 — Requirements

> **Spec**: `workpaper-k-admin-cycle`
> **版本**: v1.0
> **依赖前置 spec**：`workpaper-d-sales-cycle` ✅ + `workpaper-h-fixed-assets-cycle` ✅ + `workpaper-j-payroll-cycle`（待执行）
> **基线日期**: 2026-05-19（Sprint 0 实测基线）

## 变更记录

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-05-19 | 三件套需求初版 — Sprint 0 实测基线 + 10 项功能需求 + EARS 范式 + 8 章标准结构 |

---

## 〇、依赖矩阵

| 上游 spec | 状态 | 本 spec 依赖 | Fallback |
|-----------|------|------------|---------|
| `workpaper-d-sales-cycle` | ✅ 53/53 | `_normalize_sheet_name` / `_merge_sheets_dedup` / `_should_skip_historical_sheet` / PBT 模式 / 4-arg AUX 约定 | D spec 必须先 commit |
| `workpaper-h-fixed-assets-cycle` | ✅ 全部完成 | H-F11 折旧引擎（K8/K9 折旧分摊来源）/ VR 三角勾稽模式 / consistency_gate 集成 | H spec 必须先 commit |
| `workpaper-j-payroll-cycle` | 待执行 | J1-7 薪酬分配→K8/K9（cross_wp_ref 联动）/ J spec 起编 CW-293，K spec 起编须在 J+L 之后 | J spec 必须先执行 |
| `workpaper-l-debt-cycle` | 待执行 | L spec 起编依赖，K spec cross_wp_ref 起编须在 L 之后 | L spec 必须先执行 |
| `workpaper-f-purchase-inventory` | ✅ 44/44 | `apply_to_sheet` 写回联动模式 / `require_project_access("edit")` RBAC | - |
| `global-linkage-bus` | ✅ | LinkageGraphBuilder / stale_engine / cross-ref:updated 事件 | - |

---

## 一、为什么做（业务/技术根因）

### 1.1 业务痛点（7 类核心问题）

1. **K8 销售费用 / K9 管理费用汇总勾稽无自动校验**：K8/K9 应 = 薪酬分摊（J1-7）+ 折旧分摊（H1-13）+ 其他费用明细，当前无 VR 规则校验汇总关系
2. **费用明细表与总账无联动**：K8-2/K9-2 费用明细表应与 TB 科目余额自动对齐，当前 prefill 仅覆盖审定表层（20 entries / 99 cells），明细表/分析程序/检查表全部空白
3. **预计负债（K5）确认条件无结构化校验**：需满足"很可能流出 + 金额可靠估计"两条件，当前无校验
4. **资产减值损失（K11）与各资产底稿无联动**：K11 应汇总 H1-14 固定资产减值 + I3 无形资产减值 + G ECL 减值，当前 cross_wp_references 仅 15 条
5. **K8/K9 费用率分析无自动对比**：与上年同期 / 同行业对比分析需手工填，当前无 LLM 辅助分析能力
6. **B/C 前置底稿无联动**：C11（管理循环控制测试）与 K8A/K9A 程序执行无前置状态驱动
7. **K 循环 14 文件规模大但 prefill 仅覆盖审定表**：99 cells 全部在审定表层，明细表/分析程序查表/费用明细 全部空白

### 1.2 技术根因

1. **prefill K 类覆盖不足（20 entries / 99 cells）**：仅审定表 + K8 分析程序有 prefill；K8-2/K9-2 费用明细 / K1-2/K3-2 往来明细 / K5-2 预计负债明细 全部空白
2. **cross_wp_references K 相关仅 15 条**（CW-01/02/04/05/08/12/13/20/51/52/99/100/257/259/260），目标新增 ≥ 20 条
3. **K 循环模板干净**：实测 0 历史遗留（152 raw - 0 历史 - 43 跨文件去重 = 109 有效 sheet）
4. **K8/K9 是跨循环汇总枢纽**：接收 J1（薪酬）/ H1（折旧）/ F2（生产成本）等多循环数据，cross_wp_ref 联动路径最复杂

### 1.3 本 spec 边界

- ✅ **本 spec 做**：K0~K13 共 14 主底稿优化（K-F1 至 K-F10）
- ❌ **不做**：H1-13 折旧分配引擎（H spec 已完成）/ J1-7 薪酬分配引擎 spec 已完成）/ LLM 真实接入

---

## 一·B、Sprint 0 实测基线（附录 A）

| 变量 | 实测值 | 来源 |
|------|-------|------|
| `N_k_files` | 14 | `wp_templates/K/` 目录扫描（K0~K13）|
| `N_k_raw_sheets` | 152 | openpyxl 全文件 sheet 累加 |
| `N_k_historical_sheets` | 0 | `_should_skip_historical_sheet` 命中数（K 模板干净）|
| `N_k_dedup_sheets` | 109 | 152 raw - 0 历史 - 43 跨文件去重 = 109 有效（task 1.1 实测复核 2026-05-19）|
| `N_k_cross_file_dups` | 43 | 底稿目录×13 + 附注上市×12 + 附注国企×11 + GT_Custom×7 = 43 重复 |
| `N_k_trailing_space` | 0 | 无末尾空格 sheet |
| `N_k_prefill_entries` | 20 | K0~K18 审定表 + K8 分析程序 |
| `N_k_prefill_cells` | 99 | 全部 cells 累加 |
| `N_k_cwr_count` | 15 | CW-01/02/04/05/08/12/13/20/51/52/99/100/257/259/260 |
| `N_cwr_max_id_numeric` | 292 | 全仓 ref_id 最大值（G spec 占至 CW-292）|
| `N_k_cwr_start` | 运行时 max+1 | J+L spec 执行完毕后确定 |

**已知数据问题**：wp_account_mapping.json 中 K 循环编号（K2=销售费用/K8=其他应付款）与模板文件编号（K2=其他流动资产/K8=销售费用）不一致。**本 spec 以模板文件编号为准**（运行时 sheet 名 `审定表K8-1` = 销售费用），wp_account_mapping 的 K 循环编号是历史遗留数据质量问题，后续需独立修正。

---

## 二、关键业务发现

### A. K 循环模板干净（0 历史遗留）
- 152 sheet 全部不命中现行 4 类历史模式，0 代码改动

### B. K8/K9 是 K 循环核心汇总枢纽
- K8 销售费用（6601）/ K9 管理费用（6602）接收多循环数据
- 与 J1-7 薪酬分配 / H1-13 折旧分配 / F2 生产成本 强联动
- VR-K8-01 / VR-K9-01 三角勾稽是 K spec 核心 VR 规则

### C. K11 资产减值损失是跨循环汇总
- K11 = H1-14 固定资产减值 + I3 无形资产减值 + G ECL 减值 + F2 存货跌价
- 遵循汇总类规则时机铁律（至少 1 个来源已保存才触发 blocking）

### D. K1/K3 往来款与 D/F 循环有联动
- K1 其他应收款 / K3 其他应付款 与 D 应收 / F 应付 有重分类联动
- 需 cross_wp_ref 配置 K1→D2 / K3→F4 重分类路径

### E. 前置底稿：C11 管理循环控制测试
- 实测确认 `backend/wp_templates/C/C11 管理循环业务层面控制测试.xlsx` 存在
- B23/B51 类无 K 循环专项底稿（与 H/I/J/L spec 同款情况）

---

## 三·B、Sprint 0 关键偏差发现

| # | 起草前假设 | Sprint 0 实测 | 偏差影响 | 修正方案 |
|---|----------|--------------|---------|---------|
| 1 | K 循环可能含历史遗留 sheet | **0 命中** | 节省 K-F1 扩展 regex 工时 | 0 代码改动 |
| 2 | K 循环 sheet 名可能有末尾空格 | **0 末尾空格** | prefill sheet 字段无需特殊处理 | 正常写 sheet 名即可 |
| 3 | tb_aux_balance 660x 有费用类别维度 | ✅ 已实测：6601 aux_type='客户' / 6602 aux_type='区域2'+'客户'（非预期'费用类别'）→ K8-2/K9-2 改用 =LEDGER_DETAIL 按月度 | K-F6 prefill 公式类型调整（不降级，目标保持 ≥ 40 cells）| design ADR-K3 已修正 |
| 4 | K8/K9 prefill 已有分析程序 | ✅ 已确认（K8 分析程序 2 cells）| 无偏差 | 在此基础上扩展 |
| 5 | C11 前置底稿存在 | ✅ 已确认 | 无偏差 | C11 可用 |

---

## 三、功能需求（K-F1 至 K-F10）

### K-F1 多文件合并 + 历史遗留过滤
- **优先级**：P0
- **依赖**：复用 `_merge_sheets_dedup` + `_should_skip_historical_sheet`（0 改动）
- **Acceptance Criteria（EARS）**：
  1. WHEN K 循环 14 文件合并加载时, THE chain_orchestrator SHALL 调用 `_merge_sheets_dedup`
  2. THE `_should_skip_historical_sheet` SHALL 对 K 循环 152 sheet 命中数 = 0（K 模板干净）
  3. WHEN 跨文件出现同名 sheet, THE chain_orchestrator SHALL 按归一化名称去重保留首次出现
  4. WHEN 合并完成后, THE chain_orchestrator SHALL 输出 `N_k_dedup_sheets = 109`
- **量化指标**：合并后有效 sheet 数 = 109；0 历史遗留；0 末尾空格

### K-F2 K 循环 sheet 分组（10 类规则）
- **优先级**：P1
- **依赖**：复用 sheet 分组 composable 模式新建 `useKAdminCycleSheetGroups.ts`
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 按 10 类分组：索引 / 程序表 / 审定表 / 明细表 / 分析程序 / 检查表 / 费用明细 / 往来款检查 / 附注披露+调整分录 / 其他程序
  2. THE 索引 + 附注披露类 SHALL 设 `defaultHidden=true`
  3. WHEN 任意 K 真实 sheet 名输入 10 类规则时, THE 系统 SHALL 命中**恰好 1 类**（PBT 验证）
- **量化指标**：10 类规则覆盖 114 个有效 sheet 全部

### K-F3 三角勾稽 VR 规则（≥ 3 条）
- **优先级**：P0
- **依赖**：复用 consistency_gate 模式
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 新增 ≥ 3 条 validation_rules：
     - **VR-K8-01**（blocking, tolerance=1.0）：K8 销售费用 = K8-2 明细合计（含薪酬+折旧+其他）
     - **VR-K9-01**（blocking, tolerance=1.0）：K9 管理费用 = K9-2 明细合计（含薪酬+折旧+其他）
     - **VR-K11-01**（warning, tolerance=1.0）：K11 资产减值损失 = H1-14 + I3 + G ECL + F2 跌价（汇总类，至少 1 个来源已保存才触发）
  2. WHEN VR-K8-01 / VR-K9-01 blocking 校验失败时, THE ConsistencyGatePanel SHALL 阻断 K8/K9 签字
  3. **IF** VR-K11-01 涉及的跨循环来源全部未保存, **THEN** THE 系统 SHALL skip 不 blocking（汇总类规则时机铁律）
  4. THE VR 规则 SHALL 写入 `backend/data/k_cycle_validation_rules.json`
- **量化指标**：3 条 VR 各至少 pass/fail/skip 测试

### K-F4 cross_wp_references 新增 ≥ 20 条
- **优先级**：P0
- **依赖**：起编运行时 max+1（J+L spec 执行完毕后确定）
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 按 5 分组新增 ≥ 20 条：
     - **K 内部联动**（≥ 4）：K8-2 明细→K8 审定 / K9-2 明细→K9 审定 / K1-2 明细→K1 审定 / K5-2 明细→K5 审定
     - **K→跨循环来源**（≥ 5）：J1-7 薪酬→K8 / J1-7 薪酬→K9 / H1-13 折旧→K8 / H1-13 折旧→K9 / F2 生产成本→K9
     - **K→报表**（≥ 4）：K8→PL 销售费用 / K9→PL 管理费用 / K11→PL 资产减值 / K1→BS 其他应收款
     - **K→附注**（≥ 4）：K8→附注 5.31 / K9→附注 5.32 / K11→附注 5.33 / K5→附注 5.25
     - **K→其他循环**（≥ 3）：K11→H1-14 减值 / K11→I3 减值 / K1→D2 重分类
  2. THE 闭区间 SHALL 为 CW-X ~ CW-(X+N-1)，N ≥ 20（X = 运行时 max+1）
  3. THE severity 比例 SHALL 满足 info < 25%
- **量化指标**：N_k_cwr_count 15 → ≥ 35

### K-F5 B/C 类前置状态横幅
- **优先级**：P1
- **依赖**：复用 `usePrerequisiteStatus.ts`
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 配置 `K_CYCLE_PREREQUISITES = [C11]`（管理循环控制测试）
  2. WHEN wp_code 匹配 `^K\d` 正则, THE usePrerequisiteStatus SHALL 加载 C11 前置状态
  3. THE 横幅状态 SHALL 按 ready / partial / blocked 三档展示
- **量化指标**：K8 顶部前置横幅可见，wp_code 路由按 `^K\d` 命中 C11

### K-F6 prefill 扩展 ≥ 40 cells
- **优先级**：P0
- **依赖**：openpyxl 实测真实 sheet 名 + 4-arg AUX 强制约定
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 新增 prefill cells ≥ 40，目标分布：
     - K8-2 销售费用明细表：≥ 10 cell（=LEDGER_DETAIL 按月度费用分项 + =TB 科目余额）
     - K9-2 管理费用明细表：≥ 10 cell（=LEDGER_DETAIL 按月度费用分项 + =TB 科目余额）
     - K1-2 其他应收款明细表：≥ 6 cell（=AUX('1221','三方收款标识',code,col) 按往来分类）
     - K3-2 其他应付款明细表：≥ 6 cell（=AUX('2241','代收代付类别',code,col) 按往来分类）
     - K5-2 预计负债明细表：≥ 4 cell（=TB 按预计负债类型，**sheet 名含空格：`明细表 K5-2`**）
     - K8-3 分析程序（扩展）：≥ 4 cell（=PREV 上年 + =TB 本年）
  2. THE 全部 cell 公式 SHALL 用 4-arg AUX 或 =TB / =PREV / =LEDGER
  3. **Sprint 0.X 前置实测要求**：
     - SQL `SELECT DISTINCT aux_type, aux_code FROM tb_aux_balance WHERE account_code LIKE '6601%' OR account_code LIKE '6602%' LIMIT 50`
     - 降级方案：如无 aux 数据 → 仅 =TB/=LEDGER，目标降为 ≥ 25 cells
- **量化指标**：N_k_prefill_cells 99 → ≥ 139（新增 ≥ 40，降级目标 ≥ 124）

### K-F7 费用分析引擎（K8/K9 同比环比）
- **优先级**：P1
- **依赖**：新建 `wp_k_expense_analysis` 路由
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 提供 endpoint `POST /api/projects/{pid}/workpapers/{wid}/k8/expense-analysis`
  2. THE endpoint SHALL 接受 `current_year_amounts{} / prior_year_amounts{} / budget_amounts{} / industry_avg_rates{}` 输入
  3. THE endpoint SHALL 返回 `yoy_changes{} / budget_variances{} / industry_comparison{} / anomaly_flags[]`
  4. THE endpoint SHALL 使用 `Depends(require_project_access("edit"))` RBAC
  5. WHEN 请求含 `apply_to_sheet` 时, THE 系统 SHALL 写回 `parsed_data.expense_analysis[sheet]`
  6. THE `is_llm_stub` 字段 SHALL 由 `settings.WP_AI_SERVICE_ENABLED` 驱动
- **量化指标**：同比/环比/预算差异 3 维度计算 + 写回 + RBAC

### K-F8 K11 资产减值损失汇总引擎
- **优先级**：P2
- **依赖**：新建 `wp_k_impairment_summary` 路由
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 提供 endpoint `POST /api/projects/{pid}/workpapers/{wid}/k11/impairment-summary`
  2. THE endpoint SHALL 汇总 H1-14 固定资产减值 + I3 无形资产减值 + G ECL 减值 + F2 存货跌价
  3. THE endpoint SHALL 返回 `impairment_by_asset_type{} / total_impairment / is_llm_stub`
  4. THE `is_llm_stub` 字段 SHALL 由 `settings.WP_AI_SERVICE_ENABLED` 驱动
  5. THE endpoint SHALL 支持 `apply_to_sheet` 写回
- **量化指标**：4 类资产减值汇总 + 写回 + RBAC

### K-F9 K8A/K9A 审计导航图
- **优先级**：P2
- **依赖**：复用 WorkpaperAuditNav + resolveProcedureSheetKey
- **Acceptance Criteria（EARS）**：
  1. THE `resolveProcedureSheetKey` SHALL 加 `K8→k8a` / `K9→k9a` / `K1→k1a` / `K5→k5a` 路由
  2. WHEN 用户首次打开 K8/K9 底稿, THE 系统 SHALL 默认展开审计导航图
- **量化指标**：vitest 验证 sheetKey 路由 4/4 正确

### K-F10 IPO 专项触发器（占位实现）
- **优先级**：P2
- **依赖**：复用 `_ensure_ipo_loaded(prefix='K8')`
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 在 `_IPO_CONFIG` 注册 `'K8'` 入口，`codes=[]`（占位）
  2. WHEN 调用 `_ensure_ipo_loaded(prefix='K8')` 时, THE 函数 SHALL 不抛异常
  3. THE D/F/H/I/G/J/L 既有 IPO 触发器 SHALL 不受影响
- **量化指标**：单测验证注册 + empty result + 全循环 IPO 回归

---

## 四、非功能需求

### 4.1 性能

| 指标 | 目标 |
|------|------|
| chain 生成 K 循环 14 主底稿 | < 45s（14 文件 152 sheet，规模接近 H 的 11 文件 187）|
| K8/K9 单底稿打开 | < 8s |
| VR 校验（3 条规则）| < 500ms |
| 费用分析引擎单次计算 | < 200ms |

### 4.2 兼容性 / 回归白名单

- ✅ D/E/F/G/H/I 循环不受影响
- THE K spec SHALL NOT 修改 `_normalize_sheet_name` / `_should_skip_historical_sheet` / `_ensure_ipo_loaded` 现有行为
- THE K spec SHALL NOT 修改 H-F11 折旧引擎 / J-F7 薪酬计提引擎（K spec 仅消费其输出）
- WHEN 修改 `usePrerequisiteStatus.ts` 路由时, THE K spec SHALL 仅追加 `^K\d` 命中分支
- WHEN 新增 cross_wp_references 时, THE K spec SHALL 起编基于运行时 max(ref_id)+1

### 4.3 可观测性

- K-F1 合并去重日志记录 `chain_executions.merge_dedup_summary`
- K-F3 VR-K8-01/K9-01/K11-01 校验结果写入 `validation_rule_results` 表
- K-F4 stale 传播写 `linkage_audit_log`
- K-F7 费用分析引擎调用日志写 `wp_calculation_log`
- K-F8 减值汇总 stub 调用日志写 `wp_ai_call_log`

---

## 五、UAT 验收清单

| # | 验收项 | 需求 | P | Status |
|---|-------|------|---|--------|
| 1 | 14 文件合并后有效 sheet = 109，0 历史遗留 | K-F1 | P0 | ○ |
| 2 | K 循环 sheet 列表按 10 类分组 | K-F2 | P1 | ○ |
| 3 | VR-K8-01 blocking 阻断 K8 签字 | K-F3 | P0 | ○ |
| 4 | VR-K9-01 blocking 阻断 K9 签字 | K-F3 | P0 | ○ |
| 5 | VR-K11-01 warning + 跨循环 skip 逻辑 | K-F3 | P1 | ○ |
| 6 | cross_wp_ref K 循环条目 ≥ 35（基线 15 + 新增 ≥ 20）| K-F4 | P0 | ○ |
| 7 | K8 顶部前置横幅显示 C11 状态 | K-F5 | P1 | ○ |
| 8 | K8-2 销售费用明细 prefill ≥ 10 cell | K-F6 | P0 | ○ |
| 9 | K9-2 管理费用明细 prefill ≥ 10 cell | K-F6 | P0 | ○ |
| 10 | K1-2/K3-2 往来款明细 prefill ≥ 6 cell 各 | K-F6 | P1 | ○ |
| 11 | 费用分析引擎同比/环比/预算差异 + 写回 + RBAC | K-F7 | P1 | ○ |
| 12 | K11 减值汇总引擎 + is_llm_stub config 驱动 + 写回 | K-F8 | P2 | ○ |
| 13 | K8/K9/K1/K5 审计导航图 sheetKey 路由 | K-F9 | P2 | ○ |
| 14 | `_IPO_CONFIG['K8']` 注册 + 全循环 IPO 回归 | K-F10 | P2 | ○ |

**上线门槛**：≥ 11 项 ✓ + P0（#1/#3/#4/#6/#8/#9）全部 ✓

---

## 五·B、成功判据汇总

| 类别 | 验收项 | 量化指标 |
|------|-------|---------|
| **合并去重（P0）** | K-F1 14 文件合并 | 152 → 109 sheet（0 历史遗留 + 43 跨文件去重）|
| **导航体验（P1）** | K-F2 sheet 分组 | 10 类规则全覆盖 109 有效 sheet |
| | K-F5 前置横幅 | C11 状态可视 |
| **勾稽联动（P0）** | K-F3 三角勾稽 | 3 条 VR + VR-K8-01/K9-01 blocking 阻断签字 |
| | K-F4 cross_wp_ref | ≥ 20 条新增（运行时 max+1 起编，目标 N_k_cwr ≥ 35）|
| **数据覆盖（P0）** | K-F6 prefill | 99 → ≥ 139 cell（新增 ≥ 40，降级目标 ≥ 124）|
| **智能辅助（P1/P2）** | K-F7 费用分析 | 同比/环比/预算差异 3 维度 + 写回 + RBAC |
| | K-F8 减值汇总 | 4 类资产减值汇总 + is_llm_stub config 驱动 |
| **导航/触发（P2）** | K-F9 审计导航图 | sheetKey=k8a/k9a/k1a/k5a 路由 |
| | K-F10 IPO 占位 | `_IPO_CONFIG['K8']` 注册 + 全循环 IPO 回归 |

---

## 六、测试矩阵

### 6.1 单测（pytest）

| 测试文件 | 覆盖 |
|---------|------|
| `test_k_merge_dedup.py` | K-F1 合并去重（152→114）+ 0 历史遗留 + 跨文件去重 |
| `test_k_validation_rules.py` | K-F3 VR-K8-01/K9-01/K11-01（pass/fail/skip 全覆盖）|
| `test_k_cross_wp_refs.py` | K-F4 ≥ 20 条新增 + ref_id 闭区间 + cycle membership 双重过滤 |
| `test_k_prefill_extension.py` | K-F6 新增 ≥ 40 cell + 4-arg AUX 校验 + 真实 sheet 名校验 |
| `test_k_sheet_groups.py` | K-F2 10 类分组规则全覆盖 |
| `test_k_expense_analysis.py` | K-F7 费用分析 3 维度 + 写回 + RBAC |
| `test_k_impairment_summary.py` | K-F8 减值汇总 + 写回 + is_llm_stub |
| `test_k_ipo_trigger.py` | K-F10 注册 + empty result + 全循环 IPO 回归 |

### 6.2 PBT（hypothesis）

| PBT | Property | max_examples | Validates |
|-----|---------|-------------|-----------|
| P1 | Sheet 名归一化幂等性 | 100 | K-F1 |
| P2 | VR-K8-01 费用勾稽正确性（drift ∈ [-2,2]）| 200 + 9 boundary | K-F3 |
| P3 | K 循环 10 类 sheet 分组完备性 | 200 | K-F2 |
| P4 | cross_wp_ref ref_id 全局唯一 + 闭区间 | 50 | K-F4 |

### 6.3 前端测试（vitest）

| 测试文件 | 覆盖 |
|---------|------|
| `test_k_sheet_groups.spec.ts` | useKAdminCycleSheetGroups 10 类规则 |
| `test_k_prerequisite.spec.ts` | K8 前置横幅 C11 状态 |
| `test_k_audit_nav.spec.ts` | resolveProcedureSheetKey K8→k8a / K9→k9a / K1→k1a / K5→k5a |
| `ExpenseAnalysisDialog.spec.ts` | 费用分析弹窗 + 写回 |
| `ImpairmentSummaryDialog.spec.ts` | 减值汇总弹窗 + 写回 |

---

## 七、术语表

| 术语 | 定义 |
|------|------|
| **K 循环** | 管理循环（K0 函证 / K1 其他应收款 / K2 其他流动资产 / K3 其他应付款 / K4 其他流动负债 / K5 预计负债 / K6 持有待售 / K7 递延收益 / K8 销售费用 / K9 管理费用 / K10 其他收益 / K11 资产减值损失 / K12 营业外收入 / K13 营业外支出，共 14 文件 152 raw sheet → 109 有效 sheet）|
| **K8A** | 销售费用实质性程序表（K8 总控台）|
| **K9A** | 管理费用实质性程序表（K9 总控台）|
| **K8-2** | 销售费用明细表（按费用类别分项）|
| **K9-2** | 管理费用明细表（按费用类别分项）|
| **K11** | 资产减值损失（汇总 H/I/G/F 各循环减值）|
| **C11** | 管理循环业务层面控制测试（K 循环前置底稿）|
| **VR-K8-01** | K8 销售费用 = K8-2 明细合计（blocking）|
| **VR-K9-01** | K9 管理费用 = K9-2 明细合计（blocking）|
| **VR-K11-01** | K11 资产减值损失 = 各资产循环减值汇总（warning，汇总类时机铁律）|
