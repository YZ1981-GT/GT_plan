# 设计文档：S3　写入方归属与过期状态机（formula-writer-ownership-and-stale）

> 需求编号：requirements §1 四条依次记 R1（section + field 唯一写方矩阵）、R2（stale 状态机：`stale_source` 必写、值不变也清 stale）、R3（试算平衡表手工值读回）、R4（`useEditorSave.ts` 与其余宽放行写请求）。
> 现状基线：分支 HEAD `4c0a1e0a6` + 母 spec 整合树 `tmp_fhic/integ`（`d91f5f804`）。数字为 2026-10-29 现算。

## 0. 结论

R1 依赖附注权威源拍板（ADR-DPA-001「留前端」与「经公式管理自动推」的冲突，至今未拍板），R2~R4 不依赖。所以本 spec 分两段：第一段先做不需要拍板的三件事 —— 过期状态机（统一写入口，`stale_source` 必填，「重算成功且值不变」也清过期）、试算平衡表手工值读回、宽放行写请求改按状态码判成功；同时把附注写入方的现状清单做成可校验的登记表并冻结（新写入方必须登记）。第二段在拍板后按登记表落「每个章节每个字段只有一个写方」的强制。

## 1. 现状复核

| # | 交接结论 | 现算 | 判定 |
|---|---|---|---|
| 1 | R2：`stale_source` 从未写入 | 共享库 `disclosure_notes` 1096 行，`is_stale = true` 227 行，`stale_source` 非空 **0** 行。整合树 AST 现算，把 `disclosure_notes` 置为过期的写入点共 **14 处 / 8 个文件**。写了来源的 4 处：`disclosure_stale_marker.mark_sections_stale`（原生 SQL，`workpaper_saved`）、`note_disclosure_refresh_service.refresh_note_section`（`disclosure_refresh_no_data`）、`report_note_sync_service.mark_notes_stale_for_report_change` 2 处（`report` / `report_fallback`）。只置 `is_stale`、不写来源的 10 处：`consol_note_stale_handler.mark_consol_sections_stale` 2 处原生 SQL（合并项目下级变更）；`event_handlers/_impl.py` 3 处 —— `_mark_downstream_stale_on_rollback`（回滚后）、`_mark_reports_stale_on_adjustment`（调整分录变更）、`_mark_disclosure_notes_stale_for_project_year`（整项目年度批量，账套激活、底稿复核通过、调整分录审批 / 撤销审批 / 批量提交 5 个处理器共用）；`formula_settings/propagation.propagate_note` 1 处；`note_stale_service` 2 处（`mark_sections_stale_by_wp` / `_by_report`，全仓无调用方）；`mark_notes_stale_for_report_change` 出错后的全量兜底 `UPDATE` 1 处；`stale_propagation_engine._mark_stale_by_uri` 1 处原生 SQL（依赖图传播，数据导入、调整分录、底稿保存等经 `stale_engine.on_change` 到达）。探针另命中的 `_impl.py` 一处写的是 `FinancialReport`、`stale_propagation_engine.py` 一处是文档字符串，不计。合并附注 `consol_note_data` 另有 3 处置过期（`consol_note_formula_service.fill_by_formula`、`consol_note_value_change_service.on_note_section_saved`、`consol_push_service._mark_notes_stale`），该表没有来源列 | 成立；真库 227 行过期标记没有一行记下来源 |
| 2 | R2：值不变不清 stale | `DisclosureEngine` 刷新绑定（`refresh-all-bindings` 路径）逐格比较、只在有格变化时计入 `sections_recomputed`，路由只对 `sections_recomputed` 清过期 ⇒ 重算成功但值未变的章节保持过期 | 成立 |
| 3 | R1：同一格多个写入方 | 附注 `table_data` 的写入方现读至少 11 类：绑定生成 / 刷新（`DisclosureEngine`）、底稿同步（`wp_disclosure_sync_service` 三个入口，载荷来自前端 builder：`export function build\w*SyncPayload` 69 个定义 / 59 个文件 / 67 个不同名字，其中 2 个文件是测试，与 `disclosure-payload-authority-source` 同口径；复数形式 `…SyncPayloads` 42 个 / 25 个文件）、公式推送 `formula_push.note_writer`、附注执行器、披露刷新、从底稿拉取（`pull-from-workpapers`）、离屏同步（D2 首个）、正文批量编制、结构重对齐、AI 采纳、编辑器手工保存 | 成立；需拍板后才能定归属 |
| 4 | R3：试算平衡表手工值读不回 | `TrialBalance.vue` 的 `_mergeSavedTbSummary` 读 `saved.data.rows` / `saved.rows`，而 `GET /api/consol-worksheet-data/{pid}/{year}/{sheet_key}` 返回 `{project_id, year, sheet_key, content, version, updated_at}`，保存的行在 `content.rows` ⇒ 重载一律不恢复、断开公式标记丢失；保存 `PUT` 带 `validateStatus: s < 600`，服务端拒绝也提示「已保存」。保存值只被高级查询 `_query_tb_summary` 读取 | 成立 |
| 5 | R4：`useEditorSave.ts` 与其余 14 处 | 前端源码里 `validateStatus` 出现 144 处。按「就近调用」粗分为写请求的 19 处 / 12 个文件：`ConsolNoteTab.vue` 6 处，`ProjectDashboard.vue`、`FormulaManagerDialog.vue` 各 2 处，`TrialBalance.vue`、`SyncStatusIndicator.vue`、`CustomQueryDialog.vue`、`OcrFieldsDrawer.vue`、`PriorYearCompareDrawer.vue`、`WorkpaperLifecycleView.vue`、`useCrossCheckRules.ts`、`useReportMapping.ts`、`stores/wizard.ts` 各 1 处（`wizard.ts` 这处很可能是 GET 被误判）。另有 `useEditorSave.ts`、`useEditorUniver.ts` 各 1 处粗分判不出请求方法，需求点名的 `useEditorSave.ts` 即其一。粗分口径会把邻近的 GET 误判，实施时用 TypeScript 语法树现算精确清单 | 规模比交接大（候选 21 处 / 14 个文件），数字待精确现算 |
| 6 | 依赖 | 附注权威源拍板仍未做（memory「全链打通阶段三待拍板②」）；`note-pull-header-formula-closure` 已把部分章节改为「刷新时从底稿披露表拉取」并建了离屏同步框架，是拍板方向的事实进展 | 成立 |

