# G 投资循环底稿优化 — Requirements

> **Spec**: `workpaper-g-investment-cycle`
> **版本**: v1.0
> **依赖前置 spec**：`workpaper-d-sales-cycle` ✅ + `workpaper-f-purchase-inventory` ✅ + `workpaper-e1-cash-optimization` ✅
> **基线日期**: 2026-05-19（Sprint 0 实测落地）

## 变更记录

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-05-19 | 三件套需求初版 — Sprint 0 实测基线 + 9 项关键业务发现 + 12 项功能需求 |

---

## 〇、依赖矩阵

| 上游 spec | 状态 | 本 spec 依赖 | Fallback |
|-----------|------|------------|---------|
| `workpaper-d-sales-cycle` | ✅ 53/53 + UAT 20 | D 循环核心产出复用：`_normalize_sheet_name` / `_merge_sheets_dedup` / `_should_skip_historical_sheet`（4+1 模式）/ `SCENARIO_TO_FILE_FILTER` / `useDSalesCycleSheetGroups` 模式 / `ConsistencyGatePanel` / `usePrerequisiteStatus` / PBT P1~P7 模式 / 4-arg AUX 强制约定 / 真实 sheet 名 openpyxl 实测铁律 | D spec 必须先 commit |
| `workpaper-f-purchase-inventory` | ✅ 44/44 + UAT 16✓+1 partial+2 stub | F 循环成熟产出复用：`_ensure_ipo_loaded(prefix)` 通用化 / `apply_to_sheet` 写回联动模式 / `require_project_access("edit")` RBAC / cross_wp_references 起编 max(ref_id)+1 模式 / `consistency_gate.check_*_triangle_reconciliation` 模式 / confirmation_service 函证模式（G0 复用）| F spec 必须先 commit |
| `workpaper-e1-cash-optimization` | ✅ 91/91 | E1 9 个核心组件复用 + scenario 字段 + LLM API + attachment_service + Univer Sheet 路由 | - |
| `global-linkage-bus` | ✅ 已完成 | LinkageGraphBuilder / stale_engine / 反向索引 / `cross-ref:updated` 事件 | - |
| `template-library-coordination` | 63/64 | seed_load_history 表 / reseed 流程 / wp_template_metadata | - |
| `enterprise-linkage` | ✅ 已完成 | useEditingLock / cross-module event bus / RBAC require_project_access | - |

---

## 一、为什么做（业务/技术根因）

### 1.1 业务痛点（合伙人 / 项目经理 / 审计助理实际遇到的 9 类核心问题）

1. **金融工具分类判断复杂（IFRS 9 / CAS 22）**：G1 交易性金融资产需做"业务模式分析"（G1-8）+ "合同现金流量特征分析 SPPI 测试"（G1-10），分类错误直接影响后续计量和损益确认；当前无系统化辅助
2. **公允价值层级测试（Level 1/2/3）核心且复杂**：G1/G6/G8/G10/G12/G13 共 6 个子循环涉及公允价值测试，Level 3 需 DCF 不可观察输入估值；当前无统一弹窗辅助
3. **G7 长期股权投资三种核算方式切换**：权益法 / 成本法 / 公允价值法，每种方式的后续计量、投资收益确认、减值测试逻辑完全不同；当前无项目级配置驱动 sheet 显隐
4. **G4/G6 预期信用损失（ECL）三阶段模型**：Stage 1（12 个月 ECL）/ Stage 2（整个存续期 ECL 未信用减值）/ Stage 3（整个存续期 ECL 已信用减值），模型复杂度高于 F2 跌价 NRV
5. **投资收益跨循环联动极度欠缺**：G11 投资收益 / G13 公允价值变动收益 / G14 信用减值损失均需汇入利润表，当前 cross_wp_references 仅 8 条
6. **G0 函证与 D0/F0/H0 同模式但未配置**：G0 投资函证需复用 confirmation_service（wp_code='G0'），当前未注册
7. **15 个子循环为全部循环中最多**：G0~G14 共 15 个物理文件 197 raw sheets，管理复杂度最高
8. **4 个历史遗留 sheet 已被现行 regex 覆盖**：G11/G12/G13/G14 各含 1 个"修订前" sheet，已被 `_should_skip_historical_sheet` 现行模式命中
9. **B/C 前置底稿无联动**：C5（投资循环控制测试）与 G1A 程序执行无前置状态驱动

### 1.2 技术根因（代码锚定核验后）

1. **prefill_formula_mapping G 类极度欠覆盖（16 entries / 74 cells）**：仅审定表层 + G1 分析程序有 prefill；明细表 / 公允价值测试 / ECL 测试 / 收益测算 全部空白
2. **cross_wp_references G 相关仅 8 条**：目标新增 ≥ 25 条
3. **`_should_skip_historical_sheet` 已覆盖 G11/G12/G13/G14 历史遗留**：4 个"修订前" sheet 已被现行 regex 命中，不需扩展
4. **G7 三种核算方式无项目级配置**：当前所有 G7 sheet 全部显示，无法按企业实际核算方式过滤
5. **公允价值层级测试无统一弹窗**：Level 1（市场报价）/ Level 2（可观察输入）/ Level 3（DCF 不可观察输入）需分层处理
6. **ECL 三阶段模型未实现**：G4 债权投资 / G6 其他债权投资需 ECL 计算引擎
7. **G0 函证未注册到 confirmation_service**：D0/F0/H0 已注册，G0 缺失

### 1.3 本 spec 边界

