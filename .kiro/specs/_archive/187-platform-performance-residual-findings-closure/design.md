# 设计：平台性能收口的范围外发现

## 1 现状核实（2026-10-31 现算，探针在仓库外，用完即删）

探针对 `app.main.app.routes` 逐条取样本路径（`{x}`→`x0`、`{x:int}`→`1`、`{x:uuid}`→合法 UUID），看它之前注册的同方法路由是否已能匹配。懒路由（`GT_LAZY_ROUTES`）只推迟重属性、路由索引（`GT_ROUTE_INDEX`）按原下标取第一条，二者都不改变匹配顺序，探针结果即运行期行为。

### 1.1 遮蔽（13 条）

| 被遮蔽（后注册） | 先命中者 | 现象 | 调用方 |
|---|---|---|---|
| GET `/api/attachments/paperless-health` | 同文件 `/{attachment_id}` | 422 | 无前端调用 |
| GET `/api/report-config/row-note-mapping` | 同文件 `/{config_id}` | 422 | ReportView |
| GET `/api/report-config/candidates`（`report_config_baseline`） | `report_config` `/{config_id}` | 422 | ReportConfigBaselineTab |
| GET `/api/disclosure-notes/{p}/{y}/deleted`、`/formula-health` | 同文件 `/{p}/{y}/{note_section}` | 404「章节不存在」 | — |
| GET `/{p}/wp-mapping`（`note_wp_mapping`）、`/{p}/sections`、`/{p}/sections/trim-scheme`（`note_trim`） | `disclosure_notes` `/{p}/{year}` 等 | 422 | NoteTrimPanel（未挂载） |
| GET `/workhours/summary`（同文件）、`/budget-vs-actual`（`workhour_budget`）、`/approval`（`workhour_approval`） | `workhour_entries` `/{entry_id}` | 422 | 工时页预算对比（已挂载）、审批表（未挂载） |
| POST `/api/projects/{project_id}/batch-review`（`pm_dashboard`） | `review_prompt` `/{pid}/batch-review` | 两功能同路径 | 见 §3.6 |
| GET `/api/projects/{pid}/workpapers/{wp_id}/versions`（`version_trail` 快照列表） | `wp_export_import` 同形路径（归档历史） | 两功能同路径，版本链抽屉恒空 | GtWpVersionTrail（30+ 宿主）/ WpVersionHistoryPanel |

### 1.2 重复注册（10 组，与既有基线 `_KNOWN_DUPLICATES` 逐条一致）

| 路径 | 生效（先注册） | 死实现 | 前端按谁的契约 | 裁决 |
|---|---|---|---|---|
| GET `/api/aging/presets`、GET/PUT `/projects/{id}/aging/config` | `aging_config`（大写预设、仅登录） | `aging_analysis`（小写预设、项目鉴权） | `aging_config`（AgingConfigDialog / useAgingConfig） | 留 `aging_config`，删 `aging_analysis` 三个，**把项目鉴权移过去**（readonly / edit） |
| GET `/api/b60/chapter-definitions` | 同一函数经 `system.py §53d` 注册（无依赖） | 同一函数经 workpaper 组注册（`dedicated_wp_gate`，无 wp_id 时 no-op） | — | 删 `system.py §53d` 那次 include（端点改为须登录，GtB60Bundle 登录后才调） |
| GET `.../a16/recommended-version` | `wp_editor_router`（R4 单一分类，`recommended_code`） | `completion_phase`（旧 `business_category`，`main/supplement`） | WorkpaperWordEditor 两种都认；`useAProgramPopups` 只认死实现的 `main.code` ⇒ 推荐标记从未显示 | 留 `wp_editor_router`；删死的；`useAProgramPopups` 改读 `recommended_code` |
| GET `.../issue-hints` | `completion_phase` 内联 SQL | `issue_hints`（`issue_hints_service`，A17 第 15 章取数用的同一份） | GtA17Summary 两种都认 | 留 `issue_hints`（同页提示与第 15 章同一口径），删 `completion_phase` 的 |
| GET `.../export-word`、`.../export-word/check-incomplete` | `completion_phase`（任意编码通用模板填充） | `wp_export_word`（分发到 A17-1 / A17-2-1 / A18-2 专用导出服务） | GtRegulatoryLetter（A18-2，路径少 `/api`，下到首页 HTML） | 留 `wp_export_word`；删死的；修 A18 检查契约与前端（§3.5） |
| GET `.../workpaper-summaries/{key}` | `completion_phase` 骨架 | `workpaper_summaries`（`workpaper_summaries_service`，A17 / EQCR 取数同一份） | 无前端调用 | 留 `workpaper_summaries`，删 `completion_phase` 的 |
| POST `.../ledger-import/jobs/{job_id}/retry` | `ledger_datasets`（重排队 + runner） | `ledger_import_v2`（orchestrator.resume） | LedgerImportHistory 用生效那份；v2 访问器零调用 | 留 `ledger_datasets`，删 v2 的 |

