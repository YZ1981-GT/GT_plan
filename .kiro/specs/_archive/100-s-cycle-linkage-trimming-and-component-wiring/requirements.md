# Requirements Document

# S 类底稿联动、裁剪与组件接线 — 需求

> **修订性质**：本次只收敛现有 `s-cycle-linkage-trimming-and-component-wiring` spec，不新建 spec，不把 HEAD 中 FEAT-001~003 或任何 `[x]` 记录当作完成证据。实施前后只允许按本三件套验收；本次修订不修改生产代码、测试代码或数据库。
>
> **证据**：`.agents/tasks/s-cycle-investigation/findings.md`、`formula-impact-analysis.md`、`s-cycle-spec-review.md`、`.agents/tasks/s-cycle-p0-impl-2026-10-25/plan.md`、`2026-10-25-232000-review.md`。

## Introduction

S32~S35 bundle、S3/S4/S5/S6/S12/S13/S14/S15/S20/S21 专属组件已存在，但 S1/S8/S9/S10/S17 的 12 个 `s-checklist` componentType 尚未证明经过后端真实渲染分发；`applicable_when` 也尚未形成生成链与 render-config 的共同判定。P0 收敛目标是打通适用性、后端 dispatch、真实保存合约、S17 前置数据和 IPO 判定边界；P1/P2 继续保留只读关联、S34 公式和风险/委派目标。

## Glossary

- **S_Cycle_Workpaper**：S1~S35 专项、IPO、再融资底稿及 bundle 子底稿。
- **Applicability_Predicate**：后端共享的 `business_category_flags` 与 `applicable_when_hit`，生成链和 render-config 共用。
- **Business_Category_Flags**：由 `business_category`、`template_type` 产生的 `biz_ipo`、`biz_listed`、`biz_neeq`、`biz_refinancing`。
- **Render_Config**：`GET /workpapers/{id}/render-config` 的顶层渲染配置。
- **Renderer_Dispatch**：后端 `RENDERER_DISPATCH` 到真实渲染策略的映射。
- **S_Checklist_Component**：`frontend/src/components/workpaper/s-checklist/` 中的 12 个专属类型。
- **BatchSaveRequest**：`checklist_responses.py` 的 `project_id + items[]` 保存合约，item 含 `item_id`、`conclusion`、`remark`。
- **S17_Classification**：`workpaper_sheet_classification` 中用于 S17 sheet 的分类记录；当前实证为 0 行。
- **S_Resolver**：S 类只读自动取数 resolver；目标 14 个（既有 11 个 + 本 spec 新增 3 个），完整清单见 design §4.1。

## 实施前约束

1. 映射源文件是 `backend/data/wp_account_mapping.json`，不是 `backend/app/data/`；S34 `hasSubTable` 必须包含 S34-3，完整父码共 12 个。
2. `Project.business_category` 当前是 `String(10)`，`refinancing` 为 11 字符。实施前必须作出“批准加宽迁移”或“批准可持久化的短 canonical code”二选一；在决策前不得截断、替换或声称再融资适用性已验收。
3. S17 分类为 0 行时只能生成模板驱动的 no-write dry-run；未经用户明确批准不得写共享数据库。浏览器写入只使用【测试】项目。
4. S 类不进入 `formula_push_rules.json`（当前 S 规则为 0）；S 类只读取 resolver/本地公式，不绕过发布门写 `trial_balance`。

## Requirements
### Requirement 1: R-P0-1 — 统一 applicable_when 生成与渲染适用性

**User Story:** 作为项目负责人，我希望 S32~S35 按项目类型裁剪，避免普通年审项目生成或打开不适用底稿。

#### Acceptance Criteria