- ✅ **本 spec 做**：G0~G14 共 15 主底稿优化（G-F1 至 G-F12 共 12 项修复）
- ❌ **本 spec 不做（独立 spec）**：
  - H 循环（固定资产 + 在建工程 + 使用权资产）
  - I 循环（无形资产 + 商誉 + 开发支出）
  - 金融工具估值外部数据库 / Bloomberg / Wind 接口对接
  - 移动端 APP
  - 7 循环函证统一管理中心（O1）
  - B/C/D-N 三层联动机制（O8）
  - 衍生金融工具套期会计专项（G1-14 衍生工具核查表仅基础检查，复杂套期独立 spec）

---

## 一·B、Sprint 0 实测基线（附录 A）

| 变量 | 实测值 | 来源 |
|------|-------|------|
| `N_g_files` | 15 | `wp_templates/G/` 目录扫描（G0~G14）|
| `N_g_raw_sheets` | 197 | openpyxl 全文件 sheet 累加 |
| `N_g_historical_sheets` | **4** | G11/G12/G13/G14 各含 1 个"修订前" sheet，被现行 regex 命中 |
| `N_g_dedup_sheets` | 152 | 现行 `_normalize_sheet_name` 去重后 |
| `N_g_prefill_entries` | 16 | `prefill_formula_mapping.json` 中 wp_code 以 G 开头的 entry |
| `N_g_prefill_cells` | 74 | 同上，全部 cells 累加 |
| `N_g_cwr_count` | 8 | `cross_wp_references.json` 中 source_wp 或 targets[*].wp_code 以 G 开头 |
| `N_cwr_max_id` | 210 | 全仓 ref_id 数值最大值（运行时 max+1 起编）|

**当前 G prefill 16 entries 覆盖审定表 + G1 分析程序**：

```
G0  审定表G0-1            cells=2
G1  审定表G1-1            cells=5
G1  分析程序G1-3          cells=2
G2  审定表G2-1            cells=5
G3  审定表G3-1            cells=5
G4  审定表G4-1            cells=5
G5  审定表G5-1            cells=5
G6  审定表G6-1            cells=5
G7  长期股权投资审定表G7-1  cells=5
G8  审定表G8-1            cells=5
G9  审定表G9-1            cells=5
G10 审定表G10-1           cells=5
G11 审定表G11-1           cells=5
G12 审定表G12-1           cells=5
G13 审定表G13-1           cells=5
G14 审定表G14-1           cells=5
合计: 16 entries / 74 cells
```

---

## 二、9 项关键业务发现（驱动 spec 走向）

### A. 15 子循环为全部循环中最多 — 但无同 wp_code 多 sheet 问题
- G0~G14 共 15 物理文件 197 sheet，合并后 152 sheet
- 与 H 循环不同，G 循环**无同 wp_code 多 sheet 情况**（每个 sheet 的 wp_code 唯一）
- **影响**：不需要 `resolveMainVersionSheet` 路由保护，不需要分支选择器

### B. 4 个历史遗留 sheet 已被现行 regex 覆盖
- G11 "投资收益（修订前）" / G12 "净敞口套期收益（修订前）" / G13 "公允价值变动收益（修订前）" / G14 "信用减值损失（修订前）"
- 已被 `_should_skip_historical_sheet` 现行"修订前"模式命中
- **影响**：不需要扩展 regex，仅需回归验证

### C. 公允价值测试是 G 循环核心 — 6 个子循环涉及
- G1 交易性金融资产 / G6 其他债权投资 / G8 其他权益工具投资 / G10 交易性金融负债 / G12 净敞口套期 / G13 公允价值变动
- Level 1（活跃市场报价）/ Level 2（可观察输入）/ Level 3（DCF 不可观察输入）
- **影响**：需新增 G-F4 公允价值测试弹窗（复用 H-F12 AssetImpairmentDialog 模式）

### D. G7 长期股权投资三种核算方式（G-cycle 独有复杂度）
- 权益法（equity_method）：对联营/合营企业，按持股比例确认投资收益
- 成本法（cost_method）：对子公司，仅分红时确认投资收益
- 公允价值法（fair_value_method）：对无重大影响的少数股权
- **影响**：需新增 G-F3 项目级配置（类似 H-F2 measurement_model，但 3 档枚举）

### E. G4/G6 ECL 三阶段模型（独立于 F2 跌价 NRV）
- Stage 1：12 个月预期信用损失（信用风险未显著增加）
- Stage 2：整个存续期预期信用损失（信用风险显著增加但未信用减值）
- Stage 3：整个存续期预期信用损失（已信用减值）
- 单调性约束：Stage 1 ECL ≤ Stage 2 ECL ≤ Stage 3 ECL
- **影响**：需新增 G-F5 ECL 计算引擎

### F. 投资收益跨循环联动（G11→利润表 / G13→利润表 / G14→利润表）
- G11 投资收益 = 各子循环投资收益汇总（G1+G4+G6+G7+G8）
- G13 公允价值变动收益 = G1 公允价值变动 + G10 公允价值变动
- G14 信用减值损失 = G4 ECL 变动 + G6 ECL 变动
- **影响**：VR 规则 + cross_wp_references 联动

### G. G0 函证与 D0/F0/H0 同模式
- G0 投资函证（函证程序表G0A / 函证结果汇总表G0-1 / 核实被函证单位信息G0-2 等）
- 复用 confirmation_service（wp_code='G0'）
- **影响**：G-F8 函证反向回填（G0→G7 等）