时间线佐证：`issue_hints / workpaper_summaries / wp_export_word` 由 completion-phase-infra spec 于 2026-06-18 09:47 建立；`completion_phase.py` 同日 19:40 由「双机合并」提交带入同名路由，此后一直先注册、遮蔽设计实现。

## 2 方案选择

**遮蔽的修法：调注册顺序，不加类型转换器。** 备选是 `{config_id:uuid}` / `{year:int}` 这类 Starlette 转换器（语义更准、与顺序无关），否决理由：①会改 `route.path` 字符串，连带 `wp_bound_entry_coverage.json`、`edit_level_impact_inventory*.json`、鉴权基线等按路径登记的台账；②非法 id 从 422 变 404；③`request.path_params` 的值从 str 变成 UUID / int，依赖里按字符串读的会受影响。调顺序零 path 变化，回归由全应用守卫兜底。

- 同模块：把静态路径端点挪到参数端点之前（`attachments.check_paperless_health`、`disclosure_notes.list_deleted_sections / formula_health`、`workhour_entries.get_summary`）。`report_config.get_row_note_mapping` 实施时改为迁出到 `routers/report_row_note_mapping.py`（路径不变），在 report 组先于 `report_config` 注册（R2 要给它加项目口径，`report_config.py` 已超行数门）。
- 跨模块：`router_registry/report.py` §4 列表把 `report_config_baseline`、`note_wp_mapping`、`note_trim` 排到 `report_config` / `disclosure_notes` 之前（三者路由全是字面量段在前或段数不同，不会反过来遮蔽别人）；`collaboration.py` 把 `workhour_budget`、`workhour_approval` 排到 `workhour_entries` 之前。

**两功能同路径：改名其中一条。**
- 版本：`version_trail` 拥有整棵 `/versions` 子树（创建 / 详情 / 对比 / 回滚），只有导入导出的归档列表在这里串门 ⇒ 归档列表改为 `GET /api/projects/{project_id}/workpapers/{wp_id}/version-archives`，`useWpExportImport.versions` 同步；`version_trail.list_versions` 随之生效。
- 批量复核：见 §3.6。

**守卫**：新文件 `backend/tests/test_route_shadow_guard.py`（遮蔽，允许集为空，双向变异）；既有 `test_duplicate_route_registration_baseline.py` 的 `_KNOWN_DUPLICATES` 清空（该文件的 stale 检查本就要求修一组删一条）。遮蔽判定与探针同口径；同方法才算；HEAD / OPTIONS 不计。

## 3 逐项设计

### 3.1 aging 鉴权移交
`aging_config` 的 GET 挂 `require_project_access("readonly")`、PUT 挂 `require_project_access("edit")`（与被删的 `aging_analysis` 声明一致）；`/aging/presets` 不含项目，保持仅登录。端点用例覆盖：未登录 401、非成员 403、成员 200 / 能保存、admin 200。鉴权基线 `_IDENTITY_ONLY_BASELINE` 按现算下调锁住成果。

### 3.2 completion_phase 去重
删 5 个重复端点及只为它们存在的 `SummaryResponse`、`_summary_*`、未再使用的 import；保留 checklist-templates、completion-flags、archive-checklist 等非重复端点。`a16_version_service.recommend_supplement` 删后零调用 ⇒ 一并删除；`recommend_main_version` 仍被 `auto_data_resolvers/_completion.py` 使用，保留（该处仍按旧 `business_category` 推荐，与 R4 单一分类不一致，登记 §5）。

### 3.3 ledger / b60
`ledger_import_v2.retry_job` 删除（`ImportOrchestrator.resume` 仍被 `/resume` 用）。`system.py §53d` 的 b60 include 删除，workpaper 组那次保留。

