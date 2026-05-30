# H 固定资产循环底稿优化 — Requirements

> **Spec**: `workpaper-h-fixed-assets-cycle`
> **版本**: v1.2
> **依赖前置 spec**：`workpaper-d-sales-cycle` ✅ + `workpaper-f-purchase-inventory` ✅ + `workpaper-e1-cash-optimization` ✅
> **基线日期**: 2026-05-19（Sprint 0 实测落地）

## 变更记录

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-05-19 | 三件套需求初版 — Sprint 0 实测基线 + 5 项关键业务发现 + 14 项功能需求 |
| v1.1 | 2026-05-19 | Review 修复 P0/P1 共 7 项：①H-F9 前置改实测真实编号 C6+C7+C14（B23/B51 类无 H 对应底稿）②H-F1 多版本保留改伪需求澄清 + 新增 H-F1b wp_code 路由分支保护 ③H-F11 折旧引擎 P2→P1 ④H-F14 IPO 占位实现具体化 ⑤UAT #19 标 ⚠ partial（procedure_status seed 限制）⑥H-F10 加 Sprint 0.X 前置实测要求（aux_type/aux_code）⑦PBT-P2 max_examples 100→50 |
| v1.2 | 2026-05-19 | 对照 F spec 成熟版补 P0-P2 共 10 项结构性短板：①依赖矩阵 ②非功能需求章 ③EARS 范式改写 14 项 AC ④成功判据汇总 ⑤测试矩阵 ⑥术语表 ⑦Sprint 0 偏差段 ⑧UAT 优先级列 ⑨业务痛点细化 ⑩兼容性回归白名单 |

---

## 〇、依赖矩阵

| 上游 spec | 状态 | 本 spec 依赖 | Fallback |
|-----------|------|------------|---------|
| `workpaper-d-sales-cycle` | ✅ 53/53 + UAT 20 | D 循环核心产出复用：`_normalize_sheet_name` / `_merge_sheets_dedup` / `_should_skip_historical_sheet`（4 模式齐备）/ `SCENARIO_TO_FILE_FILTER` / `useDSalesCycleSheetGroups` 模式 / `ConsistencyGatePanel` / `usePrerequisiteStatus`（D 路由 + F 路由已加）/ `WorkpaperAuditNav` 组件 + `resolveProcedureSheetKey` 路由 / PBT P1~P7 模式 / 4-arg AUX 强制约定 / 真实 sheet 名 openpyxl 实测铁律 | D spec 必须先 commit，本 spec 方可启动 |
| `workpaper-f-purchase-inventory` | ✅ 44/44 + UAT 16✓+1 partial+2 stub | F 循环成熟产出复用：`_ensure_ipo_loaded(prefix)` 通用化（D4/F2 双前缀已验证）/ `InventoryStocktakeDialog` 模式（H 循环改名 `FixedAssetStocktakeDialog`）/ `wp_ai_stocktake` LLM stub 模式 / `consistency_gate.check_*_triangle_reconciliation` 模式 / `apply_to_sheet` 写回联动模式 / `require_project_access("edit")` RBAC / cross_wp_references 起编 max(ref_id)+1 模式 | F spec 必须先 commit |
| `workpaper-e1-cash-optimization` | ✅ 91/91 | E1 9 个核心组件复用 + scenario 字段 + LLM API + attachment_service + Univer Sheet 路由 | - |
| `global-linkage-bus` | ✅ 已完成 | LinkageGraphBuilder / stale_engine / 反向索引 / `cross-ref:updated` 事件 | - |
| `template-library-coordination` | 63/64 | seed_load_history 表 / reseed 流程 / wp_template_metadata | - |
| `enterprise-linkage` | ✅ 已完成 | useEditingLock / cross-module event bus / RBAC require_project_access | - |

---

## 一、为什么做（业务/技术根因）

### 1.1 业务痛点（合伙人 / 项目经理 / 审计助理实际遇到的 8 类核心问题）

1. **大额单笔资产 100% 函证 + 实物盘点缺位**：H 类资产单笔可能数千万至数亿（如生产线/厂房/油气资产），与 D 应收/F 存货抽样模式不同，必须全额函证 + 实地盘点；当前无强制"100% 函证 + 实物盘点确认"校验，质控复核多次回退
2. **累计折旧月度递增连续性无校验**：H1-12 折旧测算表月度累计折旧应严格单调递增（除处置月份外），当前无 PBT/VR 规则；助理手填错位时无报警
3. **跨年度联动重灾区（PREV 公式频繁错位）**：H1 累计折旧 / H1-12 折旧测算与上年期末数严格连续，PREV 公式错位导致期初对不上是 H 类底稿最常见错报源（参考 D spec PREV 修复经验复用）
4. **折旧计算 4 种方法逻辑复杂**：直线法 / 双倍余额递减 / 年数总和法 / 工作量法，每种方法 = f(原值, 残值率, 使用年限, 累计已计提期数)；当前无统一公式引擎，靠手工填或 Univer 内置公式分散维护，单元格错位/公式被覆盖问题频发
5. **资产分类多类折旧政策不同**：房屋建筑物（20-30 年）/ 通用设备（5-10 年）/ 专用设备（10-15 年）/ 运输工具（4-6 年）/ 电子设备（3-5 年），每类残值率/使用年限不同，缺乏 LLM 辅助按资产名称建议分类的能力
6. **减值测试（H1-14）资产组逻辑独立 — 不同于 F2 跌价 NRV**：可收回金额 vs 账面价值，未来现金流折现模型与 F2 跌价 NRV 模型不同（F2 是孰低法，H1-14 是 DCF 资产组），需独立 ECL stub
7. **租赁两表（H8/H9）强联动但当前无回填**：H9 租赁负债初始计量驱动 H8 入账，与 F0↔F2 反向回填同模式但 H 循环未实现 cross_wp_references 路径
8. **B/C 前置底稿无联动**：C6（固定资产控制测试）/ C7（在建工程控制测试）/ C14（租赁循环控制测试）与 H1A 程序执行无前置状态驱动；项目经理无法看到前置完成度决定是否可启动 H 实质性程序
9. **F2 / D5 跨循环联动缺失**：H1-12 月度折旧应分摊到 D5 营业成本 + K 期间费用 + F2 库存商品，当前 cross_wp_references 仅 9 条，对比 F 循环修复后 43 条差距悬殊
10. **同 wp_code 多 sheet 路由冲突**：H1-12 折旧测算 3 版（不含/含/多次减值）/ H3 双计量模式 / H8-8 折旧 2 版等共 9 个位置存在同 wp_code 多 sheet，前端按 wp_code 跳转时撞多个匹配项

### 1.2 技术根因（代码锚定核验后）

1. **prefill_formula_mapping H 类极度欠覆盖（12 entries / 56 cells）**：仅审定表层有 prefill；明细表 / 折旧测算 / 减值测试 / 监盘 / 资产处置 / 评估增值 全部空白 — 与 F 修复前 45 cells 同款问题
2. **cross_wp_references H 相关仅 9 条**（CW-01/02/03 折旧分摊 + CW-13/14 H8/H9 租赁 + CW-45/46 H1 附注+报表 + CW-96 H1 控制依赖 + CW-99 K8→H1 反向），目标新增 ≥ 30 条
3. **`_ensure_ipo_loaded(prefix)` 已在 F spec 通用化** — H 循环可零改动复用；但 H 模板**未提供 IPO 应对类专属文件**（187 sheet 全 0 历史遗留），降级为占位
4. **`_should_skip_historical_sheet` 已支持 4 种历史遗留模式** — H 循环模板干净（实测 0 命中），不需扩展
5. **SCENARIO_TO_FILE_FILTER 不能复用于双计量模式**：H3/H7 成本/公允价值不是 IPO/normal 维度，需新增 `MEASUREMENT_MODEL_FILTER` 字典
6. **PREV 公式语法已就绪但 H1-12 折旧表未配置**：累计折旧上年期末连续性校验需 prefill =PREV() 公式 + 加 VR-H1 单调性规则
7. **B/C 前置底稿配置错位**：仓库现 B23 类无 H 对应业务控制底稿（仅 B23-15 信息处理 + B23-XX-5 通用模板），B51 类仅 -3 货币 / -5 收入 — 实测真实前置应为 **C6 + C7 + C14**

