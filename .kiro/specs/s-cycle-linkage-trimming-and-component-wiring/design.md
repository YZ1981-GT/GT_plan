# S 类底稿联动、裁剪与组件接线 — 设计

> 本文件描述后续实施目标，不表示代码已修好。FEAT-001~003、已有 registry/override 改动和评审文档中的“已完成”均须重新按本设计验证；本次 spec 修订只改三件套。

## Overview

本设计把 S 类底稿的适用性裁剪、真实渲染分发、组件保存、只读联动和风险展示收敛为可实施的 P0/P1/P2 方案。以下内容仍是目标设计与验收边界，不代表生产代码、测试代码或共享数据已经修好。

### §0 现状与收敛边界

| 事实 | 当前证据 | 对本设计的影响 |
|---|---|---|
| `applicable_when` 已写入映射但生成/render-config 未形成共同判定 | `wp_generation_matching.py` 无 dict 分支；评审 D2 | 新增后端共享 `business_category_flags`/`applicable_when_hit`，两条链共用 |
| 映射源在 `backend/data/wp_account_mapping.json` | P0 plan B | 禁止再写 `backend/app/data` 路径 |
| render-config 顶层没有 `project_context` | P0 review | 后端计算顶层 `not_applicable`；GtWpRenderer 只读该布尔值 |
| 12 个 S-checklist 类型只有前端/override 证据 | findings、D3 | 新建 `_s_checklist_sheets.py` 并注册 `RENDERER_DISPATCH` |
| 9 个组件发送旧 `{sheet_name,data}`，真实合约要求 `items[]` | P0 plan D4 | 按 `BatchSaveRequest` 统一保存体并补 readonly/identity 测试 |
| S17 `workpaper_sheet_classification` 为 0 行；模板是 `.xls` | P0 plan D6 | 只做模板驱动 dry-run，未批准不写共享库 |
| 既有 S resolver 为 11 个 | spec review G7 | 新增 3 个后目标为 14 个，不把总 resolver 数误写成 10 |
| S34 `hasSubTable` 父码共 12 个，包含 S34-3 | findings、spec review NIT-1 | 公式任务和验收均列出 S34-3 |
| `Project.business_category` 为 `String(10)`，`refinancing` 为 11 字符 | P0 plan B/D2 | 加宽迁移或短 canonical code 必须由用户/环境先决策 |

#### §0.1 非目标与前置决策

- `/api/s-special/*` 当前不存在；S1/S17 导入导出入口标记“导入导出（开发中）”并禁用，不把端点实现列为完成条件。
- S17 classification dry-run 的候选行从 `.xls` 模板实读；dry-run 及审批前均禁止写共享数据库。
- 若选择加宽 `String(10)`，迁移另行批准并遵守运行时迁移规范；若选择 canonical code，须先给出持久化值与映射契约。两者未决时，`refinancing` 的真实 PG/render 验收阻塞，但内存 predicate 单测仍可覆盖 flag 语义。
- S34 前端公式引擎是运行时计算层；`formula_settings` 是后端公式定义治理层，两者正交。`formula_push_rules.json` 当前 S 规则为 0，S 类不进入 formula-push 写回。

## Architecture

架构遵循“声明一次、生成与渲染共用、前端只消费结果、只读联动不越过发布门”的边界：

- **P0 适用性流**：从 `backend/data/wp_account_mapping.json` 读取声明，经共享 `business_category_flags`/`applicable_when_hit` 同时驱动生成链和 render-config；render-config 输出顶层 `not_applicable`，前端覆盖层只消费该结果。
- **P1 联动流**：`linked_workpapers` 解析关联关系，14 个只读 resolver 按 render-schema/程序表绑定提供数据；S34 由 `useS34FormulaEngine.ts` 在前端本地计算子表结果，既不写目标底稿/TB，也不进入 `formula_push`。
- **P2 风险流**：读取风险结论和 bundle tab 委派，按四象限生成 `recommended`/`applicable`/`not_applicable` 与负责人展示，缺 staff 时回退 username，保持只读。

具体接口、集合和保存体分别在后续 Components and Interfaces 与 Data Models 章节固定。

### §1 P0 适用性与 IPO 判定

#### §1.1 共享后端 predicate

目标文件：`backend/app/services/wp_generation_matching.py`、`chain_orchestrator.py`、`wp_classification_service.py`、`wp_render_config.py`。