### 3.4 报表附注列（R2）
> 实施改动（2026-10-31，代码为准）：原设计第一条「`fetchNoteSectionsWithData` 改用目录树端点」作废。导出编号方案本就按附注「有数据」口径决定哪些节占号，页面直接用方案算出的格值即可，不必再单独取「附注有内容」章节 ⇒ `fetchNoteSectionsWithData` 与 notes-tree 取数删除（R2.1 同步改写）。

- 唯一来源 `services/report_note_refs.py`：`build_report_note_ref_plan`（导出 `ReportExcelExporter._build_note_ref_plan` 直接委托这里，SAVEPOINT + 出错回 None）；`project_row_note_refs` 扫模板里整格是附注列占位的格，用导出同一个 `render_note_refs` 渲染格值（方案为 None 时与导出一样按静态映射），再按行名（`title_key`，限同一张表）挂到本项目报表行；库内没有同名行的格不登记（模板与库内是两套编码，按编码硬挂会挂错行）。`note_deliverable_outline.FsNoteRefPlan` 加 `note_sections` / `section_for`，给出点击跳转用的库内附注编号。
- 端点迁出为 `routers/report_row_note_mapping.py`（路径不变，见 §2）：只给 `applicable_standard` 时原样返回静态映射；同给 `project_id` + `year` 时先校验项目只读权限，返回 `{row_code: {section_code, section_title, seq, display}, "_meta": {source, has_notes}}`，`display` 即导出该行附注列的格值（null = 导出留空）。
- 前端 `fetchRowNoteRefs`（`useReportData.ts`）：没有年度不请求；失败或响应没有 `_meta`（旧接口）返回 null ⇒ 附注列不显示编号，不猜编号。`useReportColumns` 只读 `rowNoteDisplay` / `rowNoteSection`；删除按金额计数的回退编号与前端写死的映射表（`_ROW_NOTE_SECTION_MAP`、`hasNoteMappingForRow`、`getNoteSectionForJump`，删前全仓零调用）；ConsolidationIndex 同步改调用。
- 对拍：同项目同年度导出 Excel，读附注列（行名→编号），与端点 `display` 逐行比较（结果见 §7）。

### 3.5 A18-2 导出
- `wp_export_word` 的检查端点用 `CheckIncompleteResponse(**result)`，A17 两个检查函数返回统一契约 `{complete, missing_fields, wp_code, reason}`，A18 的 `a18_check_incomplete` 返回 `{has_incomplete, count, incomplete_topics}` ⇒ 一旦生效即 500。改 `a18_check_incomplete`（分发表专用的模块级函数）映射到统一契约（`complete = not has_incomplete`、`missing_fields = incomplete_topics`、`reason = "N 项议题未填写"`），类方法 `check_completeness` 不动。
- GtRegulatoryLetter：路径补 `/api`；按 `complete === false` 与 `missing_fields.length` 提示；导出拿 blob 下载。
- 实施时发现同组件另外 5 个请求同样少 /api（读写检查表、建议、表头带出），整页读写从未生效，一并修（§7.2）：检查表改走 `/api/workpapers/{wp}/checklist-responses`（原路径 `/projects/{pid}/working-papers/{wp}/…` 后端不存在），保存体 `{project_id, items}`、未选适用性存 null（A18-2 结论只收 Y / N / done / pending），表头年度取 `audit_year`，合伙人先取签字合伙人。

### 3.6 批量复核同路径
`POST /api/projects/{pid}/batch-review` 生效的是 AI 批量复核（`review_prompt`，body `{wp_code_prefix, year}`，AI 复核面板在用）。被遮蔽的 `pm_dashboard.batch_review`（body `{wp_ids, action}`）从未可达，且其服务直接把 `pending_levelN` 改成 `levelN_passed/rejected`，绕过 `WorkingPaperService.update_review_status` 状态机（不记退回原因、不建复核记录、不覆盖三 / 四级），返回 BulkResult 而复核工作台读 `succeeded_count`。⇒ 删除该死路由及 `pm_service.BatchReviewService`；复核工作台「单条通过 / 退回、批量退回」照旧恒 422，**不擅自接到别的流转上**，列待裁决（§5）。

