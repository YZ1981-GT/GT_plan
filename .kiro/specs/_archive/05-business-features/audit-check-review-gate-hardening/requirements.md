# Requirements Document

## Introduction

项目概览页「审计检查」入口（`DetailProjectPanel「审计检查」→ /projects/:projectId/audit-checks → AuditCheckDashboard.vue`）当前是「精细化提取检查（fine_checks）的项目级汇总视图」：数据来自 `GET /api/projects/{pid}/fine-checks/summary`（`wp_fine_rules.py`），**直接读 `WorkingPaper.parsed_data.fine_checks` 缓存**，按循环分组展示通过/未通过/待验证/通过率 + B→C→D 依赖图。fine_checks 由 `extract_with_fine_rule`（`wp_fine_rule_engine.py` 读 Excel 文件 + `_run_audit_checks` 判定）产生，写入点仅两处：`POST .../fine-extract` 与 OnlyOffice WOPI 保存回调（`wopi_service.py`）。QC-27/QC-28（`qc_engine.py`）把 blocking/warning 级 fine_check 接入提交门禁。

用户希望把「审计检查」用作**完成复核阶段的最后一次检查（复核收口 gate）**。本会话复盘（已读码确认，非推测）发现当前实现作为该定位存在实质缺口：

- **数据陈旧且覆盖不到主体成果**：summary 端点只读缓存、从不重算；`fine-extract` 前端**几乎无 UI 触发入口**；缓存另一写入点是 OnlyOffice WOPI，但 D~N 全部专属组件 + Univer 底稿的数据存 `checklist_responses`、**不走 WOPI** → 这些底稿的 fine_checks 基本永远为空或陈旧。仪表盘对着 Excel 旧快照检查，看不到审计师在专属组件里编制的最新审定数/调整分录/披露。
- **大量检查判定为 pending（`None`）→ 通过率虚高**：`_check_aging`（CHK-12/13/14）全返 `None`、`_check_reconciliation`/`_check_confirmation` 多为 `None`、`_check_completeness` 多数 `None`、`_check_balance` 的 CHK-02 `None`、`_check_sheet_filled` 用「填了 >50% 就算通过」的弱判定。通过率 = `passed / total`，分母含大量从未真正判定的项 → 数字不代表证据充分性，作为复核 gate 会给出误导性「绿灯」。
- **与平台已有的强校验体系割裂**：平台已有更权威、更新鲜的运行时校验源——审定表 `adjustmentReconcile`（审定↔集中登记）、`tbReconcile`（审定↔TB）、`useReportCrossCheck`（报表恒等式）、各 `useXCrossSheet`（审定↔明细勾稽）、`NoteValidationEngine`（附注校验）、QC 28 条、未更正错报汇总、AI 复核 findings（`cycle_review_context`）。fine_checks 另起炉灶读 Excel，与这些真源口径可能不一致，且这些真源的结果**未汇聚进「审计检查仪表盘」**。
- **缺可执行的收口动作**：检查项只读展示（✓/✗/—），点击不能跳转定位到出问题的底稿；无导出（复核留痕）；无「复核人已确认/签认」闭环；未通过项无法指派整改或推 A13 错报。
- **展示细节**：依赖图循环列表硬编码 `['D','E','F','G','H','I','J','K','L','N']` 与 `CYCLE_NAMES` 均缺 M 权益循环；无按 severity/未通过筛选；未通过项未置顶；不显示数据新鲜度。

本功能把「审计检查」从「精细化提取快照旁路展示」升级为「**反映最新编制成果、聚合平台运行时真源、可收口的复核检查面板**」，作为完成复核的最后一次检查。

**核心设计约束（据本会话调研，交由 design 定实现细节）**：

- **不重写各底稿的运行时校验逻辑**：`adjustmentReconcile`/`tbReconcile`/`useReportCrossCheck`/`useXCrossSheet`/`NoteValidationEngine`/QC/未更正错报 等已存在，本功能**聚合与暴露**这些真源的判定结果，不新造第二套判定口径。
- **不改各底稿的数据存储与编制流程**；不改 fine-extract 的既有语义（保留对 Excel/OnlyOffice 底稿的适用性）。
- **数据新鲜度必须可见且可主动刷新**：面板要显示每张底稿检查结果的时间戳与陈旧标记，并提供主动重算入口。
- **通过率口径必须区分「已判定」与「未覆盖/待验证」**，`None`（pending）不得计入通过分母冒充绿灯。
- **权限**沿用项目级访问控制，不放宽；写入型收口动作（签认/推错报/触发重算）按对应角色门控。

## Glossary