### 1.3 本 spec 边界

- ✅ **本 spec 做**：H0~H10 共 11 主底稿优化（H-F1 / H-F1b / H-F2 至 H-F14 共 15 项修复）
- ❌ **本 spec 不做（独立 spec）**：
  - I 循环（无形资产 + 商誉 + 长期待摊 + 累计摊销 + 研发支出）
  - J 循环（职工薪酬 + 股份支付）
  - 资产评估机构外部数据库 / 第三方接口对接
  - 移动端 APP（盘点 / 拍照 / GPS）
  - 7 循环函证统一管理中心（O1）
  - B/C/D-N 三层联动机制（O8）
  - H 循环 IPO 评估增值应对类专属底稿（致同模板未提供，TD-H6）

---

## 一·B、Sprint 0 实测基线（附录 A）

| 变量 | 实测值 | 来源 |
|------|-------|------|
| `N_h_files` | 11 | `wp_templates/H/` 目录扫描（H0~H10）|
| `N_h_raw_sheets` | 187 | openpyxl 全文件 sheet 累加 |
| `N_h_historical_sheets` | **0** | 现行 `_should_skip_historical_sheet` 对全部 187 sheet 跑过的命中数 |
| `N_h_dedup_sheets` | 159 | 现行 `_normalize_sheet_name` 去重后（**含问题**，见 §二.B2）|
| `N_h_prefill_entries` | 12 | `prefill_formula_mapping.json` 中 wp_code 以 H 开头的 entry |
| `N_h_prefill_cells` | 56 | 同上，全部 cells 累加 |
| `N_h_cwr_count` | 9 | `cross_wp_references.json` 中 source_wp 或 targets[*].wp_code 以 H 开头 |
| `N_cwr_max_id_numeric` | 210 | 全仓 ref_id 数值最大值（CW-210 已被 F spec 占用，本 spec 起编 **CW-211**）|

**当前 H prefill 12 entries 全部仅覆盖审定表（H0-1 至 H10-1）+ H1 分析程序**：

```
H0  审定表H0-1            cells=2
H1  审定表H1-1            cells=7
H1  分析程序H1-3          cells=2
H2  审定表H2-1            cells=5
H3  审定表（成本模式）H3-1  cells=5
H4  审定表H4-1            cells=5
H5  审定表H5-1            cells=5
H6  审定表H6-1            cells=5
H7  审定表（成本模式）H7-1  cells=5
H8  审定表H8-1            cells=5
H9  审定表H9-1            cells=5
H10 审定表H10-1           cells=5
```

**当前 9 条 H 相关 cross_wp_references**（grep 实测，参考补充而非全量修复目标）。

---

## 二、5 项关键业务发现（驱动 spec 走向）

### A. H 循环模板"干净"——不需要新增历史遗留过滤模式
- 187 sheet 全部命中现行 4 类历史模式（修订前 / G+数字+删除/移至 / 示例括号 / 示例末尾）→ 0
- **影响**：不需要扩展 `_should_skip_historical_sheet`，省去 D-F1+F-F2 的"扩 regex"工作量

### B. 同 wp_code 多 sheet — 前端路由要求分支保护（不是合并去重问题）
模板中 4 个 H 子循环存在**同一 wp_code 多版本**情况：

| wp_code | 版本数 | 区分维度 | 真实 sheet 名（实测带括号修饰词区分）|
|---------|-------|---------|--------------|
| `H1-12` | 3 | 减值次数 | `折旧测算表（不含减值）-直线法H1-12` / `折旧测算表（含减值）H1-12` / `折旧测算表（多次减值）H1-12` |
| `H3-1` | 2 | 计量模式 | `审定表（成本模式）H3-1` / `审定表（公允价值模式）H3-1` |
| `H3-2` | 2 | 计量模式 | `明细表（成本模式）H3-2` / `明细表（公允价值模式）H3-2` |
| `H3-5` | 2 | 计量模式 | `增减检查表（成本模式）H3-5` / `增减检查表（公允价值模式）H3-5` |
| `H3-7` | 2 | 减值 | `折旧测算表（成本模式不含减值）H3-7` / `折旧测算表（成本模式含减值）H3-7` |
| `H5-12` | 2 | 减值 | `折耗测算表（不含减值）H5-12` / `折耗测算表（含减值）H5-12` |
| `H7-1/2/6/7` | 2 | 计量模式 | 成本模式 / 公允价值模式 各 1 |
| `H7-11` | 2 | 减值 | `折旧测算表（不含减值）-直线法H7-11` / `折旧测算表（含减值）H7-11` |
| `H8-6` | 2 | 计算频率 | `使用权资产 租赁负责初始及后续计量（按年）H8-6` / `（按月）H8-6` |
| `H8-8` | 2 | 减值 | `折旧测算表（不含减值）H8-8` / `折旧测算表（含减值）H8-8` |

**Sprint 0 实测核验（重要校正）**：
- Excel 同 workbook 内不允许同名 sheet → 模板里这些"多版本"sheet 的实际 sheet 名**已带括号修饰词区分**
- 现行 `_normalize_sheet_name` 对带括号的 sheet 名（不含 GT_Custom/底稿目录）会保留括号内容，归一化后仍是不同 key → **不会误去重**
- 实测同文件内多版本被误去重数 = **0**（运行 `python script` 统计 187 raw / 28 重复均为跨文件"底稿目录/GT_Custom/附注披露通用样式"等合法去重）

**真实问题**：
- 前端按 wp_code 路由（如 cross_wp_references 落点 H1-12）会撞 3 个匹配 sheet → 归 H-F1b（路由分支保护）+ H-F3（分支选择器）解决
- 不需要扩展归一化策略，复用 D/F spec 现行 `_merge_sheets_dedup` 即可

### C. 双计量模式（成本 / 公允价值）不是 IPO scenario
- H3 投资性房地产 + H7 生产性生物资产支持企业自选「成本模式」或「公允价值模式」
- **影响**：不能复用 SCENARIO_TO_FILE_FILTER（IPO/normal）模式，需新增 **measurement_model** 维度（cost / fair_value）控制 sheet 显隐

### D. H8 ↔ H9 租赁两表强联动（类似 F0↔F2 反向回填）
- H9 租赁负债 = 未来租金现值（折现率 + 租赁期 = 关键 input）
- H8 使用权资产 = H9 初始计量 + 初始直接费用 - 激励
- **影响**：需 cross_wp_references 配置 H9→H8 反向回填路径，参照 F-F8 F0→F2 模式

### E. prefill 严重欠覆盖（仅 12 entries / 56 cells）
- 当前仅审定表层有 prefill；明细表 / 折旧测算 / 减值测试 / 监盘 / 资产处置 / 评估增值 全部空白
- F spec 经修复后 F-cycle 12 entries / 109 cells；本 spec 目标 **≥ 18 entries / ≥ 110 cells**（基线 12+56 → 目标 30+166，新增 ≥ 110）
- **关键**：prefill cell 必须用 openpyxl 实测真名（D/F spec 教训：3-arg AUX → None / 臆造 sheet 名 → 空数据）