### H. 金融工具分类（IFRS 9 / CAS 22）是 G 循环独有逻辑
- G1-8 业务模式分析：持有以收取合同现金流量 / 既收取又出售 / 其他
- G1-10 合同现金流量特征分析（SPPI 测试）：仅为本金和利息的支付
- 分类结果决定后续计量方式（摊余成本 / FVOCI / FVTPL）
- **影响**：G-F11 辅助分类逻辑（P2 打磨）

### I. 无 measurement_model 双模式（与 H 循环不同）
- G 循环不存在"成本模式 vs 公允价值模式"的项目级切换
- G7 三种核算方式是按**每笔投资**配置，不是项目级全局切换
- **影响**：G-F3 设计为 per-investment 配置而非 project-level 全局

---

## 三、功能需求（G-F1 至 G-F12）

> 命名规则：`G-F<n>` 与 D/F/H/I spec 保持一致；每项需求标注「依赖前置 spec」「P 优先级」「主受益 wp_code」。

### G-F1 15 文件合并 + GT_Custom/底稿目录跨文件去重
- **优先级**：P0
- **依赖**：复用 `_merge_sheets_dedup`（D/F/H spec 已实现，0 改动）
- **User Story**：As a 审计助理，I want G 循环 15 个物理文件合并后自动去除跨文件重复 sheet，so that 合并后 sheet 列表干净无冗余。
- **Acceptance Criteria（EARS）**：
  1. WHEN G 循环 15 文件合并加载时, THE chain_orchestrator SHALL 调用 `_merge_sheets_dedup` 对底稿目录/GT_Custom/附注披露(上市公司)/附注披露(国企)/调整分录汇总通用样式 sheet 按归一化名称去重保留首次出现
  2. WHEN 合并完成后, THE chain_orchestrator SHALL 将原始 197 sheet 去重至 = `N_g_dedup_sheets`（实测 152）
  3. THE chain_orchestrator SHALL 复用 D spec 已实现的 `_normalize_sheet_name` 函数（0 代码改动）
  4. WHEN G11/G12/G13/G14 "修订前" sheet 出现时, THE `_should_skip_historical_sheet` SHALL 正确过滤（已被现行 regex 覆盖，0 代码改动）
  5. WHEN 合并过程中遇到任意 G 循环 sheet, THE chain_orchestrator SHALL 全部保留（G 循环无同 wp_code 多 sheet 问题）
- **量化指标**：合并后 sheet 数 = 152；4 个历史遗留 sheet 被过滤；无重复"底稿目录"/"GT_Custom"

### G-F2 G 循环 sheet 分组 12 类规则
- **优先级**：P1
- **依赖**：复用 `useDSalesCycleSheetGroups` 模式新建 `useGInvestmentCycleSheetGroups.ts`
- **User Story**：As a 审计助理，I want G 循环 sheet 按业务类型分组显示，so that 我能在 152 个 sheet 中快速定位目标。
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 将 G 循环 152 个 sheet 按 12 类规则分组：索引 / 历史遗留 / 总控台 / 审定表 / 附注披露 / 明细表 / 公允价值测试 / 减值测试 / 收益测算 / 分类检查 / 函证 / 调整分录（+ fallback 其他）
  2. 索引 + 历史遗留类 defaultHidden=true；附注披露类 readonly=true
  3. THE 分组规则 SHALL 对任意真实 G sheet 名匹配恰好 1 类（PBT-P5 验证）
- **量化指标**：12 类规则对 152 个 sheet 全覆盖；PBT-P5 通过

### G-F3 G7 长期股权投资三种核算方式切换
- **优先级**：P0（G7 是投资循环核心底稿，22 sheet 最多）
- **依赖**：新增 per-investment 配置（不同于 H-F2 project-level measurement_model）
- **User Story**：As a 项目经理，I want 按每笔长期股权投资配置核算方式（权益法/成本法/公允价值法），so that G7 底稿只显示该投资适用的 sheet。
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 支持 G7 长期股权投资三种核算方式枚举：`equity_method` / `cost_method` / `fair_value_method`
  2. WHEN 项目配置某笔投资为 equity_method 时, THE 系统 SHALL 显示权益法相关 sheet（投资收益确认/权益变动/减值测试）
  3. WHEN 项目配置某笔投资为 cost_method 时, THE 系统 SHALL 显示成本法相关 sheet（分红确认/减值测试）
  4. WHEN 项目配置某笔投资为 fair_value_method 时, THE 系统 SHALL 显示公允价值法相关 sheet（公允价值测试/变动损益）
  5. IF 项目未配置核算方式, THEN THE 系统 SHALL 默认显示全部 G7 sheet（不过滤）
  6. THE 核算方式配置 SHALL 持久化在 `working_paper.parsed_data.g7_accounting_methods[]`（per-investment 数组）
- **量化指标**：G7 22 sheet 按核算方式过滤后显示正确子集；vitest 3 种方式切换测试通过

