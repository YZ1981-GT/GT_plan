# Requirements Document

## Introduction

本 spec 是**全局工程加固与机制沉淀（hardening / consolidation）**专项，**不引入任何新的审计业务功能、不新增审计循环或底稿类型**。其唯一目标是：把"功能扩张期"沉淀下来的一次性口头约定（memory 里的"底稿 UI 铁律""取数口径铁律"等），升级为**工程化的强制机制**，从而在一个开发周期内"焊死全局机制"，让此后每个新底稿的**开发成本与 bug 率断崖式下降**。

需求来源为资深合伙人基于代码库实测（8,993 文件 / 154k 节点 / 329k 边；715 routers + 731 services；2,037 Vue 组件 + 1,439 底稿 composables）撰写的全局评估报告 `docs/proposals/platform-partner-review-2026-07-12.md`，其中列出 10 条代码可验证的问题，并给出三波（P0 止血 / P1 沉淀 / P2 降本）落地路线。本文档将该报告的可执行部分转化为符合 EARS 与 INCOSE 质量规则的需求。

**核心判断（管理层一句话）**：功能深度已足够，须停止加新循环，先花一个周期把全局机制焊死。因此本 spec 的所有需求都属于"存量收敛"而非"增量功能"，验收基准是**行为一致性 + 强制接线 + CI 阻断能力**，而非新增用户可见特性。

**优先级说明**：每个需求标注 P0 / P1 / P2，对应报告的三波路线。P0 为"止血项"（投入小、对全体用户与运维即时受益），P1 为"防漏 + 沉淀"，P2 为"持续降本"。P2 需求在本 spec 范围内，但排期靠后（optional-ish）。**排期建议**：报告第一、二、八条（displayPrefs 收敛 / Shell 强制接线 / 工程硬门禁）是"投入小、全员即时受益"的止血项，应优先；其中 **render 冒烟 + Vite transform 冒烟（Req 3.2/3.5/3.6）是根治"假绿"的验收硬门槛，已置于 Wave 0**，是本 spec 交付的必过项，不以单测绿为准。

**相关 spec（协同，非依赖）**：`workpaper-bulk-tab-import-export`（项目级底稿批量导入导出）与本 spec 同属"机制/收敛"专项，共享 CI 守卫与 render 冒烟哲学；本 spec Coverage_Ledger 的 `importExport` 能力接入状态（Req 2.3）即 bulk 可导出性的就绪信号——一个底稿未接 I/E 则无法纳入 bulk ZIP。二者可并行推进，无硬依赖。

## Glossary