- **审计检查面板 (Audit_Check_Panel)**：`AuditCheckDashboard.vue`，项目概览「审计检查」入口打开的复核检查界面。
- **精细化检查 (Fine_Check)**：`extract_with_fine_rule` + `_run_audit_checks` 从底稿产生、缓存于 `WorkingPaper.parsed_data.fine_checks` 的检查项，每项含 `code/type/severity/description/passed/message`。
- **检查汇总接口 (Check_Summary_Endpoint)**：`GET /api/projects/{pid}/fine-checks/summary`，批量读取项目所有底稿的 fine_checks 缓存。
- **精细化提取 (Fine_Extract)**：`POST /api/projects/{pid}/workpapers/{wp_id}/fine-extract`，读底稿文件按 `wp_fine_rules/{code}.json` 规则提取并重算检查，写回缓存。
- **运行时校验源 (Runtime_Check_Source)**：底稿编制态已存在的权威校验，含审定↔集中登记（`adjustmentReconcile`）、审定↔TB（`tbReconcile`）、报表恒等式（`useReportCrossCheck`）、审定↔明细（`useXCrossSheet`）、附注校验（`NoteValidationEngine`）、QC 28 条、未更正错报汇总、AI 复核 findings（`cycle_review_context`）。
- **专属组件底稿 (Dedicated_Workpaper)**：D~N 等以专属 Vue 组件渲染、数据存 `checklist_responses`、不走 OnlyOffice WOPI 的底稿。
- **检查项判定 (Check_Verdict)**：单个检查的三态结果——`passed=true`（通过）/`passed=false`（未通过）/`passed=null`（待验证/未覆盖，pending）。
- **已判定检查 (Decided_Check)**：`passed` 非 `null` 的检查项（通过或未通过）。
- **未覆盖检查 (Uncovered_Check)**：`passed=null` 的检查项。
- **数据新鲜度 (Freshness)**：某底稿检查结果对应的 `fine_extracted_at`（或运行时真源的采集时间）与是否陈旧（底稿在检查后又被修改）的标记。
- **阻断项 (Blocking_Finding)**：`severity=blocking` 且 `passed=false` 的检查项。
- **复核签认 (Review_Sign_Off)**：复核人对审计检查面板结果的确认动作与留痕。
- **循环 (Cycle)**：审计业务循环分类（A~N/S），面板按循环分组。

## Requirements

### Requirement 1: 数据新鲜度可见

**User Story:** 作为复核人，我希望看到每张底稿检查结果的采集时间与是否陈旧，以便判断这次「最后检查」依据的是不是最新编制成果。

#### Acceptance Criteria

1. THE 审计检查面板 SHALL 为每张有检查结果的底稿显示其检查结果采集时间（`fine_extracted_at` 或运行时真源采集时间）。
2. WHERE 底稿在其检查结果采集时间之后又被修改（`WorkingPaper.updated_at` 晚于采集时间），THE 审计检查面板 SHALL 将该底稿标记为「检查结果已过期」。
3. WHERE 某底稿从未产生过检查结果（无缓存且无运行时真源结果），THE 审计检查面板 SHALL 将其标记为「未检查」，而非隐藏或计入通过率。
4. THE 检查汇总接口 SHALL 在返回中包含每张底稿的检查结果采集时间与底稿最近修改时间，供前端判定陈旧。

### Requirement 2: 主动重算入口

**User Story:** 作为复核人，我希望能一键触发重新检查，以便在复核前把陈旧/未检查的底稿刷新到最新。

#### Acceptance Criteria

1. THE 审计检查面板 SHALL 提供「重新检查全部」操作，触发对本项目底稿的检查结果重算。
2. THE 审计检查面板 SHALL 提供对单张底稿的「重新检查」操作。
3. WHILE 重算进行中，THE 审计检查面板 SHALL 显示进行中状态并禁用重复触发，重算完成后自动刷新展示。
4. WHERE 某底稿因文件缺失或规则缺失无法重算，THE 审计检查面板 SHALL 如实标记该底稿重算失败并给出原因，不阻断其余底稿重算。
5. WHERE 用户不具备触发重算所需权限，THE 审计检查面板 SHALL 隐藏或禁用重算入口。

### Requirement 3: 覆盖专属组件底稿的检查

**User Story:** 作为复核人，我希望审计检查反映 D~N 专属组件底稿的最新编制成果，以便这次检查不漏掉主体工作。

#### Acceptance Criteria

1. THE 审计检查面板 SHALL 反映专属组件底稿（数据存 `checklist_responses`、不走 OnlyOffice WOPI）的检查结果，而不仅是 Excel/OnlyOffice 文件快照。
2. THE 检查汇总接口 SHALL 对专属组件底稿基于其最新持久化数据（`checklist_responses`）或运行时真源产出检查结果，不得仅依赖可能陈旧的 `parsed_data.fine_checks` Excel 快照。
3. WHERE 某专属组件底稿存在对应的运行时校验源结果，THE 审计检查面板 SHALL 将其纳入该底稿的检查项集合。
4. THE 本功能 SHALL NOT 改变各底稿的数据存储结构或编制流程。

### Requirement 4: 聚合平台运行时校验源

**User Story:** 作为复核人，我希望审计检查汇总平台已有的强校验结果（审定↔TB、审定↔明细、报表恒等式、附注校验、未更正错报等），以便一处看全所有关键勾稽是否通过。

#### Acceptance Criteria

