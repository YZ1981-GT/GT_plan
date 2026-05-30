# I 无形资产循环底稿优化 — Requirements

> **Spec**: `workpaper-i-intangible-assets-cycle`
> **版本**: v1.0
> **依赖前置 spec**：`workpaper-d-sales-cycle` ✅ + `workpaper-f-purchase-inventory` ✅ + `workpaper-h-fixed-assets-cycle` ✅
> **基线日期**: 2026-05-19（Sprint 0 实测落地）

## 变更记录

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-05-19 | 三件套需求初版 — Sprint 0 实测基线 + 7 项关键业务发现 + 10 项功能需求 |
| v1.1 | 2026-05-19 | 对照 H spec 复盘修复 P0-P2 共 10 项：①附录 A prefill 数字修正 ②ADR-I1 分支选择器语义修正（不同 wp_code 间跳转 vs 同 wp_code 多 sheet 路由）③tasks 2.23 与 Sprint 0.X 去重 ④加 §七 边界章 ⑤加 §八 启动条件 ⑥ADR-I5 实测占位 ⑦压缩比规则（已有）⑧README ⑨格式微调 ⑩Sprint 2 中期 checkpoint |

---

## 〇、依赖矩阵

| 上游 spec | 状态 | 本 spec 依赖 | Fallback |
|-----------|------|------------|---------|
| `workpaper-d-sales-cycle` | ✅ 53/53 + UAT 20 | D 循环核心产出复用：`_normalize_sheet_name` / `_merge_sheets_dedup` / `_should_skip_historical_sheet`（4+1 模式）/ `SCENARIO_TO_FILE_FILTER` / `useDSalesCycleSheetGroups` 模式 / `ConsistencyGatePanel` / `usePrerequisiteStatus` / PBT P1~P7 模式 / 4-arg AUX 强制约定 / 真实 sheet 名 openpyxl 实测铁律 | D spec 必须先 commit |
| `workpaper-f-purchase-inventory` | ✅ 44/44 + UAT 16✓+1 partial+2 stub | F 循环成熟产出复用：`_ensure_ipo_loaded(prefix)` 通用化 / `apply_to_sheet` 写回联动模式 / `require_project_access("edit")` RBAC / cross_wp_references 起编 max(ref_id)+1 模式 / `consistency_gate.check_*_triangle_reconciliation` 模式 | F spec 必须先 commit |
| `workpaper-h-fixed-assets-cycle` | ○ 待实施 | H 循环产出复用：`AssetImpairmentDialog` DCF 弹窗模式（I-F4 商誉减值复用）/ `useDepreciationBranchSelector` 分支选择器模式（I-F2 摊销版本复用）/ `MEASUREMENT_MODEL_FILTER` 独立维度模式参照 / 折旧引擎 4 方法（I 循环仅用 straight_line + units_of_production 2 种）| H spec 完成后 I spec 可并行启动（仅 I-F4 依赖 H-F12 模式） |
| `workpaper-e1-cash-optimization` | ✅ 91/91 | E1 9 个核心组件复用 + scenario 字段 + LLM API + attachment_service + Univer Sheet 路由 | - |
| `global-linkage-bus` | ✅ 已完成 | LinkageGraphBuilder / stale_engine / 反向索引 / `cross-ref:updated` 事件 | - |
| `template-library-coordination` | 63/64 | seed_load_history 表 / reseed 流程 / wp_template_metadata | - |
| `enterprise-linkage` | ✅ 已完成 | useEditingLock / cross-module event bus / RBAC require_project_access | - |

---

## 一、为什么做（业务/技术根因）

### 1.1 业务痛点（合伙人 / 项目经理 / 审计助理实际遇到的 7 类核心问题）

1. **无形资产摊销测算 2 版本选择无引导**：I1-10（不含减值）/ I1-11（含减值）两版摊销测算表，用户不知道选哪个；比 H1-12 的 3 版简单但仍需分支选择器引导
2. **商誉减值测试（I3-6/I3-7/I3-8）DCF 模型复杂**：商誉不摊销但需年度减值测试，DCF 资产组模型与 H1-14 同款但商誉特殊性在于"不可单独识别现金流"→ 必须按资产组（CGU）分摊；当前无 AI 辅助
3. **研发费用 ↔ 开发支出强联动缺失**：I6 研发费用（费用化）与 I2 开发支出（资本化）是同一研发活动的两面，资本化时点判断（I2-6 五条件）是审计重点；当前无 cross_wp_references 联动
4. **I2 开发支出资本化时点判断无辅助**：CAS 6 规定 5 个资本化条件（技术可行性/完成意图/使用或出售能力/未来经济利益/资源充足），当前靠手工逐项勾选无系统化校验
5. **I4 长期待摊费用摊销方法多样**：I4-6 直线法 / I4-7 工作量法，与 H 循环折旧引擎同款但仅需 2 种方法（直线 + 工作量）
6. **跨循环联动极度欠缺**：I 循环与 D5 营业成本（摊销分摊）/ K 期间费用（研发费用）/ A 报表 / 附注 5.14~5.16 联动当前 cross_wp_references 仅 5 条
7. **B/C 前置底稿无联动**：C8（无形资产及其他长期资产循环控制测试）/ C9（研发循环控制测试）与 I1A/I2A 程序执行无前置状态驱动