- **displayPrefs Store（`useDisplayPrefsStore`）**：全局显示偏好 Pinia store（`stores/displayPrefs.ts`），涵盖金额单位（万/元/亿）、字号、小数位、负数红字、变动高亮阈值、表格密度、按页固定列，并持久化 localStorage。本文档中作为系统名时记为 **DisplayPrefs_Store**。
- **displayPrefs 硬编码闭包**：底稿主入口当前 `provide('displayPrefs', {...})` 提供的固定 2 位小数 / 固定"元"口径 / 固定负数括号的本地对象，**非** DisplayPrefs_Store。
- **DisplayPrefs_Key**：类型化的 Vue `InjectionKey`，用于替代字符串 key `'displayPrefs'` 的注入。
- **useAgingConfig**：全局账龄配置服务（`useAgingConfig(projectId, subject)`），提供项目级可配置账龄段。
- **GtWorkpaperShell**：本 spec 拟建的底稿骨架组件（或等价 composable `useWorkpaperScaffold`），默认注入全部全局能力。本文档中作为系统名时记为 **Workpaper_Shell**。
- **Coverage_Ledger**：全局能力接入率看板（Global Capability Coverage Ledger），记录每个底稿是否接入 displayPrefs / agingConfig / 版本链 / 复核 / AI / 导入导出 / ACNR 等全局能力。
- **CI_Drift_Guard**：CI 漂移守卫，扫描"应接未接"并阻断构建。
- **WpKit**：底稿专用组件库（`components/workpaper/kit/`），含 `<WpSection>` / `<WpAmountCell>` / `<WpFormulaCell>` / `<WpOpinionCard>` / `<WpImportExport>` / `<WpDynamicTable>`。本文档中作为系统名时记为 **Wp_Kit**。
- **AuditData_SDK**：本 spec 拟建的统一取数 hook `useAuditData(projectId, year)`，提供语义化取数方法。
- **PermissionMatrix**：单一权限判定服务，前后端共享定义，入口为 `can(action, resource, context)`。本文档中作为系统名时记为 **Permission_Matrix**。
- **Trace_Drawer**：统一"溯源抽屉"组件，展示"四表→报表→审定→底稿→调整→附注"完整链且每一跳可点击跳转。
- **AiContext_Factory**：统一 AI 上下文工厂 `buildAiContext(wpCode, sheet)`。
- **wp_code**：底稿编码（如 D2-1），唯一标识底稿类型。
- **componentType**：前端渲染类型（如 audit-sheet / a-program-console）。
- **GtIndexChip**：跨底稿索引跳转组件，prop 名为 `value`（索引语法如 `wp:D2` / `cell:{sheet}!{coord}`）。
- **ACNR**：地址坐标名称注册中心，平台级目录真源；主键为 addr_id。
- **EventBus**：进程内事件总线（publish=EventPayload / broadcast_raw=纯 SSE）。
- **CI 守卫（现存）**：`check_wp_ref_contract.py`（ref 解包契约）、`fix_wp_composables_import_depth.py --check`（import 深度）等已挂 `governance-checks.yml` 的守卫脚本。
- **Vite transform 冒烟**：curl `/src/....vue` 判 http 200/500，比 Volar/get_diagnostics 更权威的崩溃检测手段。
- **U+FFFD**：UTF-8 替换字符（replacement char），PowerShell 破坏中文编码后出现，可用 `raw.count(b'\xef\xbf\xbd')` 检测。
- **render 冒烟测试集**：对每个 wp_code 打开一次、断言 0 console error + 关键区块存在的测试集，用于根治"假绿"。

---

## Requirements

## 第一波 · P0 止血（体感最强、投入小、对全体用户与运维即时受益）

### Requirement 1: 全局显示偏好收敛到单一真源（P0）

**User Story:** 作为审计助理与项目合伙人，我希望底稿的金额单位、字号、小数位、密度、负数红字与全局设置及报表/序时账保持一致，以便复核时同一个数在任何视图口径一致，无需反复心算。

#### Acceptance Criteria

1. THE DisplayPrefs_Store SHALL 作为底稿显示偏好的唯一数据源，提供 `fmtAmount`、`amountClass`、`unitSuffix`、`unitDivisor`、`tableDensity`、`fontConfig` 的响应式引用。
2. WHEN 底稿主入口初始化时，THE 底稿主入口 SHALL 通过 DisplayPrefs_Key 注入 DisplayPrefs_Store 的响应式引用，而非提供硬编码闭包。
3. THE 底稿 tab SHALL 通过 DisplayPrefs_Key 消费 DisplayPrefs_Store，禁止在 `inject('displayPrefs', {fallback})` 中提供本地格式化实现。
4. WHEN 用户在全局设置中修改金额单位、字号、小数位或表格密度时，THE 底稿 SHALL 在同一会话内响应式更新其显示，无需刷新页面。
5. THE 底稿根容器 SHALL 将 `fontConfig` 映射为 CSS 变量 `--wp-font-size`，且底稿内表格 SHALL 使用 `var(--wp-font-size)` 而非 `font-size:13px` 字面量。
6. WHEN 用户导出底稿 Excel 时，THE 导出结果 SHALL 按当前 `unitDivisor` 口径还原金额并标注单位，使屏幕口径与导出口径一致。
7. THE CI_Drift_Guard SHALL 检测并阻断在底稿代码中出现 `inject('displayPrefs', {硬编码 fallback})` 或散落的 `font-size:13px` 字面量的提交。

---

### Requirement 2: 全局能力默认注入的底稿骨架（P0）

**User Story:** 作为现场经理与运维，我希望新底稿"套壳即拥有"全部全局能力（显示偏好、账龄、版本链、复核、AI、导入导出、审计目标/编制提示），以便不再依赖开发者手工记忆接线，杜绝"新页面漏接全局服务"。

#### Acceptance Criteria