1. THE 审计检查面板 SHALL 聚合并展示运行时校验源的判定结果，作为检查项与精细化检查并列。
2. THE 本功能 SHALL 复用既有运行时校验源的判定口径，SHALL NOT 为同一勾稽新造第二套判定逻辑。
3. WHERE 运行时校验源与精细化检查对同一勾稽（如审定↔TB）均产出结果，THE 审计检查面板 SHALL 以单一口径呈现，避免同一勾稽出现互相矛盾的两条检查项。
4. THE 每个聚合来的检查项 SHALL 标注其来源（如「审定表勾稽」「报表恒等式」「附注校验」「精细化规则」「QC」「未更正错报」）。
5. WHERE 某运行时校验源在当前项目不适用或无数据，THE 审计检查面板 SHALL 将相关检查项标记为未覆盖，而非误判为通过。

### Requirement 5: 通过率口径区分已判定与未覆盖

**User Story:** 作为复核人，我希望通过率只反映真正判定过的检查，以便不被「待验证」项拉高的虚假绿灯误导。

#### Acceptance Criteria

1. THE 审计检查面板 SHALL 分别统计已判定检查数、未通过检查数、未覆盖检查数。
2. THE 审计检查面板 SHALL 以「已通过 / 已判定」为通过率分母口径计算通过率，SHALL NOT 将未覆盖检查（`passed=null`）计入通过分母。
3. THE 审计检查面板 SHALL 单独、显式展示未覆盖检查的数量与占比，使复核人明确知道有多少检查尚未真正验证。
4. WHERE 存在未覆盖检查，THE 审计检查面板 SHALL NOT 呈现「全部通过」等暗示证据充分的整体结论。

### Requirement 6: 未通过项定位跳转

**User Story:** 作为复核人，我希望点击未通过的检查项能跳到对应底稿，以便快速核查与整改。

#### Acceptance Criteria

1. WHEN 复核人点击某检查项，THE 审计检查面板 SHALL 导航到该检查项对应的底稿（可定位到相关 sheet）。
2. WHERE 某检查项无法解析出可跳转的底稿目标，THE 审计检查面板 SHALL 保持该项不可跳转并给出提示，不得静默失败或导航到错误底稿。
3. THE 审计检查面板 SHALL 支持按未通过/未覆盖/阻断级筛选，并默认将未通过与阻断项置顶展示。

### Requirement 7: 检查结果导出留痕

**User Story:** 作为复核人，我希望能导出审计检查结果，以便作为复核工作的留痕证据。

#### Acceptance Criteria

1. THE 审计检查面板 SHALL 提供导出当前项目审计检查结果的操作。
2. THE 导出内容 SHALL 包含每张底稿的检查项（编号、描述、来源、severity、判定、消息）、汇总统计（已判定/未通过/未覆盖/通过率）与导出时间。
3. THE 导出文件名 SHALL 采用可读中文名并正确处理中文编码（RFC5987）。
4. WHERE 用户不具备导出权限，THE 审计检查面板 SHALL 隐藏或禁用导出入口。

### Requirement 8: 复核签认闭环

**User Story:** 作为复核人，我希望能对审计检查结果做确认签认并留痕，以便记录「最后一次检查」已复核。

#### Acceptance Criteria

1. THE 审计检查面板 SHALL 允许具备复核权限的用户对本次审计检查结果执行复核签认。
2. WHEN 复核人执行签认，THE 本功能 SHALL 记录签认人、签认时间与签认时的检查汇总快照（已判定/未通过/未覆盖/通过率）。
3. WHERE 存在阻断项（`severity=blocking` 且 `passed=false`）未处理，THE 审计检查面板 SHALL 在签认前明确提示存在未处理阻断项。
4. WHERE 用户不具备复核签认权限，THE 审计检查面板 SHALL 隐藏或禁用签认入口。

### Requirement 9: 循环覆盖与展示完整性

**User Story:** 作为复核人，我希望所有业务循环（含权益循环 M）都被正确分组展示，以便检查不遗漏循环。

#### Acceptance Criteria

1. THE 审计检查面板 SHALL 覆盖全部业务循环分组，包含权益循环 M，不得因硬编码循环列表而遗漏。
2. THE 依赖关系图循环选择 SHALL 与实际存在检查数据的循环一致，不得硬编码缺失循环。
3. WHERE 某循环无任何检查数据，THE 审计检查面板 SHALL 明确显示该循环暂无检查数据，而非静默省略导致复核人误以为该循环无需检查。

### Requirement 10: 权限与零回归

**User Story:** 作为平台维护者，我要求本功能沿用现有访问控制且不破坏既有 fine-extract/QC 行为，以便安全上线。

#### Acceptance Criteria

1. THE 检查汇总接口与重算/导出/签认接口 SHALL 沿用项目级访问控制，只读操作按只读权限、写入型收口动作按对应角色权限校验，SHALL NOT 放宽既有授权。
2. THE 本功能 SHALL NOT 改变 `fine-extract` 对 Excel/OnlyOffice 底稿的既有提取与检查语义。
3. THE 本功能 SHALL NOT 改变 QC-27/QC-28 既有的提交门禁行为。
4. WHERE 本功能新增聚合/重算逻辑，THE 既有 fine_checks 缓存读取路径 SHALL 保持向后兼容（无运行时真源时退回读缓存展示）。