### G-F4 公允价值测试弹窗（Level 1/2/3 层级）
- **优先级**：P1
- **依赖**：复用 H-F12 `AssetImpairmentDialog` 模式
- **User Story**：As a 审计助理，I want 公允价值测试 sheet 有 AI 辅助分析弹窗，so that Level 3 DCF 估值有系统化支撑。
- **Acceptance Criteria（EARS）**：
  1. WHEN 用户打开 G1-6/G6 公允价值测试/G8 公允价值测试等 sheet, THE SYSTEM SHALL 提供"公允价值测试"按钮
  2. THE 弹窗输入 SHALL 包含：公允价值层级（Level 1/2/3）+ 金融工具类型 + 面值/数量
  3. WHEN Level 1 时, THE 系统 SHALL 仅需输入市场报价日期 + 收盘价
  4. WHEN Level 2 时, THE 系统 SHALL 需输入可观察输入参数（利率曲线/信用利差/波动率）
  5. WHEN Level 3 时, THE 系统 SHALL 需输入 DCF 参数（现金流预测/折现率/终值）并计算公允价值
  6. 当前为 stub 实现（Level 1/2 公式正确，Level 3 DCF 待 LLM 真实接入）
  7. 支持 `apply_to_sheet` 写回 + `Depends(require_project_access("edit"))` RBAC
- **量化指标**：单测验证 3 层级公式 + write-back 联动 + RBAC

### G-F5 G4/G6 ECL 预期信用损失模型
- **优先级**：P1
- **依赖**：新建 `wp_g_ecl` 路由（G-cycle 独有）
- **User Story**：As a 审计助理，I want 系统辅助计算 G4/G6 债权投资的预期信用损失，so that ECL 三阶段模型有系统化支撑。
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 提供 endpoint `POST /api/projects/{pid}/workpapers/{wid}/g/ecl-calc` 接受 ECL 三阶段参数
  2. THE 输入 SHALL 包含：stage（1/2/3）+ 账面余额 + PD（违约概率）+ LGD（违约损失率）+ EAD（违约风险暴露）
  3. WHEN stage=1 时, THE 系统 SHALL 计算 12 个月 ECL = EAD × PD_12m × LGD
  4. WHEN stage=2 时, THE 系统 SHALL 计算整个存续期 ECL = EAD × PD_lifetime × LGD
  5. WHEN stage=3 时, THE 系统 SHALL 计算整个存续期 ECL（已信用减值）= EAD × PD_lifetime × LGD（PD 接近 100%）
  6. THE 系统 SHALL 校验单调性约束：Stage 1 ECL ≤ Stage 2 ECL ≤ Stage 3 ECL
  7. THE endpoint SHALL 使用 `Depends(require_project_access("edit"))` RBAC + `apply_to_sheet` 写回
- **量化指标**：单测 3 阶段 × 3 边界 case + 单调性校验 + 写回 + RBAC

### G-F6 三角勾稽 VR 规则 ≥ 4 条
- **优先级**：P0
- **依赖**：复用 `consistency_gate.check_*_triangle` 模式
- **User Story**：As a 合伙人，I want 投资收益/公允价值变动/信用减值勾稽自动校验，so that G 类底稿异常能及时发现。
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 新增 4 条 validation_rules：
     - **VR-G7-01**（blocking, tolerance=1.0）：G7 权益法投资收益 = 被投资方净利润 × 持股比例 ± 内部交易抵消
     - **VR-G11-01**（blocking, tolerance=1.0）：G11 投资收益 = G1 投资收益 + G4 利息收入 + G6 利息收入 + G7 投资收益 + G8 处置收益
     - **VR-G1-01**（blocking, tolerance=1.0）：G1 公允价值变动 = 期末公允价值 − 期初公允价值（或上次确认公允价值）
     - **VR-G14-01**（blocking, tolerance=1.0）：G14 信用减值损失 = G4 ECL 本期变动 + G6 ECL 本期变动
  2. WHEN VR blocking 规则校验失败时, THE ConsistencyGatePanel SHALL 阻断对应底稿签字
  3. THE VR 规则 SHALL 写入 `backend/data/g_cycle_validation_rules.json`
  4. THE consistency_gate 服务 SHALL 新增 `check_g_cycle_triangle_reconciliation()` 方法注入主 `run_all_checks` 流程
- **量化指标**：4 条 VR 各至少 1 个 pass / 1 个 fail / 1 个 skip 测试；阻断签字 e2e 测试通过

### G-F7 cross_wp_references ≥ 25 条新增
- **优先级**：P0
- **依赖**：复用 F-F7 ref_id 起编模式（基于运行时 max(ref_id)+1）
- **User Story**：As a 项目经理，I want G 循环跨底稿引用完整覆盖，so that 联动传播和 stale 标记正常工作。
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 新增 ≥ 25 条 cross_wp_references（起编基于运行时 max(ref_id)+1）
  2. 按 6 分组：G 内部联动（≥ 6）/ G→利润表（≥ 4）/ G→附注（≥ 5）/ G→A 财务报表（≥ 4）/ G11→各子循环汇总（≥ 3）/ G→T1 IPE（≥ 3）
  3. 强制场景：G11 投资收益 ← G1+G4+G6+G7+G8 汇总 / G14 信用减值 ← G4+G6 ECL 变动
  4. THE ref_id SHALL 基于运行时 `max(ref_id) + 1` 起编（禁止硬编码起始编号）
- **量化指标**：N_g_cwr_count 从 8 → ≥ 33（即新增 ≥ 25）

### G-F8 G0 函证→G7 反向回填
- **优先级**：P1
- **依赖**：复用 confirmation_service（wp_code='G0'）+ F-F8/H-F8 反向回填模式
- **User Story**：As a 审计助理，I want G0 函证结果确认后自动回填 G7 长期股权投资对应确认金额，so that 我不需要手工抄录函证回函金额。
- **Acceptance Criteria（EARS）**：
  1. THE confirmation_service SHALL 注册 wp_code='G0'（复用 D0/F0/H0 已有模式）
  2. THE cross_wp_references SHALL 新增 G0→G7 反向回填条目（category=data_flow_reverse, severity=warning）
  3. WHEN G0 函证结果确认（回函金额确定）, THE event_handler SHALL emit `WORKPAPER_SAVED` + wp_code='G0' 过滤
  4. WHEN 事件触发时, THE stale_engine SHALL 沿 cross_wp_references 路径传播到 G7 对应 cell
  5. THE 前端 G7 编辑器 SHALL 订阅 `cross-ref:updated` 事件自动刷新
