# F 采购存货循环底稿优化 — Requirements

> **Spec**: workpaper-f-purchase-inventory
> **档级**: 档 3 完整三件套
> **版本**: v1.0（2026-05-19 初版，基于 README v1.1 A+ 评级 + D 循环 spec 实施经验）
> **状态**: 待 Sprint 0 实测核验
> **参照**: workpaper-d-sales-cycle（D 循环 spec，~60% 代码复用）

## 变更记录

| 版本 | 日期 | 摘要 | 触发原因 |
|------|------|------|---------|
| v1.0 | 2026-05-19 | 三件套起草初版 | README v1.1 A+ 评级达成，启动 spec 实施 |

## 依赖矩阵

| 上游 spec | 状态 | 本 spec 依赖 | Fallback |
|-----------|------|------------|---------|
| `workpaper-d-sales-cycle` | ✅ UAT 20/21 pass | D 循环核心产出复用：`_normalize_sheet_name` / `_merge_sheets_dedup` / `_should_skip_historical_sheet` / `SCENARIO_TO_FILE_FILTER` / `useDSalesCycleSheetGroups` 模式 / `CustomerInterviewDialog` 模式 / `ConsistencyGatePanel` / `usePrerequisiteStatus` / VR-D4-03 毛利率规则 / PBT P1~P5 模式 | D spec 必须先 commit，F spec 方可启动 |
| `workpaper-e1-cash-optimization` | ✅ 91/91 completed | E1 9 个核心组件复用 + scenario 字段 + LLM API + attachment_service | - |
| `global-linkage-bus` | ✅ 已完成 | LinkageGraphBuilder / stale_engine / 反向索引 / `cross-ref:updated` 事件 | - |
| `template-library-coordination` | 63/64 completed | seed_load_history 表 / reseed 流程 / wp_template_metadata | - |
| `enterprise-linkage` | ✅ 已完成 | useEditingLock / cross-module event bus | - |

---

## 一、为什么做（业务/技术根因）

### 1.1 业务痛点（基于 README v1.1 §一 7 类核心问题）

合伙人/审计助理打开 F 采购存货循环底稿时遇到 7 类核心问题：

1. **F2 存货 90 sheet 平铺无分组**：F2 是全系统最复杂底稿（11 文件 90 sheet，超过 D4 的 8 文件 48 sheet），合并后 sheet 全部平铺，审计助理完全迷失
2. **prefill 仅覆盖审定表（45 cell）**：F2 明细表/盘点类/计价测试/跌价准备 + F3/F4 明细表全部 0 cell prefill，大量手工填写
3. **cross_wp_references 严重不足（仅 8 条）**：F 循环涉及 8 条引用，对比 D 循环 40 条新增，缺口 ≥ 35 条
4. **F2 存货监盘纯表格无弹窗**：监盘是审计中唯一需要现场执行的程序，需要 D 类弹窗（照片/录像附件 + 双人签字），当前纯 Univer 表格
5. **F5↔D4↔F2 三角勾稽缺失**：营业成本 = 期初存货 + 本期采购 - 期末存货，当前 F2 与 F5 之间完全无勾稽规则
6. **F2 IPO 应对 15 sheet 普通项目全量加载**：scenario=normal 已被 D spec SCENARIO_TO_FILE_FILTER 自动覆盖，但 B51-4 高风险触发自动追加逻辑缺失
7. **B/C 前置底稿无联动**：B23-3/C4/B51-4 与 F2A 程序执行无前置状态驱动

### 1.2 技术根因

1. **F2 11 文件合并去重逻辑未配置**：D spec 已实现 `_merge_sheets_dedup`，但 F2 未注册；合并后含 ≥ 23 个重复/历史遗留 sheet
2. **`_should_skip_historical_sheet` 不覆盖 F 循环新模式**：F 循环含 4 种新历史遗留模式（`G1A-修订前` / `G2-*-删除` / `G2-*-移至` / `示例`），当前 regex 只匹配"修订前/(原)"
3. **prefill_engine 取数粒度不足**：F2 两级链路（TB/AUX → F2-2 明细汇总表 → F2-1 审定表 487 cross_sheet 公式），prefill 目标是中间 sheet F2-2 而非审定表本身
4. **cross_wp_references 现 175 条但 F 相关仅 8 条**：README §1.4 实测 8 条，目标 ≥ 35 条新增
5. **VR 规则缺失**：F5↔D4↔F2 三角勾稽无 validation_rules，D spec VR-D4-03 毛利率已实施但 F 侧未闭环
6. **`_ensure_d4_ipo_loaded` 非通用**：当前硬编码 D4 前缀，需扩展为通用 `_ensure_ipo_loaded(wp_code_prefix)`