1. THE `business_category_flags` SHALL 对大小写和空值归一化，并返回 `biz_ipo`、`biz_listed`、`biz_neeq`、`biz_refinancing`；`biz_listed` SHALL 在 `template_type == 'listed'` 时为 true，即使分类为空或为 `C`。
2. WHEN `applicable_when` 为字典，THE `applicable_when_hit` SHALL 遍历所有支持键；同一字典内任一键的任一值命中即返回 true，`business_category` 使用 `biz_` 前缀，`industry` 使用 `ind_` 前缀。
3. WHEN `key_filter` 被提供，THE `applicable_when_hit` SHALL 只计算过滤键；未提供时 SHALL 保留所有支持键的通用遍历能力，并对无对应 flag 的键返回未命中。
4. WHEN 工作稿生成链评估映射，THE `Workpaper_Generation_Chain` SHALL 调用上述同一 predicate；IPO 项目生成 S32~S34，普通年审 `C` 或空分类不自动生成 S32~S35，`template_type='listed'` 生成 S32~S34，再融资按已批准的存储决策评估 S35。
5. WHEN `Render_Config` 返回受 `business_category` 限制的 S 底稿，THE `Render_Config_Endpoint` SHALL 在响应顶层返回 `applicable_when` 与布尔 `not_applicable`；`not_applicable` SHALL 使用同一后端 predicate，并考虑 `template_type`。
6. WHEN `GtWpRenderer` 收到顶层 `not_applicable=true`，THE `GtWpRenderer` SHALL 对 bundle 与 `a-program-console` 显示中文“不适用”覆盖层；值为 false 或缺失时 SHALL 不显示。THE `GtWpRenderer` SHALL 只消费该顶层布尔值，不读取不存在的 `project_context`，不复制后端判定。
7. THE predicate/render-config tests SHALL 覆盖 IPO、普通年审、`template_type='listed'`、多键 OR、`key_filter`、bundle 父码聚合与顶层字段；THE GtWpRenderer tests SHALL 覆盖 bundle 和通用组件两条路径。

### Requirement 2: R-P0-2 — 前端适用性路径一致

**User Story:** 作为审计员，我希望程序表和 bundle 对同一项目类型显示一致的适用性结果。

#### Acceptance Criteria

1. WHEN `useAProgramData` 收到字符串适用性声明，THE `useAProgramData` SHALL 保留既有 `consolidated` 行为。
2. WHEN `useAProgramData` 收到 `business_category` 字典声明，THE `useAProgramData` SHALL 使用核心 `isIpoProject(biz, allowedCats?)` 计算前端兼容路径；该路径不得新增第三套 IPO 定义。
3. WHEN bundle 或普通组件进入 `GtWpRenderer`，THE `GtWpRenderer` SHALL 以 `Render_Config.not_applicable` 为唯一覆盖层输入。

### Requirement 3: R-P0-3 — IPO 可见性收敛为方案 B

**User Story:** 作为维护人员，我希望 IPO 判定统一，同时保留 D4 舞弊风险和 F2 历史兼容行为。

#### Acceptance Criteria

1. THE 核心工具 SHALL 暴露 `isIpoProject(businessCategory, allowedCats?)`；核心签名 SHALL 保持字符串参数，不改成上下文对象。
2. WHEN D4 判断 IPO/舞弊分组，THE D4 consumer SHALL 通过 `allowedCats` 包含 `fraud_risk` 调用核心工具。
3. WHEN F2 判断特殊表，THE F2 wrapper SHALL 保留 `project_type → template_type → 中文 IPO_CATEGORIES` 三级瀑布，并在第一级复用核心工具。
4. THE 前端仓库 SHALL 只有核心工具和 F2 wrapper 两个 IPO 判定来源；D4 不得保留独立 wrapper；D4/F2 tests 与 grep SHALL 证明该约束。
### Requirement 4: R-P0-4 — 12 个 s-checklist componentType 真实接线

**User Story:** 作为审计员，我希望已有 S 类检查表经过后端真实渲染分发，而不是只在 overrides 或前端 registry 中登记。

#### Acceptance Criteria