---

## 三、功能需求（H-F1 至 H-F14）

> 命名规则：`H-F<n>` 与 D spec/F spec 保持一致；每项需求标注「依赖前置 spec」「P 优先级」「主受益 wp_code」。

### H-F1 多文件合并 + GT_Custom/底稿目录跨文件去重
- **优先级**：P0
- **依赖**：复用 `_merge_sheets_dedup`（D/F spec 已实现，0 改动）
- **User Story**：As a 审计助理，I want H 循环 11 个物理文件合并后自动去除跨文件重复 sheet，so that 合并后 sheet 列表干净无冗余。
- **Acceptance Criteria（EARS）**：
  1. WHEN H 循环 11 文件合并加载时, THE chain_orchestrator SHALL 调用 `_merge_sheets_dedup` 对底稿目录/GT_Custom/附注披露(上市公司)/附注披露(国企)/调整分录汇总通用样式 sheet 按归一化名称去重保留首次出现
  2. WHEN 合并完成后, THE chain_orchestrator SHALL 将原始 187 sheet 去重至 = `N_h_dedup_sheets`（实测 159）
  3. THE chain_orchestrator SHALL 复用 D spec 已实现的 `_normalize_sheet_name` 函数（0 代码改动）
  4. **关键澄清（Sprint 0 实测）**：Excel 同 workbook 内不允许同名 sheet → 模板里"H1-12 折旧 3 版"等已用括号修饰词区分，含括号修饰词的 normalized key 不同，**不会被误去重**；实测同文件内多版本误去重数 = **0**；全部 28 个去重均为跨文件合法去重
  5. WHEN 合并过程中遇到任意"伪同名"sheet（含括号修饰词区分）, THE chain_orchestrator SHALL 全部保留为不同 sheet
- **量化指标**：合并后 sheet 数 = 159；无重复"底稿目录"/"GT_Custom"/"附注披露信息（上市公司）"

### H-F1b 同 wp_code 多 sheet 时前端路由不冲突
- **优先级**：P0（H-F3 分支选择器的前置依赖）
- **依赖**：UniverSheetNav + sheet 路由匹配逻辑
- **User Story**：As a 审计助理，I want 跨底稿引用跳转到 wp_code='H1-12'（多 sheet 共享）时不报错且默认显示主版本，so that 我能正常进入折旧测算继续填写。
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 识别 9 个"同 wp_code 多 sheet"位置：H1-12（3 版）/ H3-1（2 模式）/ H3-2（2 模式）/ H3-5（2 模式）/ H3-7（2 减值）/ H5-12（2 减值）/ H7-1+H7-2+H7-6+H7-7（5 sheet 共 4 wp_code 双模式）/ H7-11（2 减值）/ H8-6（2 频率）/ H8-8（2 减值）
  2. WHEN 用户按 wp_code 跳转（如 cross_wp_references 落点指向 H1-12）, THE 系统 SHALL 默认路由到该 wp_code 的"主版本"
  3. THE 主版本识别规则 SHALL 按以下优先级：sheet 名末尾 wp_code 编号唯一 → 直接选；多个匹配 → 选名称含"（不含减值）"或"-直线法"或"（成本模式）"或"（按月）"的版本
  4. WHEN 跳转 wp_code='H1-12' 时, THE 系统 SHALL 默认显示"折旧测算表（不含减值）-直线法H1-12"且 H-F3 分支选择器自动加载其余 2 个版本入口
  5. THE 路由不冲突逻辑 SHALL 同款适用于 H3-1/H3-7/H5-12/H7-11/H8-8 共 5 个剩余 wp_code 位置
- **量化指标**：跳转 9 个目标 wp_code 全部不报错；vitest 路由测试 9/9 通过

### H-F2 计量模式（cost / fair_value）显隐控制
- **优先级**：P0
- **依赖**：新增 `MEASUREMENT_MODEL_FILTER` 字典（类比 SCENARIO_TO_FILE_FILTER）
- **User Story**：As a 项目经理，I want 项目按企业自选的计量模式（成本 / 公允价值）控制 H3/H7 sheet 显隐，so that 审计助理只看到本项目适用的版本。
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 新增 `MEASUREMENT_MODEL_FILTER` 字典，含 `cost` / `fair_value` 两档枚举（独立于 `SCENARIO_TO_FILE_FILTER`）
  2. WHILE 项目配置 H3 / H7 计量模式 = "cost"（成本模式）, THE 系统 SHALL 在 sheet 列表隐藏所有名称含"（公允价值模式）"的 sheet
  3. WHILE 项目配置切换为"fair_value"（公允价值模式）, THE 系统 SHALL 隐藏所有名称含"（成本模式）"的 sheet
  4. IF 项目未配置计量模式, THEN THE 系统 SHALL 默认显示成本模式（监管允许的默认值）
  5. THE measurement_model 字段 SHALL 持久化在 project 表（已有 scenario 字段同表新增列）
  6. WHEN 用户切换计量模式时, THE 前端 SHALL 立即重新计算 sheet 列表（不需要重新加载底稿）
- **量化指标**：H3 模式切换后 H3-1/H3-2/H3-5/H3-7 共 8 张 sheet 中 4 张可见 / 4 张隐藏；H7 同款

### H-F3 折旧/减值分支选择器
- **优先级**：P1
- **依赖**：UniverSheetNav 视觉适配
- **需求**：
  - WHEN 用户打开 H1-12 折旧测算 sheet，THE SYSTEM SHALL 在 sheet 顶部显示分支选择器（不含减值 / 含减值 / 多次减值）
  - WHEN 用户选择某分支，THE SYSTEM SHALL 路由到对应 sheet 名后缀的真实 sheet
  - WHEN 切换分支，THE SYSTEM SHALL 保留前一分支已填数据（不清空）
  - 同款应用于 H3-7 / H5-12 / H7-11 / H8-8 共 5 个折旧/折耗测算位置

### H-F4 H 循环 sheet 分组（14 类规则）
- **优先级**：P1
- **依赖**：复用 `useDSalesCycleSheetGroups` 模式新建 `useHFixedAssetSheetGroups.ts`
- **需求**：
  - 索引 / 历史遗留 / 总控台 / 审定表 / 明细表 / 折旧测算 / 减值测试 / 增减检查 / 实物盘点 / 权属/产权检查 / 关联交易 / 租赁专项 / 评估增值（IPO）/ 附注披露 / 调整分录 共 14 类（部分类小类合并到大类）
  - 索引 + 历史遗留 + 附注披露 类 defaultHidden=true / readonly=true（参照 F spec 规则）
  - 验收门槛：14 类规则对任意真实 H sheet 名匹配恰好 1 类（PBT-P5 验证）

### H-F5 实物盘点弹窗（D 类弹窗复用）
- **优先级**：P1
- **依赖**：复用 `InventoryStocktakeDialog.vue` 改名 `FixedAssetStocktakeDialog.vue`
- **需求**：
  - WHEN 用户打开 H1-9/H1-10/H1-11 监盘 sheet（或 H2/H3/H5/H7 同类），THE SYSTEM SHALL 提供"开始盘点"按钮触发 D 类弹窗
  - 弹窗字段：盘点地点（含 GPS）+ 日期 + 盘点人/复核人双签 + 资产编号清单 + 盘点状态（在用/闲置/报废/盘亏）+ 照片/视频附件 + 结论
  - WHEN 盘点结果含"盘亏"项，THE SYSTEM SHALL 强制要求填写盘亏原因 + 责任认定
  - WHEN 盘点完成且双签已齐，THE SYSTEM SHALL 调用 `wp_ai_stocktake` 端点生成差异分析摘要（复用 F-F5 实现，传 wp_code='H1' 参数化）
  - 验收门槛：FixedAssetStocktakeDialog.spec.ts 至少 8 项测试通过