### 1.2 技术根因（代码锚定核验后）

1. **prefill_formula_mapping I 类极度欠覆盖（7 entries / 34 cells）**：仅审定表层有 prefill；明细表 / 摊销测算 / 减值测试 / 资本化时点 全部空白
2. **cross_wp_references I 相关仅 5 条**：目标新增 ≥ 20 条
3. **`_should_skip_historical_sheet` 已覆盖 I3 历史遗留**：I3 "参考－商誉减值测试示例" 已被现行 regex 命中（含"示例"末尾模式），不需扩展
4. **I6↔I2 反向回填路径不存在**：研发费用费用化/资本化拆分后无 cross_wp_references 联动
5. **摊销引擎未实现**：I 循环仅需直线法 + 工作量法（H 循环 4 种方法的子集），可复用 H-F11 引擎

### 1.3 本 spec 边界

- ✅ **本 spec 做**：I1~I6 共 6 主底稿优化（I-F1 至 I-F10 共 10 项修复）
- ❌ **本 spec 不做（独立 spec）**：
  - J 循环（职工薪酬 + 股份支付）
  - K 循环（期间费用）
  - 研发费用加计扣除税务计算（N 循环）
  - 移动端 APP
  - 7 循环函证统一管理中心（O1）
  - B/C/D-N 三层联动机制（O8）

---

## 一·B、Sprint 0 实测基线（附录 A）

| 变量 | 实测值 | 来源 |
|------|-------|------|
| `N_i_files` | 6 | `wp_templates/I/` 目录扫描（I1~I6）|
| `N_i_raw_sheets` | 86 | openpyxl 全文件 sheet 累加 |
| `N_i_historical_sheets` | **1** | I3 "参考－商誉减值测试示例" 被现行 regex 命中 |
| `N_i_dedup_sheets` | 67 | 现行 `_normalize_sheet_name` 去重后 |
| `N_i_prefill_entries` | 7 | `prefill_formula_mapping.json` 中 wp_code 以 I 开头的 entry |
| `N_i_prefill_cells` | 34 | 同上，全部 cells 累加 |
| `N_i_cwr_count` | 5 | `cross_wp_references.json` 中 source_wp 或 targets[*].wp_code 以 I 开头 |
| `N_cwr_max_id` | 210 | 全仓 ref_id 数值最大值（运行时 max+1 起编，H spec 后预计 CW-241+）|

**当前 I prefill 7 entries 全部仅覆盖审定表 + 分析程序**：

```
I1  审定表I1-1          cells=7
I1  分析程序I1-3        cells=2
I2  审定表I2-1          cells=5
I3  审定表I3-1          cells=5
I4  审定表I4-1          cells=5
I5  审定表I5-1          cells=5
I6  审定表I6-1          cells=5
合计: 7 entries / 34 cells
```

---

## 二、7 项关键业务发现（驱动 spec 走向）

### A. I3 商誉模板有 1 个历史遗留 sheet — 已被现行 regex 覆盖
- I3 "参考－商誉减值测试示例(HISTORICAL)" 被 `_should_skip_historical_sheet` 现行"示例"末尾模式命中
- **影响**：不需要扩展 regex，仅需回归验证（D/F/H 模式不受影响）

### B. I1 摊销测算 2 版本（比 H1-12 的 3 版简单）
- I1-10 摊销测算表（不含减值）— 剩余年限法
- I1-11 摊销测算表（含减值）
- **影响**：复用 H-F3 `useDepreciationBranchSelector` 模式，仅 2 分支（比 H 的 3 分支简单）

### C. I4 长期待摊费用摊销 2 版本（按方法区分）
- I4-6 摊销测算（直线法）
- I4-7 摊销测算表（工作量法）
- **影响**：同 B，复用分支选择器模式

### D. I2 开发支出资本化时点判断（I-cycle 独有逻辑）
- I2-6 "研发项目资本化时点判断" sheet 是 I 循环独有的核心审计程序
- CAS 6 五条件：①技术可行性 ②完成意图 ③使用或出售能力 ④未来经济利益 ⑤资源充足
- **影响**：需新增 I-F5 辅助校验逻辑（5 条件全勾选 → 建议资本化起始日期）