1. THE Workpaper_Shell SHALL 默认注入以下全局能力：displayPrefs、agingConfig（useAgingConfig）、版本链工具栏、复核 provide、AI provide、导入导出 dropdown、审计目标插槽、编制提示插槽。
2. WHERE 一个底稿通过 Workpaper_Shell 编写，THE 该底稿 SHALL 自动获得全部第 1 条所列全局能力，无需逐项手工 import 与接线。
3. THE Coverage_Ledger SHALL 记录每个 wp_code 对 displayPrefs、agingConfig、版本链、复核、AI、导入导出、ACNR 各全局能力的接入状态。
4. WHEN CI 运行时，THE CI_Drift_Guard SHALL 扫描 Coverage_Ledger 并对被明确检出为"应接未接"（should-wire-but-didn't）的底稿使构建失败。
5. IF 一个非 Workpaper_Shell 底稿未在 Coverage_Ledger 登记豁免原因，THEN THE CI_Drift_Guard SHALL 报告该底稿为未接线并阻断构建。
6. THE Workpaper_Shell SHALL 在缺少必要上下文（projectId、wp_code、year）时给出明确的开发期错误提示，标明缺失的上下文项名称。
7. WHERE 一个底稿通过 Workpaper_Shell 编写，THE CI_Drift_Guard SHALL 将该底稿视为自动接入（auto-covered）并豁免其显式的 Coverage_Ledger 登记要求。
8. WHERE CI_Drift_Guard 无法确定一个底稿的接线状态，THE 构建 SHALL 被允许通过（对守卫自身的检测不确定性采取 fail-open），且被明确检出为未接线的底稿 SHALL 仍然阻断构建。

---

### Requirement 3: 工程纪律硬门禁（P0）

**User Story:** 作为运维与全体开发者，我希望编码破坏、假绿、脚本改 Vue 等反复踩坑的问题由 CI 硬门禁强制拦截，以便不再依赖人肉记忆铁律，从根本上消除"单测绿但浏览器 500/白屏"的问题。

#### Acceptance Criteria

1. WHEN 提交包含 Vue 或其他文本文件时，THE UTF-8 完整性检查 SHALL 统计文件中的 U+FFFD 替换字符数量（`raw.count(b'\xef\xbf\xbd')`），且 IF 数量大于 0，THEN THE 检查 SHALL 使 pre-commit 与 CI 失败并列出受影响文件。
2. WHEN CI 运行时，THE Vite transform 冒烟 SHALL 对底稿源码树中的每个 `.vue` 与 `.ts` 文件请求 `/src/....`，且 IF 任一文件返回 HTTP 500，THEN THE 冒烟 SHALL 使构建失败并列出返回 500 的文件路径。
3. THE ref 解包契约守卫（`check_wp_ref_contract.py`）SHALL 以 `--strict` 模式挂载于 CI 并在检出反模式时阻断构建。
4. THE import 深度守卫（`fix_wp_composables_import_depth.py --check`）SHALL 挂载于 CI 并在检出错误相对导入层级时阻断构建。
5. THE render 冒烟测试集 SHALL 对每个 wp_code 打开一次，断言浏览器 console error 数量为 0 且该底稿的关键区块存在。
6. IF render 冒烟测试集检出任一 wp_code 存在 console error 或缺失关键区块，THEN THE 测试集 SHALL 使 CI 失败并报告对应 wp_code 与错误摘要。
7. WHEN 提交的 diff 中 Vue 文件包含 U+FFFD 替换字符时，THE CI SHALL 判定该提交为"疑似 shell 文本替换破坏"并失败。

---

## 第二波 · P1 沉淀（防漏 + 组件化 + 取数收敛）

### Requirement 4: 底稿 UI Kit 组件库（P1）

**User Story:** 作为全体审计角色，我希望底稿的交互细节（框高、按钮位置、公式提示、金额格式）由统一组件库保证一致，以便平台观感统一，且运维改一次交互规范不必动几十上百个文件。

#### Acceptance Criteria

