# Requirements Document

## Introduction

本 spec 改造 B50「汇总风险评估结果」底稿：补齐缺失的汇总程序表 Tab、对齐 Tab3 认定矩阵与源模板结构、引入 HTML↔OnlyOffice 双模式、引导式录入弹窗与页面美化统一，同时保证现有 4-Tab 与全部联动零回归。

## 背景

B50「汇总风险评估结果」是风险导向审计枢纽（`B50 → D~N 认定层次程序 → C 控制测试 → A13 错报`）。当前专属组件 `GtB50RiskAssessment.vue`（2343 行）已实现 4-Tab（风险因素/报表层次/认定矩阵/特别风险）+ 上游 B22A/B2 事件订阅 + B15 重要性联动 + 版本链 + 复核对话 + 合伙人审批锁定 + 舞弊推定反驳弹窗，工程质量高。

复盘（2026-07-22）发现相对源模板的系统性缺口：
1. **🔴 汇总程序表（wp_code=B50 真实内容，43 行）UI 完全缺失** — 组件只渲 4 风险 Tab，从不渲 `html_data`，也无 `a-program-console`，编制主脉断链。
2. **Tab3 与源 B50-3（244 行×23 列）结构偏差** — 源是"确定审计范围+风险评估+风险应对"合一科目宽表（余额/类别 SCOT+·仅金额重大·其他/是否会计估计/相关 vs 适用认定/固有/特别风险区分舞弊·错误/仅实质性是否足够/拟信赖控制/综合 vs 实质性方案/业务循环→D~N），当前 Tab3 仅"科目×6 认定 H/M/L 矩阵"，缺余额/类别/会计估计列。
3. **🔴 无双模式** — 组件零 OnlyOffice/segmented，审计师无法查看源 xlsx 版式（参照 D4 双模式：健康检查 healthy 才 enable 在线编辑）。
4. **宽表点点点缺失** — B50-3 23 列宜做引导式弹窗录入（参照 J3PlanDialog/D2DerecognitionWizard）。
5. **页面美化未对齐** — 硬编码色值/字号，未对齐平台 13px/EP 变量/审计目标 alert/方法论琥珀块规范。

## Glossary

- **程序表 Tab**：B50 汇总风险评估结果程序表（43 行，序号/程序/是否适用/执行人/执行说明/索引号/风险指标），复用 `GtAProgramConsole` 渲染。
- **认定层次计划矩阵（Tab3）**：科目级审计范围+风险评估+应对方案合一表。
- **双模式**：`html`（结构化专属组件）↔ `onlyoffice`（源 xlsx 在线编辑），由 `GET /api/workpapers/onlyoffice/health` 的 `data.healthy` gate。
- **源子底稿**：程序表=wp_code B50、风险因素=B50-1、报表层次=B50-2、认定层次=B50-3、特别风险=B50-4（分属独立 xlsx 文件）。

## Requirements

### Requirement 1: 汇总程序表 Tab（P0）

**User Story:** 作为审计助理，我要在 B50 底稿看到汇总风险评估结果程序表，按程序步骤逐项推进并跳转到对应明细表，以还原致同"程序驱动明细"的编制主脉。

#### Acceptance Criteria
1. WHEN 打开 B50 底稿 THEN 组件 SHALL 在 Tab 容器首位显示"汇总程序表"Tab，复用 `GtAProgramConsole` 渲染 43 行程序表（数据源 `procedure_table_templates.json` 的 "B50" 条目经 render-config `html_data.programs`）。
2. WHEN 程序表某步骤的"索引号"列为 B50-1/B50-2/B50-3/B50-4 THEN 该索引 SHALL 渲染为可点击 chip，点击后切换到对应的风险 Tab（B50-1→风险因素、B50-2→报表层次、B50-3→认定矩阵、B50-4→特别风险）。
3. WHEN 程序步骤"是否适用/执行人/执行情况说明"被编辑 THEN SHALL 持久化到 checklist_responses（沿用 a-program-console 既有持久化，item_id 前缀不与 B50-T* 冲突），并纳入版本链自动快照。
4. IF 程序表模板缺失或加载失败 THEN 组件 SHALL 显示降级提示且不阻断其余 Tab 渲染。
5. WHEN 计算整体进度 THEN 程序表 Tab 状态 SHALL 纳入进度指示（不破坏现有 4-Tab 进度语义）。

### Requirement 2: Tab3 认定矩阵结构对齐（P0）

**User Story:** 作为现场经理，我要 Tab3 计划矩阵包含科目余额、类别（SCOT+/仅金额重大/其他）、是否会计估计，以对齐源 B50-3 并驱动应对方案判断。

#### Acceptance Criteria
1. WHEN 从试算表导入重要科目（`/api/b50/scope-accounts`）THEN 每个科目行 SHALL 一并带入余额（若后端可提供），并在矩阵行展示"余额/金额"列。
2. WHEN 编辑科目行 THEN SHALL 提供"类别"下拉（SCOT+ / 仅金额重大 / 其他）与"是否会计估计"下拉（是/否），持久化到 checklist_responses（`B50-T3-*` 前缀，新增 suffix，向后兼容既有键）。
3. WHEN 类别=仅金额重大 且 无高风险认定 THEN SHALL 自动建议应对方案为"实质性方案"；WHEN 类别=SCOT+ 或存在高综合风险认定 THEN SHALL 自动建议"综合性方案"（仅建议，不覆盖审计师手选）。
4. WHEN 科目行完整性判定 THEN incompleteAccounts 计算 SHALL 保持对既有必填项（认定风险）的判定不放宽，新增列不强制必填（避免既有数据回归为未完成）。
5. WHEN 展示矩阵 THEN 新增列 SHALL 支持列显隐（⚙ 列设置，localStorage 持久化），默认显示余额/类别，会计估计可隐藏。