### 3.7 公式端点登记（R4）
`formula.ts` 新增 `formulaCrossCheck.history(pid)`、`formulaSettings.dependencies(pid)`（若已有同名对象则挂到已有对象）、`formulaPush.coverage` / `latest(pid)`；barrel 补 `formulaHealth, formulaDebug, formulaPushVerify, formulaTimeline` 与新访问器；三个面板改用访问器。四个后端路由已现算存在。

### 3.8 字典标签类型（R5.1）
`stores/dict.ts` 的 `type()`：颜色为 `""` 返回 `'primary'`（Element Plus 2.13 的默认值，基础样式本就是 primary，外观不变），不在合法集合内返回 `'info'`。后端字典大量用 `"color": ""` 表示默认，改前端一处覆盖全部消费方。模板里硬编码 `:type="… ? '' : …"` 的 `<el-tag>` 另行计数，按 §4 ROI 决定。

### 3.9 重复 GET（R5.2）
浏览器按 initiator 定位 Ledger（`/ledger/years`、项目详情）与 D2（项目详情、`capability-snapshot`）的两次请求；同参数同时发起的改为共享在途 / 复用 store；参数不同（如 sheet 变化后重取能力快照）属正常，登记不改。

### 3.10 公式管理首次打开才挂载（R5.3）
四个宿主（TrialBalance、ReportView、DisclosureEditor、ThreeColumnLayout）用同一个小组合式 `useMountOnFirstOpen(visible)`：`visible` 第一次为真后 `mounted` 置真且不再回落；模板 `<FormulaManagerDialog v-if="fmMounted" …>`。弹窗已支持「挂载时即打开」（上一 spec 的 `openedBeforeMount`）。按挂载断言的测试（`ThreeColumnLayout.year.spec`）先打开再断言；标签存在类守卫不受影响。

### 3.11 测试卫生（R6）
- `tabToRoute`：生产与测试各一份，`map[tab] || 默认` 对 `"__proto__"` 返回原型对象。抽到 `layouts/defaultLayoutRoutes.ts`（`Object.hasOwn` 判定），DefaultLayout 与测试都用它。
- `guidanceBar.spec`：`text()` 会去首尾空白，判据改为比较 `element.textContent`。
- G6 `transposeToRows` P6：生产语义是「列头去空白后非空或该列有数据才算有效列，空列头取『投资N』」，测试判据假设所有列头非空；按生产语义写判据。
- S34-16-1：先复现反例定位根因（公式引擎还是判据），再修对应一方。
- `audit_amount_input_columns.py` 加 `--out <路径>`（默认仍写已跟踪产物）；spec 写系统临时目录并读回。

## 4 ROI 裁决

| 项 | 收益 | 代价 / 风险 | 裁决 |
|---|---|---|---|
| 类型转换器替代调顺序 | 语义更准 | 多份台账 / 清单连带、422→404 | 否 |
| 报表附注列与导出同源 | 页面与交付件编号一致（现三套口径） | 端点多一次附注读取（异步、不阻塞渲染） | 做 |
| 公式管理首次打开才挂载 | 未打开的页省约 264 KB 下载与解析 | 4 宿主 + 1 个测试 | 做 |
| 硬编码 `<el-tag type="">` 全仓改 | 仅开发态 warn，生产无影响、外观不变 | 跨多文件、与并发会话改动面重叠 | 计数登记，不改 |
| 复核工作台通过 / 退回接正确流转 | 修复从未可用的按钮 | 需定复核流转语义（三 / 四级、是否允许跳过「复核中」） | 待用户裁决 |
| `{pid}` 命名路由不在鉴权守卫视野 | 补上守卫盲区 | 属鉴权域，基线需重算 | 登记，另立 |

## 5 范围外登记（不改）