- **量化指标**：集成测试 `test_g0_g7_confirmation_callback.py` 全过；G0 确认后 G7 单元格 0.5s 内可见 stale 标记

### G-F9 B/C 前置状态横幅 C5
- **优先级**：P1
- **依赖**：复用 `usePrerequisiteStatus.ts` 加 G_CYCLE_PREREQUISITES
- **User Story**：As a 项目经理，I want G 循环底稿顶部显示前置控制测试完成状态，so that 我能判断是否可启动实质性程序。
- **Acceptance Criteria（EARS）**：
  1. THE 前置底稿（Sprint 0 实测核验过，致同 2025 真实编号）SHALL 为：
     - **C5 投资循环控制测试**（G0~G14 共用）
  2. 横幅状态：全完成 → ready；部分完成 → partial；未启动 → blocked
  3. 路由：`^G\d` 命中 → 加载 G_CYCLE_PREREQUISITES = [C5]
- **量化指标**：G1 顶部前置横幅可见，wp_code 路由按 `^G\d` 命中 C5

### G-F10 prefill 扩展 ≥ 80 cells
- **优先级**：P0
- **依赖**：openpyxl 实测真实 sheet 名（**ADR-G 铁律：禁止臆造**）
- **User Story**：As a 审计助理，I want G 循环明细表/公允价值测试/收益测算有预填公式，so that 我不需要手工从试算平衡表抄录数据。
- **Acceptance Criteria（EARS）**：
  1. 全部 cell 必须用 4-arg `=AUX(code, aux_type, aux_code, column)`（D/F/H spec 修复轮校验过的语法）
  2. 全部 sheet 名必须经 openpyxl 实测核对
  3. 目标分布：
     - G1 明细表G1-2 + 结存表G1-4 + 收益测算表G1-5：≥ 15 cell
     - G4 明细表 + ECL 测试：≥ 12 cell
     - G6 明细表 + ECL 测试：≥ 10 cell
     - G7 明细表 + 投资收益确认：≥ 15 cell
     - G8 明细表 + 公允价值测试：≥ 8 cell
     - G11 投资收益汇总：≥ 10 cell
     - G13 公允价值变动汇总 + G14 信用减值汇总：≥ 10 cell
     - 合计：**≥ 80 cells**
  4. WHEN Sprint 0.X 实测 tb_aux_balance 无 G 类辅助账数据时, THE 目标 SHALL 降级为仅 =TB/=LEDGER（≥ 50 cells）
- **量化指标**：`test_g_prefill_extension.py` 12 项测试通过（含 4-arg AUX 校验 + 真实 sheet 名校验）

### G-F11 G1-8 业务模式分析 + G1-10 SPPI 测试辅助
- **优先级**：P2
- **依赖**：新建 `wp_g_classification` 路由（G-cycle 独有 CAS 22 逻辑）
- **User Story**：As a 审计助理，I want 系统辅助判断金融资产分类（业务模式+SPPI），so that 分类结果有系统化支撑。
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 提供 endpoint `POST /api/projects/{pid}/workpapers/{wid}/g1/classification-check`
  2. THE 输入 SHALL 包含：business_model（hold_to_collect / hold_and_sell / other）+ sppi_result（pass / fail）
  3. WHEN business_model='hold_to_collect' AND sppi_result='pass', THE 系统 SHALL 建议分类为"以摊余成本计量的金融资产"
  4. WHEN business_model='hold_and_sell' AND sppi_result='pass', THE 系统 SHALL 建议分类为"以公允价值计量且其变动计入其他综合收益的金融资产（FVOCI）"
  5. WHEN sppi_result='fail' OR business_model='other', THE 系统 SHALL 建议分类为"以公允价值计量且其变动计入当期损益的金融资产（FVTPL）"
  6. 支持 `apply_to_sheet` 写回 + `Depends(require_project_access("edit"))` RBAC
- **量化指标**：单测 3 种分类结果 + 写回 + RBAC

### G-F12 G1A 审计导航图
- **优先级**：P2
- **依赖**：复用 WorkpaperAuditNav 组件 + 加 `G1→g1a` 路由
- **User Story**：As a 审计助理，I want G1 底稿首屏显示审计导航图，so that 我能快速了解各程序完成状态。
- **Acceptance Criteria（EARS）**：
  1. THE `resolveProcedureSheetKey` SHALL 加 `G1→g1a` / `G4→g4a` / `G7→g7a` 路由
  2. WHEN 用户首次打开 G1 底稿, THE SYSTEM SHALL 显示导航图（默认展开）
  3. THE 导航图 SHALL 展示 16+ 项程序完成状态
- **量化指标**：vitest 验证 sheetKey 路由正确

---

## 三·B、Sprint 0 关键偏差发现（修正后续 design.md ADR）