### 1.3 本 spec 边界

- ✅ **本 spec 做**：F0~F5 共 6 主底稿优化（F-F1 至 F-F14 共 14 项修复）
- ❌ **本 spec 不做（独立 spec）**：
  - O1: 7 循环函证统一管理中心（D0+E0+F0+G0+H0+K0+L0）
  - O8: B/C/D-N 三层联动机制（统一规划 14 循环前置依赖）
  - F2 ERP 对接（外部系统导入存货台账）
  - F2 实物盘点 APP（移动端扫码盘点）

---

## 二、范围边界（做/不做明确清单）

### 2.1 必做（F-F1 至 F-F14 共 14 项，12.5 天工时）

| 编号 | 优先级 | 修复项 | 工时 | README 锚点 |
|------|-------|-------|------|------------|
| **F-F1** | P0 | F2 11 文件合并去重 | 0.3 天 | §四 F-F1 |
| **F-F2** | P0 | F2 历史遗留 sheet 过滤（扩展 `_should_skip_historical_sheet`）| 0.1 天 | §四 F-F2 |
| **F-F3** | P0 | scenario=normal 排除 F2-61~F2-72 IPO 应对（已自动覆盖，验证） | 0 天 | §四 F-F3 |
| **F-F4** | P1 | F2 sheet 分组 16 类规则（useFPurchaseInventorySheetGroups） | 1.5 天 | §四 F-F4 |
| **F-F5** | P1 | F2 存货监盘 D 类弹窗（InventoryStocktakeDialog.vue） | 1.5 天 | §四 F-F5 |
| **F-F6** | P1 | F5↔D4↔F2 三角勾稽 4 条 VR | 1 天 | §四 F-F6 |
| **F-F7** | P1 | cross_wp_references ≥ 35 条新增 | 1 天 | §四 F-F7 |
| **F-F8** | P1 | F0 函证 → F2 反向回填 | 0.5 天 | §四 F-F8 |
| **F-F9** | P1 | B/C 前置状态横幅（B23-3/C4/B51-4） | 0.5 天 | §四 F-F9 |
| **F-F10** | P1 | prefill 扩展 ≥ 60 cell | 2 天 | §四 F-F10 |
| **F-F11** | P2 | F2 计价测试自动抽样（=LEDGER_DETAIL） | 1 天 | §四 F-F11 |
| **F-F12** | P2 | F2 跌价准备 ECL 模型辅助（LLM 建议） | 1 天 | §四 F-F12 |
| **F-F13** | P2 | F2 审计导航图首屏 | 0.5 天 | §四 F-F13 |
| **F-F14** | P2 | B51-4 高风险 → F2-61A 自动加载 | 0.5 天 | §四 F-F14 |
| **小计** | | | **12.5 天** | |

> P0 quickfix（F-F1+F-F2+F-F3 共 0.4 天）建议 Sprint 1 首日完成

### 2.2 排除（独立 spec）

| 编号 | 描述 | 触发条件 |
|------|------|---------|
| O1 | 7 循环函证统一管理中心 | 多客户反馈"看不到全项目函证完成率" |
| O8 | B/C/D-N 三层联动机制 | E1+D+F 各自实现完后统一规划 |
| — | F2 ERP 对接（外部系统导入存货台账） | 真实项目触发 |
| — | F2 实物盘点 APP（移动端扫码盘点） | 移动端需求明确后 |

---

## 三、功能需求（F-F1 至 F-F14 详细）

### F-F1: F2 11 文件合并去重（P0）

**User Story:** As a 审计助理, I want F2 存货 11 个物理文件合并后自动去除重复 sheet, so that 合并后 sheet 列表干净无冗余。

#### Acceptance Criteria

1. WHEN F2 存货 11 文件合并加载时, THE chain_orchestrator SHALL 调用 `_merge_sheets_dedup` 对底稿目录/GT_Custom/修订说明类 sheet 按归一化名称去重保留首次出现
2. WHEN 合并完成后, THE chain_orchestrator SHALL 将 F2 原始 90 sheet 去重至 ≤ 67 sheet（实际值由 Sprint 0 实测确认）
3. THE chain_orchestrator SHALL 复用 D spec 已实现的 `_normalize_sheet_name` 函数对中英文圆括号归一化
4. IF 去重过程中遇到同名但内容不同的 sheet, THEN THE chain_orchestrator SHALL 保留首次出现并记录 warning 日志

### F-F2: F2 历史遗留 sheet 过滤（P0）

**User Story:** As a 审计助理, I want 历史遗留的无效 sheet 自动隐藏, so that 我只看到当前有效的业务 sheet。