## 2. 架构裁定

**ADR-WOS-01 附注过期状态机单一写入口（R2）。** 新模块 `backend/app/services/stale_state.py`：`mark_note_stale(db, project_id, *, source, sections=None, year=None)` 与 `clear_note_stale(db, project_id, *, sections, year=None, reason)`，只管 `disclosure_notes`（唯一有来源列的过期表）。底子用现有的 `disclosure_stale_marker.mark_sections_stale`：它已带 `source` 参数，且只改过期标记、不动 `table_data`，扩展为 `sections=None` 表示整项目年度，不另起一套。`source` 取枚举 `StaleSource`：已有值 `workpaper_saved / report / report_fallback / disclosure_refresh_no_data`，新增 `consol_child_changed / rollback / adjustment / ledger_activated / workpaper_reviewed / formula_settings / trial_balance …`（实施时按写入点现读补全，每个值写中文含义）。标记时同时写 `is_stale` 与 `stale_source`，清除时把 `stale_source` 置空；清除点（置 `is_stale = false` 的位置）一并改调 `clear_note_stale`，数量在任务 0 现算。§1 第 1 行的 14 处全部改调：已写来源的 4 处换成调用；不写来源的 10 处补来源，其中共用 helper `_mark_disclosure_notes_stale_for_project_year` 加 `source` 参数，由 5 个处理器各自传入（`ledger_activated` / `workpaper_reviewed` / `adjustment`），`_mark_stale_by_uri` 按传播起点 URI 的前缀定来源（`TB:` ⇒ `trial_balance`、`ADJ:` ⇒ `adjustment` …，实施时现读起点清单），`mark_notes_stale_for_report_change` 的出错兜底写 `report_fallback`；`note_stale_service` 两个无调用方的方法按删旧代码铁律删除（删前 grep 0 调用方、删前后测试全绿），不改调。AST + SQL 文本守卫：`backend/app` 内除 `stale_state.py` 外不得出现对 `DisclosureNote.is_stale` 的赋值 / `.values(is_stale=…)` 或 `UPDATE disclosure_notes SET is_stale`（带违规样本自检）。报表过期沿用母 spec `report_freshness`。合并附注 `consol_note_data` 的 3 处与底稿预填没有来源列，不进本模块（§4 D4）。

**ADR-WOS-02 重算成功即清过期（R2）。** 附注的「重算」类入口（刷新绑定、从底稿拉取、附注执行器的 auto_calc 回写；合并附注的「按公式填入」写的是 `consol_note_data`，不在此列）在**本章节计算成功**时调用 `clear_note_stale`，不论值是否变化；只有计算失败或部分失败时保持过期并把失败原因写进 `stale_source` 对应的说明字段（附注 `table_data._stale_reason`）。返回体区分 `changed`（值变）与 `recomputed`（值未变、已清过期），与母 spec Draft Refresh 的计数口径一致。