| # | 起草前假设 | Sprint 0 实测 | 偏差影响 | 修正方案 |
|---|----------|--------------|---------|---------|
| 1 | G 循环有同 wp_code 多 sheet 问题（参照 H 循环经验）| **无**（G 循环每个 sheet wp_code 唯一）| 不需要分支选择器/路由保护 | 删除分支选择器需求 |
| 2 | G 循环有 measurement_model 双模式（参照 H 循环）| **无**（G7 三种核算方式是 per-investment 而非 project-level）| G-F3 设计为 per-investment 配置 | 不复用 MEASUREMENT_MODEL_FILTER |
| 3 | G 循环历史遗留 sheet 需扩展 regex | **4 命中已被覆盖**（G11/G12/G13/G14 "修订前"）| 不需扩展 regex | 保留回归测试即可 |
| 4 | G 循环有 B23-X / B51-X 前置底稿 | **无**（仅 C5 投资循环控制测试）| G-F9 前置清单简化 | 仅配置 C5 |
| 5 | G 循环 prefill 覆盖度类似 H（12 entries / 56 cells）| 16 entries / **74 cells**（略好于 H 但仍仅审定表层）| 明细表/公允价值/ECL/收益测算全空 | G-F10 目标 ≥ 80 新 cells |
| 6 | G7 核算方式切换类似 H3 计量模式（project-level）| G7 是 **per-investment** 配置（同一项目可能有权益法+成本法+公允价值法的不同投资）| 不能用 project 表全局列 | 存入 working_paper.parsed_data |

**关键修正后的实施基线**：
```python
N_g_files = 15                    # ✅
N_g_raw_sheets = 197              # ✅
N_g_historical_sheets = 4         # ✅ G11/G12/G13/G14 "修订前"
N_g_dedup_sheets = 152            # ✅
N_g_prefill_entries = 16          # ✅
N_g_prefill_cells = 74            # ✅
N_g_cwr_count = 8                 # ✅
N_cwr_max_id = 210                # ✅ 运行时 max+1 起编
N_g_branch_selector_positions = 0 # ✅ 无同 wp_code 多 sheet
N_g_c_prerequisites = 1           # ✅ 仅 C5
N_g_accounting_methods = 3        # equity_method / cost_method / fair_value_method
```

---

## 四、非功能需求

### 4.1 性能

| 指标 | 目标 | 参照 |
|------|------|------|
| chain 生成 G 循环 15 主底稿（scenario=normal）| < 75s（G 循环 15 文件 197 sheet，全循环最大）| H spec < 60s（11 文件 187 sheet）|
| G1 单底稿打开（含 17 sheet）| < 8s | H spec H1 同基线 |
| G7 单底稿打开（含 22 sheet，最大）| < 10s | 新增 |
| G 循环 sheet 分组导航切换 | < 200ms | F/H spec |
| G-F6 VR 三角勾稽校验（4 条规则）| < 500ms | H spec VR-H1 |
| G-F7 cross_wp_ref stale 传播 | < 500ms | E1 spec |
| G-F5 ECL 计算引擎单次 | < 200ms（纯算法，无 DB IO）| 新增 |
| G-F4 公允价值测试弹窗打开 | < 300ms | H spec AssetImpairmentDialog |

### 4.2 兼容性 / 回归白名单

**必须不破坏的现有循环**：
- ✅ D 销售循环（53 task + 20 UAT pass）
- ✅ E1 货币资金循环（91 task pass）
- ✅ F 采购存货循环（44 task + 16 UAT ✓ + 1 partial + 2 stub）
- ✅ H 固定资产循环（待实施，不影响）
- ✅ I 无形资产循环（待实施，不影响）
- ✅ J/K/L/M/N 其他循环

**关键兼容性约束**：
- THE G spec SHALL NOT 修改 `_normalize_sheet_name` 函数签名或行为
- THE G spec SHALL NOT 修改 `_should_skip_historical_sheet` 现有模式（G11~G14 已被覆盖，无需扩展）
- THE G spec SHALL NOT 引入新 vue 依赖
- WHEN 修改 prerequisite-status 路由时, THE G spec SHALL 仅追加 `^G\d` 命中分支
- THE G spec SHALL NOT 修改 confirmation_service 核心接口（仅追加 wp_code='G0' 注册）

### 4.3 可观测性

- G-F1 合并去重日志记录 `chain_executions.merge_dedup_summary`（已 D/F/H spec 实现）
- G-F3 G7 核算方式切换日志记录 `chain_executions.g7_accounting_method_summary`（新增）
- G-F6 VR-G7-01/G11-01/G1-01/G14-01 校验结果写入 `validation_rule_results` 表
- G-F7 stale 传播写 `linkage_audit_log`
- G-F8 G0→G7 反向回填事件写 `event_log`
- G-F5 ECL 计算日志写 `wp_calculation_log`
- G-F4 公允价值测试 stub 调用日志写 `wp_ai_call_log`

---

## 四·B、UAT 验收清单（17 项 ⭐ 上线门槛 ≥ 14 项 ✓ pass）

> 状态枚举：`✓ pass` / `⚠ partial` / `⚠ stub` / `✗ fail` / `○ pending-uat`
>
> **上线门槛**：≥ 14 项 ✓ pass + **P0 关键项**（#1, #3, #5, #9, #10, #12, #13）必须**全部** ✓ pass