1. 新增可复用 `business_category_flags(business_category, template_type)`：统一小写/空值，生成四个 `biz_` flag；`biz_listed = 'listed' in category or template_type == 'listed'`。生成链 SELECT 必须带 `Project.business_category`，并把 `template_type` 传给该函数；不要在两个调用方各写一份布尔表达式。
2. 新增 `applicable_when_hit(applicable_when, flags, *, key_filter=None)`：字典键之间 OR、值之间 OR；`business_category → biz_`，`industry → ind_`，未知键只按约定前缀查找；`key_filter` 存在时只计算所选键。`match_workpapers` 的第四路径直接调用它。
3. `_WP_APPLICABLE_WHEN` 从 `backend/data/wp_account_mapping.json` 加载。bundle 父码 S32/S33/S34/S35 若自身无声明，则对子码的 `business_category` 值取并集，形成父码声明；不得把 `wp_code_overrides.json` 当适用性来源。
4. render-config 使用同一 `_WP_APPLICABLE_WHEN` 和 predicate。对有 `business_category` 限制的 wp_code，按当前项目分类与 `template_type` 计算 `not_applicable`；行业字段没有可用 `Project.industry` 时不凭空隐藏行业条目。响应顶层至少包含 `applicable_when` 与 `not_applicable`，后续 sheet payload 不改变这两个字段。
5. 测试采用真实 mapping 文件加纯函数夹具：`('IPO','soe')` 命中 S32~S34、`('C','soe')` 不命中 S32~S35、`(None,'listed')` 命中 S32~S34；另测多键 OR、key filter、bundle 聚合。`refinancing` 的 PG 场景必须在 String(10) 决策后再验收。

#### §1.2 Render_Config 与 GtWpRenderer

render-config 负责业务适用性判定，前端不重新推导。`GtWpRenderer` 的唯一门控是：

```ts
const isWpNotApplicable = computed(
  () => renderConfig.value?.not_applicable === true,
)
```

模板对 `s34-ipo-bundle` 和 `a-program-console` 都显示中文“不适用”覆盖层；false/缺失不显示。实现不得读取 `renderConfig.project_context`、sheet 内偶然存在的 `html_data.project_context`，也不得复制 `isIpoProject` 逻辑。`useAProgramData` 的旧 `consolidated` 分支保留；其兼容 dict 分支可以调用核心工具，但不改变 GtWpRenderer 的单一输入。

#### §1.3 IPO 方案 B

前端核心工具固定为 `isIpoProject(businessCategory: string, allowedCats?: string[])`，默认 `IPO_BIZ_KEYWORDS = ['ipo','listed','neeq','restructuring','refinancing']`；空值返回 false，`allowedCats` 非空时只使用传入集合。

- D4 导出 `D4_IPO_GROUP_CATS = [...IPO_BIZ_KEYWORDS, 'fraud_risk']`，消费方直接调用核心工具，保留 `fraud_risk`。
- F2 导出 `isF2IpoProject(ctx)` wrapper：先用核心工具判断 `ctx.business_category`，再按 `project_type`、`template_type`、中文 `IPO_CATEGORIES` 逐级兼容；composable 对外仍可提供现有 computed 名称。
- D4 不保留 `isIpoGroupVisible` 定义；前端判定定义来源只允许核心工具与 F2 wrapper。测试须同时覆盖 D4 的 fraud_risk、refinancing 和 F2 的中文值/三级顺序，并 grep 定义位置。后端 F2 的中文常量是协议兼容数据，不改变本条“前端定义来源”约束。

## Components and Interfaces

本节固定具体后端/前端文件、`RENDERER_DISPATCH`、组件保存接口、resolver 注册点及路由/模板验证边界；这些是实现接口，不表示当前已经接线。

### §2 P0 S-checklist 后端接线与真实保存

#### §2.1 12-type parity 与 backend dispatch

12-type canonical set 为：

`{s1-regulation-record, s8-adjudication, s9-adjudication, s9-internal-control, s9-legal-regulations, s9-program-description, s10-adjudication, s10-internal-control, s10-environmental-regulations, s17-nonrecurring-detail, s17-reconciliation, s17-tax-impact}`。

新增 `backend/app/routers/wp_render_strategies/_s_checklist_sheets.py`，注册到 `RENDERER_DISPATCH`。策略维护 componentType→item identity：