1. THE Wp_Kit SHALL 提供 `<WpSection>` 组件，统一渲染"标题行 + 审计目标 el-alert + 编制提示 details + 右侧 AI/复核按钮"。
2. THE Wp_Kit SHALL 提供 `<WpAmountCell>` 与 `<WpFormulaCell>` 组件，金额格式统一走 DisplayPrefs_Store，且公式列 SHALL 显示虚线下划线与来源 tooltip。
3. THE Wp_Kit SHALL 提供 `<WpOpinionCard>` 组件，内置 `autosize` 且 `minRows` 为 5 的文本域、AI 辅助按钮与复核按钮。
4. THE Wp_Kit SHALL 提供 `<WpImportExport>` 组件，渲染"导入导出▾"dropdown（导出模板 / 导出数据 / 导入数据）。
5. THE Wp_Kit SHALL 提供 `<WpDynamicTable>` 组件，支持 13px 字体、紧凑密度、auto-calc-col 计算列、合计行、动态新增/删除行与账龄动态列。
6. WHERE 某处存在可用的 Wp_Kit 组件，THE ESLint 规则 SHALL 禁止手写等价结构，并在检出时报错。
7. WHEN `<WpAmountCell>` 或 `<WpDynamicTable>` 渲染金额时，THE 组件 SHALL 反映当前 DisplayPrefs_Store 的单位、小数位与负数红字设置。

---

### Requirement 5: 统一取数 SDK（P1）

**User Story:** 作为底稿开发者，我希望通过统一取数 SDK 的语义方法获取审定数/未审数/账龄/序时账/上年数，以便底稿不再各自拼 URL 与参数，杜绝"漏 year → 422""字段名猜错取不到"这类口径漂移 bug。

#### Acceptance Criteria

1. THE AuditData_SDK SHALL 提供语义方法 `getTbAmount(accountCode, {basis})`、`getAging(subject)`、`getLedgerEntries(...)`、`getPrevYear(...)`。
2. WHEN 调用任一 AuditData_SDK 方法时，THE AuditData_SDK SHALL 从 projectContext 内置解析 year，调用方无需手动传入 year。
3. THE AuditData_SDK SHALL 对返回数据执行字段归一化，屏蔽底层字段名差异，向调用方返回稳定的语义字段。
4. THE AuditData_SDK SHALL 内聚并支持全部三种取数口径约定（借正贷负 v1 / 正数 v2 / 损益发生额），且 WHEN 调用方按数据域取数时，THE AuditData_SDK SHALL 返回该数据域对应的正确口径，而非统一强制为单一口径。
5. WHERE 序时账数据已缓存，THE AuditData_SDK SHALL 复用缓存（`useLedgerCache`）而不重复拉取。
6. IF 取数请求失败或数据缺失，THEN THE AuditData_SDK SHALL 返回明确的错误降级结果，且 SHALL NOT 抛出未捕获异常导致底稿白屏。
7. THE 底稿 SHALL 仅调用 AuditData_SDK 的语义方法，禁止直接拼接取数 URL 或裸传取数参数。

---

## 第三波 · P2 降本（持续，排期靠后）

### Requirement 6: 巨型文件拆分与 composable 工厂化（P2）

**User Story:** 作为运维与 reviewer，我希望核心巨型文件按域拆分、上千个同构 composable 收敛为工厂，以便降低单文件改动风险与"改 A 漏 B"的重复维护成本。

#### Acceptance Criteria

1. THE 巨型文件拆分 SHALL 按业务域拆分下列前端文件：`LedgerPenetration.vue`（3,706 行）、`TrialBalance.vue`（2,683 行）。
2. THE 巨型文件拆分 SHALL 按业务域拆分下列后端文件：`_d1_import_export.py`（2,989 行）、`event_handlers.py`（1,725 行）、`consistency_gate.py`（2,141 行）。
3. WHERE 一个文件被拆分，THE 拆分 SHALL 按域边界而非固定行数硬切，且拆分后各文件对外行为不变。
4. THE CI size guard SHALL 对上述文件类别设置行数上限，且 IF 任一受管文件超过上限，THEN THE size guard SHALL 使构建失败。
5. THE composable 工厂 SHALL 提供 `createCycleFormData`、`createDualMode`、`createImportExport`、`createDetailTable` 参数化工厂，用于收敛现有底稿 composable。
6. WHEN 一个新底稿需要表单数据、双模式、导入导出或明细表能力时，THE 开发者 SHALL 通过对应工厂参数化生成，而非复制同构实现。

---

### Requirement 7: 单一权限矩阵（P2）