- 复核工作台「通过 / 退回」恒 422（§3.6）。
- `review_prompt` 的 `/api/projects/{pid}/batch-review` 与 `/batch-review-progress` 不校验登录 / 项目；路径参数名为 `{pid}` 的路由不在 `test_project_endpoint_authorization_baseline.py` 两维视野内。
- ~~留下的 `issue_hints`、`workpaper_summaries`、`wp_export_word` 端点仅登录~~（实施时改为修，见 §7.2）：`issue_hints`、`workpaper_summaries` 去重后才真正生效，一生效即可跨项目读，按 R1.4「鉴权级别与同域端点一致」补 `require_project_access("readonly")`；`wp_export_word` 已有路由级 `dedicated_wp_gate`，不改。
- `auto_data_resolvers/_completion.py` 的 A16 推荐仍按旧 `business_category`。
- `commonApi.ts` 的 `getAgingPresets / getAgingConfig / saveAgingConfig` 零调用且类型按已删实现写。
- `audit_chain_head` 无 ORM 模型：属远端 audit-log-chain-integrity（V221 建表），不改。
- 硬编码 `<el-tag type="">`（§4）。

## 6 验证

- 后端：遮蔽 / 重复守卫；受影响模块既有用例（attachments、report_config、disclosure_notes、workhour、aging、ledger retry、completion_phase、wp_export_word、version gate）；新增端点级用例（aging 鉴权四态、row-note-mapping 带 / 不带项目、A18 检查契约、版本两路径）；`test_project_endpoint_authorization_baseline.py`、`test_x3_entry_coverage_ledger.py`、`check_drift` 前后对比无新增归因到本 spec 的发现。
- 前端：受影响 spec、`formulaPaths.spec.ts`、单区域类型检查、ESLint、行数门。
- 浏览器：报表页（无 4xx、附注列编号与导出 Excel 对拍）、工时预算对比、底稿版本历史两面板、A16 程序表推荐标记、A18-2 导出（如有【测试】数据）、公式管理四宿主首次打开、项目树无 warn。

## 7 实施记录（2026-10-31，代码为准）

### 7.1 与设计的偏离
- §2：row-note-mapping 迁出到 `routers/report_row_note_mapping.py`（R2 要加项目口径，`report_config.py` 已超行数门），路径不变、先于 `report_config` 注册。
- §3.4：删除 notes-tree 取数（导出编号方案自带「有数据」口径），R2.1 同步改写。
- §5：`issue_hints`、`workpaper_summaries` 去重后才生效、一生效即可跨项目读 ⇒ 按 R1.4 补 readonly 项目鉴权（原设计「只登记」）；`wp_export_word` 已有路由级 `dedicated_wp_gate`，不改。
- §3.11：`tabToRoute` 用 `Object.prototype.hasOwnProperty.call`（仓库先例）而不是 `Object.hasOwn`。

### 7.2 验收期发现并修复

| 发现 | 根因 | 修法 | 证据 |
|---|---|---|---|
| 报表页签跳 `financial-reports`（404） | 页签映射写错路由名 | 改 `reports` | PBT 按真实路由表 resolve，自检 NotFound |
| 报表页切年度不生效；带 `?year=` 打开时选择器停在「请选择」 | 取数年度路由优先，切年度只改 store | 写路由 `?year=&tab=`（整页按新年度重挂、页签保留）；路由给年度时同步选择器 | `yearSwitchUpdatesRoute.spec.ts` + 浏览器 |
| D2 能力快照请求两次 | 监听 getter 每次返回新数组，上下文对象整体替换即触发 | 按请求主体多源监听 | `useShellCapability.spec.ts` + 浏览器 1 次 |
| `formulaPaths.spec.ts` 提取器把 `global_router` 的路径算错 | 前缀按文件取而不是按 router 变量取 | 按变量取前缀 + 自检 | spec 全绿 |
| 工时「预算对比」下拉恒空 | 工时页与「我的填报」同时 GET 同一地址，utils/http 去重取消先发的那次，工时页 catch 静默 | `getMyAssignments` 经 apiProxy 共享在途 | 单测 HEAD 红 + 浏览器 |
| 15 处请求少 /api 前缀 | baseURL 是 '/'，只有 /api、/wopi 转给后端；GET 拿到首页 HTML、PUT / POST 404，调用方静默 | 逐处修（A18-2 ×5、I1/I3~I6 改统一探针 ×5、H3 ×2、K10 ×2 含字段与行级证据、H5、PBC、凭证识别弹窗）+ 全仓守卫 | 4 个 spec 在 HEAD 上打红；PBC 浏览器 200 |

K10 两处识别原先读不存在的 `text` 字段（D4 识别返回 `ocr_text` / `extracted_fields`），且路径没带底稿 id（后端无 `/api/d4/contract-ocr`）。改成按底稿调用后进入小眼睛守卫视野，按 K9 写法补行级证据（`rowEv.append` + `RowEvidenceEye`）；小眼睛豁免清单只许删，不能靠加豁免过守卫。