| componentType | payload source / item identity |
|---|---|
| s1-regulation-record | `S1-1-sheet-data` |
| s8-adjudication | `S8-1-sheet-data` |
| s9-adjudication | `S9-1-sheet-data` |
| s9-internal-control | `S9-2-sheet-data` |
| s9-legal-regulations / s9-program-description | 无保存 item，返回轻量专属 payload |
| s10-adjudication | `S10-1-sheet-data` |
| s10-internal-control | `S10-2-sheet-data` |
| s10-environmental-regulations | 无保存 item，返回轻量专属 payload |
| s17-nonrecurring-detail | 以 S17 detail view 的 item identity 载入，默认 `S17-1-sheet-data` |
| s17-reconciliation | `S17-11-sheet-data` |
| s17-tax-impact | `S17-21-sheet-data` |

策略查询对应 `checklist_responses` 的 `remark`，合并 JSON payload，并返回 `component_type`、精确 `sheet_name` 和专属数据；无行返回轻量 payload；异常在隔离保存点内回滚并返回可诊断的轻量结果。策略任何分支都不返回 `cells`。render-config 的 componentType 命中 dispatch 后，不进入 `onlyoffice-sheet` 或 `noRendererGridFallback`。

Parity gate 比对 4 份集合：overrides、frontend registry、backend valid/whitelist、`RENDERER_DISPATCH`；每个类型至少一条策略契约测试。前端 registry 不是 backend dispatch 的替代物。

#### §2.2 S17 映射、组件保存和 readonly

`wp_code_overrides.json` 的目标映射必须是：

- `S17-1`、`S17-2`、`S17-3` → `s17-nonrecurring-detail`
- `S17-11` → `s17-reconciliation`
- `S17-21` → `s17-tax-impact`

S17 detail 是一个 componentType，按 `sheetName` 在 S17-1/S17-2/S17-3 视图间切换；S17-11/S17-21 走各自独立类型。不要把 S17-11/S17-21 留在 `a-program-console`，也不要把 S17-2/S17-3 错接到 reconciliation/tax。

九个可写组件统一使用：

```ts
{ project_id: props.projectId,
  items: [{ item_id, conclusion: null, remark: JSON.stringify(payload) }] }
```

每个组件将 `readonly?: boolean` 归一为 `computed(() => props.readonly === true)`，所有写控件和保存函数使用该值。加载按 `componentType`/item identity 选择 render-config sheet，不再按 sheet 名 substring 猜测。S1 与 S17 的导入导出按钮显示“导入导出（开发中）”并 disabled；`useSSpecialImportExport` 不作为本 spec 的可用端点证据。

#### §2.3 S17 classification dry-run

当前 S17 为 0 行，原因包含 `.xls` 未被既有 `.xlsx` 扫描。实施时用能读取 `.xls` 的模板通路生成模板派生候选分类（计划约 8 行，最终以 dry-run 输出为准），输出 sheet、class code、来源和冲突；只写文件/报告，不执行 INSERT/UPDATE。用户批准后另行执行共享库写入；未批准则 S17 真实浏览器渲染保持阻塞，不能用空分类假装通过。

### P1/P2 只读组件接口

- 后端 `_s_linkage.py` 注册 3 个新增 resolver，与既有 11 个统一为 `async (db, project_id, year, **kwargs) -> dict`；每个 resolver 必须在 render-schema 或通用程序表取数路径存在绑定，且只读。
- 前端接口包括 `GtWpRenderer.vue` 的顶层 overlay 门控、`useS34FormulaEngine.ts` 的 12 个 S34 parent 计算、`resolveProcedureSheetKey.ts` 的 S 侧边栏 namespace，以及 S-checklist 组件的 `componentType`/item identity 加载和 `BatchSaveRequest` 保存体。
- 外部 chip 只读消费 `cycle_audited_amounts`；P2 bundle tab 只展示 `users → staff_members` 解析结果，不修改目标底稿、TB 或 assignment_service 粒度。

### §3 P0 路由与模板验证

`resolveProcedureSheetKey` 在长前缀优先原则下增加 S20/S17/S15/S14/S13/S12/S10/S8/S1 的专属 key；S16、S11 显式返回 `e1a`，S2/S9/S21/S32/S34 走既定 `e1a`。该函数只为有独立程序表 sheet 的侧边栏状态提供 namespace；S3/S4/S5/S6 虽有顶层专属组件但没有该类独立状态源，不因组件存在而新增 route。路由单测覆盖 S 前缀与 D~N 回归，浏览器验证仅在后端 dispatch 可用后进行。