### H-F6 三角勾稽 VR 规则（≥ 4 条）
- **优先级**：P0
- **依赖**：复用 `consistency_gate.check_*_triangle` 模式（F 已实现 check_f5_f2_triangle_reconciliation）
- **User Story**：As a 合伙人，I want 固定资产期末/累计折旧/使用权资产-租赁负债勾稽自动校验，so that H 类底稿成本配比关系异常能及时发现。
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 新增 4 条 validation_rules：
     - **VR-H1-01**（blocking, tolerance=1.0）：H1 期末 = H1 期初 + H1 增加（H1-7） − H1 减少（H1-8）+ H10 处置
     - **VR-H1-02**（blocking, tolerance=1.0）：H1 累计折旧期末 = H1 累计折旧期初 + 本期计提（H1-12 折旧汇总）− 本期处置（H10 处置时同步冲减）
     - **VR-H8-01**（blocking, tolerance=1.0）：H8 使用权资产期末 = H9 租赁负债期末 + 初始直接费用 − 激励
     - **VR-H1-03**（warning, tolerance=0.05）：H1 平均折旧率波动 < 5%（与上年）
  2. WHEN VR-H1-01 / VR-H1-02 / VR-H8-01 blocking 规则校验失败时, THE ConsistencyGatePanel SHALL 阻断 H1 / H8 底稿签字
  3. WHEN VR-H1-03 warning 规则触发时, THE ConsistencyGatePanel SHALL 显示告警但不阻断签字
  4. THE VR 规则 SHALL 写入 `backend/data/h_cycle_validation_rules.json`（参照 F spec `f_cycle_validation_rules.json` 模式）
  5. THE consistency_gate 服务 SHALL 新增 `check_h_cycle_triangle_reconciliation()` 方法注入主 `run_all_checks` 流程
- **量化指标**：4 条 VR 各至少 1 个 pass / 1 个 fail / 1 个 skip 测试；阻断签字 e2e 测试通过

### H-F7 cross_wp_references ≥ 30 条新增
- **优先级**：P0
- **依赖**：复用 F-F7 ref_id 起编模式（基于运行时 max(ref_id)+1）
- **需求**：
  - 起编 **CW-211** 起（基于实测 max=210）
  - 按 6 分组：H 内部联动（≥ 8）/ H→报表（≥ 5）/ H→附注（≥ 6）/ H→D5 营业成本（折旧分摊，≥ 4）/ H→A 财务报表（≥ 4）/ H→T1 IPE（≥ 3）
  - 强制场景：H1-12 月度折旧 → D5 营业成本 + 期间费用（折旧分摊）
  - 验收门槛：N_h_cwr_count 从 9 → ≥ 39（即新增 ≥ 30）

### H-F8 H9 → H8 反向回填（类似 F0→F2）
- **优先级**：P1
- **依赖**：复用 F-F8 反向回填模式
- **User Story**：As a 审计助理，I want H9 租赁负债保存后自动回填 H8 使用权资产初始计量，so that 我不需要手工抄录折现金额。
- **Acceptance Criteria（EARS）**：
  1. THE cross_wp_references SHALL 新增 H9→H8 反向回填条目（category=data_flow_reverse, severity=warning）
  2. WHEN H9 租赁负债保存（折现率 / 租赁期 / 月租金确定）, THE event_handler SHALL emit `EventType.LEASE_LIABILITY_UPDATED` 事件（或复用 `WORKPAPER_SAVED` 加 wp_code 过滤）
  3. WHEN 事件触发时, THE stale_engine SHALL 沿 cross_wp_references 路径传播到 H8 使用权资产初始计量单元格
  4. WHEN H9 租赁变更（H8-7 租赁变更检查表保存）, THE stale_engine SHALL 触发 stale 传播到 H8 后续计量
  5. THE 前端 H8 编辑器 SHALL 订阅 `cross-ref:updated` 事件自动刷新公式
- **量化指标**：集成测试 `test_h9_h8_lease_callback.py` 全过；H9 保存后 H8 单元格 0.5s 内可见 stale 标记

### H-F9 B/C 类前置状态横幅
- **优先级**：P1
- **依赖**：复用 `usePrerequisiteStatus.ts` 加 H_CYCLE_PREREQUISITES
- **需求**：
  - 前置底稿（**Sprint 0 实测核验过，致同 2025 真实编号**）：
    - **C6 固定资产循环控制测试**（H1/H2/H3/H4/H5/H6/H7/H10 共用）
    - **C7 在建工程循环控制测试**（H2 专用）
    - **C14 租赁循环控制测试**（H8/H9 专用）
  - **NOTE**：实测 `backend/wp_templates/B/` 仅有 B23-15 / B23-XX-5（无 H 循环业务层面控制专项底稿），B51 类仅 -3 货币资金 / -5 收入（无 H 循环资产舞弊专项底稿）→ B23-X / B51-X 不在 H 前置清单（与 D spec 用 B23-1/B51-5 / F spec 用 B23-3/B51-4 的模式不一致，但实测如此）
  - 横幅状态：全完成 → ready；部分完成 → partial；未启动 → blocked（参照 F-F9 模式）
  - 路由：`^H\d` 命中 → 加载 H_CYCLE_PREREQUISITES = [C6, C7, C14]（其中 C7/C14 仅 H2/H8/H9 路径强制）
  - 验收门槛：H1 顶部前置横幅可见，wp_code 路由按 `^H\d` 命中 C6 + C7 + C14 三条

### H-F10 prefill 扩展 ≥ 110 cells
- **优先级**：P0
- **依赖**：openpyxl 实测真实 sheet 名（**ADR-H 铁律：禁止臆造**，复用 F-F10 修复轮经验）
- **需求**：
  - 全部 cell 必须用 4-arg `=AUX(code, aux_type, aux_code, column)`（D/F spec 修复轮校验过的语法）
  - 全部 sheet 名必须经 openpyxl 实测核对（实测真实 sheet 名清单见 Sprint 0 报告）
  - **Sprint 0.X 前置实测要求（实施前必做，避免重蹈 F-F10 占位 AUX 名教训）**：
    - 跑 openpyxl 读 H1-2 明细表真实表头，确认资产分类维度（房屋/通用/专用/运输/电子 共 5 类是否成立 — 致同模板可能更细分如"房屋建筑物→生产用/办公用/职工福利用"3 子类）
    - 跑 SQL `SELECT DISTINCT aux_type, aux_code FROM tb_aux_balance WHERE account_code LIKE '160%' LIMIT 50`（覆盖 1601 固定资产 / 1602 累计折旧 / 1603 减值准备）确认真实 aux_type / aux_code 维度
    - 实测结果写入 design.md ADR-H4
  - 目标分布（实施时按实测 aux_type/aux_code 调整）：
    - H1 明细表H1-2：≥ 15 cell（按资产分类 N 类 × 期初/期末/本期增/本期减，N 由实测决定）
    - H1 折旧测算 3 版（不含/含/多次减值）：≥ 30 cell（=LEDGER_DETAIL 抽样按月）
    - H1-13 折旧分配分析：≥ 8 cell（=AUX 按部门，aux_type 待实测）
    - H1-14 减值测算：≥ 12 cell（=AUX 按资产组 + 可收回金额）
    - H2 在建工程明细 + 转固时点（H2-2/H2-5）：≥ 12 cell
    - H3 投资性房地产明细（含双模式）：≥ 12 cell
    - H8 使用权资产 + 折旧测算：≥ 10 cell
    - H9 租赁负债明细 + 未确认融资费用：≥ 8 cell
    - H10 资产处置损益明细：≥ 8 cell
    - 合计：**≥ 115 cells**（target 安全边际）
  - 验收门槛：`test_h_prefill_extension.py` 12 项测试通过（含 4-arg AUX 校验 + 真实 sheet 名校验 + 真实 aux_type 校验）