| # | 验收项 | 对应需求 | Sprint | P | Status |
|---|-------|---------|--------|---|--------|
| 1 | 15 文件合并后 sheet 数 = 152，4 个历史遗留 sheet 被过滤，无重复"底稿目录"/"GT_Custom" | G-F1 | S1 | **P0** | ○ |
| 2 | G 循环 sheet 列表按 12 类分组显示，可折叠展开 | G-F2 | S2 | P1 | ○ |
| 3 | G7 三种核算方式切换后对应 sheet 显隐正确（equity/cost/fair_value） | G-F3 | S1 | **P0** | ○ |
| 4 | G1-6 公允价值测试弹窗 Level 1/2/3 三层级可用 | G-F4 | S2 | P1 | ○ |
| 5 | G4/G6 ECL 三阶段模型计算 + 单调性校验 + write-back | G-F5 | S2 | **P0** | ○ |
| 6 | ECL Stage 1 ≤ Stage 2 ≤ Stage 3 单调性约束校验 | G-F5 | S2 | P1 | ○ |
| 7 | Level 3 DCF 公允价值计算公式正确 + write-back | G-F4 | S2 | P1 | ○ |
| 8 | G0 函证注册到 confirmation_service（wp_code='G0'）| G-F8 | S2 | P1 | ○ |
| 9 | VR-G7-01 / VR-G11-01 / VR-G1-01 / VR-G14-01 blocking 阻断对应底稿签字 | G-F6 | S2 | **P0** | ○ |
| 10 | cross_wp_references G 循环条目 ≥ 33（基线 8 + 新增 ≥ 25，起编运行时 max+1） | G-F7 | S2 | **P0** | ○ |
| 11 | G0 函证确认后 G7 自动回填（stale 0.5s 内可见） | G-F8 | S2 | P1 | ○ |
| 12 | G1 顶部前置横幅显示 C5（实测真实编号） | G-F9 | S2 | **P0** | ○ |
| 13 | G1 明细表 + 收益测算 prefill ≥ 15 cell（=AUX 4-arg 真实维度） | G-F10 | S2 | **P0** | ○ |
| 14 | G7 明细表 + 投资收益 prefill ≥ 15 cell | G-F10 | S2 | P1 | ○ |
| 15 | G11/G13/G14 汇总表 prefill ≥ 10 cell | G-F10 | S2 | P1 | ○ |
| 16 | G1-8 业务模式分析 + G1-10 SPPI 测试辅助分类 | G-F11 | S3 | P2 | ○ |
| 17 | G1 首屏审计导航图 + 路由 sheetKey=g1a | G-F12 | S3 | P2 | ○ |

---

## 五、测试矩阵

### 5.1 单测（pytest）

| 测试文件 | 覆盖 |
|---------|------|
| `test_g_merge_dedup.py` | G-F1 15 文件合并去重（197→152 sheet）+ 4 历史遗留过滤 |
| `test_g7_accounting_method.py` | G-F3 三种核算方式切换 + sheet 显隐 |
| `test_g_fair_value_dialog.py` | G-F4 公允价值测试 Level 1/2/3 + write-back |
| `test_g_ecl_model.py` | G-F5 ECL 三阶段 + 单调性 + write-back + RBAC |
| `test_g_validation_rules.py` | G-F6 VR-G7-01/G11-01/G1-01/G14-01 共 4 条规则 |
| `test_g_cross_wp_refs.py` | G-F7 ≥ 25 条新增 + ref_id 唯一 + stale 传播 |
| `test_g0_g7_confirmation_callback.py` | G-F8 G0→G7 反向回填集成测试 |
| `test_g_prefill_extension.py` | G-F10 新增 ≥ 80 cell + 4-arg AUX 校验 + 真实 sheet 名校验 |
| `test_g1_classification.py` | G-F11 CAS 22 分类逻辑 + write-back + RBAC |

### 5.2 属性测试（hypothesis）

| PBT | Property | Sprint | max_examples | Validates |
|-----|---------|--------|-------------|-----------|
| P1 | Sheet 名归一化幂等性 | S1 | 100 | G-F1 |
| P2 | 历史遗留 sheet 过滤正确性（G11~G14 4 命中 + D/F/H/I 回归）| S1 | 50 | G-F1 |
| P3 | cross_wp_references ref_id 全局唯一性 | S2 | 50 | G-F7 |
| P4 | VR-G7-01 / VR-G11-01 / VR-G1-01 / VR-G14-01 三角勾稽正确性 | S2 | 200 + 9 显式 boundary | G-F6 |
| P5 | G 循环 12 类 sheet 分组规则完备性 | S2 | 200 | G-F2 |
| P6 | ECL 三阶段模型单调性（Stage 1 ≤ Stage 2 ≤ Stage 3）| S2 | 100 | G-F5 |

### 5.3 集成测试

| 测试文件 | 覆盖 |
|---------|------|
| `test_g_cycle_full_chain.py` | G 循环 15 主底稿 chain 生成 + sheet 数验证 |
| `test_g0_g7_confirmation_callback.py` | G-F8 G0 函证确认 → G7 stale 传播端到端 |
| `test_g11_income_aggregation.py` | G-F6 VR-G11-01 投资收益汇总跨 G1+G4+G6+G7+G8 联动 |

### 5.4 UAT（手动验收，详见 §四·B）

17 项验收项 + 7 项 P0 关键项门槛（#1/#3/#5/#9/#10/#12/#13）。

---

## 五·B、成功判据汇总