模板对账以实际文件格式分流：`.xlsx` 用 openpyxl，S17 `.xls` 用对应读取通路；记录 12 个类型的 sheet、列、item identity 和可写字段。S1/S8/S9/S10/S17 的参考/说明 sheet 只返回专属只读 payload，不强行变成可写表格。

## Data Models

本节把实现中需要稳定对齐的输入、响应和持久化契约集中列出；行为细节仍以 Architecture 与 Components and Interfaces 中的边界为准。

### 适用性与 Render_Config 模型

- `business_category_flags(business_category, template_type)` 返回 `biz_ipo`、`biz_listed`、`biz_neeq`、`biz_refinancing` 四个布尔 flag；`template_type='listed'` 必须使 `biz_listed=true`。
- `applicable_when` 是按支持键组织的字典，键和值均为 OR 语义；`business_category` 映射 `biz_`，`industry` 映射 `ind_`，可选 `key_filter` 限制参与计算。
- `Render_Config` 顶层至少包含 `applicable_when` 与布尔 `not_applicable`；前端 overlay 只消费这个顶层布尔值，不依赖不存在的 `project_context`。

### S-checklist、dispatch 与保存模型

- 12-type canonical set 为：`{s1-regulation-record, s8-adjudication, s9-adjudication, s9-internal-control, s9-legal-regulations, s9-program-description, s10-adjudication, s10-internal-control, s10-environmental-regulations, s17-nonrecurring-detail, s17-reconciliation, s17-tax-impact}`。
- `RENDERER_DISPATCH` 返回专属 `component_type`、精确 `sheet_name`/item identity 和 payload；任何类型均不返回 `cells`，也不降级为 `onlyoffice-sheet` 或通用网格。
- `BatchSaveRequest` 为 `{project_id, items[]}`，每个 item 含 `item_id`、`conclusion`、`remark`；旧 `{sheet_name,data}` 不是有效保存模型。
- S17 mapping 固定为 `S17-1/S17-2/S17-3 → s17-nonrecurring-detail`、`S17-11 → s17-reconciliation`、`S17-21 → s17-tax-impact`。

### 联动、公式与风险模型

- `linked_workpapers` 至少包含 S20→D4、S15→D4/M2、S17→K12/K13、S6→K1、S33-5→D4/F5；resolver 总数为既有 11 个加新增 3 个，共 14 个，统一返回 `dict` 且只读。
- S34 formula engine 覆盖 12 个 parent：S34-2、S34-3、S34-4、S34-8、S34-9、S34-11、S34-16、S34-18、S34-20、S34-25、S34-30、S34-34；该运行时模型不并入 `formula_settings`，S 类不进入 `formula_push_rules.json`。
- 风险展示使用“风险/底稿是否存在”的四象限，输出 `recommended`、`applicable` 或 `not_applicable`；负责人关系为 `users.id → staff_members.user_id → staff_members.name`，缺 staff 时回退 `users.username`。

### 持久化决策模型与禁止边界

- `Project.business_category` 当前为 `String(10)`，`refinancing` 的 11 字符持久化方案只能在“批准加宽迁移”或“批准短 canonical code”二选一后确定；决策前不截断、不替换、不声称 PG/render 已验收。
- `workpaper_sheet_classification` 当前 S17 为 0 行时，只能生成模板驱动 no-write dry-run；未获明确批准不得写共享数据库，浏览器写入只使用【测试】项目。
- S 类只读取 resolver/本地公式，不绕过显式发布门写 `trial_balance`；`formula_settings` 定义治理与前端 runtime 计算保持正交。

### §4 P1 只读联动与 S34 公式

#### §4.1 linked_workpapers 与 resolver

在 `backend/data/wp_account_mapping.json` 补 S20→D4、S15→D4/M2、S17→K12/K13、S6→K1、S33-5→D4/F5；实施时 grep 现有消费方，若按 componentType 过滤则扩展白名单而不新造面板。

新增 `_s_linkage.py` 的 3 个 resolver，和既有 11 个一起以 `async (db, project_id, year, **kwargs) -> dict` 注册；分别读取关联方余额、D4/F5 收入成本、估计相关 TB 数据。注册后必须在 render-schema 或通用程序表取数路径有调用绑定，避免“注册成功但无人调用”。所有 resolver 只读。