### E. I3 商誉减值（不摊销，年度 DCF 测试）
- 商誉不摊销（CAS 8），但需年度减值测试
- I3-6 商誉减值测试 / I3-7 可收回金额测试 / I3-8 复核公司减值测试过程及结论
- DCF 模型与 H1-14 同款，但商誉特殊性：不可单独识别现金流 → 按 CGU 分摊
- **影响**：复用 H-F12 `AssetImpairmentDialog` 模式，参数化为商誉版本

### F. I6 研发费用 ↔ I2 开发支出强联动
- I6 研发费用 = 费用化部分（计入当期损益）
- I2 开发支出 = 资本化部分（计入无形资产）
- 同一研发项目的支出 = I6 费用化 + I2 资本化
- **影响**：需 cross_wp_references 配置 I6→I2 / I2→I6 双向回填路径 + VR 规则校验

### G. 规模约为 H 循环 50%
- 6 文件 / 86 sheet（vs H 的 11 文件 / 187 sheet）
- 预估总工时 ~8 天（vs H 的 14.5 天）
- 功能需求 10 项（vs H 的 15 项）

---

## 三、功能需求（I-F1 至 I-F10）

> 命名规则：`I-F<n>` 与 D/F/H spec 保持一致；每项需求标注「依赖前置 spec」「P 优先级」「主受益 wp_code」。

### I-F1 6 文件合并 + GT_Custom/底稿目录跨文件去重
- **优先级**：P0
- **依赖**：复用 `_merge_sheets_dedup`（D/F/H spec 已实现，0 改动）
- **User Story**：As a 审计助理，I want I 循环 6 个物理文件合并后自动去除跨文件重复 sheet，so that 合并后 sheet 列表干净无冗余。
- **Acceptance Criteria（EARS）**：
  1. WHEN I 循环 6 文件合并加载时, THE chain_orchestrator SHALL 调用 `_merge_sheets_dedup` 对底稿目录/GT_Custom/附注披露(上市公司)/附注披露(国企)/调整分录汇总通用样式 sheet 按归一化名称去重保留首次出现
  2. WHEN 合并完成后, THE chain_orchestrator SHALL 将原始 86 sheet 去重至 = `N_i_dedup_sheets`（实测 67）
  3. THE chain_orchestrator SHALL 复用 D spec 已实现的 `_normalize_sheet_name` 函数（0 代码改动）
  4. WHEN I3 "参考－商誉减值测试示例" sheet 出现时, THE `_should_skip_historical_sheet` SHALL 正确过滤（已被现行 regex 覆盖，0 代码改动）
  5. WHEN 合并过程中遇到 I1 摊销测算 2 版本（I1-10/I1-11）或 I4 摊销 2 版本（I4-6/I4-7）, THE chain_orchestrator SHALL 全部保留为不同 sheet（含括号/方法修饰词区分，不会被误去重）
- **量化指标**：合并后 sheet 数 = 67；I3 历史遗留 1 sheet 被过滤；无重复"底稿目录"/"GT_Custom"

### I-F2 I1 摊销测算 2-version 分支选择器
- **优先级**：P1
- **依赖**：复用 H-F3 `useDepreciationBranchSelector` 模式
- **User Story**：As a 审计助理，I want 打开 I1 摊销测算时看到分支选择器（不含减值/含减值），so that 我能快速切换到正确版本。
- **Acceptance Criteria（EARS）**：
  1. WHEN 用户打开 I1-10 或 I1-11 摊销测算 sheet, THE SYSTEM SHALL 在 sheet 顶部显示分支选择器（不含减值 / 含减值）
  2. WHEN 用户选择某分支, THE SYSTEM SHALL 路由到对应 sheet
  3. WHEN 切换分支, THE SYSTEM SHALL 保留前一分支已填数据（不清空）
  4. 同款应用于 I4-6 / I4-7（直线法 / 工作量法）共 2 个摊销位置
- **量化指标**：vitest 分支选择器测试 3/3 通过（I1-10/I1-11 + I4-6/I4-7 + 切换保留数据）

### I-F3 I 循环 sheet 分组 10 类规则
- **优先级**：P1
- **依赖**：复用 `useDSalesCycleSheetGroups` 模式新建 `useIIntangibleAssetSheetGroups.ts`
- **User Story**：As a 审计助理，I want I 循环 sheet 按业务类型分组显示，so that 我能快速定位目标 sheet。
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 将 I 循环 67 个 sheet 按 10 类规则分组：索引 / 历史遗留 / 总控台 / 审定表 / 附注披露 / 明细表 / 摊销测算 / 减值测试 / 针对性检查 / 调整分录（+ fallback 其他）
  2. 索引 + 历史遗留类 defaultHidden=true；附注披露类 readonly=true
  3. THE 分组规则 SHALL 对任意真实 I sheet 名匹配恰好 1 类（PBT-P5 验证）