#### Acceptance Criteria

1. THE `_should_skip_historical_sheet` 函数 SHALL 扩展匹配以下 4 种 F 循环新模式：`G1A-修订前` / 含"删除"且以 G 开头 / 含"移至"且以 G 开头 / 含"示例"或"（示例）"
2. WHEN sheet 名匹配历史遗留模式时, THE chain_orchestrator SHALL 将该 sheet 标记为 hidden 不加载到编辑器
3. THE 扩展后的过滤规则 SHALL 不影响 D/E 循环已有的过滤行为（回归安全）
4. WHEN F2 计价测试文件加载时, THE chain_orchestrator SHALL 过滤 `存货计价测试程序G2-8-删除` / `产品年度成本比较G2-8-4-移至分析类` / `产品月度成本比较G2-8-5（删除）` / `产品同行业成本比较G2-8-7-移至舞弊应对` 共 4 个历史遗留 sheet

### F-F3: scenario=normal 排除 F2 IPO 应对验证（P0）

**User Story:** As a 项目经理, I want 普通项目不加载 F2 IPO 应对 15 sheet, so that 审计助理不被无关内容干扰。

#### Acceptance Criteria

1. WHILE scenario=normal, THE SCENARIO_TO_FILE_FILTER SHALL 排除文件名含"IPO/上市/新三板/重组/舞弊应对"关键字的 F2-61至F2-72 文件（D spec 已实现，本项仅验证）
2. WHEN B51-4 高风险评估触发后, THE event_handler SHALL 自动追加 F2-61~F2-72 文件加载（F-F14 实现）
3. THE 验证测试 SHALL 确认陕西华氏 scenario=normal 时 F2 加载文件数 = 10（排除 F2-61至F2-72 的 1 个物理文件）

### F-F4: F2 sheet 分组 16 类规则（P1）

**User Story:** As a 审计助理, I want F2 合并后的 67 sheet 按业务类型分组导航, so that 我能快速定位目标 sheet。

#### Acceptance Criteria

1. THE useFPurchaseInventorySheetGroups composable SHALL 定义 16 类分组规则：索引 / 历史遗留 / 总控台 / 审定表 / 明细表 / 跌价准备 / 分析 / 存货监盘 / 截止测试 / 检查表 / 计价测试 / 关联方 / 合同履约 / 供应商访谈 / 附注披露 / 调整分录
2. WHEN 审计助理打开 F2 底稿时, THE UniverSheetNav 组件 SHALL 按分组规则展示 sheet 列表（复用 E1 useUniverSheetNav）
3. THE 索引类（底稿目录/GT_Custom/修订说明）SHALL 默认隐藏（defaultHidden=true）
4. THE 历史遗留类（G2-*-删除/移至/示例）SHALL 默认隐藏（defaultHidden=true）
5. THE 附注披露类 SHALL 标记为 readonly
6. THE 分组规则 SHALL 同时适用于 F0/F1/F3/F4/F5 底稿（通用 F 循环分组）

### F-F5: F2 存货监盘 D 类弹窗（P1）

**User Story:** As a 审计助理, I want 存货监盘程序通过弹窗交互完成（含照片/录像附件 + 双人签字）, so that 现场盘点记录规范完整。

#### Acceptance Criteria