### H-F11 折旧自动测算引擎（4 种方法）
- **优先级**：**P1**（核心增量，独立于 LLM 可测试）
- **依赖**：扩展 prefill_engine 或新建 `wp_h_depreciation` 路由
- **User Story**：As a 审计助理，I want 输入"原值/残值率/使用年限/起始月份/已计提月数"后系统自动计算折旧，so that 我不需要手工填月度折旧表。
- **Acceptance Criteria（EARS）**：
  1. THE 系统 SHALL 提供 endpoint `POST /api/projects/{pid}/workpapers/{wid}/h1/depreciation-calc` 接受 `method: 'straight_line' | 'double_declining' | 'sum_of_years' | 'units_of_production'` 4 种方法
  2. WHEN 用户在 H1-12 折旧测算表填入完整 5 字段（原值 + 残值率 + 使用年限 + 起始月份 + 已计提月数）并选定方法时, THE 系统 SHALL 返回月度折旧 + 累计折旧序列
  3. THE endpoint SHALL 使用 `Depends(require_project_access("edit"))` RBAC 校验（参照 F-F11 修复轮经验）
  4. WHEN 请求 body 含 `apply_to_sheet: str` 字段时, THE 系统 SHALL 把计算结果写回 `working_paper.parsed_data.depreciation_calcs[sheet]`（参照 F-F11 apply_to_sheet 模式）
  5. THE 4 种方法计算公式 SHALL 在 design.md ADR-H6 详细定义
  6. **业务正确性约束**：直线法每月折旧应严格相等；双倍余额递减法应在剩余折旧年限 ≤ 2 年时切换为直线法；累计折旧不应超过原值 − 残值
- **量化指标**：每种方法至少 3 个边界 case 单元测试通过 + 写回联动测试 + RBAC 测试

### H-F12 减值 DCF 模型 LLM 辅助（资产组维度）
- **优先级**：P2
- **依赖**：新建 `wp_h_impairment` 路由 + `AssetImpairmentDialog.vue`
- **需求**：
  - WHEN 用户打开 H1-14 减值测算 sheet，THE SYSTEM SHALL 提供"AI 辅助分析"按钮
  - 输入：资产组 ID / 账面价值 / 5 年现金流预测 / 折现率 / 终值
  - 输出：可收回金额 = max(公允价值-处置费用, 未来现金流现值)，与账面价值比较
  - 当前为 stub 实现（计算公式正确但 LLM 真实接入待 wp_ai_service 升级，与 F-F12 同状态）
  - 支持采纳并写回（apply_to_sheet 模式）
  - 验收门槛：单测验证 DCF 公式 + write-back 联动

### H-F13 H1A 审计导航图（28+ 项程序）
- **优先级**：P2
- **依赖**：复用 WorkpaperAuditNav 组件 + 加 `H1→h1a` 路由
- **需求**：
  - 在 `WorkpaperAuditNav.vue` 的 `resolveProcedureSheetKey` 加 `H1→h1a` / `H2→h2a` / `H3→h3a` / `H8→h8a` / `H9→h9a` 路由
  - WHEN 用户首次打开 H1 底稿，THE SYSTEM SHALL 显示导航图（默认展开）
  - 验收门槛：vitest 验证 sheetKey 路由正确

### H-F14 评估增值核查机制（IPO 专项 — 占位实现）
- **优先级**：P2
- **依赖**：复用 `_ensure_ipo_loaded(prefix='H1')`
- **User Story**：As a 项目经理，I want H 循环 IPO 评估增值核查触发器框架就位，so that 后续致同模板补齐后可零改动接入。
- **Acceptance Criteria（EARS）**：
  1. **触发器降级说明**：实测 `backend/wp_templates/B/` 无 B51-X 资产舞弊专项底稿（仅 B51-3 货币 / B51-5 收入）→ 没有现成事件源驱动 IPO 应对加载
  2. THE 系统 SHALL 在 `_IPO_CONFIG` 注册表添加 `'H1'` 入口，`codes` 列表暂为空 `[]`，保留通用 `_ensure_ipo_loaded(prefix='H1')` 的 dispatch 入口
  3. WHEN 调用 `_ensure_ipo_loaded(prefix='H1')` 时, THE 函数 SHALL 不抛异常，返回 `{prefix: 'H1', added_codes: [], skipped_existing: [], errors: []}`
  4. THE event_handler SHALL 暂不订阅任何事件（占位状态）
  5. THE D spec / F spec 已注册的 IPO trigger（_on_b515_high_risk / _on_b514_high_risk）SHALL 不受影响（回归保留）
  6. **TD-H6**（新增技术债）：用户后续提供 H 循环 IPO 应对类专属模板（如 H1-XX 评估增值核查表）后再立 spec 接入触发器和 sheet 加载
- **量化指标**：单测验证 `_IPO_CONFIG['H1']` 注册 + empty result + D/F 既有 IPO 触发器 18+16 测试全过

---

## 三·B、Sprint 0 关键偏差发现（修正后续 design.md ADR）

实测 vs 起草前假设对比（**spec 起草偏差归零原则**：所有偏差必须明确标注 + 修正方案）：

| # | 起草前假设 | Sprint 0 实测 | 偏差影响 | 修正方案 |
|---|----------|--------------|---------|---------|
| 1 | H 循环也有"修订前/G删除/示例"等历史遗留 sheet（参照 D/F 经验）| **0 命中** | 节省 H-F2"扩展 regex"工时（约 0.1 天） | 删除 H-F2 历史遗留扩展任务，保留过滤规则纯回归测试 |
| 2 | H1-12/H3-1 等同 wp_code 多版本 sheet 会被 `_normalize_sheet_name` 误去重为 1 个（README v1.0 假设 187→159 = 28 个被吃掉，其中相当部分是合法多版本）| 同文件内多版本误去重数 = **0**；28 个去重全部是跨文件合法去重（"底稿目录"/"GT_Custom"/"附注披露通用样式"等）| H-F1 从"扩展归一化策略保留版本"伪需求改为 "复用 D/F 现行 `_merge_sheets_dedup` 0 改动 + H-F1b 前端路由保护" | H-F1 大幅简化；新增 H-F1b 处理 wp_code 路由冲突（9 个位置）|
| 3 | H 循环也有 IPO 应对类专属底稿（参照 D4-22~D4-32 + F2-61~F2-72 模式） | 11 个 H 模板文件**未发现 H1-XX IPO 应对类专属文件** | H-F14 从"加载 H1-XX IPO sheet"完整需求降级为占位实现（`_IPO_CONFIG['H1']` codes=[]）| 加 TD-H6 长期债：客户提供 H IPO 应对模板后再立 spec |
| 4 | H 循环前置底稿应有 B23-X 业务控制 + B51-X 资产舞弊（参照 D 用 B23-1/B51-5、F 用 B23-3/B51-4 模式） | B23 类**仅 B23-15 信息处理 + B23-XX-5 通用模板**（无 H 业务专项）；B51 类**仅 -3 货币 + -5 收入**（无 H 资产舞弊专项）；C 类有 **C6 固定资产 + C7 在建工程 + C14 租赁** | H-F9 前置清单从"B23-?+C-?+B51-?"改为实测真实"C6+C7+C14" | 加 TD-H5 长期债：B51 类资产舞弊底稿致同未提供 |
| 5 | H 循环 prefill 现有覆盖度类似 F（修复后 12 entries / 109 cells）| 仅 12 entries / **56 cells**（仅审定表层有 prefill；明细表/折旧测算/减值/监盘/资产处置全空） | 工时投入比预估更大；F-F10 修复轮经验（4-arg AUX + 真实 sheet 名 + apply_to_sheet 写回）必须前置应用 | H-F10 加 Sprint 0.X 前置实测要求 |
| 6 | H 循环模板已有"实物盘点专属 sheet"可直接复用 InventoryStocktakeDialog | H1-9/H1-10/H1-11 / H2-12/H2-13/H2-14 / H3-9 / H5-9/H5-10/H5-11 / H7-8/H7-9/H7-10 共 **13 处监盘类 sheet**（多于 F2 的 6 处）| H-F5 监盘弹窗触发点比 F 多 1 倍；需 sheet 路由匹配规则覆盖 7 个不同 wp_code | H-F5 加"按 wp_code 模式匹配触发"逻辑 + sheet 名识别正则 |