1. WHEN render-config 返回下列 12 个类型时，THE `Renderer_Dispatch` SHALL 经 `_s_checklist_sheets.py` 返回专属 payload：`s1-regulation-record`、`s8-adjudication`、`s9-adjudication`、`s9-internal-control`、`s9-legal-regulations`、`s9-program-description`、`s10-adjudication`、`s10-internal-control`、`s10-environmental-regulations`、`s17-nonrecurring-detail`、`s17-reconciliation`、`s17-tax-impact`。
2. THE S-checklist strategy SHALL 返回 `component_type`、精确 sheet identity 和组件所需 payload；strategy SHALL 不返回 `cells`，render-config SHALL 不把这些类型改写为 `onlyoffice-sheet` 或通用网格 fallback。Contract test SHALL assert：策略输出 dict 无 `cells` 键，且 render-config 响应中 12 个类型的 componentType 不属于 `{'onlyoffice-sheet', 'noRendererGridFallback', 'audit-sheet'}`。
3. THE frontend registry、overrides、backend valid-type/whitelist 与 `RENDERER_DISPATCH` SHALL 具有相同 12-type 集合；contract tests SHALL 逐类型检查集合、payload 和无 fallback。
4. WHEN S1/S8/S9/S10/S17 目标 sheet 被打开，THE renderer SHALL 选择对应 S-checklist 组件；S17 的 detail/reconciliation/tax mapping SHALL 遵循 R-P0-6。

### Requirement 5: R-P0-5 — S 段侧边栏路由

**User Story:** 作为审计员，我希望有独立程序表 sheet 的 S 底稿使用正确侧边栏状态，并避免短前缀误捕获。

#### Acceptance Criteria

1. WHEN `resolveProcedureSheetKey` 收到 S20/S17/S15/S14/S13/S12/S10/S8/S1，THE resolver SHALL 分别返回 `s20a/s17a/s15a/s14a/s13a/s12a/s10a/s8a/s1a`。
2. WHEN resolver 收到 S16 或 S11，THE resolver SHALL 返回 `e1a`，且结果不被 S1 规则覆盖。
3. WHEN resolver 收到 S2/S9/S21/S32/S34，THE resolver SHALL 返回既定 `e1a` fallback；路由测试 SHALL 覆盖各前缀与既有 D~N 路由回归。

### Requirement 6: R-P0-6 — 真实保存合约与 S17 前置闸门

**User Story:** 作为审计员，我希望检查表保存、只读和模板映射符合真实后端合约，避免 422 或保存到错误 sheet。

#### Acceptance Criteria

1. WHEN 九个可写 S-checklist 组件保存数据，THE component SHALL 发送 `project_id` 和 `items: [{item_id, conclusion, remark}]`；component SHALL 不发送旧 `{sheet_name, data}` 体。
2. WHILE component 收到 `readonly=true`，THE component SHALL 禁用写控件且 SHALL 不发 batch-save 请求。
3. WHEN component 加载数据，THE component SHALL 按 `componentType` 与 item identity 选择数据；S17 detail SHALL 按 `sheetName` 在 S17-1/S17-2/S17-3 视图间切换，不使用模糊 sheet-name substring 路由。
4. IF `/api/s-special/*` 导入导出端点不存在，THEN S1/S17 SHALL 显示并禁用“导入导出（开发中）”，且 SHALL 不调用这些端点；端点实现不属于本 spec 验收。
5. THE S17 mapping SHALL 为 `S17-1/S17-2/S17-3 → s17-nonrecurring-detail`、`S17-11 → s17-reconciliation`、`S17-21 → s17-tax-impact`。
6. IF S17 classification 行数为 0，THEN implementation SHALL 生成模板驱动的 no-write dry-run，记录候选行和分类，不写共享数据库，直到用户明确批准；未批准时 S17 运行时验收保持阻塞。

### Requirement 7: R-P1-1 — S 类关联声明与只读 resolver

**User Story:** 作为负责人，我希望关键 S 底稿能读取关联数值并显示既有关联入口，同时不绕过 TB 发布门。

#### Acceptance Criteria

1. WHEN mapping 被加载，THE system SHALL expose S20→D4、S15→D4/M2、S17→K12/K13、S6→K1、S33-5→D4/F5 的 `linked_workpapers`，并复用既有链接消费方。
2. THE resolver registry SHALL retain 11 existing S resolvers and add `s6_related_party_summary`、`s33_5_revenue_cost_check`、`s14_estimate_related_data`；all 14 SHALL use `async (db, project_id, year, **kwargs) -> dict` and read-only behavior。
3. WHEN a new resolver is registered，THE corresponding render-schema or generic program-console binding SHALL reference it；resolver SHALL not write `trial_balance` or `tb_balance`。