**User Story:** 作为质控复核合伙人与 EQCR，我希望"谁能编辑/复核/查看"的判定收口到单一权限矩阵，以便 5 角色的权限边界一致执行，且安全判定由后端兜底。

#### Acceptance Criteria

1. THE Permission_Matrix SHALL 提供单一入口 `can(action, resource, context)`，前后端共享同一权限定义。
2. THE 底稿前端 SHALL 通过 Permission_Matrix 判定 `isReadonly`、按钮禁用与字段可编辑状态，禁止各底稿自行判断。
3. WHEN 前端需要判定编辑或复核权限时，THE 前端 SHALL 调用 Permission_Matrix 而非直接读取 `canEditInProject` 或 `BUILDER_ROLES` 等分散判定。
4. THE 后端 deps 层 SHALL 作为安全边界强制校验权限，且 THE 前端权限判定 SHALL 仅用于体验优化而非安全边界。
5. IF 前端权限判定与后端 deps 层判定不一致，THEN THE 后端 deps 层判定 SHALL 生效。
6. THE Permission_Matrix SHALL 支持 5 角色（审计助理、现场经理、业务合伙人、质量控制复核合伙人、EQCR 技术复核人）的项目级权限区分。

---

### Requirement 8: 统一溯源抽屉与刷新链端到端回归（P2）

**User Story:** 作为项目合伙人与 EQCR，我希望任意金额可一屏式反查"四表→报表→审定→底稿→调整→附注"完整链，且"改上游→下游标脏→一键刷新"链路有端到端实测背书，以便追溯与失效传播确定可靠。

#### Acceptance Criteria

1. THE Trace_Drawer SHALL 对任意金额展示"四表→报表→审定→底稿→调整→附注"完整溯源链。
2. WHEN 用户点击溯源链中的任一跳时，THE Trace_Drawer SHALL 跳转到对应的底稿、单元格或调整分录。
3. THE Trace_Drawer SHALL 收敛现有的 ReportTracePanel 与 GtIndexChip 两套入口为单一溯源入口。
4. THE draft-refresh 端到端回归 SHALL 覆盖 5 角色链路：合伙人点刷新 → 审计助理看到底稿初稿 → 经理复核 → 附注同步 → EQCR 抽查。
5. WHEN draft-refresh 端到端回归运行时，THE 回归 SHALL 以 Playwright 实测断言链路成功，而非仅依赖单元测试通过。
6. IF draft-refresh 链路中任一环节的下游标脏或刷新未按预期发生，THEN THE 端到端回归 SHALL 失败并报告断点环节。
7. THE draft-refresh 端到端回归（验收标准 4、5、6）与 Trace_Drawer 功能（验收标准 1、2、3）SHALL 作为相互独立的关注点，且 IF Trace_Drawer 功能不完整或缺失，THEN THE draft-refresh 端到端回归 SHALL NOT 因此失败。

---

### Requirement 9: AI 上下文工厂（P2）

**User Story:** 作为使用 AI 辅助的审计角色，我希望 AI 生成基于本底稿的实际数据（联动数据/审定数/账龄/异常项/源模板方法论），且输出走"生成→预览 diff→确认"三段式，以便 AI 结论从通用套话升级为可用内容且不误覆盖已填内容。

#### Acceptance Criteria

1. THE AiContext_Factory SHALL 提供 `buildAiContext(wpCode, sheet)`，自动附带该底稿的联动数据、审定数、账龄、异常项与源模板方法论。
2. WHEN 底稿触发 AI 生成时，THE 底稿 SHALL 通过 AiContext_Factory 构建上下文并随请求提交，而非传空 context。
3. THE AI 输出流程 SHALL 采用三段式：生成 → 预览 diff → 确认填入。
4. WHEN 用户确认 AI diff 预览时，THE 底稿 SHALL 立即填入确认的内容，且确认动作与内容填入之间 SHALL NOT 存在额外延迟。
5. IF 目标区域已有用户填写内容，THEN THE AI 输出流程 SHALL 在预览 diff 中标示差异并要求确认，SHALL NOT 直接覆盖已填内容。
6. WHEN AI 生成完成时，THE 底稿 SHALL 先展示 diff 预览，且在用户确认前 SHALL NOT 填入内容。