### 7.3 登记不改
- DisclosureEditor 切年度只改 store（与报表页同一缺陷）：改成写路由会整页重挂，切年度后「没有附注就自动生成」那一支要重新安排，编辑器行数在上限、并发会话在改保存流程 ⇒ `yearSwitchUpdatesRoute.spec.ts` 的 `KNOWN_GAPS`（只许删）。
- 华氏 2025 导出把「七、9」写在油气资产行（附注八、25 有表格数据，项目报表没有油气资产行），页面不挂；这一节该不该出现在交付件由附注模板 / 导出规则决定。
- 告警：NotificationCenter 提示组件「Runtime directive used on component with non-element root node」、ReportView / TrialBalance 多根组件在 Transition 内，HEAD 同有；工时页 el-radio「label 当 value」弃用告警来自页内其他组件。
- `watch(() => [ … ])` 现算 238 处 / 233 个文件（不含测试）：getter 每次返回新数组，被读的响应式源一触发就回调；只有源会「值没变也触发」（整体替换的对象）时才重复取数。本 spec 只修了浏览器定位到的能力快照一处。
- D2 项目详情、查账 `ledger/years` 与项目详情的两次 GET（任务 16）。
- 写死空串类型的 `<el-tag>` 14 处（任务 15）。
- utils/http 的 GET 去重是「取消先发的」：同页两个调用方同时取同一地址时先发方静默失败。本 spec 只修了工时页；改平台语义影响全站，另议。
- A18-2「打开即保存」：加载数据与表头带出都会触发 1.5 秒后的自动保存；只读打开会提示「保存失败」（修前每次打开都会，因为保存从未成功过）。
- 鉴权守卫只看端点签名，看不到 include 级的 `dedicated_wp_gate`（`wp_export_word` 被记为仅登录）。
- 仅登录、未校项目的接口（不在本 spec 改动面，均在 `_IDENTITY_ONLY_BASELINE` 基线内）：`POST /api/projects/{pid}/document-recognize`、`POST /api/projects/{pid}/assignments`；`GET …/pbc/by-workpaper/{wp}` 按底稿 id 读、不看项目。

## 8 待用户裁决（用户 2026-10-31 已裁决，实现见 §9；第 1 项待定规则，见 §9.5）
1. 复核工作台「通过 / 退回、批量退回」恒 422：要先定复核流转语义（三 / 四级、能否跳过「复核中」），再接到 `WorkingPaperService.update_review_status`。
2. 路径参数名为 `{pid}` 的路由不在鉴权基线两维视野内（如 `review_prompt` 的 batch-review / batch-review-progress 不校验登录与项目）：属鉴权域，需另立 spec 重算基线。
3. `WorkpaperWordEditor` 推荐版本读 `main.code` 的旧分支在去重后已无数据来源，是否删除。
4. DisclosureEditor 切年度怎么改（见 §7.3 第一条）。
5. utils/http GET 去重「取消先发」是否改为共享在途（全站影响）。
6. A18-2 是否改为只在用户改动后保存（表头带出要不要用户确认后再落库）。
## 9 批 G：§8 裁决的实现（2026-10-31）

### 9.1 A16 推荐版本（R8）
- `loadRecommendedVersion` 只读 `recommended_code` / `all_versions` / `always_required`。
- 补充声明开关：先读字段覆盖 `word_template:A16:A16-7` 的 `enabled`（`'true'` / `'false'`，`onSupplementToggle` 写的就是它），有值按它；没有记录或取不到年度时按 `always_required` 含 A16-7。
- `WorkpaperWordEditor.spec.ts` 的 mock 全部改成真实形状；「不需要补充声明」的用例改为字段覆盖 `enabled=false`；加旧形状不再生效、记录优先于 `always_required` 两个用例。