### Requirement 8: R-P1-2 — S34 子表公式完整化

**User Story:** 作为 IPO 项目审计员，我希望所有有子表的 S34 模板按模板定义计算。

#### Acceptance Criteria

1. THE S34 formula metadata SHALL cover exactly 12 parents: S34-2、S34-3、S34-4、S34-8、S34-9、S34-11、S34-16、S34-18、S34-20、S34-25、S34-30、S34-34。
2. WHEN supported subtable receives valid grid data，THE runtime formula engine SHALL calculate its defined ratio/sum/threshold values。
3. THE runtime engine SHALL remain separate from `formula_settings` definition governance；S 类 SHALL remain absent from `formula_push_rules.json` and SHALL not participate in formula-push writeback。

### Requirement 9: R-P1-3 — 跨引用只读数值

**User Story:** 作为审计人员，我希望跨引用芯片显示只读的审定数和试算表数值，以便核对关联信息时不修改目标底稿或试算表数据。

#### Acceptance Criteria

1. WHEN S34/S35 external cross-reference chip is hovered，THE chip SHALL request `cycle_audited_amounts` and display read-only audited/TB values。
2. THE cross-reference display SHALL not mutate target workpaper or trial-balance data。

### Requirement 10: R-P2-1 — 风险导向与委派展示

**User Story:** 作为项目负责人，我希望 S 检查表根据风险结论和底稿委派展示推荐状态及负责人，以便按风险导向安排审计工作。

#### Acceptance Criteria

1. WHEN `risk_assessments` contains a mapped high-fraud or S-related conclusion，THE S checklist SHALL report `recommended` or `applicable` according to the documented mapping；the value domain SHALL be verified with `SELECT DISTINCT account_or_cycle ... LIMIT 50`。风险数据的代码真源路径为 `b50_risk_reader.py`（从 B50 checklist 的 `checklist_responses` 中按 `item_id LIKE 'B50-T3-%'` 读取循环值与风险矩阵），消费方包括 `b60_data_pull`、`auto_data_resolvers/_cycle.py`、`_control_b.py` 及 `a176_agenda_prefill.py`。
2. WHEN risk exists without a workpaper，THE checklist SHALL report `recommended`；when risk or an existing workpaper is present，THE checklist SHALL report `applicable`；when neither is present，THE checklist SHALL report `not_applicable`。
3. WHEN a bundle tab has `assigned_to`，THE bundle UI SHALL resolve `users.id → staff_members.user_id → staff_members.name` and fall back to `users.username` when staff data is absent。

## Acceptance Standard

本 spec 只能在实现阶段同时满足以下条件后完成：共享 predicate 在生成链和 render-config 复用且场景测试通过；render-config 顶层 `not_applicable` 驱动 overlay；12 个类型经过 backend dispatch 且无 `cells`/`onlyoffice-sheet` fallback；9 个组件符合 `items[]` 且 readonly/加载测试通过；S17 映射正确并有 no-write dry-run/批准证据；方案 B 的 D4/F2 tests 与 grep 闭合；11+3 resolver、12 张 S34 子表和 P1/P2 均有测试或明确环境阻塞。当前三件套修订不得把任何任务勾选完成，也不得把 capability manifest 预存失败或未批准的 S17 写库当作通过。

## Scope Exclusions

- 不实现 `/api/s-special/*` 导入导出端点；只禁用入口。
- 不把 S 子底稿全部拆成独立顶层 bundle component；不迁移 S17 `.xls` 格式。
- 不新增 S 类 formula-push 规则，不向 `trial_balance` 回写，不绕过显式发布门。
- 不在本 spec 内自动执行 `String(10)` 迁移或写共享 `workpaper_sheet_classification`；两者都需前置决策/批准。
- 不把循环级 `assignment_service` 改成底稿级委派；本轮只展示 bundle tab 负责人。