#### §4.2 S34 formula engine

`useS34FormulaEngine.ts` 逐表覆盖 S34-2、S34-3、S34-4、S34-8、S34-9、S34-11、S34-16、S34-18、S34-20、S34-25、S34-30、S34-34，共 12 个 parent；具体公式列以模板对账为准，复用现有 ratio/sum/threshold factory。该前端 runtime 与 `formula_settings` 的定义治理正交；没有项目级覆盖需求时不迁入 `wp` 域。S 类继续保持 `formula_push_rules.json` 零规则，不接 `formula_push`。

#### §4.3 跨引用

S34/S35 外部 chip 复用 `cycle_audited_amounts` 只读数据源，hover 展示审定/TB 值；内部 tab 仍可导航。任何展示路径不得写目标底稿或 TB。

### §5 P2 风险与委派

S34 checklist 先用 `SELECT DISTINCT account_or_cycle FROM risk_assessments LIMIT 50` 实读值域，再建立高舞弊/S 事项到 `recommended/applicable` 的映射。四象限为“风险+有底稿 applicable、风险+无底稿 recommended、无风险+有底稿 applicable、无风险+无底稿 not_applicable”。bundle tab 负责人沿 `wp_index.assigned_to → users.id → staff_members.user_id → staff_members.name` 读取，缺 staff 时显示 username，不改变 assignment_service 的循环级粒度。

## Delivery Gates and Validation

D1-D8 和验证风险是实现阶段的交付门，不是完成声明；本设计不勾选任何任务。

### §6 D1-D8 收敛门与依赖

D1-D8 是实施收敛标签，不是当前完成状态；任务清单全部保持 `[ ]`。

| 门 | 交付与验收 | 依赖 |
|---|---|---|
| D1 overlay | GtWpRenderer 顶层 `not_applicable`，bundle/通用 true/false/缺失测试 | D2 |
| D2 predicate/render-config | `business_category_flags`、`applicable_when_hit`、生成链/render-config 共用、顶层字段、OR/key-filter/IPO/普通/listed 测试 | §0.1 的 String(10) 决策；映射路径核对 |
| D3 backend dispatch | `_s_checklist_sheets.py`、12 type parity、专属 payload、无 cells/onlyoffice、策略契约测试 | D5；模板/item audit |
| D4 save/readonly | 9 个组件 `items[]`、readonly、componentType identity、S17 detail view、导入导出 disabled | D3；S17 runtime 浏览器另受 D6 阻塞 |
| D5 S17 mapping | 五组 S17 override 精确值与映射测试 | 模板事实已读取 |
| D6 classification dry-run | `.xls` 派生候选分类 no-write、冲突/来源报告、审批闸门 | D5；用户批准是外部决策 |
| D7 D4/F2 | 核心工具、D4 fraud_risk、F2 三级 wrapper、8 个现有例/PBT/grep | 核心工具定义（与 D2 可并行） |
| D8 类型与归因 | 单区域 `vue-tsc` + 注入 `number = string` mutation proof；记录 capability manifest 预存解析失败，既不修也不归因本 spec | D1/D3/D4/D7 前端改动 |

D2 未完成时 D1 不得验收；D3 未完成时 D4 和 12-type 浏览器验收不得验收；D6 未获批准时只能保留 dry-run 阻塞项；D8 的 capability manifest failure 只写验证记录，不得通过增加 allowlist 或修改其他文件消除。

### §7 实施验证与风险

- 后端按真实 contract 测试 predicate、render-config、dispatch、S17 mapping；保存点隔离异常，不把异常吞掉当成功。
- 前端按单区域 tsconfig 验证改动文件，并先注入可诊断类型错误证明检查器真的生效；全量 vue-tsc OOM 时如实记录。
- Playwright 只在 start-dev 已启动且使用【测试】项目时运行；S17 分类未批准不得把“无 sheet”归因于组件已完成。
- 预存 `test_component_capability_contract`/manifest generator 无法解析 `registry/index.ts` 的失败属于既有环境/基线问题，只记录复现证据，不修改 capability 产物、不归因给本 spec。
- 所有任务完成前重新核对 requirements/design/tasks 三件套，禁止以 FEAT JSON、代码 diff 数量或单纯 registry 测试代替端到端证据。

## Correctness Properties