- **量化指标**：10 类规则对 67 个 sheet 全覆盖；PBT-P5 通过

### I-F4 I3 商誉减值 DCF 弹窗
- **优先级**：P1
- **依赖**：复用 H-F12 `AssetImpairmentDialog` 模式
- **User Story**：As a 审计助理，I want I3 商誉减值测试有 AI 辅助 DCF 分析，so that 我能快速评估商誉是否减值。
- **Acceptance Criteria（EARS）**：
  1. WHEN 用户打开 I3-6/I3-7 商誉减值测试 sheet, THE SYSTEM SHALL 提供"AI 辅助分析"按钮
  2. THE 弹窗输入 SHALL 包含：资产组(CGU) ID / 商誉账面价值 / 资产组账面价值 / 5 年现金流预测 / 折现率 / 终值增长率
  3. THE 输出 SHALL 为：可收回金额 = max(公允价值−处置费用, 未来现金流现值) + 与含商誉资产组账面价值比较 + 减值金额
  4. THE 商誉减值特殊逻辑 SHALL 为：减值先冲减商誉，剩余再按比例分摊到资产组其他资产（CAS 8 规定）
  5. 当前为 stub 实现（DCF 公式正确但 LLM 真实接入待 wp_ai_service 升级）
  6. 支持 `apply_to_sheet` 写回 + `Depends(require_project_access("edit"))` RBAC
- **量化指标**：单测验证 DCF 公式 + 商誉减值分摊逻辑 + write-back 联动

### I-F5 I2 开发支出资本化时点判断辅助
- **优先级**：P1
- **依赖**：新建 `wp_i_capitalization` 路由（I-cycle 独有）
- **User Story**：As a 审计助理，I want 系统辅助判断研发项目资本化时点（CAS 6 五条件），so that 我能准确确定资本化起始日期。
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 提供 endpoint `POST /api/projects/{pid}/workpapers/{wid}/i2/capitalization-check` 接受 5 个条件布尔值 + 项目起止日期
  2. WHEN 5 个条件全部为 True 时, THE 系统 SHALL 返回建议资本化起始日期 = 最后一个条件满足日期
  3. WHEN 任一条件为 False 时, THE 系统 SHALL 返回"不满足资本化条件" + 缺失条件清单
  4. THE endpoint SHALL 使用 `Depends(require_project_access("edit"))` RBAC 校验
  5. WHEN 请求 body 含 `apply_to_sheet: str` 字段时, THE 系统 SHALL 把判断结果写回 `working_paper.parsed_data.capitalization_checks[sheet]`
  6. THE 前端 I2-6 sheet SHALL 提供"资本化时点判断"按钮触发弹窗
- **量化指标**：单测 5 条件组合（32 种）至少 8 个 case 通过 + 写回联动 + RBAC

### I-F6 三角勾稽 VR 规则 ≥ 3 条
- **优先级**：P0
- **依赖**：复用 `consistency_gate.check_*_triangle` 模式
- **User Story**：As a 合伙人，I want 无形资产期末/商誉减值/研发费用勾稽自动校验，so that I 类底稿异常能及时发现。
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 新增 3 条 validation_rules：
     - **VR-I1-01**（blocking, tolerance=1.0）：I1 无形资产期末 = I1 期初 + I1 增加(I1-5) − I1 减少(I1-6) − 本期摊销(I1-10/I1-11)
     - **VR-I3-01**（blocking, tolerance=1.0）：I3 商誉期末 = I3 期初 − 本期减值(I3-6)（商誉不摊销，仅减值）
     - **VR-I6-01**（blocking, tolerance=1.0）：I6 研发费用总额 = 费用化支出(I6) + 资本化支出(I2)（同一研发活动两面）
  2. WHEN VR-I1-01 / VR-I3-01 / VR-I6-01 blocking 规则校验失败时, THE ConsistencyGatePanel SHALL 阻断对应底稿签字
  3. THE VR 规则 SHALL 写入 `backend/data/i_cycle_validation_rules.json`
  4. THE consistency_gate 服务 SHALL 新增 `check_i_cycle_triangle_reconciliation()` 方法注入主 `run_all_checks` 流程
- **量化指标**：3 条 VR 各至少 1 个 pass / 1 个 fail / 1 个 skip 测试；阻断签字 e2e 测试通过