### 9.2 A18-2 只在用户改动后保存（R9）
- 保存内容抽成 `buildPayload()`，`doSave` 与比较共用。挂载流程（读议题定义 → 读已存内容 → 表头为空时带出）全程 `loading`，结束时记下基线 `JSON.stringify(buildPayload())`；监听回调里基线为空不动作，与基线相同则撤掉待发的保存，不同才防抖保存；保存成功后基线更新为本次发出的内容。
- 读已存内容失败：不记基线（本页不自动保存），提示「读取已填内容失败，本页不自动保存，请刷新重试」—— 否则一改动就会用带出值覆盖已存表头（PUT 按 item_id upsert，表头整行覆盖）。
- 卸载时只有待发的保存才补发（原逻辑不变）。导出：`regulatory_letter_service` 在表头缺公司名 / 年度时取项目信息，未改。

### 9.3 附注编辑页切年度（R10）
- `onYearChange(y)`：①未保存拦截（`guardUnsaved()`，取消则 `selectedYear` 回到当前年度）②确认放弃后清两个脏标记（push 时更新守卫不再问第二次）③`projectStore.changeYear(y)` 先于 push（`year:changed` 落在旧实例上，重挂后的新实例不会亮「数据已更新」）④`router.push({ path: route.path, query: { year } })`：只带年度 —— `section` / `table_index` / `noteTemplate` 是一次性参数，挂载后用 `history.replaceState` 清掉了，但 vue-router 的 `route.query` 里还在，展开会把它们带回去。
- 「没有附注就自动生成」：原先在 `onYearChange` 里；现由重挂后的 `onMounted`（取树 → 等编辑判定 → 为空且可写 → 生成）执行，条件不变。
- 未保存拦截抽成 `guardUnsaved()`，`onBeforeRouteLeave` 与 `onBeforeRouteUpdate` 共用（先例：试算表 `useTbSummaryNavigationGuard`）。附注路由没有 `reuseOnQueryChange`，任何 query / 参数变化都整页重挂，所以更新守卫按离开同样处理。
- 行数：编辑器在上限 3164，本处净增 ≤ 0。`DisclosureEditorRoute.vue` 注释同步。

### 9.4 GET 共享在途（R11）
- 新内核 `utils/getSingleFlight.ts`（从 apiProxy 抽出）：`planSharedGet(url, config)`（配置项白名单 `params / responseType / _silent / _dedupe / signal`，参数规范化，键含登录身份代际）、`sharedGet(flights, plan, start, copyForFollower)`、`standaloneGet(producer, signal, config)`、`advanceGetShareBarrier()`。每个调用方一个订阅（自己的 signal、身份代际边界）；底层请求不带任何调用方的 signal；成功、失败都出在途表（不缓存结果）。
- 拷贝：第一个拿到结果的调用方拿原对象，其余在结算时（任何调用方代码运行前）拿拷贝：普通对象 / 数组 `clonePlain`，ArrayBuffer `slice(0)`，Blob / 字符串 / 其他原样。utils/http 层拷的是 `{ ...response, data: 拷贝 }`。
- 新鲜度屏障：在途记录带创建时的屏障号，屏障号变了就不再给新请求共用（旧请求照常把结果交给已有订阅者）。utils/http 在非 GET 请求发出、结束时推进；项目事件流 `_dispatch` 收到任一事件时推进。
- utils/http：`addPending` 对 GET 直接返回（GET 不再进去重表，调用方 signal 保留）；`http.get` 换成包装：能出计划的走 `sharedGet`（生产者用原 `get`、去掉 signal），出不了计划的原样独立发送。重试、401 刷新、全局提示都在生产者那一条链上，只发生一次。POST / PUT / PATCH 防重复提交不变。
- apiProxy：改用内核（键、取消、身份边界不变，新增屏障与后加入者拷贝）；`download` 仍独立发送。
- 测试：新 `httpGetShare.spec.ts`（真实 http + 假适配器）；`httpDedupe.signal.spec.ts` 第三例、`staffApiMyAssignmentsShared.spec.ts` 机制自检按新语义改写；`apiProxy.inflightShare.spec.ts` 补屏障与拷贝。
- 不改：各处为绕开「取消先发」写的在途表 / `_dedupe:false` / 被取消重取（语义仍成立，只是不再必要），注释保留原因；`isRequestCancelled` 注释改为现语义。