1. THE InventoryStocktakeDialog.vue 组件 SHALL 提供 fullscreen 模式弹窗，包含以下表单字段：盘点地点 / 盘点日期 / 盘点方式（全面盘点/抽样盘点/循环盘点）/ 盘点人员（盘点人+复核人双签）/ 照片录像附件 / 盘点差异记录表 / 监盘结论
2. WHEN 审计助理点击 F2-21~F2-26 监盘类 sheet 的"开始监盘"按钮时, THE 系统 SHALL 打开 InventoryStocktakeDialog
3. THE 附件上传 SHALL 支持 image/* 和 video/* 类型，存储在 attachment_service（object_type=workpaper_item）
4. WHEN 盘点差异记录填写完成后, THE 系统 SHALL 提供 LLM 辅助生成监盘差异分析摘要（API: POST /api/projects/{pid}/workpapers/{wid}/ai/stocktake-summary）
5. THE 双人签字 SHALL 要求盘点人和复核人均签字后方可提交
6. IF 网络不稳定, THEN THE 弹窗 SHALL 支持离线草稿保存，后续网络恢复时同步

### F-F6: F5↔D4↔F2 三角勾稽 4 条 VR（P1）

**User Story:** As a 合伙人, I want 营业成本/营业收入/存货变动三角勾稽自动校验, so that 成本配比关系异常能及时发现。

#### Acceptance Criteria

1. THE 系统 SHALL 新增 4 条 validation_rules：
   - VR-F5-01：营业成本 = 期初存货 + 本期采购 - 期末存货（blocking, tolerance=1.0 元）
   - VR-F5-02：毛利率 = (D4收入 - F5成本) / D4收入，波动 < 5%（warning，与 VR-D4-03 交叉验证）
   - VR-F2-01：存货跌价准备计提率 vs 上年变动合理性（warning, tolerance=3%）
   - VR-F2-02：存货周转天数 vs 行业均值合理性（warning, tolerance=30 天）
2. WHEN VR-F5-01 blocking 规则校验失败时, THE ConsistencyGatePanel SHALL 阻断 F5 底稿签字
3. WHEN VR-F5-02 warning 规则触发时, THE ConsistencyGatePanel SHALL 显示告警但不阻断签字
4. THE VR-F5-02 SHALL 与 D spec 已实施的 VR-D4-03 形成双向交叉验证（D4 侧看毛利率 + F5 侧看毛利率）

### F-F7: cross_wp_references ≥ 35 条新增（P1）

**User Story:** As a 项目经理, I want F 循环跨底稿引用关系完整登记, so that stale 传播和联动刷新能正确触发。

#### Acceptance Criteria

1. THE cross_wp_references SHALL 新增 ≥ 35 条 F 循环条目，按以下分组：
   - F0 内部联动（F0-1→F0-3/F0-4/F0-5/F2-1 反向回填）：5 条
   - F2 内部联动（F2-2→F2-1/F2-47/F2-14）：4 条
   - F 循环跨底稿（F2/F4/F5 互相引用，存货→成本→应付三角）：8 条
   - F → A 跨循环（F2/F5→A1-1/A1-15/A1-16/A5-1）：8 条
   - F → T1 IPE（F2-24/F2-33/F2-34→T1）：4 条
   - F → 附注/报表（F2-1/F3-1/F4-1/F5-1→disclosure）：6 条
2. THE 新增条目 ref_id SHALL 基于运行时 `max(ref_id) + 1` 起编（禁止硬编码起始编号）
3. WHEN 任一 source_wp 数据变更时, THE stale_engine SHALL 沿 cross_wp_references 链路传播 stale 标记
4. THE 新增条目格式 SHALL 与现有 175 条保持 schema 一致（ref_id / source_wp / target_wp / category / description）

### F-F8: F0 函证 → F2 反向回填（P1）

**User Story:** As a 审计助理, I want F0 函证结果自动回填到 F2 审定表, so that 函证确认数不需要手工抄录。

#### Acceptance Criteria

1. THE cross_wp_references SHALL 新增 F0→F2 反向回填条目（category=data_flow_reverse）
2. WHEN F0-1 函证结果汇总表收到回函确认时, THE confirmation_service SHALL emit `EventType.CONFIRMATION_RECEIVED` 事件
3. WHEN `confirmation:received` 事件触发时, THE stale_engine SHALL 传播至 F2-1 审定表对应单元格
4. THE F2-1 编辑器 SHALL 订阅 `cross-ref:updated` 事件自动刷新公式（复用 D spec F6 模式）

### F-F9: B/C 前置状态横幅（P1）

**User Story:** As a 项目经理, I want F 循环底稿顶部显示 B/C 前置底稿完成状态, so that 我知道实质性程序的前置条件是否满足。

#### Acceptance Criteria

1. THE WorkpaperEditor 顶部 SHALL 显示前置状态横幅，包含 B23-3（采购存货循环业务层面控制）/ C4（采购存货循环控制测试）/ B51-4（存货舞弊风险评估）完成情况
2. THE usePrerequisiteStatus composable SHALL 复用 D spec 已实现的模式，仅扩展 F 循环前置清单配置
3. WHILE B23-3 或 C4 未完成时, THE 横幅 SHALL 显示 warning 状态提示"前置底稿未完成，实质性程序范围可能需调整"
4. WHEN B51-4 评估为高风险时, THE 横幅 SHALL 显示 danger 状态并触发 F-F14 IPO 应对加载

### F-F10: prefill 扩展 ≥ 60 cell（P1）

**User Story:** As a 审计助理, I want F 循环明细表/盘点/计价/跌价自动取数, so that 我不需要手工从 TB/AUX 抄录数据。

#### Acceptance Criteria

1. THE prefill_formula_mapping SHALL 新增 ≥ 60 cell F 循环条目，分布如下：
   - F2-2 明细汇总表（=AUX 按子科目/仓库/产品取数）：20 cell
   - F2-21~F2-26 盘点类（=LEDGER 取数 + 盘点差异计算）：10 cell
   - F2-38~F2-44 计价测试（=LEDGER_DETAIL 自动抽样）：15 cell
   - F2-47~F2-49 跌价准备（=AUX 按产品取可变现净值）：10 cell
   - F3/F4 明细表（=AUX 按供应商取数）：10 cell（F3 5 + F4 5）
2. WHEN F2-2 明细汇总表 prefill 完成后, THE F2-1 审定表 487 个 cross_sheet 公式 SHALL 自动计算出值
3. THE prefill 扩展 SHALL 使 F 循环总 prefill 从当前 45 cell 提升至 ≥ 105 cell
4. THE 新增 prefill 条目 SHALL 遵循 F2 两级链路：TB/AUX → F2-2 明细汇总表 → F2-1 审定表（prefill 目标是中间 sheet）

### F-F11: F2 计价测试自动抽样（P2）

**User Story:** As a 审计助理, I want 计价测试自动从序时账抽样, so that 我不需要手工挑选测试样本。

#### Acceptance Criteria

1. WHEN 审计助理打开 F2-38~F2-44 计价测试 sheet 时, THE 系统 SHALL 提供"自动抽样"按钮
2. WHEN 点击自动抽样时, THE prefill_engine SHALL 使用 =LEDGER_DETAIL 公式按金额分层抽样（参照 D spec D4-17/18 截止测试模式）
3. THE 抽样结果 SHALL 填入计价测试表对应行（品名/入库日期/数量/单价/金额）
4. THE 抽样策略 SHALL 支持加权平均/先进先出/标准成本 3 种计价方法的差异化抽样

### F-F12: F2 跌价准备 ECL 模型辅助（P2）

**User Story:** As a 审计助理, I want LLM 辅助分析存货跌价准备计提充分性, so that 我能快速判断管理层估计是否合理。

#### Acceptance Criteria

1. THE 系统 SHALL 提供 API `POST /api/projects/{pid}/workpapers/F2/impairment-analysis` 返回跌价准备分析建议
2. WHEN 审计助理在 F2-47 跌价准备测试 sheet 点击"AI 分析"时, THE 系统 SHALL 调用 LLM 分析可变现净值/计提方法/充分性
3. THE LLM 分析 SHALL 基于库龄分析（F2-48）+ 行业数据 + 历史计提率生成建议（参照 D spec F12 D2 业务模式分析模式）
4. THE 分析结果 SHALL 以弹窗形式展示，支持用户确认/修改后写入底稿

### F-F13: F2 审计导航图首屏（P2）

**User Story:** As a 审计助理, I want F2 打开时首屏显示审计导航图, so that 我能一目了然看到 32 项程序的执行状态。

#### Acceptance Criteria

1. WHEN 审计助理首次打开 F2 底稿时, THE 系统 SHALL 显示 WorkpaperAuditNav 组件（复用 D spec 已有组件）
2. THE 导航图 SHALL 展示 F2A 32 项程序的完成状态（未开始/进行中/已完成/不适用）
3. WHEN 点击导航图中某项程序时, THE 系统 SHALL 跳转到对应 sheet（如点击"存货监盘"跳转到 F2-21A）
4. THE 导航图 SHALL 区分常规程序（32 项中 26 项）和 IPO 应对程序（6 项，scenario=normal 时灰显）

### F-F14: B51-4 高风险 → F2-61A 自动加载（P2）

**User Story:** As a 项目经理, I want B51-4 评估高风险后自动加载 F2 IPO 应对程序, so that 高风险项目不会遗漏舞弊应对程序。

#### Acceptance Criteria

1. WHEN B51-4 存货舞弊风险评估结论为"高风险"时, THE event_handler SHALL 自动追加 F2-61~F2-72 文件加载
2. THE `_ensure_d4_ipo_loaded` 函数 SHALL 重构为通用 `_ensure_ipo_loaded(wp_code_prefix)` 支持 D4/F2 等多底稿
3. WHEN IPO 应对文件加载后, THE F2-61A 子总控台 SHALL 出现在 sheet 分组的"总控台"类别中
4. IF scenario 从 normal 切换为 ipo/fraud_response, THEN THE 系统 SHALL 自动加载所有 IPO 应对文件（不仅限于 B51-4 触发）

---

## 四、非功能需求

### 4.1 性能

| 指标 | 目标 |
|------|------|
| chain 生成 F 循环 6 主底稿（普通项目 scenario=normal）| < 45s（F2 11 文件合并去重 + 其余 5 底稿）|
| F2 单底稿打开（67 sheet 合并 + prefill）| < 8s（F2 复杂度是 D2 的 3 倍，允许更长加载）|
| F2 sheet 分组导航切换 | < 200ms |
| F-F6 VR 勾稽校验（4 条规则）| < 500ms |
| F-F7 cross_wp_ref stale 传播 | < 500ms（参照 E1 spec 基线）|
| InventoryStocktakeDialog 弹窗打开 | < 300ms |

### 4.2 兼容性

- 兼容现有 chain_orchestrator 流程（不破坏 D/E/G/H/I/J/K/L/M/N 其他循环）
- 兼容 D spec 已实施的 SCENARIO_TO_FILE_FILTER / `_merge_sheets_dedup` / `_should_skip_historical_sheet`
- 兼容 enterprise-linkage spec 已落地的 useEditingLock / event bus
- 不引入新前端依赖（复用 E1 + D spec 组件，仅新建 useFPurchaseInventorySheetGroups.ts + InventoryStocktakeDialog.vue）

### 4.3 可观测性

- F-F1 合并去重日志记录 `chain_executions.merge_dedup_summary`（去重前/后 sheet 数）
- F-F4 scenario 裁剪日志记录 `chain_executions.scenario_filter_summary`
- F-F6 VR 规则校验结果写入 `validation_rule_results` 表
- F-F7 stale 传播写 `linkage_audit_log`（global-linkage-bus 已有）
- F-F5 监盘弹窗操作写 `workpaper_audit_log`（附件上传/签字/LLM 调用）

---

## 五、测试矩阵

### 5.1 单测（pytest）

| 测试文件 | 覆盖 |
|---------|------|
| `test_f2_merge_dedup.py` | F-F1 F2 11 文件合并去重（90→≤67 sheet） |
| `test_f_historical_sheet_filter.py` | F-F2 4 种新历史遗留模式过滤 + 回归 D/E 不受影响 |
| `test_f_scenario_filter.py` | F-F3 scenario=normal 排除 F2 IPO 文件验证 |
| `test_f_sheet_groups.py` | F-F4 16 类分组规则全覆盖 |
| `test_f5_validation_rules.py` | F-F6 VR-F5-01/02 + VR-F2-01/02 |
| `test_f_cross_wp_refs.py` | F-F7 ≥ 35 条新增条目格式 + stale 传播 |
| `test_f0_confirmation_callback.py` | F-F8 F0 函证回函 → F2 审定表 stale |
| `test_f_prefill_extension.py` | F-F10 新增 ≥ 60 cell 取数正确 |

### 5.2 属性测试（hypothesis）

| Property | 描述 | max_examples |
|---------|------|--------------|
| **P1** | F2 sheet 名 normalize 后，底稿目录/GT_Custom/修订说明/G2-*-删除/移至/示例 类必去重或过滤 | 50 |
| **P2** | `_should_skip_historical_sheet` 扩展后对任意含"修订前/删除/移至/示例"的 sheet 名返回 True，对正常业务 sheet 名返回 False | 100 |
| **P3** | cross_wp_references 任两条 ref_id 不重复（全局唯一性） | 50 |
| **P4** | VR-F5-01 blocking 规则：营业成本 = 期初存货 + 本期采购 - 期末存货（tolerance=1.0）对任意合法输入幂等 | 50 |
| **P5** | F 循环 16 类 sheet 分组规则对任意 F2 sheet 名恰好匹配 1 类（无遗漏无重叠） | 100 |

### 5.3 集成测试

| 测试文件 | 覆盖 |
|---------|------|
| `test_f_cycle_full_chain.py` | F 循环 6 主底稿 chain 生成 + scenario=normal 应有 14 文件（排除 F2 IPO 1 文件）|
| `test_f0_f2_confirmation_callback.py` | F-F8 F0 函证回函 → F2 审定表 stale 传播端到端 |
| `test_f5_d4_f2_triangle.py` | F-F6 三角勾稽 VR-F5-01 blocking 阻断签字 |
| `test_f2_stocktake_dialog.py` | F-F5 监盘弹窗 + 附件上传 + LLM 摘要 |

### 5.4 UAT（手动验收清单）

| # | 验收项 | 对应修复项 | 优先级 |
|---|-------|-----------|--------|
| 1 | F2 11 文件合并后 sheet 数 ≤ 67（无重复底稿目录/GT_Custom） | F-F1 | P0 |
| 2 | F2 历史遗留 sheet（G2-*-删除/移至/示例）不可见 | F-F2 | P0 |
| 3 | scenario=normal 时 F2 不加载 IPO 应对文件 | F-F3 | P0 |
| 4 | F2 sheet 列表按 16 类分组显示，可折叠展开 | F-F4 | P1 |
| 5 | F2-21~F2-26 监盘 sheet 可打开 D 类弹窗 | F-F5 | P1 |
| 6 | 监盘弹窗支持照片/录像上传 + 双人签字 | F-F5 | P1 |
| 7 | 监盘弹窗 LLM 差异分析摘要可生成 | F-F5 | P1 |
| 8 | F5 底稿签字时 VR-F5-01 blocking 阻断（成本≠存货变动） | F-F6 | P1 |
| 9 | VR-F5-02 毛利率波动 > 5% 显示 warning | F-F6 | P1 |
| 10 | cross_wp_references F 循环条目 ≥ 43 条（8 现有 + 35 新增） | F-F7 | P1 |
| 11 | F0 函证回函后 F2-1 审定表自动刷新 | F-F8 | P1 |
| 12 | F2 顶部显示 B23-3/C4/B51-4 前置状态横幅 | F-F9 | P1 |
| 13 | F2-2 明细汇总表 prefill 自动取数（=AUX） | F-F10 | P1 |
| 14 | F2-1 审定表 cross_sheet 公式基于 F2-2 自动计算 | F-F10 | P1 |
| 15 | F3/F4 明细表 prefill 按供应商取数 | F-F10 | P1 |
| 16 | F2-38 计价测试自动抽样按钮可用 | F-F11 | P2 |
| 17 | F2-47 跌价准备 AI 分析弹窗可用 | F-F12 | P2 |
| 18 | F2 首屏审计导航图显示 32 项程序状态 | F-F13 | P2 |
| 19 | B51-4 高风险后 F2-61A 自动出现 | F-F14 | P2 |

上线门槛：≥ 16 项 ✓ pass + P0 项（#1, #2, #3）必须 ✓ pass。

---

## 六、成功判据汇总

| 类别 | 验收项 | 量化指标 |
|------|-------|---------|
| **合并去重（P0）**| F-F1 F2 合并去重 | 90 → ≤ 67 sheet（Sprint 0 实测确认） |
| | F-F2 历史遗留过滤 | 4 种新模式全覆盖 + D/E 回归无影响 |
| | F-F3 scenario 裁剪 | normal 时 F2 加载 10 文件（排除 IPO 1 文件） |
| **导航体验（P1）**| F-F4 sheet 分组 | 16 类规则全覆盖 F 循环 6 主底稿 |
| **现场执行（P1）**| F-F5 监盘弹窗 | D 类弹窗 + 附件 + 双签 + LLM 摘要 |
| **勾稽联动（P1）**| F-F6 三角勾稽 | 4 条 VR + VR-F5-01 blocking 阻断签字 |
| | F-F7 cross_wp_ref | ≥ 35 条新增（基于运行时 max_id 起编） |
| | F-F8 函证回填 | F0 回函 → F2-1 stale 传播 |
| **前置驱动（P1）**| F-F9 前置横幅 | B23-3/C4/B51-4 状态可视 |
| **数据覆盖（P1）**| F-F10 prefill | 45 → ≥ 105 cell（新增 ≥ 60） |
| **智能辅助（P2）**| F-F11 计价抽样 | =LEDGER_DETAIL 自动抽样 |
| | F-F12 跌价分析 | LLM 建议 + 用户确认 |
| **导航（P2）**| F-F13 审计导航图 | 32 项程序状态首屏展示 |
| **风险触发（P2）**| F-F14 IPO 自动加载 | B51-4 高风险 → F2-61A 出现 |

---

## 七、术语表

| 术语 | 定义 |
|------|------|
| **F 循环** | 采购存货循环（F0 函证 / F1 预付账款 / F2 存货及跌价准备 / F3 应付票据 / F4 应付账款 / F5 营业成本 共 6 主底稿，15 物理文件 151 sheet）|
| **F2A** | 存货实质性程序表（总控台，32 项程序，53R × 14C）|
| **F2-61A** | IPO 应对程序表（子总控台，IPO/上市/新三板/重组/舞弊应对场景专用，15 sheet）|
| **三角勾稽** | D4 营业收入 ↔ F5 营业成本 ↔ F2 存货变动 三者数据一致性校验（营业成本 = 期初存货 + 本期采购 - 期末存货）|
| **ECL 模型** | 预期信用损失模型（F2-47 跌价准备测试 / D2-9 坏账准备 共用概念，用于存货可变现净值评估）|
| **LEAP** | 致同审计方法论程序分类体系（常规程序/应对措施-分析/应对措施-检查/存货程序/会计估计/IPE）|
| **G2-*-删除** | 致同模板历史遗留 sheet（旧版编号 G2 已重编为 F2，但 sheet 名未清理，含"删除"/"移至"标记，需过滤）|
| **两级 prefill 链路** | F2 特有的取数架构：TB/AUX → F2-2 明细汇总表（prefill 目标）→ F2-1 审定表（487 cross_sheet 公式自动计算），与 D2 直接从 TB 取数不同 |
| **scenario** | 项目场景：normal / ipo / listed / restructure / fraud_response 5 档（E1 spec 定义，D spec 实施 SCENARIO_TO_FILE_FILTER）|
| **cross_wp_references** | 跨底稿引用配置（当前 175 条总 / F 相关 8 条，目标 ≥ 43 条）|
| **prefill_formula_mapping** | 底稿单元格预填充公式配置（当前 F 循环 45 cell，目标 ≥ 105 cell）|
| **VR-F5-01** | 营业成本三角勾稽 blocking 规则（成本 = 期初存货 + 采购 - 期末存货）|
| **InventoryStocktakeDialog** | 存货监盘 D 类弹窗组件（fullscreen + 表单 + 附件 + 双签 + LLM 摘要）|
| **useFPurchaseInventorySheetGroups** | F 循环 sheet 分组 composable（16 类规则）|
| **`_should_skip_historical_sheet`** | 历史遗留 sheet 过滤函数（需扩展支持 G2-*-删除/移至/示例 3 种新模式）|
| **`_ensure_ipo_loaded`** | 通用 IPO 应对文件加载函数（从 D spec `_ensure_d4_ipo_loaded` 重构而来，支持多底稿前缀）|

---

## 附录 A：Sprint 0 基线变量（实施前必须实测确认）

```python
# Sprint 0 实测结果（2026-05-19）
N_f_template_files = 15          # F 循环物理文件数 ✅
N_f2_files = 10                  # F2 物理文件数（10 个 F2-* 文件）✅
N_f2_raw_sheets = 90             # F2 合并前 sheet 总数 ✅
N_f2_dedup_sheets = ~75          # F2 合并去重后预估（实施 F-F1+F-F2 后实测）
N_f_prefill_entries = 7          # prefill_formula_mapping F 类 entry 数 ✅
N_f_prefill_cells = 45           # prefill_formula_mapping F 类 cell 总数 ✅
N_f_cwr_count = 8                # cross_wp_references 涉及 F 循环条数 ✅
N_cwr_max_id = 175               # 当前 cross_wp_references 最大 ref_id（CW-175）✅
N_f2_formulas = 487              # F2-1 审定表 Univer 内置公式数 ✅
N_f2a_programs = 32              # F2A 总控台程序项数 ✅
N_f_historical_sheets = 12       # F 循环历史遗留 sheet 数 ✅（实测，非 README 估算 10）
N_f_historical_skip_gap = 11     # 当前 _should_skip_historical_sheet 缺口数 ✅
```

**Sprint 0 关键偏差发现（修正 design.md ADR-F3）**：

实测发现历史遗留 sheet **12 条**（README 估算 10 条偏差 +2），分布：
- 1 条 `修订前`（F1 文件：`预付账款实质性程序表G1A-修订前`）— 当前 regex 命中 ✅
- 8 条 `G-编号-删除/移至`（F2-38/F2-47/F2-52 文件）— 当前 regex **未命中** ❌
- 3 条 `示例`（F0/F2-55/F2-61 文件）— 当前 regex **未命中** ❌

**Sprint 0 修正 design.md ADR-F3 regex**（关键修正：G 不在开头而在中间）：
```python
def _should_skip_historical_sheet(name: str) -> bool:
    if name is None:
        return False
    s = str(name)
    return (
        ("修订前" in s) or ("（原）" in s) or ("(原)" in s)
        # 修正：G 编号可在 sheet 名中间（如 "存货计价测试程序G2-8-删除"）
        or (re.search(r"G\d+", s) is not None and ("删除" in s or "移至" in s))
        or ("（示例）" in s) or ("(示例)" in s) or s.endswith("示例") or s.endswith("示例）")
    )
```

**SCENARIO_TO_FILE_FILTER 验证结果**：
- scenario=normal: 加载 14/15 F 文件（仅排除 `F2-61至F2-72 存货及跌价准备-IPO 上市 新三板 重组 舞弊应对.xlsx`）✅
- scenario=ipo: 加载 15/15 F 文件 ✅
- F-F3 验证通过，无需新代码

---

> **本 requirements.md 配套文档**：design.md（架构决策）+ tasks.md（实施计划）
> **README v1.1 锚点**：§一 痛点 / §二 真实结构 / §九 总控台拆解 / §十 公式拓扑 / §十一 全 sheet 清单 / §十二 代码骨架
> **下一步**：Sprint 0 已完成 ✅ → Sprint 1 P0 quickfix 启动