### I-F7 cross_wp_references ≥ 20 条新增
- **优先级**：P0
- **依赖**：复用 F-F7 ref_id 起编模式（基于运行时 max(ref_id)+1）
- **User Story**：As a 项目经理，I want I 循环跨底稿引用完整覆盖，so that 联动传播和 stale 标记正常工作。
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 新增 ≥ 20 条 cross_wp_references（起编基于运行时 max(ref_id)+1，预计 CW-241+ after H spec）
  2. 按 5 分组：I 内部联动（≥ 5）/ I→报表（≥ 3）/ I→附注（≥ 4）/ I→K 期间费用(摊销+研发分摊)（≥ 4）/ I→A 财务报表（≥ 4）
  3. 强制场景：I6 研发费用 → K8 管理费用（研发费用归集）+ I1 摊销 → D5/K8 分摊
  4. THE ref_id SHALL 基于运行时 `max(ref_id) + 1` 起编（禁止硬编码起始编号）
- **量化指标**：N_i_cwr_count 从 5 → ≥ 25（即新增 ≥ 20）

### I-F8 I6↔I2 研发费用↔开发支出反向回填
- **优先级**：P1
- **依赖**：复用 F-F8 反向回填模式
- **User Story**：As a 审计助理，I want I2 开发支出保存后自动回填 I6 研发费用对应资本化金额，so that 费用化+资本化=总额勾稽自动维护。
- **Acceptance Criteria（EARS）**：
  1. THE cross_wp_references SHALL 新增 I2→I6 + I6→I2 双向回填条目（category=data_flow_reverse, severity=warning）
  2. WHEN I2 开发支出保存（资本化金额确定）, THE event_handler SHALL emit `WORKPAPER_SAVED` + wp_code='I2' 过滤
  3. WHEN 事件触发时, THE stale_engine SHALL 沿 cross_wp_references 路径传播到 I6 研发费用对应 cell
  4. WHEN I6 研发费用保存（费用化金额确定）, THE stale_engine SHALL 反向传播到 I2 开发支出
  5. THE 前端 I6/I2 编辑器 SHALL 订阅 `cross-ref:updated` 事件自动刷新
- **量化指标**：集成测试 `test_i6_i2_reverse_backfill.py` 全过；I2 保存后 I6 单元格 0.5s 内可见 stale 标记

### I-F9 B/C 前置状态横幅 C8+C9
- **优先级**：P1
- **依赖**：复用 `usePrerequisiteStatus.ts` 加 I_CYCLE_PREREQUISITES
- **User Story**：As a 项目经理，I want I 循环底稿顶部显示前置控制测试完成状态，so that 我能判断是否可启动实质性程序。
- **Acceptance Criteria（EARS）**：
  1. THE 前置底稿（Sprint 0 实测核验过，致同 2025 真实编号）SHALL 为：
     - **C8 无形资产及其他长期资产循环控制测试**（I1/I3/I4/I5 共用）
     - **C9 研发循环控制测试**（I2/I6 专用）
  2. 横幅状态：全完成 → ready；部分完成 → partial；未启动 → blocked
  3. 路由：`^I\d` 命中 → 加载 I_CYCLE_PREREQUISITES = [C8, C9]（其中 C9 仅 I2/I6 路径强制）
- **量化指标**：I1 顶部前置横幅可见，wp_code 路由按 `^I\d` 命中 C8 + C9 两条

### I-F10 prefill 扩展 ≥ 60 cells
- **优先级**：P0
- **依赖**：openpyxl 实测真实 sheet 名（**ADR-I 铁律：禁止臆造**）
- **User Story**：As a 审计助理，I want I 循环明细表/摊销测算/减值测试有预填公式，so that 我不需要手工从试算平衡表抄录数据。
- **Acceptance Criteria（EARS）**：
  1. 全部 cell 必须用 4-arg `=AUX(code, aux_type, aux_code, column)`（D/F/H spec 修复轮校验过的语法）
  2. 全部 sheet 名必须经 openpyxl 实测核对
  3. 目标分布：
     - I1 明细表I1-2：≥ 10 cell
     - I1 摊销测算 2 版（I1-10/I1-11）：≥ 12 cell
     - I2 明细表I2-2 + 资本化时点I2-6：≥ 10 cell
     - I3 明细表I3-2 + 减值测试I3-6：≥ 8 cell
     - I4 明细表I4-2 + 摊销测算I4-6/I4-7：≥ 8 cell
     - I6 明细表I6-2：≥ 8 cell
     - 合计：**≥ 60 cells**
  4. WHEN Sprint 0.X 实测 tb_aux_balance 无 I 类辅助账数据时, THE 目标 SHALL 降级为仅 =TB/=LEDGER（≥ 40 cells）
- **量化指标**：`test_i_prefill_extension.py` 10 项测试通过（含 4-arg AUX 校验 + 真实 sheet 名校验）

---

## 三·B、Sprint 0 关键偏差发现（修正后续 design.md ADR）