### 9.5 复核工作台（R12，待用户定规则）
现算（2026-10-31）：
- 列表模式单条通过 / 退回、批量退回 → `POST /batch-review`（AI 批量复核，请求体不符）恒 422；三栏模式通过 / 退回 → `PUT …/review-status` 发 `pending_level1 → level1_passed`，状态机要求先进「复核中」，恒 400；批量通过 → `/batch-review-pass`，不论当前在哪级都写 `level1_passed` + 底稿 `review_passed`（从二级待复核会退回成一级通过，同时把底稿标成复核完成）。
- 两套状态机：①`WorkingPaperService.update_review_status`（在用）：固定两级、必须经「复核中」、二级通过为终态；界面上没有任何入口进「复核中」或把一级通过推到二级待复核 ⇒ 现有界面无法让任何底稿走完复核。②`ReviewStateMachine`（Phase 6 F8、ADR-5）：按项目 `review_config.levels`（2~4，默认 2：L1 经理、L2 合伙人）、待复核或复核中都可直接通过、非末级通过后自动进下一级待复核；零调用。复核配置接口 `/review-config` 已能把项目设成 3 / 4 级，但在用的状态机走不到三级。
- 真库：3820 张底稿全是 `not_submitted`，0 个项目设过 `review_config` ⇒ 换规则不涉及存量数据。
- 方案 A（建议）：以 F8 为唯一状态机——级数按项目配置；待复核 / 复核中都可直接通过或退回；非末级通过自动进下一级待复核；末级通过底稿标复核完成；退回必填原因、建复核记录、底稿改「需修改」；批量通过 / 退回逐张走同一状态机、不符合的跳过并写原因。方案 B：保留「必须先开始复核」，打开条目时自动进复核中。方案 C：固定两级、去掉三 / 四级配置。

**用户 2026-10-31 选方案 A**。实施要点：

#### 9.5.1 后端：状态机统一
1. `WorkingPaperService.update_review_status` 中的 `REVIEW_TRANSITIONS` 重写为：读项目 `review_config`（默认 2 级），按级数动态生成合法转换表。核心规则：
   - `pending_levelN` / `levelN_in_progress` 都可以直接 → `levelN_passed` / `levelN_rejected`（去掉「必须先进复核中」的强制中间步骤，与调整分录对齐）。
   - `levelN_passed` 若 N < 项目配置的级数 → 自动推进 `pending_level{N+1}`；若 N == 级数 → 终态，底稿标 `review_passed`。
   - `levelN_rejected` → `not_submitted`（退回编制人修改后重提），底稿标 `revision_required`。
   - 退回必填原因并建 `ReviewRecord`。
2. 删 `ReviewStateMachine` 类（零调用），把逻辑内联进 `update_review_status`，避免两套状态机并存。
3. 增加 `resolve_review_level(project_id)` 辅助函数：读 `Project.review_config` JSONB，缺省返回 `{"levels": 2, "level_roles": {"L1": "manager", "L2": "partner"}}`。

#### 9.5.2 后端：批量通过 / 退回端点
- 新端点 `POST /api/projects/{pid}/workpapers/batch-review-pass`（替换前端调的 `/batch-review-pass`），逐张走同一状态机，不符合跳过并写原因回报。
- 新端点 `POST /api/projects/{pid}/workpapers/batch-review-reject`，同理。
- 删前端调用已不存在的 `POST /batch-review`（AI 批量复核端点，名称冲突，不做底稿复核）。

#### 9.5.3 前端：ReviewWorkbench
- `approveCurrent()` 改为发当前条目的 `review_status` 对应的下一个 `levelN_passed`（如 `pending_level1` → `level1_passed`、`level1_in_progress` → `level1_passed`）。
- `rejectCurrent()` 同理发 `levelN_rejected`。
- `reviewStatusLabel()` 补 Level 3/4 标签。
- 批量模式改调新的 `batch-review-pass` / `batch-review-reject` 端点。
- inbox 列表的查询条件扩展到 `pending_level3` / `pending_level4`。

#### 9.5.4 前端：复核配置页
- 项目设置里加「复核层级」设置（2/3/4 级 + 各级角色），调 `GET|PUT /review-config`。目前后端已有，前端无入口。

### 9.6 `{pid}` 鉴权盲区（§8.2）
另立 spec `project-pid-path-authz-coverage`：现算 49 个 `/api/projects/{pid}/…` 路由（review_prompt 3 个无鉴权，抽样 / 程序复核 / 版本链等靠函数体内底稿级校验或仅登录），鉴权基线守卫只认 `{project_id}`。