| 类别 | 验收项 | 量化指标 |
|------|-------|---------|
| **合并去重（P0）** | G-F1 15 文件合并 | 197 → 152 sheet（4 历史遗留过滤 + 跨文件去重）|
| **核算方式（P0）** | G-F3 G7 三种方式 | equity/cost/fair_value 切换后 sheet 显隐正确 |
| **导航体验（P1）** | G-F2 sheet 分组 | 12 类规则全覆盖 152 sheet |
| **公允价值（P1）** | G-F4 公允价值弹窗 | Level 1/2/3 三层级 + DCF stub + write-back |
| **ECL 模型（P1）** | G-F5 ECL 三阶段 | 3 阶段计算 + 单调性约束 + write-back |
| **勾稽联动（P0）** | G-F6 三角勾稽 | 4 条 VR blocking 阻断签字 |
| | G-F7 cross_wp_ref | ≥ 25 条新增（目标 N_g_cwr ≥ 33）|
| | G-F8 函证回填 | G0→G7 stale 0.5s 内传播 |
| **前置驱动（P1）** | G-F9 前置横幅 | C5 状态可视 |
| **数据覆盖（P0）** | G-F10 prefill | 74 → ≥ 154 cell（新增 ≥ 80）|
| **智能辅助（P2）** | G-F11 分类辅助 | CAS 22 业务模式 + SPPI 判断 |
| | G-F12 审计导航图 | sheetKey=g1a 路由 + 16+ 项程序状态 |

---

## 六、术语表

| 术语 | 定义 |
|------|------|
| **G 循环** | 投资循环（G0 函证 / G1 交易性金融资产 / G2 应收利息 / G3 应收股利 / G4 债权投资 / G5 长期应收款 / G6 其他债权投资 / G7 长期股权投资 / G8 其他权益工具投资 / G9 其他非流动金融资产 / G10 交易性金融负债 / G11 投资收益 / G12 净敞口套期收益 / G13 公允价值变动收益 / G14 信用减值损失 共 15 主底稿，15 物理文件 197 sheet）|
| **G1A** | 交易性金融资产实质性程序表（G1 总控台，约 16+ 项程序）|
| **G1-6** | 公允价值测试表（Level 1/2/3 层级）|
| **G1-7** | 第三层次公允价值计量的调节表 |
| **G1-8** | 业务模式分析（CAS 22 / IFRS 9 金融工具分类第一步）|
| **G1-10** | 合同现金流量特征分析（SPPI 测试，分类第二步）|
| **G4** | 债权投资（以摊余成本计量，需 ECL 三阶段模型）|
| **G6** | 其他债权投资（FVOCI，需 ECL + 公允价值双重测试）|
| **G7** | 长期股权投资（三种核算方式：权益法/成本法/公允价值法）|
| **ECL（预期信用损失）** | Expected Credit Loss，IFRS 9 / CAS 22 要求的前瞻性减值模型 |
| **ECL 三阶段** | Stage 1: 12 个月 ECL / Stage 2: 整个存续期（未信用减值）/ Stage 3: 整个存续期（已信用减值）|
| **PD** | Probability of Default，违约概率 |
| **LGD** | Loss Given Default，违约损失率 |
| **EAD** | Exposure at Default，违约风险暴露 |
| **SPPI 测试** | Solely Payments of Principal and Interest，合同现金流量仅为本金和利息的支付 |
| **业务模式** | CAS 22 三种：持有以收取合同现金流量 / 既收取又出售 / 其他（交易性）|
| **FVTPL** | Fair Value Through Profit or Loss，以公允价值计量且其变动计入当期损益 |
| **FVOCI** | Fair Value Through Other Comprehensive Income，以公允价值计量且其变动计入其他综合收益 |
| **公允价值层级** | Level 1: 活跃市场报价 / Level 2: 可观察输入 / Level 3: 不可观察输入（DCF）|
| **权益法** | 对联营/合营企业，按持股比例确认投资收益，调整长期股权投资账面价值 |
| **成本法** | 对子公司，仅被投资方宣告分红时确认投资收益 |
| **C5** | 投资循环控制测试（致同 2025 真实编号）|
| **三角勾稽（G 循环版）** | G7 权益法收益 = 净利润×持股比例 / G11 = 各子循环汇总 / G1 公允价值变动 = 期末−期初 / G14 = ECL 变动 |
| **confirmation_service** | 函证服务，支持 D0/F0/H0/G0 等 wp_code 注册 |

---

## 七、本 spec 的明确不做（边界）

- ❌ H 循环（固定资产 + 在建工程 + 使用权资产）— 独立 spec
- ❌ I 循环（无形资产 + 商誉 + 开发支出）— 独立 spec
- ❌ 衍生金融工具套期会计专项（G1-14 仅基础核查表）
- ❌ 金融工具估值外部数据库 / Bloomberg / Wind 接口
- ❌ 移动端 APP
- ❌ 7 循环函证统一管理中心（O1）
- ❌ B/C/D-N 三层联动机制（O8）
- ❌ 真实 LLM 接入（G-F4 Level 3 DCF / G-F11 分类辅助停留在 stub）

---

## 八、启动条件检查清单（实施前必满足）

- [x] Sprint 0 现状核验通过（N_g_files=15 / raw=197 / dedup=152 / historical=4 / prefill_entries=16 / prefill_cells=74 / cwr_count=8 / max_id=210）
- [x] D spec git commit 锁定
- [x] F spec 44/44 completed + UAT 达标
- [x] E1 spec 91/91 completed
- [ ] requirements.md review 完成
- [ ] design.md review 完成
- [ ] tasks.md review 完成
- [ ] Sprint 0.X 前置实测（G1-2 明细表表头 + tb_aux_balance G 类真实 aux_type/aux_code）

**启动条件 4/8 已满足 — 待 review + Sprint 0.X 前置实测后启动 Sprint 1**

---

> **本 requirements.md 配套**：design.md v1.0 + tasks.md v1.0