| # | 起草前假设 | Sprint 0 实测 | 偏差影响 | 修正方案 |
|---|----------|--------------|---------|---------|
| 1 | I 循环也有多个历史遗留 sheet | **仅 1 命中**（I3 "参考－商誉减值测试示例"）| 不需扩展 regex | 保留回归测试即可 |
| 2 | I 循环有 B23-X / B51-X 前置底稿 | **无**（仅 C8 + C9）| I-F9 前置清单简化 | 仅配置 C8 + C9 |
| 3 | I 循环 prefill 覆盖度类似 H（12 entries / 56 cells）| 仅 7 entries / **34 cells** | 工时投入比预估更大 | I-F10 加 Sprint 0.X 前置实测 |
| 4 | I2 开发支出有 IPO 应对类底稿 | **无**（I 循环模板无 IPO 专属文件）| 不需 IPO 占位 | 删除 IPO 相关需求 |
| 5 | I3 商誉有复杂多版本 sheet | **无**（I3 仅单版本，减值测试 3 sheet 各有独立 wp_code I3-6/I3-7/I3-8）| 不需分支选择器 | I3 走标准路由 |

**关键修正后的实施基线**：
```python
N_i_files = 6                     # ✅
N_i_raw_sheets = 86               # ✅
N_i_historical_sheets = 1         # ✅ I3 "参考－商誉减值测试示例"
N_i_dedup_sheets = 67             # ✅
N_i_prefill_entries = 7           # ✅
N_i_prefill_cells = 34            # ✅
N_i_cwr_count = 5                 # ✅
N_cwr_max_id = 210                # ✅ 运行时 max+1 起编
N_i_branch_selector_positions = 2 # I1-10/I1-11 + I4-6/I4-7
N_i_c_prerequisites = 2           # C8 + C9
```

---

## 四、非功能需求

### 4.1 性能

| 指标 | 目标 | 参照 |
|------|------|------|
| chain 生成 I 循环 6 主底稿（scenario=normal）| < 30s（I 循环 6 文件 86 sheet，约 H 的 46%）| H spec < 60s |
| I1 单底稿打开（含 17 sheet）| < 5s | H spec H1 < 8s |
| I 循环 sheet 分组导航切换 | < 200ms | F/H spec |
| I-F6 VR 三角勾稽校验（3 条规则）| < 500ms | H spec VR-H1 |
| I-F7 cross_wp_ref stale 传播 | < 500ms | E1 spec |
| I-F5 资本化时点判断 API | < 200ms（纯逻辑，无 DB IO）| 新增 |
| I-F4 商誉减值 DCF 弹窗打开 | < 300ms | H spec AssetImpairmentDialog |

### 4.2 兼容性 / 回归白名单

**必须不破坏的现有循环**：
- ✅ D 销售循环（53 task + 20 UAT pass）
- ✅ E1 货币资金循环（91 task pass）
- ✅ F 采购存货循环（44 task + 16 UAT ✓ + 1 partial + 2 stub）
- ✅ H 固定资产循环（待实施，不影响）
- ✅ G/J/K/L/M/N 其他循环

**关键兼容性约束**：
- THE I spec SHALL NOT 修改 `_normalize_sheet_name` 函数签名或行为
- THE I spec SHALL NOT 修改 `_should_skip_historical_sheet` 现有模式（I3 已被覆盖，无需扩展）
- THE I spec SHALL NOT 引入新 vue 依赖
- WHEN 修改 prerequisite-status 路由时, THE I spec SHALL 仅追加 `^I\d` 命中分支

### 4.3 可观测性

- I-F1 合并去重日志记录 `chain_executions.merge_dedup_summary`（已 D/F/H spec 实现）
- I-F6 VR-I1-01/I3-01/I6-01 校验结果写入 `validation_rule_results` 表
- I-F7 stale 传播写 `linkage_audit_log`
- I-F8 I6↔I2 反向回填事件写 `event_log`
- I-F5 资本化时点判断日志写 `wp_calculation_log`
- I-F4 商誉减值 DCF stub 调用日志写 `wp_ai_call_log`

---

## 四·B、UAT 验收清单（15 项 ⭐ 上线门槛 ≥ 12 项 ✓ pass）

> 状态枚举：`✓ pass` / `⚠ partial` / `⚠ stub` / `✗ fail` / `○ pending-uat`
>
> **上线门槛**：≥ 12 项 ✓ pass + **P0 关键项**（#1, #3, #9, #10, #11）必须**全部** ✓ pass