**关键修正后的实施基线**（Sprint 0 关键偏差归零后）：
```python
# 真实基线（替代 v1.0 起草假设）
N_h_files = 11                    # ✅ 与假设一致
N_h_raw_sheets = 187              # ✅ 与假设一致
N_h_historical_sheets = 0         # ❌ 偏差：假设 ≥ 5，实测 0
N_h_dedup_sheets = 159            # ✅ 与假设一致（基于跨文件合法去重）
N_h_misdedup = 0                  # ❌ 偏差：假设 ≥ 11，实测 0（同 wp_code 多 sheet 是真问题但走 H-F1b 路由保护，非合并去重问题）
N_h_prefill_entries = 12          # ✅
N_h_prefill_cells = 56            # ✅（远低于 F 修复后 109）
N_h_cwr_count = 9                 # ✅（含 9 条实测：CW-01/02/03/13/14/45/46/96/99）
N_cwr_max_id_numeric = 210        # ✅ 起编 CW-211
N_h_stocktake_sheets = 13         # ❌ 偏差：起草未实测，建议 H-F5 触发点扩展
N_h_ipo_sheets = 0                # ❌ 偏差：假设 ≥ 5，实测 0 → H-F14 降级
N_h_b51_dedicated = 0             # ❌ 偏差：假设有 B51-X 资产舞弊，实测 B51 仅 -3/-5
N_h_b23_dedicated = 0             # ❌ 偏差：假设有 B23-X 业务控制，实测 B23 仅 -15/-XX-5
N_h_c_prerequisites = 3           # ✅ 实测 C6 + C7 + C14
```

---

## 四、非功能需求

### 4.1 性能

| 指标 | 目标 | 参照 |
|------|------|------|
| chain 生成 H 循环 11 主底稿（普通项目 scenario=normal）| < 60s（H 循环 11 文件 187 sheet 比 F 的 15 文件 151 sheet 略大）| F spec < 45s 基线 |
| H1 单底稿打开（含 26 sheet + 多版本路由）| < 8s | F spec F2 同基线 |
| H 循环 sheet 分组导航切换 | < 200ms | F spec |
| H-F6 VR 三角勾稽校验（4 条规则）| < 500ms | F spec VR-F5 |
| H-F7 cross_wp_ref stale 传播 | < 500ms | E1 spec |
| FixedAssetStocktakeDialog 弹窗打开 | < 300ms | F spec InventoryStocktakeDialog |
| H-F11 折旧引擎单次计算（任一方法）| < 100ms（纯算法，无 DB IO）| 新增 |
| H-F11 折旧 36 期序列写回 parsed_data | < 1s | F-F11 valuation-sample |

### 4.2 兼容性 / 回归白名单

**必须不破坏的现有循环**（每项需对应回归测试）：
- ✅ D 销售循环（53 task + 20 UAT pass）— 不影响 `_normalize_sheet_name` / `_should_skip_historical_sheet` / `_ensure_d4_ipo_loaded` 已有行为
- ✅ E1 货币资金循环（91 task pass）— 不影响 useUniverSheetNav / scenarioFilter / WorkpaperAuditNav
- ✅ F 采购存货循环（44 task + 16 UAT ✓ + 1 partial + 2 stub）— 不影响 `_ensure_ipo_loaded(prefix='F2')` / F-F8 反向回填 / F-F11 valuation-sample / F-F12 impairment-analysis
- ✅ G/I/J/K/L/M/N 其他循环 — 不影响 chain_orchestrator 主流程，scenarioFilter 不引入 H 专属硬编码

**关键兼容性约束**：
- THE H spec SHALL NOT 修改 `_normalize_sheet_name` 函数签名或行为（D/F spec 已实施 + 锁定）
- THE H spec SHALL NOT 修改 `_should_skip_historical_sheet` 现有 4 模式（H 实测 0 命中，无需扩展）
- THE H spec SHALL NOT 修改 `_ensure_ipo_loaded(prefix)` 通用接口（仅追加 `_IPO_CONFIG['H1']` 注册）
- THE H spec SHALL NOT 引入新 vue 依赖（复用 E1 + D + F 已有组件）
- WHEN 修改 prerequisite-status 路由时, THE H spec SHALL 仅追加 `^H\d` 命中分支（不影响 D/E/F 现有路由）

### 4.3 可观测性

- H-F1 合并去重日志记录 `chain_executions.merge_dedup_summary`（去重前/后 sheet 数）（已 D/F spec 实现）
- H-F2 measurement_model 切换日志记录 `chain_executions.measurement_model_filter_summary`（新增）
- H-F6 VR-H1-01/02/03 + VR-H8-01 校验结果写入 `validation_rule_results` 表（复用 D/F 已有架构）
- H-F7 stale 传播写 `linkage_audit_log`（global-linkage-bus 已有）
- H-F8 H9→H8 反向回填事件写 `event_log`（含 H9 wp_code 触发源 + H8 stale 标记落点）
- H-F11 折旧引擎计算日志写 `wp_calculation_log`（method + 输入参数 + 月度序列摘要）
- H-F12 减值 DCF stub 调用日志写 `wp_ai_call_log`（与 F-F12 同表）
- H-F5 实物盘点弹窗操作写 `workpaper_audit_log`（附件上传/双签/LLM 摘要，复用 F-F5 模式）



> 状态枚举遵循 F spec 修复轮规约：`✓ pass`（用户层完整可用）/ `⚠ partial`（部分实现）/ `⚠ stub`（占位实现）/ `○ pending-uat`