*属性是应在所有有效执行中成立的特征或行为，是把人类可读需求连接到可验证正确性保证的桥梁。*

### Property 1: 业务分类 flag 归一化

For any `business_category` and `template_type` pair, `business_category_flags` SHALL return exactly the four boolean flags `biz_ipo`、`biz_listed`、`biz_neeq`、`biz_refinancing`，并在 `template_type='listed'` 时令 `biz_listed=true`。

**Validates: Requirements 1.1**

### Property 2: 适用性声明与过滤保持 OR 语义

For any valid `applicable_when` dictionary, flags, and optional `key_filter`, `applicable_when_hit` SHALL return true exactly when 任一参与键的任一值命中；提供过滤键时，未参与的键不得改变结果。

**Validates: Requirements 1.2, 1.3**

### Property 3: IPO 核心判定尊重允许集合

For any business-category string and any `allowedCats` value, `isIpoProject` SHALL return false for empty input and SHALL match only the default IPO keywords when `allowedCats` is absent, or only the supplied allowed set when it is present。

**Validates: Requirements 3.1**

### Property 4: S34 公式计算保持定义不变量

For any valid S34 subtable grid accepted by a supported parent, the extracted ratio/sum/threshold results SHALL equal the configured formula evaluation, and recalculating the same grid SHALL not introduce a second write or change the result。

**Validates: Requirements 8.2**

### Property 5: 风险与底稿状态形成唯一四象限

For any combination of risk presence and workpaper presence, the P2 classifier SHALL return exactly one of `recommended`、`applicable`、`not_applicable` according to the documented four-quadrant rule。

**Validates: Requirements 10.2**

## Error Handling

- 空值、大小写差异和未知适用性键由共享 predicate 安全处理；未知键不命中，不因缺少 `Project.industry` 而凭空隐藏行业底稿。
- render-config 必须返回可判定的顶层 `not_applicable`；false 或缺失时前端不显示“不适用”覆盖层。渲染 payload 不得通过异常或缺少数据改写该字段。
- S-checklist 无对应行时返回轻量专属 payload；读取/保存异常须在隔离保存点内回滚并返回可诊断结果，不得吞异常后报告保存成功；任何策略分支均不得返回 `cells`。
- `readonly=true` 时组件不发送 batch-save；S1/S17 导入导出端点不存在时只显示并禁用“导入导出（开发中）”，不得发请求。
- S17 classification 为 0 行时只能保留 no-write dry-run；未获批准不得写共享库。`String(10)` 的加宽迁移或短 canonical code 未决时，`refinancing` 的 PG/render 验收必须保持阻塞，不得截断或伪造通过。
- P1 resolver、S34 公式和跨引用均为只读路径，不得通过异常兜底写入 `trial_balance`、`tb_balance` 或目标底稿；S 类不进入 `formula_push`。

## Testing Strategy

本设计阶段不修改生产代码或测试代码，以下是实施阶段的验证分层；任务仍保持未完成状态。

- **纯函数单元与属性测试**：使用目标语言已有的 Hypothesis/等价属性测试库覆盖 Property 1~5；每个属性使用单个属性测试、至少 100 个 examples，并在测试注释中标注 `Feature: s-cycle-linkage-trimming-and-component-wiring, Property N`。属性测试只覆盖 flags、predicate、IPO 核心工具、公式纯计算和四象限分类，不把数据库/API/文件 I/O 随机化。
- **后端契约/集成测试**：使用真实 mapping 文件和代表性 TestClient/PG 场景验证生成链与 render-config 共用 predicate、顶层字段、12-type parity、`RENDERER_DISPATCH` payload、无 `cells`/fallback、14 个 resolver、S17 mapping 与保存点隔离。S17 先验证 `.xls` dry-run 零写入，批准写入另用【测试】项目；`String(10)` 决策前不验收 refinancing PG 场景。
- **前端单元与静态守卫**：覆盖 GtWpRenderer true/false/缺失三态、D4/F2 IPO 路径、9 个可写组件的 `items[]`/readonly/identity、S17 三视图映射和 procedure key；用 registry/override/backend dispatch 四集合 parity 及 grep/AST 守卫确认没有第三套 IPO 定义或旧保存体。单区域 `vue-tsc` 必须先用 `number = string` 变异证明检查器有效；全量检查若 OOM 如实记录。
- **浏览器与真实运行时**：仅在 `start-dev.bat` 已启动、使用【测试】项目且前后端重启加载路由后做 Playwright；验证 render-config overlay、组件真实保存/只读、只读联动和风险负责人展示。S17 分类未批准时，浏览器只能记录阻塞，不得把无 sheet 当作完成。
- **回归与证据**：实现前后重新核对 requirements/design/tasks 三件套、D1-D8 门和关键边界；不以 FEAT JSON、单纯 registry 通过、代码 diff 或任何 `[x]` 记录替代端到端证据，也不在本设计中声称已实现。