**ADR-WOS-03 附注写入方登记表（R1 第一段）。** `backend/app/services/note_writers.py` 登记每个写入方：`writer_id`、入口函数、写的字段（`rows[].values` / `sub_table_data` / `_tables` / `text_content` / `_formulas` / `_user_formulas` / 过期标记）、触发方式、是否尊重 `_cell_modes`（manual / locked）。AST 守卫：`backend/app` 内对 `DisclosureNote.table_data` / `text_content` 的写入（赋值、`flag_modified(note, "table_data")`、`DisclosureEngine.update_note` 调用）所在函数都必须在登记表里；登记表条目真实存在。前端 `*SyncPayload` builder 的数量冻结为现算值（只许变少），与 `disclosure-payload-authority-source` 已有的 builder 守卫同口径、不重复造守卫（实施时现读该守卫并直接引用）。

**ADR-WOS-04 拍板后的唯一写方强制（R1 第二段，§4 D1）。** 拍板后在登记表上为每个「章节 × 字段」指定唯一写方（矩阵按章节编号键控、来自 `note_workpaper_sync_registry.json` 的章节清单），写入函数在写之前查矩阵：非所有者写 ⇒ 记一条「被拒写入」日志并跳过该字段（不报错、不阻断其他字段），手工保存与锁定格不受矩阵限制（用户意图优先）。矩阵与前后端对拍守卫按拍板结论设计，本文不预先写死。

**ADR-WOS-05 试算平衡表手工值读回（R3）。** `_mergeSavedTbSummary` 改读 `saved.content.rows`（保留对 `saved.data.rows` 的兼容读取一个版本，并在代码注释写明移除条件）；`saveTbSummary` 去掉宽放行，失败交全局拦截器与 `handleApiError`，成功后用响应里的 `version` 更新本地版本，并在保存后立即重载一次核对（逐行比对 `unadjusted / rcl_dr / rcl_cr / formula_detached`，不一致提示）。

**ADR-WOS-06 写请求按状态码判成功（R4）。** 写请求（POST / PUT / PATCH / DELETE）一律不带「放行 ≥ 400」的 `validateStatus`；确有业务含义的非 2xx（如向导「已完成时 404 正常」）改写成显式列举（`s < 300 \|\| s === 404`）并在调用处处理该码。vitest 源码守卫 `writeRequestValidateStatusGuard.spec.ts`：用 TypeScript 编译器 API 找 `api|http.(post|put|patch|delete)` 调用的配置对象，`validateStatus` 的函数体若对 `>= 400` 的任意码返回真且不是显式列举 ⇒ 红；带违规样本自检。母 spec 已改的公式管理 3 处不重复。

## 3. 测试与变异

- 单元：`stale_state` 按章节与整项目年度两种范围的标记 / 清除；`StaleSource` 每个值都有中文含义；守卫违规样本自检。
- 真 PG（回滚事务内【测试】项目）：触发调整分录审批事件后附注 `stale_source = 'adjustment'`；回滚、合并下级变更、公式设置变更各一条来源断言；刷新绑定一节值未变 ⇒ 过期被清、返回 `recomputed`；计算失败 ⇒ 过期保留并有原因。共享库只读统计：任务完成后新产生的过期行 `stale_source` 非空率 = 100%（存量 227 行不回填，单列）。
- 端点：`consol-worksheet-data` 保存后读回（后端端点测试，断言响应 `content.rows`）。
- 前端 vitest：`_mergeSavedTbSummary` 读 `content.rows`；保存失败不提示「已保存」；写请求守卫。
- 磁盘变异：任一批量标记恢复为只置 `is_stale` ⇒ 守卫红；清过期条件改回「有格变化才清」⇒ `recomputed` 用例红；读回改回 `saved.data.rows` ⇒ vitest 红；任一写请求加回 `s < 600` ⇒ 写请求守卫红。

## 4. 待用户拍板

| # | 事项 | 建议 |
|---|---|---|
| D1 | 附注权威源（ADR-DPA-001「留前端」vs「经公式管理自动推」） | 按章节交接：已接「从底稿拉取 / 离屏同步」的章节以后端为唯一写方，其余章节暂留前端同步，前后端对拍守卫钉住两边一致（memory 记录的建议方向）；拍板后执行 ADR-WOS-04 |
| D2 | 存量 227 行无来源的过期标记 | 不回填（无法确定当时来源）；界面显示「过期（来源未记录）」 |
| D3 | 试算平衡表保存值的旧格式兼容读取 | 保留一个版本后删除 |
| D4 | 合并附注 `consol_note_data` 与底稿预填的过期来源（两处都没有来源列，§1 第 1 行） | 本 spec 不做；界面目前不显示这两处的过期来源，有需求时再加列（需迁移） |