| # | 验收项 | 对应需求 | Sprint | P | Status |
|---|-------|---------|--------|---|--------|
| 1 | 6 文件合并后 sheet 数 = 67，I3 历史遗留 1 sheet 被过滤，无重复"底稿目录"/"GT_Custom" | I-F1 | S1 | **P0** | ○ |
| 2 | I1-10/I1-11 摊销分支选择器可用 + I4-6/I4-7 摊销分支选择器可用 | I-F2 | S2 | P1 | ○ |
| 3 | I 循环模板历史遗留 1 sheet 正确过滤 + D/F/H 历史遗留过滤回归无影响 | I-F1 | S1 | **P0** | ○ |
| 4 | I 循环 sheet 列表按 10 类分组显示，可折叠展开 | I-F3 | S2 | P1 | ○ |
| 5 | I3-6/I3-7 商誉减值 DCF 弹窗 + AI 辅助分析按钮 | I-F4 | S2 | P1 | ○ |
| 6 | 商誉减值分摊逻辑正确（先冲商誉，剩余按比例分摊） | I-F4 | S2 | P1 | ○ |
| 7 | I2-6 资本化时点判断 5 条件全勾选 → 建议起始日期 | I-F5 | S2 | P1 | ○ |
| 8 | I2-6 资本化时点判断任一条件 False → 返回缺失清单 | I-F5 | S2 | P1 | ○ |
| 9 | VR-I1-01 / VR-I3-01 / VR-I6-01 blocking 阻断对应底稿签字 | I-F6 | S2 | **P0** | ○ |
| 10 | cross_wp_references I 循环条目 ≥ 25（基线 5 + 新增 ≥ 20，起编运行时 max+1） | I-F7 | S2 | **P0** | ○ |
| 11 | I6↔I2 双向回填（I2 保存后 I6 stale 0.5s 内可见 + 反向） | I-F8 | S2 | **P0** | ○ |
| 12 | I1 顶部前置横幅显示 C8 + C9（实测真实编号） | I-F9 | S2 | P1 | ○ |
| 13 | I1-2 明细表 prefill ≥ 10 cell（=AUX 4-arg 真实维度） | I-F10 | S2 | P1 | ○ |
| 14 | I1-10/I1-11 摊销测算 prefill ≥ 12 cell | I-F10 | S2 | P1 | ○ |
| 15 | I 循环摊销引擎 2 种方法（直线+工作量）+ write-back + RBAC | I-F2/I-F10 | S3 | P1 | ○ |

---

## 五、测试矩阵

### 5.1 单测（pytest）

| 测试文件 | 覆盖 |
|---------|------|
| `test_i_merge_dedup.py` | I-F1 6 文件合并去重（86→67 sheet）+ I3 历史遗留过滤 |
| `test_i_branch_selector.spec.ts` | I-F2 I1-10/I1-11 + I4-6/I4-7 分支选择器 |
| `test_i_sheet_groups.py` | I-F3 10 类分组规则全覆盖 |
| `test_i_goodwill_impairment.py` | I-F4 商誉减值 DCF + 分摊逻辑 + write-back |
| `test_i2_capitalization_check.py` | I-F5 5 条件组合 + 写回联动 + RBAC |
| `test_i_validation_rules.py` | I-F6 VR-I1-01/I3-01/I6-01 共 3 条规则 |
| `test_i_cross_wp_refs.py` | I-F7 ≥ 20 条新增 + ref_id 唯一 + stale 传播 |
| `test_i6_i2_reverse_backfill.py` | I-F8 I6↔I2 双向回填集成测试 |
| `test_i_prefill_extension.py` | I-F10 新增 ≥ 60 cell + 4-arg AUX 校验 |

### 5.2 属性测试（hypothesis）

| PBT | Property | Sprint | max_examples | Validates |
|-----|---------|--------|-------------|-----------|
| P1 | Sheet 名归一化幂等性 | S1 | 100 | I-F1 |
| P2 | 历史遗留 sheet 过滤正确性（I3 1 命中 + D/F/H 回归） | S1 | 50 | I-F1 |
| P3 | cross_wp_references ref_id 全局唯一性 | S2 | 50 | I-F7 |
| P4 | VR-I1-01 / VR-I3-01 / VR-I6-01 三角勾稽正确性 | S2 | 200 + 9 显式 boundary | I-F6 |
| P5 | I 循环 10 类 sheet 分组规则完备性 | S2 | 200 | I-F3 |

### 5.3 集成测试

| 测试文件 | 覆盖 |
|---------|------|
| `test_i_cycle_full_chain.py` | I 循环 6 主底稿 chain 生成 + sheet 数验证 |
| `test_i6_i2_reverse_backfill.py` | I-F8 I6↔I2 双向回填端到端 |
| `test_i3_goodwill_impairment_apply.py` | I-F4 商誉减值写回 → I3-6 sheet parsed_data 验证 |

### 5.4 UAT（手动验收，详见 §四·B）

15 项验收项 + 5 项 P0 关键项门槛（#1/#3/#9/#10/#11）。

---

## 五·B、成功判据汇总