| # | 验收项 | 对应需求 | Sprint | P | Status |
|---|-------|---------|--------|---|--------|
| 1 | 11 文件合并后 sheet 数 = `N_h_dedup_sheets`（实测 159），无重复"底稿目录"/"GT_Custom"/"附注披露（上市/国企）" | H-F1 | S1 | **P0** | ○ |
| 2 | wp_code='H1-12' 跳转默认显示"折旧测算表（不含减值）-直线法H1-12"主版本，不报错；同款验证 H3-1/H3-7/H5-12/H7-11/H8-8 | H-F1b | S1 | **P0** | ○ |
| 3 | H 循环模板无历史遗留 sheet（实测 0 命中）+ D/F 历史遗留过滤回归无影响 | H-F1 | S1 | **P0** | ○ |
| 4 | H 循环 sheet 列表按 14 类分组 + 折叠展开 | H-F4 | S2 | P1 | ○ |
| 5 | H3/H7 计量模式切换后对应 sheet 显隐正确（cost / fair_value） | H-F2 | S2 | **P0** | ○ |
| 6 | H1-12 / H3-7 / H5-12 / H7-11 / H8-8 折旧分支选择器可用 | H-F3 | S2 | P1 | ○ |
| 7 | 实物盘点弹窗双签 + 照片/视频附件 + 盘亏原因强制 | H-F5 | S2 | P1 | ○ |
| 8 | 盘点弹窗 LLM 差异分析（H1 参数化复用 wp_ai_stocktake） | H-F5 | S2 | P1 | ○ |
| 9 | VR-H1-01 / VR-H1-02 / VR-H8-01 blocking 阻断 H1 / H8 签字 | H-F6 | S2 | **P0** | ○ |
| 10 | VR-H1-03 折旧率波动 warning + cross_to_D5 | H-F6 | S2 | P1 | ○ |
| 11 | cross_wp_references H 循环条目 ≥ 39（基线 9 + 新增 ≥ 30，起编 CW-211） | H-F7 | S2 | **P0** | ○ |
| 12 | H9 租赁负债保存后 H8 使用权资产自动回填（stale 0.5s 内可见） | H-F8 | S2 | P1 | ○ |
| 13 | H1 顶部前置横幅显示 C6 + C7 + C14（实测真实编号） | H-F9 | S2 | P1 | ○ |
| 14 | H1-2 明细表 prefill ≥ 15 cell（=AUX 4-arg 真实 aux_type 维度） | H-F10 | S2 | **P0** | ○ |
| 15 | H1-12 折旧测算 prefill ≥ 30 cell（=LEDGER_DETAIL 真实 sheet 名） | H-F10 | S2 | **P0** | ○ |
| 16 | H1-14 减值测算 prefill ≥ 12 cell（=AUX 资产组维度） | H-F10 | S2 | P1 | ○ |
| 17 | H1-12 4 种折旧方法计算 + write-back（apply_to_sheet）+ RBAC | H-F11 | S3 | P1 | ○ |
| 18 | H1-14 AI DCF 减值分析弹窗 + 采纳写回 | H-F12 | S3 | P2 | ○ |
| 19 | H1 首屏审计导航图 + 路由 sheetKey=h1a | H-F13 | S3 | P2 | ○（**预期 ⚠ partial**：组件 ✓ + 路由 ✓，但 procedure_status[h1a] 数据需项目首次填写后才不全 pending；与 F-F18 同款限制） |

**上线门槛**：
- ≥ 16 项 ✓ pass + **P0 关键项**（#1, #2, #3, #5, #9, #11, #14, #15）必须**全部** ✓ pass
- 实测 P0 共 8 项（vs F spec 3 项），权重高于 F 因 H 循环新增了"双计量模式 H-F2 + 路由分支保护 H-F1b + 三角勾稽 VR-H8 跨表"三个关键架构改动，必须严格通过

---

## 五、测试矩阵

### 5.1 单测（pytest）

| 测试文件 | 覆盖 |
|---------|------|
| `test_h_merge_dedup.py` | H-F1 11 文件合并去重（187→159 sheet）+ 跨文件"底稿目录/GT_Custom/附注披露（上市/国企）"去重验证 |
| `test_h_route_branch_protection.py` | H-F1b 9 个 wp_code 多 sheet 路由主版本识别（H1-12 默认显示"不含减值-直线法"等）|
| `test_h_measurement_model_filter.py` | H-F2 cost / fair_value 双模式 sheet 显隐切换（H3 8 sheet / H7 14 sheet）|
| `test_h_sheet_groups.py` | H-F4 14 类分组规则全覆盖 |
| `test_h_validation_rules.py` | H-F6 VR-H1-01/02/03 + VR-H8-01 共 4 条规则（pass/fail/skip 全覆盖）|
| `test_h_cross_wp_refs.py` | H-F7 ≥ 30 条新增 + ref_id 起编 CW-211 + stale 传播 |
| `test_h9_h8_lease_callback.py` | H-F8 H9→H8 反向回填集成测试（events emit + cross_wp_ref 路径验证）|
| `test_h_prefill_extension.py` | H-F10 新增 ≥ 110 cell + 4-arg AUX 校验 + 真实 sheet 名校验 + 真实 aux_type 校验 |
| `test_h1_depreciation_engine.py` | H-F11 4 种方法 × 至少 3 个边界 case + 写回联动 + RBAC |
| `test_h_ipo_trigger.py` | H-F14 `_IPO_CONFIG['H1']` 注册 + empty result + D/F 既有 IPO 触发器回归 |

### 5.2 属性测试（hypothesis）

| PBT | Property | Sprint | max_examples | Validates |
|-----|---------|--------|-------------|-----------|
| P1 | Sheet 名归一化幂等性（保留版本修饰词）| S1 | 100 | H-F1.3 |
| P2 | 历史遗留 sheet 过滤正确性（H 模板 0 命中，仅回归 D/F 模式）| S1 | 50 | H-F1.4 |
| P3 | cross_wp_references ref_id 全局唯一性 | S2 | 50 | H-F7.2 |
| P4 | VR-H1-01 / VR-H1-02 三角勾稽公式正确性（恒等点 + 边界内 + 边界外 + 对称性）| S2 | 200 + 9 显式 boundary 用例 | H-F6 |
| P5 | H 循环 14 类 sheet 分组规则完备性（任意 H sheet 名恰好匹配 1 类）| S2 | 200 | H-F4 |
| P6 | 计量模式 + scenario 文件级裁剪一致性（H-F2 cost/fair_value × normal/ipo 4 组合幂等）| S3 | 50 | H-F2, H-F3 |
| P7 | `_ensure_ipo_loaded('H1')` 通用性（empty codes 不抛异常）| S3 | 50 | H-F14 |

### 5.3 集成测试

| 测试文件 | 覆盖 |
|---------|------|
| `test_h_cycle_full_chain.py` | H 循环 11 主底稿 chain 生成 + scenario=normal × measurement_model=cost 应有的 sheet 数验证 |
| `test_h9_h8_lease_callback.py` | H-F8 H9 租赁负债保存 → H8 使用权资产 stale 传播端到端 |
| `test_h1_h10_disposal_triangle.py` | H-F6 三角勾稽 VR-H1-01/02 跨 H1+H10 联动 |
| `test_h1_stocktake_dialog.py` | H-F5 实物盘点弹窗（FixedAssetStocktakeDialog）+ 附件上传 + 双签 + LLM 摘要 |
| `test_h1_h12_depreciation_apply.py` | H-F11 折旧引擎写回 → H1-12 sheet parsed_data 验证 |

### 5.4 UAT（手动验收，详见 §四）

19 项验收项 + 8 项 P0 关键项门槛（#1/#2/#3/#5/#9/#11/#14/#15）。

---

## 五·B、成功判据汇总