### Requirement 3: 引导式科目风险录入弹窗（P1，optional*）

**User Story:** 作为审计助理，我要一个科目一个引导弹窗录入范围/认定/特别风险/应对，减少 244 行宽表逐格 Popover 操作。

#### Acceptance Criteria
1. WHEN 点击科目行"编辑"或矩阵工具栏"引导录入" THEN SHALL 打开 `B50AccountRiskDialog`，分组卡片：① 审计范围（余额/类别/是否风险因素/是否会计估计）② 认定层次风险（6 认定的 IR/CR/RMM 点选）③ 特别风险（是否+舞弊/错误）④ 应对方案（拟信赖控制/仅实质性是否足够/综合 vs 实质性/业务循环→D~N）。
2. WHEN 在弹窗内改字段 THEN 右侧实时联动面板 SHALL 提示：高风险+舞弊→CAS 强制细节测试；应对方案=综合→"→C 控制测试"；业务循环已选→"→{循环}程序表"。
3. WHEN 保存弹窗 THEN SHALL 一次性批量 `saveImmediate` 全部字段（避免 debounce 被后续 immediate 的 clearTimeout 取消丢失数据）。
4. WHEN 弹窗关闭后 THEN 矩阵表 SHALL 反映弹窗录入结果（同一数据源，无双写）。

### Requirement 4: 双模式 HTML ↔ OnlyOffice（P1）

**User Story:** 作为业务合伙人，我要能在结构化视图与源 xlsx 在线编辑视图间切换，且只有 OnlyOffice 服务真正可用时才允许切换。

#### Acceptance Criteria
1. WHEN 组件挂载 THEN SHALL 调 `GET /api/workpapers/onlyoffice/health` 并据 `data.healthy` 设置 `ooAvailable`；顶部工具栏 SHALL 显示 `el-segmented`（结构化 / 在线编辑），"在线编辑"选项 SHALL 在 `!ooAvailable` 时 disabled 并显示"OO 不可用"tag。
2. WHEN 切到"在线编辑" AND 当前处于某 Tab THEN SHALL 用 `GtOnlyOfficeSheet` 打开该 Tab 对应源子底稿（程序表→B50、风险因素→B50-1、报表层次→B50-2、认定矩阵→B50-3、特别风险→B50-4），`sheet-name` SHALL 与源 xlsx tab 名完全一致。
3. WHEN 解析源子底稿 wp_id THEN SHALL 经 `/api/custom-query/wp-id-by-code`（复用既有范式）；IF 该源子底稿在本项目未实例化 THEN SHALL 显示"该子表未实例化，请用结构化模式"降级提示，不崩溃。
4. WHEN `GtOnlyOfficeSheet` 触发 `@fallback` THEN SHALL 自动切回结构化模式。
5. WHEN 从在线编辑切回结构化 THEN SHALL 重新 `loadAll()` 刷新 allResponses（反映 OnlyOffice 侧可能的改动）。
6. WHEN readonly 或已审批锁定 THEN OnlyOffice 视图 SHALL 以只读打开。

### Requirement 5: 页面美化统一（P2，optional*）

**User Story:** 作为质控复核人，我要 B50 与 D~N 已打磨底稿视觉一致，便于复核。

#### Acceptance Criteria
1. WHEN 渲染表格 THEN 字体 SHALL 统一 13px。
2. WHEN 使用颜色 THEN 硬编码色值 SHALL 尽量替换为 Element Plus CSS 变量（风险色板保留语义映射即可）。
3. WHEN 每个 Tab 顶部 THEN SHALL 提供审计目标 el-alert + 编制提示 details（CAS 1211/1231 依据）+ 方法论琥珀块（内嵌源 B50-1"固有风险因素"知识库要点，可一键套用到风险因素）。
4. WHEN 顶部工具栏 THEN 版本历史/复核/双模式切换 SHALL 布局统一、不重叠。

### Requirement 6: 零回归（贯穿）

**User Story:** 作为平台维护者，我要改造不破坏现有 B50 功能。

#### Acceptance Criteria
1. WHEN 改造完成 THEN 既有 4-Tab 的数据键（B50-T1/T2/T3/T4/rebuttal/approval/amend）SHALL 完全兼容，历史数据可正常回读。
2. WHEN 改造完成 THEN 上游事件订阅（b50:push-risk-factor / control:conclusion-changed / control:environment-weak）、下游 risk_for_cycle / b50_risk_summary（经 b50_risk_reader 读 checklist_responses）、合伙人审批锁定、版本链、复核对话 SHALL 全部保持可用。
3. WHEN 改造完成 THEN `b50_risk_reader` 的 item_id 契约（B50-T3-matrix/cycle/plan、B50-T2-*）SHALL 不被破坏；新增 suffix 不影响既有解析。
4. WHEN 运行 `get_diagnostics` + Vite transform + 后端 AST + 既有 b50 vitest/pytest THEN SHALL 全部通过。