| 类别 | 验收项 | 量化指标 |
|------|-------|---------|
| **合并去重（P0）** | I-F1 6 文件合并 | 86 → 67 sheet（I3 历史 1 过滤 + 跨文件去重）|
| **导航体验（P1）** | I-F2 摊销分支选择器 | 2 个位置（I1-10/I1-11 + I4-6/I4-7）|
| | I-F3 sheet 分组 | 10 类规则全覆盖 67 sheet |
| **智能辅助（P1）** | I-F4 商誉减值 DCF | stub + 分摊逻辑 + write-back |
| | I-F5 资本化时点 | 5 条件判断 + 建议日期 + write-back |
| **勾稽联动（P0）** | I-F6 三角勾稽 | 3 条 VR blocking 阻断签字 |
| | I-F7 cross_wp_ref | ≥ 20 条新增（目标 N_i_cwr ≥ 25）|
| | I-F8 I6↔I2 回填 | 双向 stale 0.5s 内传播 |
| **前置驱动（P1）** | I-F9 前置横幅 | C8 + C9 状态可视 |
| **数据覆盖（P0）** | I-F10 prefill | 34 → ≥ 94 cell（新增 ≥ 60）|

---

## 六、术语表

| 术语 | 定义 |
|------|------|
| **I 循环** | 无形资产循环（I1 无形资产 / I2 开发支出 / I3 商誉 / I4 长期待摊费用 / I5 其他非流动资产 / I6 研发费用 共 6 主底稿，6 物理文件 86 sheet）|
| **I1A** | 无形资产实质性程序表（I1 总控台）|
| **I1-10 / I1-11** | 摊销测算表 2 版（不含减值-剩余年限法 / 含减值）|
| **I2-6** | 研发项目资本化时点判断（CAS 6 五条件）|
| **I3 商誉** | 企业合并中购买方成本超过被购买方可辨认净资产公允价值的差额；不摊销，年度减值测试 |
| **I4-6 / I4-7** | 长期待摊费用摊销测算 2 版（直线法 / 工作量法）|
| **I6 研发费用** | 研发活动中费用化部分（计入当期损益），与 I2 开发支出（资本化）互为补充 |
| **CAS 6 五条件** | 开发支出资本化条件：①技术可行性 ②完成意图 ③使用或出售能力 ④未来经济利益 ⑤资源充足 |
| **CGU（资产组）** | Cash-Generating Unit，商誉减值测试的最小单元 |
| **商誉减值分摊** | CAS 8 规定：减值先冲减商誉，剩余按比例分摊到资产组其他资产（但不低于各资产可收回金额）|
| **三角勾稽（I 循环版）** | I1 期末 = 期初 + 增加 − 减少 − 摊销；I3 期末 = 期初 − 减值；I6 总额 = 费用化 + 资本化 |
| **直线法（摊销）** | (原值 − 残值) / 使用年限，每月摊销严格相等 |
| **工作量法（摊销）** | (原值 − 残值) / 总工作量 × 当期工作量 |
| **C8** | 无形资产及其他长期资产循环控制测试（致同 2025 真实编号）|
| **C9** | 研发循环控制测试（致同 2025 真实编号）|

---

---

## 七、本 spec 的明确不做（边界）

- ❌ J 循环（职工薪酬 + 股份支付）— 独立 spec
- ❌ K 循环（期间费用）— 独立 spec
- ❌ N 循环（税费 — 研发费用加计扣除税务计算）
- ❌ 移动端 APP
- ❌ 7 循环函证统一管理中心（O1）
- ❌ B/C/D-N 三层联动机制（O8）
- ❌ I 循环 IPO 应对类底稿（致同模板未提供，Sprint 0 实测确认无 IPO 专属文件）
- ❌ 真实 LLM 接入（I-F4 商誉减值停留在 stub，待 O-LLM-Integration spec）

---

## 八、启动条件检查清单（实施前必满足）

- [x] Sprint 0 现状核验通过（N_i_files=6 / raw=86 / dedup=67 / historical=1 / prefill_entries=7 / prefill_cells=34 / cwr_count=5 / max_id=210）
- [x] D spec git commit 锁定
- [x] F spec 44/44 completed + UAT 达标
- [x] E1 spec 91/91 completed
- [ ] H spec 实施完成（I-F4 依赖 H-F12 AssetImpairmentDialog 模式；可并行启动，I-F4 延后）
- [ ] requirements.md review 完成
- [ ] design.md review 完成
- [ ] tasks.md review 完成
- [ ] Sprint 0.X 前置实测（I1-2 明细表表头 + tb_aux_balance I 类真实 aux_type/aux_code）

**启动条件 4/9 已满足 — 待 H spec 实施 + review + Sprint 0.X 前置实测后启动 Sprint 1**

---

> **本 requirements.md 配套**：design.md v1.0 + tasks.md v1.0