## 阻塞项闭环执行记录（2026-10-26，用户要求"阻塞项该修复修复"）

本节为 append-only 执行轨迹，记录三个运行时/数据阻塞的真实修复与证据，不改写既有任务勾选。

### P0.3 / R4 运行时 dispatch — 已修复（根因=运行中 worker 加载旧代码，非代码缺陷）
- 诊断：进程内直调真实入口 `_get_render_config_impl` 对 S1/S8/S9/S10 全部正确命中 s-checklist 类型；而实时 HTTP 仍返回 `a-program-console`/`audit-sheet`/`h-static-doc`。运行中的 uvicorn worker（PID 启动于当日早于 P0/D3 改动）未重载。
- 处置：经用户授权重启 backend（`backfill`/kill 端口 + `run_uvicorn.py` 无 reload 单 worker）。重启后实时 HTTP 复验：S1 `S1-1对法律法规的考虑记录表`→`s1-regulation-record`、S8 `审定表S8-1`→`s8-adjudication`、S9 四张（adjudication/internal-control/program-description/legal-regulations）、S10 三张（adjudication/internal-control/environmental-regulations）全部正确，无 grid_fallback/onlyoffice 劫持。顶层 `not_applicable` 同时正确输出 False。

### R6.6 / S17 运行时 — 已解锁（用户 2026-10-26 明确批准写共享库）
- 根因：S17 模板是 `.xls`，未被既有 `.xlsx` 扫描收录，`workpaper_sheet_classification` 中 S17 为 0 行 → render-config 返回 0 sheet。
- 处置：先跑 `generate_s17_classification_dry_run.py`（8 候选 / 4 处 legacy-xlsx 分类器不一致，均属 .xls 新通路预期），再经批准用 `backend/scripts/ops/backfill_s17_classification.py --apply` 幂等写入 8 行（class_code 遵循 S9/S10 约定；ON CONFLICT DO NOTHING）。
- 复验（实时 HTTP）：S17 8 sheet，`审定表S17-1`/`审核表（合并）S17-2`/`审核表（个别报表）S17-3`→`s17-nonrecurring-detail`、`S17-11`→`s17-reconciliation`、`S17-21`→`s17-tax-impact`，与 R6.5 mapping、R4.1 逐一吻合，无 a-program-console 残留、无 detail/reconciliation/tax 串接。

### P1.1 / R7.1 linked_workpapers — 已修复
- 在 `backend/data/wp_account_mapping.json` 补 5 条声明：S20→D4、S15→D4/M2、S17→K12/K13、S6→K1、S33-5→D4/F5（映射表为单一权威源）。
- `_s_linkage.py` 新增 `linked_workpapers_for()`（读映射表、lru_cache），S6/S33-5 resolver 改为从映射读取（S6 由自引用 `["S6"]` 纠正为 `["K1"]`），避免双写漂移。
- 守卫：`test_s_linkage_resolvers.py` 新增 `TestR71LinkedWorkpapersDeclarations`（3 例）断言 5 条声明精确目标 + helper 单一来源 + S6 不再自引用。全文件 13 passed。

### R10 风险/委派（P2.1）— 诚实保持数据阻塞（代码已验，不伪造审计数据）
- 真库 `risk_assessments` 0 行、B50 checklist 0 行（全库皆空）。P2.2/P2.3 代码正确（空→"未知"象限、负责人回退 username），但无真实风险数据不展示填充结果。用户 2026-10-26 确认接受为数据阻塞，不向共享库写入风险数据。

### 回归
- 相关套件全绿：`test_s_linkage_resolvers`(13) + `test_s17_override_mapping`(?) + `test_s17_classification_dry_run` + `test_s_checklist_render_strategy` + `test_s_checklist_registry_parity` + `test_render_config_wire_contract` 合计 40 passed；`business_category_service`/`linkage_service` 映射加载 1025 条不变。