| 类别 | 验收项 | 量化指标 |
|------|-------|---------|
| **合并去重（P0）** | H-F1 11 文件合并 | 187 → 159 sheet（实测，0 跨文件重复"底稿目录/GT_Custom"）|
| | H-F1b 路由分支保护 | 9 个 wp_code 多 sheet 跳转 0 报错 |
| | H-F2 计量模式切换 | H3+H7 共 22 sheet 按 cost/fair_value 显隐分组正确 |
| **导航体验（P1）** | H-F3 折旧分支选择器 | 5 个位置（H1-12/H3-7/H5-12/H7-11/H8-8）选择器可用 |
| | H-F4 sheet 分组 | 14 类规则全覆盖 H 循环 11 主底稿 |
| **现场执行（P1）** | H-F5 监盘弹窗 | 13 处监盘类 sheet 触发点 + D 类弹窗 + 双签 + LLM |
| **勾稽联动（P0/P1）** | H-F6 三角勾稽 | 4 条 VR + VR-H1-01/02/H8-01 blocking 阻断签字 |
| | H-F7 cross_wp_ref | ≥ 30 条新增（起编 CW-211，目标 N_h_cwr ≥ 39）|
| | H-F8 租赁回填 | H9→H8 stale 0.5s 内传播 |
| **前置驱动（P1）** | H-F9 前置横幅 | C6 + C7 + C14 状态可视（实测真实编号）|
| **数据覆盖（P0）** | H-F10 prefill | 56 → ≥ 166 cell（新增 ≥ 110，含 4-arg AUX 真实维度）|
| **智能辅助（P1/P2）** | H-F11 折旧引擎 | 4 种方法 × 3 边界 case + 写回 + RBAC |
| | H-F12 减值 DCF | LLM stub + 写回联动（与 F-F12 同 stub 状态）|
| **导航/触发（P2）** | H-F13 审计导航图 | sheetKey=h1a 路由 + 32+ 项程序状态展示 |
| | H-F14 IPO 占位 | `_IPO_CONFIG['H1']` 注册 + 占位 codes=[] + D/F IPO 回归 |

---

## 六、术语表

| 术语 | 定义 |
|------|------|
| **H 循环** | 固定资产循环（H0 函证 / H1 固定资产 / H2 在建工程 / H3 投资性房地产 / H4 工程物资 / H5 油气资产 / H6 固定资产清理 / H7 生产性生物资产 / H8 使用权资产 / H9 租赁负债 / H10 资产处置损益 共 11 主底稿，11 物理文件 187 sheet）|
| **H1A** | 固定资产实质性程序表（H1 总控台，约 28+ 项程序）|
| **H1-12** | 折旧测算表，含 3 版（不含减值/含减值/多次减值）|
| **H1-14** | 减值测算表，DCF 资产组维度评估 |
| **H8 使用权资产** | 新租赁准则下租入资产的资产化处理（CAS 21 修订版）|
| **H9 租赁负债** | 与 H8 配对的负债，未来租金现值 |
| **H10 资产处置损益** | 固定资产处置利得/损失，与 H1 期末余额勾稽 |
| **三角勾稽（H 循环版）** | H1 期末 = 期初 + 增加 − 减少 + H10 处置；H1 累计折旧期末 = 期初 + 本期计提 − 处置；H8 = H9 + 初始直接费用 − 激励 |
| **DCF 模型** | 现金流折现模型（discounted cash flow），用于 H1-14 减值测试中"未来现金流现值"计算，与 F2-47 跌价孰低法不同 |
| **资产组（CGU）** | 减值测试单元（Cash-Generating Unit），单项资产无独立现金流时的最小可识别资产组合 |
| **可收回金额** | max(公允价值−处置费用, 未来现金流现值)；与账面价值比较定减值 |
| **直线法** | 折旧方法 A：(原值 − 残值) / 使用年限，每月折旧严格相等 |
| **双倍余额递减法** | 折旧方法 B：年初账面净值 × (2 / 使用年限)，剩余 ≤ 2 年时切换为直线 |
| **年数总和法** | 折旧方法 C：(原值 − 残值) × (剩余使用年限 / 年数总和)，加速折旧 |
| **工作量法** | 折旧方法 D：(原值 − 残值) / 总工作量 × 当期工作量，需输入 unit_count |
| **计量模式（measurement_model）** | H3 投资性房地产 + H7 生产性生物资产可选「成本模式」或「公允价值模式」，独立于 scenario |
| **MEASUREMENT_MODEL_FILTER** | H spec 新增字典，控制 H3/H7 双模式 sheet 显隐（cost / fair_value）|
| **租赁两表强联动** | H8 使用权资产 ↔ H9 租赁负债 反向回填关系（CAS 21 入账时 H8 = H9 + 初始直接费用 − 激励）|
| **wp_code 多 sheet 路由** | 同 wp_code 对应多版本 sheet 时（如 H1-12 三版折旧）的前端 sheet 选择规则 |
| **主版本识别规则** | 同 wp_code 多 sheet 时默认显示规则：含"（不含减值）/-直线法/（成本模式）/（按月）"为主版本 |
| **`_ensure_ipo_loaded(prefix)`** | 通用 IPO 应对文件加载函数（D/F spec 已通用化），H spec 复用但 codes 列表为空 |
| **`_IPO_CONFIG`** | IPO 应对配置注册表（已含 D4/F2 入口，H spec 追加 'H1' 占位）|
| **C6 / C7 / C14** | H 循环真实前置控制测试底稿（实测核验）：C6 固定资产 / C7 在建工程 / C14 租赁循环 |
| **TD-H1 ~ TD-H6** | 已知技术债编号（详见 §七）|

---

## 七、已知缺口与技术债（TD）

| ID | 缺口 | 优先级 | 后续 spec |
|----|------|-------|---------|
| TD-H1 | I 循环（无形资产 + 商誉 + 长期待摊）独立 spec | P1 | `workpaper-i-intangible-assets-cycle` |
| TD-H2 | H 循环 IPO 评估增值应对类底稿（致同模板未提供）| P2 | 待客户提供后立 spec |
| TD-H3 | H1 折旧引擎 LLM 辅助按资产名称建议分类 / 残值率 | P2 | 接入 wp_ai_service 后立 spec |
| TD-H4 | 移动端实物盘点 APP（H + F2 合并） | P2 | 移动端方案明确后 |
| TD-H5 | B51 类资产舞弊风险评估专项底稿（实测仓库 B51 仅 -3 货币 / -5 收入两条业务专项，无 H 循环对应；致同 2025 模板亦未提供 — 客户实际有需求时立 spec） | P2 | 与 O8 三层联动机制合并 |
| TD-H6 | H 循环 IPO 应对类专属模板（致同 2025 未提供，仅 H 主底稿 11 个；用户后续提供 H1-XX 评估增值核查表等后立 spec） | P2 | 客户提供模板后 |

---

## 八、本 spec 的明确不做（边界）

- ❌ I 循环（无形资产 + 商誉 + 长期待摊 + 累计摊销 + 研发支出）— 独立 spec
- ❌ J 循环（职工薪酬 + 股份支付）
- ❌ 资产评估机构外部数据库 / 第三方接口对接
- ❌ 移动端 APP（盘点 / 拍照 / GPS）
- ❌ 7 循环函证统一管理中心（O1）
- ❌ 真实 LLM 接入（H-F12 减值分析停留在 stub，与 F-F12 同状态，待 O-LLM-Integration spec）

---

## 九、启动条件检查清单（实施前必满足）

- [x] Sprint 0 基线已实测（N_h_files=11 / raw=187 / dedup=159 / prefill_entries=12 / prefill_cells=56 / cwr_count=9 / max_id=CW-210）
- [x] 前置 spec 已上线：D ✅（53/53 + UAT 20）/ F ✅（44/44 + UAT 16+1+2）/ E1 ✅（91/91）
- [x] requirements.md review 完成（2026-05-19 P0/P1 修复 7 项已落地）
- [ ] design.md 起草完成 + ADR-H1~H6 review 通过
- [ ] tasks.md 起草完成 + Sprint 划分 review 通过
- [ ] Sprint 0.X 前置实测（H1-2 明细表表头 + tb_aux_balance H 类真实 aux_type/aux_code）

---

> **本 requirements.md 配套**：design.md（待 review 后启动）+ tasks.md（待 design 确认后启动）
> **下一步**：用户 review requirements.md → 反馈 → 启动 design.md
