# 设计文档：S3　写入方归属与过期状态机（formula-writer-ownership-and-stale）

> 需求编号：requirements §1 四条依次记 R1（写入方登记与 D1 后唯一写方矩阵）、R2（附注 stale 状态机与重算结果契约）、R3（试算平衡表手工值读回核验）、R4（前端写请求按状态码判成功）。
> 当前实施依据：文末 §11「2026-10-31 重基线实施勘误」覆盖本文与旧基线冲突的数量、路径和验收解释。所有调用点和数字以任务 0 的 AST/源码现算为准，不把旧 HEAD `4c0a1e0a6` 或旧整合树作为当前基线。

## 0. 结论

R1 依赖附注权威源拍板（ADR-DPA-001「留前端」与「经公式管理自动推」的冲突，至今未拍板），R2~R4 不依赖。所以本 spec 分两段：第一段先做不需要拍板的三件事 —— 过期状态机（统一写入口，`stale_source` 必填，「重算成功且值不变」也清过期）、试算平衡表手工值读回、宽放行写请求改按状态码判成功；同时把附注写入方的现状清单做成可校验的登记表并冻结（新写入方必须登记）。第二段在拍板后按登记表落「每个章节每个字段只有一个写方」的强制。

## 1. 现状复核

> 历史基线记录。当前实施不得直接采用本节的固定数量或旧路径；以文末 §11 任务 0 的现算产物为准。

| # | 交接结论 | 现算 | 判定 |
|---|---|---|---|
| 1 | R2：`stale_source` 从未写入 | 共享库 `disclosure_notes` 1096 行，`is_stale = true` 227 行，`stale_source` 非空 **0** 行。整合树 AST 现算，把 `disclosure_notes` 置为过期的写入点共 **14 处 / 8 个文件**。写了来源的 4 处：`disclosure_stale_marker.mark_sections_stale`（原生 SQL，`workpaper_saved`）、`note_disclosure_refresh_service.refresh_note_section`（`disclosure_refresh_no_data`）、`report_note_sync_service.mark_notes_stale_for_report_change` 2 处（`report` / `report_fallback`）。只置 `is_stale`、不写来源的 10 处：`consol_note_stale_handler.mark_consol_sections_stale` 2 处原生 SQL（合并项目下级变更）；`event_handlers/_impl.py` 3 处 —— `_mark_downstream_stale_on_rollback`（回滚后）、`_mark_reports_stale_on_adjustment`（调整分录变更）、`_mark_disclosure_notes_stale_for_project_year`（整项目年度批量，账套激活、底稿复核通过、调整分录审批 / 撤销审批 / 批量提交 5 个处理器共用）；`formula_settings/propagation.propagate_note` 1 处；`note_stale_service` 2 处（`mark_sections_stale_by_wp` / `_by_report`，全仓无调用方）；`mark_notes_stale_for_report_change` 出错后的全量兜底 `UPDATE` 1 处；`stale_propagation_engine._mark_stale_by_uri` 1 处原生 SQL（依赖图传播，数据导入、调整分录、底稿保存等经 `stale_engine.on_change` 到达）。探针另命中的 `_impl.py` 一处写的是 `FinancialReport`、`stale_propagation_engine.py` 一处是文档字符串，不计。合并附注 `consol_note_data` 另有 3 处置过期（`consol_note_formula_service.fill_by_formula`、`consol_note_value_change_service.on_note_section_saved`、`consol_push_service._mark_notes_stale`），该表没有来源列 | 成立；真库 227 行过期标记没有一行记下来源 |
| 2 | R2：值不变不清 stale | `DisclosureEngine` 刷新绑定（`refresh-all-bindings` 路径）逐格比较、只在有格变化时计入 `sections_recomputed`，路由只对 `sections_recomputed` 清过期 ⇒ 重算成功但值未变的章节保持过期 | 成立 |
| 3 | R1：同一格多个写入方 | 附注 `table_data` 的写入方现读至少 11 类：绑定生成 / 刷新（`DisclosureEngine`）、底稿同步（`wp_disclosure_sync_service` 三个入口，载荷来自前端 builder：`export function build\w*SyncPayload` 69 个定义 / 59 个文件 / 67 个不同名字，其中 2 个文件是测试，与 `disclosure-payload-authority-source` 同口径；复数形式 `…SyncPayloads` 42 个 / 25 个文件）、公式推送 `formula_push.note_writer`、附注执行器、披露刷新、从底稿拉取（`pull-from-workpapers`）、离屏同步（D2 首个）、正文批量编制、结构重对齐、AI 采纳、编辑器手工保存 | 成立；需拍板后才能定归属 |
| 4 | R3：试算平衡表手工值读不回 | `TrialBalance.vue` 的 `_mergeSavedTbSummary` 读 `saved.data.rows` / `saved.rows`，而 `GET /api/consol-worksheet-data/{pid}/{year}/{sheet_key}` 返回 `{project_id, year, sheet_key, content, version, updated_at}`，保存的行在 `content.rows` ⇒ 重载一律不恢复、断开公式标记丢失；保存 `PUT` 带 `validateStatus: s < 600`，服务端拒绝也提示「已保存」。保存值只被高级查询 `_query_tb_summary` 读取 | 成立 |
| 5 | R4：`useEditorSave.ts` 与其余 14 处 | 前端源码里 `validateStatus` 出现 144 处。按「就近调用」粗分为写请求的 19 处 / 12 个文件：`ConsolNoteTab.vue` 6 处，`ProjectDashboard.vue`、`FormulaManagerDialog.vue` 各 2 处，`TrialBalance.vue`、`SyncStatusIndicator.vue`、`CustomQueryDialog.vue`、`OcrFieldsDrawer.vue`、`PriorYearCompareDrawer.vue`、`WorkpaperLifecycleView.vue`、`useCrossCheckRules.ts`、`useReportMapping.ts`、`stores/wizard.ts` 各 1 处（`wizard.ts` 这处很可能是 GET 被误判）。另有 `useEditorSave.ts`、`useEditorUniver.ts` 各 1 处粗分判不出请求方法，需求点名的 `useEditorSave.ts` 即其一。粗分口径会把邻近的 GET 误判，实施时用 TypeScript 语法树现算精确清单 | 规模比交接大（候选 21 处 / 14 个文件），数字待精确现算 |
| 6 | 依赖 | 附注权威源拍板仍未做（memory「全链打通阶段三待拍板②」）；`note-pull-header-formula-closure` 已把部分章节改为「刷新时从底稿披露表拉取」并建了离屏同步框架，是拍板方向的事实进展 | 成立 |

## 2. 架构裁定

> 下列 ADR 是原始设计基线。与 §11 冲突时，以 §11 的事务边界、结果集合、R3 核验口径和 R4 AST 范围为准。

**ADR-WOS-01 附注过期状态机单一写入口（R2）。** 新模块 `backend/app/services/stale_state.py`：`mark_note_stale(db, project_id, *, source, sections=None, year=None)` 与 `clear_note_stale(db, project_id, *, sections, year=None, reason)`，只管 `disclosure_notes`（唯一有来源列的过期表）。底子用现有的 `disclosure_stale_marker.mark_sections_stale`：它已带 `source` 参数，且只改过期标记、不动 `table_data`，扩展为 `sections=None` 表示整项目年度，不另起一套。`source` 取枚举 `StaleSource`：已有值 `workpaper_saved / report / report_fallback / disclosure_refresh_no_data`，新增 `consol_child_changed / rollback / adjustment / ledger_activated / workpaper_reviewed / formula_settings / trial_balance …`（实施时按写入点现读补全，每个值写中文含义）。标记时同时写 `is_stale` 与 `stale_source`，清除时把 `stale_source` 置空；清除点（置 `is_stale = false` 的位置）一并改调 `clear_note_stale`，数量在任务 0 现算。§1 第 1 行的 14 处全部改调：已写来源的 4 处换成调用；不写来源的 10 处补来源，其中共用 helper `_mark_disclosure_notes_stale_for_project_year` 加 `source` 参数，由 5 个处理器各自传入（`ledger_activated` / `workpaper_reviewed` / `adjustment`），`_mark_stale_by_uri` 按传播起点 URI 的前缀定来源（`TB:` ⇒ `trial_balance`、`ADJ:` ⇒ `adjustment` …，实施时现读起点清单），`mark_notes_stale_for_report_change` 的出错兜底写 `report_fallback`；`note_stale_service` 两个无调用方的方法按删旧代码铁律删除（删前 grep 0 调用方、删前后测试全绿），不改调。AST + SQL 文本守卫：`backend/app` 内除 `stale_state.py` 外不得出现对 `DisclosureNote.is_stale` 的赋值 / `.values(is_stale=…)` 或 `UPDATE disclosure_notes SET is_stale`（带违规样本自检）。报表过期沿用母 spec `report_freshness`。合并附注 `consol_note_data` 的 3 处与底稿预填没有来源列，不进本模块（§4 D4）。

**ADR-WOS-02 重算成功即清过期（R2）。** 附注的「重算」类入口（刷新绑定、从底稿拉取、附注执行器的 auto_calc 回写；合并附注的「按公式填入」写的是 `consol_note_data`，不在此列）在**本章节计算成功**时调用 `clear_note_stale`，不论值是否变化；只有计算失败或部分失败时保持过期并把失败原因写进 `stale_source` 对应的说明字段（附注 `table_data._stale_reason`）。返回体区分 `changed`（值变）与 `recomputed`（值未变、已清过期），与母 spec Draft Refresh 的计数口径一致。

**ADR-WOS-03 附注写入方登记表（R1 第一段）。** `backend/app/services/note_writers.py` 登记每个写入方：`writer_id`、入口函数、写的字段（`rows[].values` / `sub_table_data` / `_tables` / `text_content` / `_formulas` / `_user_formulas` / 过期标记）、触发方式、是否尊重 `_cell_modes`（manual / locked）。AST 守卫：`backend/app` 内对 `DisclosureNote.table_data` / `text_content` 的写入（赋值、`flag_modified(note, "table_data")`、`DisclosureEngine.update_note` 调用）所在函数都必须在登记表里；登记表条目真实存在。前端 `*SyncPayload` builder 的数量冻结为现算值（只许变少），与 `disclosure-payload-authority-source` 已有的 builder 守卫同口径、不重复造守卫（实施时现读该守卫并直接引用）。

**ADR-WOS-04 拍板后的唯一写方强制（R1 第二段，§4 D1）。** 拍板后在登记表上为每个「章节 × 字段」指定唯一写方（矩阵按章节编号键控、来自 `note_workpaper_sync_registry.json` 的章节清单），写入函数在写之前查矩阵：非所有者写 ⇒ 记一条「被拒写入」日志并跳过该字段（不报错、不阻断其他字段），手工保存与锁定格不受矩阵限制（用户意图优先）。矩阵与前后端对拍守卫按拍板结论设计，本文不预先写死。

**ADR-WOS-05 试算平衡表手工值读回（R3）。** `_mergeSavedTbSummary` 改读 `saved.content.rows`（保留对 `saved.data.rows` 的兼容读取一个版本，并在代码注释写明移除条件）；`saveTbSummary` 去掉宽放行，失败交全局拦截器与 `handleApiError`，成功后用响应里的 `version` 更新本地版本，并在保存后立即重载一次核对（逐行比对 `unadjusted / rcl_dr / rcl_cr / formula_detached`，不一致提示）。

**ADR-WOS-06 写请求按状态码判成功（R4）。** 写请求（POST / PUT / PATCH / DELETE）一律不带「放行 ≥ 400」的 `validateStatus`；确有业务含义的非 2xx（如向导「已完成时 404 正常」）改写成显式列举（`s < 300 \|\| s === 404`）并在调用处处理该码。vitest 源码守卫 `writeRequestValidateStatusGuard.spec.ts`：用 TypeScript 编译器 API 找 `api|http.(post|put|patch|delete)` 调用的配置对象，`validateStatus` 的函数体若对 `>= 400` 的任意码返回真且不是显式列举 ⇒ 红；带违规样本自检。母 spec 已改的公式管理 3 处不重复。

## 3. 测试与变异

> 原始测试基线。当前最低测试集合和变异边界以 §11.8 为准。

- 单元：`stale_state` 按章节与整项目年度两种范围的标记 / 清除；`StaleSource` 每个值都有中文含义；守卫违规样本自检。
- 真 PG（回滚事务内【测试】项目）：触发调整分录审批事件后附注 `stale_source = 'adjustment'`；回滚、合并下级变更、公式设置变更各一条来源断言；刷新绑定一节值未变 ⇒ 过期被清、返回 `recomputed`；计算失败 ⇒ 过期保留并有原因。共享库只读统计：任务完成后新产生的过期行 `stale_source` 非空率 = 100%（存量 227 行不回填，单列）。
- 端点：`consol-worksheet-data` 保存后读回（后端端点测试，断言响应 `content.rows`）。
- 前端 vitest：`_mergeSavedTbSummary` 读 `content.rows`；保存失败不提示「已保存」；写请求守卫。
- 磁盘变异：任一批量标记恢复为只置 `is_stale` ⇒ 守卫红；清过期条件改回「有格变化才清」⇒ `recomputed` 用例红；读回改回 `saved.data.rows` ⇒ vitest 红；任一写请求加回 `s < 600` ⇒ 写请求守卫红。

## 4. 待用户拍板

> 本节保留原始决策记录；D1 的矩阵维度、manual/locked 语义和 D3 当前取舍以 §11.5、§11.10 为准。

| # | 事项 | 建议 |
|---|---|---|
| D1 | 附注权威源（ADR-DPA-001「留前端」vs「经公式管理自动推」） | 按章节交接：已接「从底稿拉取 / 离屏同步」的章节以后端为唯一写方，其余章节暂留前端同步，前后端对拍守卫钉住两边一致（memory 记录的建议方向）；拍板后执行 ADR-WOS-04 |
| D2 | 存量 227 行无来源的过期标记 | 不回填（无法确定当时来源）；界面显示「过期（来源未记录）」 |
| D3 | 试算平衡表保存值的旧格式兼容读取 | 保留一个版本后删除 |
| D4 | 合并附注 `consol_note_data` 与底稿预填的过期来源（两处都没有来源列，§1 第 1 行） | 本 spec 不做；界面目前不显示这两处的过期来源，有需求时再加列（需迁移） |


## 11. 2026-10-31 重基线实施勘误（当前实施依据）

> 本节覆盖本文前面与当前代码树、requirements.md 或 tasks.md 冲突的同名结论。旧 §1 的 14 处、R3 旧读取 bug、R4 的固定 14 处均只保留为历史发现，不再作为当前分母或实施指令。

### 11.1 当前基线与重算原则

1. 当前工作区的代码 HEAD 已不再是旧文档记录的 `4c0a1e0a6`；实施时由任务 0 记录当时的 HEAD、候选树和源码摘要。若并发会话使 HEAD 在任务 0 后前移，必须在候选提交树上重跑，不用工作区旧快照替代。
2. 任务 0 输出 `tmp_writer_ownership/baseline/`：
   - `baseline.json`：HEAD、扫描时间、文件 sha256、当前分母和扫描器版本；
   - `disclosure_stale_writers.json`：所有 DisclosureNote 标记/清除入口及事务边界；
   - `write_validate_status.json`：AST 判定的写请求、合法例外和文件归属；
   - `tb_persistence.json`：试算表读写链和现有测试证据。
3. 数量只用于本次候选树验收，不写回为永久常量。所有只许减少的棘轮必须以文件/函数身份为键，不以行号为键。
4. 当前源码已存在 `useTbSummaryPersistence.ts`、`consolWorksheetDataApi.ts` 和对应 vitest。R3 不再按旧的 `TrialBalance.vue` 直接读取 `saved.data.rows` 作为待修生产缺陷；任务只核验现有链路，除非验收发现回归。

### 11.2 R2 的真实写入/清除边界

R2 的统一入口只约束 `DisclosureNote`，不约束同名但不同模型的 `is_stale`。任务 0 必须至少扫描以下实际路径，并现读是否仍存在：

- `backend/app/services/disclosure_stale_marker.py`：已有 `mark_sections_stale(..., source=...)`，应成为兼容薄壳或改调 `stale_state`；不得继续让默认字符串绕过来源校验。
- `backend/app/services/event_handlers/_impl.py`：回滚、账套激活、底稿复核、调整分录事件的整项目标记。
- `backend/app/services/consol_note_stale_handler.py`：合并下级变化对 `disclosure_notes` 的原生 SQL 标记；它虽然名字含 consol，但目标表仍在 R2 范围。
- `backend/app/services/stale_propagation_engine.py`：`_mark_stale_by_uri` 的 NOTE 分支。该函数当前没有传播起点参数，实施时必须显式传入 `source` 或 `source_uri` 后再落来源。
- `backend/app/services/formula_settings/stale_marks.py` 与 `propagation.py`：S4 已落地的附注标记，必须改调统一入口并保持 outbox 同事务。
- `backend/app/services/note_stale_service.py`、`report_note_sync_service.py`：标记和清除路径；无调用方的旧标记方法只有在任务 0 证明 0 调用后才能删除。
- `backend/app/services/formula_push/engine.py`、`wp_disclosure_sync_service.py`、`routers/note_wp_mapping.py`：成功写入/重算后的清除路径，必须同时清 `stale_source`。

统一入口的事务约定：

```python
async def mark_note_stale(
    db, project_id, *, source: StaleSource,
    sections: Sequence[str] | None = None, year: int | None = None,
) -> int: ...

async def clear_note_stale(
    db, project_id, *, sections: Sequence[str],
    year: int | None = None,
) -> int: ...
```

两者只使用传入 `db`，只 flush，不 commit，不自行 rollback；调用方按自己的事务边界决定是否回滚。事件型 fail-soft 只能在事件编排层记录 warning，不能在状态入口内吞掉数据库异常。

`StaleSource` 保存稳定英文编码，中文含义由后端/前端共享映射提供。初始值包括现有 `workpaper_saved`、`report`、`report_fallback`、`disclosure_refresh_no_data`，以及回滚、调整、账套激活、底稿复核、公式设置、试算表、合并下级变化所需的编码。任务 0 必须对现有字符串做反向清单，新增值不得超过数据库 `String(32)` 限制；未知值在写入前拒绝，而不是静默落库。

本 spec 不把失败原因写入 `table_data._stale_reason`。失败原因作为章节级结果 `errors` 和结构化日志返回；`stale_source` 只表示来源，避免下一次 table_data 重建覆盖诊断信息。若产品要求刷新页面后仍显示失败原因，另建带持久化字段的迁移需求，不用 JSONB 旁路伪装。

### 11.3 R2 重算结果契约

`DisclosureEngine.refill_sections()` 当前只有在 `_values_differ()` 为真时才把章节加入 `sections_recomputed`。这不能继续作为 stale 清除判据。实施时保留兼容字段，但新增明确集合：

```python
@dataclass
class NoteRecomputeOutcome:
    requested_sections: list[str]
    changed_sections: list[str]
    recomputed_sections: list[str]  # 计算完整成功，值不变也包括
    failed_sections: list[str]
    cleared_sections: list[str]
    errors: list[dict[str, str]]  # section / stage / message
```

规则：

- 绑定取数、表内公式二次求值、最终公式写回均成功，才可进入 `recomputed_sections`；
- 只有值实际变化才进入 `changed_sections`；
- 纯文本、没有可计算表格、解析失败、部分表失败进入 `failed_sections` 或明确的 skipped 集合，不得进入清除集合；
- `clear_note_stale` 只接收 `recomputed_sections` 与当前项目/年度；
- 每个入口都必须把 `cleared_sections` 原样返回，不能只返回一个模糊的 `stale_cleared` 数字；
- `refresh-all-bindings`、`refresh-from-workpapers`、后台 `NoteStaleService.refresh_stale_sections`、单章节刷新和公式推送都必须使用同一成功判定。

特别注意：当前 `note_wp_mapping.py` 在公式二次求值失败后仍可能依据 `report.sections_recomputed` 清 stale。实现必须按章节记录公式阶段错误，失败章节不得被清除。

### 11.4 R1a writer registry

新建 `backend/app/services/note_writers.py`，但先只冻结登记，不执行 D1 后的唯一写方拒绝。建议数据结构：

```python
@dataclass(frozen=True)
class NoteWriterSpec:
    writer_id: str
    entrypoint: str                 # module:function
    trigger: str
    scopes: tuple[str, ...]          # project / section / table
    template_types: tuple[str, ...]  # listed / soe / unknown
    fields: tuple[str, ...]          # canonical field keys
    respects_cell_modes: bool
    transaction: str                # caller / own_session / post_commit
    status: str                     # active / legacy / dead_candidate
```

规范字段键不得直接把任意 Python 路径当作矩阵键。第一版至少统一为：

- `table.rows.values`
- `table.sub_table_data`
- `table._tables`
- `text_content`
- `table.formulas`
- `table.user_formulas`
- `stale_state`

登记守卫必须覆盖以下写法：

1. `DisclosureNote` 属性赋值和构造/更新载荷；
2. `flag_modified(note, "table_data")` 及其调用函数；
3. SQLAlchemy `update(...).values(table_data=...)` / `values(text_content=...)`；
4. 原生 SQL 更新 `disclosure_notes.table_data` / `text_content`；
5. 通过 `DisclosureEngine.update_note`、写回 adapter 或动态 registry 间接写入的入口；
6. JSONB 原地修改后赋回或 `flag_modified` 的函数闭包。

守卫必须同时断言：

- 每个生产入口恰有一个登记项；
- `writer_id` 不重复；
- 登记的入口真实存在；
- 登记字段属于规范字段键；
- 故意排除项有可验证的 `excluded_reason` 和反向断言；
- 新增未登记 writer 的磁盘变异会变红。

### 11.5 R1b 唯一写方矩阵

D1 拍板后，矩阵键至少为：

```text
(template_type, note_section, table_key, field_key)
```

值为 `writer_id` 和行为策略。不能只按章节号键控，因为 listed/soe 可以共享章节号而结构不同。

自动写入方不匹配矩阵时：

- 该字段不写入；
- 其他合法字段继续处理；
- 记录结构化 `blocked_write` 日志；
- 响应返回 `blocked_writes[{section, table, field, writer_id, owner_id, reason}]`；
- 未知矩阵项在强制阶段 fail-closed，不得因为矩阵缺行而放行。

手工保存不是“任意 writer 绕过”。手工入口必须经过现有编辑权限、项目锁和 `manual` 模式检查；自动 writer 永远不得覆盖 `locked` 单元格。具体 bypass 规则由 D1 写入矩阵附录后才能实施。

### 11.6 R3 当前实现解释

当前链路应优先复用：

```text
TrialBalance.vue
  → useTbSummaryPersistence.hydrate()
  → loadWorksheetData()
  → response.content → data.rows

saveTbSummary()
  → tbSummaryPersistence.flush(true)
  → saveWorksheetData()
  → response.version / CAS
```

验收重点是页面刷新后的真实读回、零值、`formula_detached` 和手工 RJE 标记。若这些条件已满足，不再新建另一套 `_mergeSavedTbSummary` API 读取逻辑。设计旧文中“必须保存后立即 GET”不作为本 spec 的硬要求；任务只验证服务端版本回执和页面刷新读回。

### 11.7 R4 AST 守卫边界

任务 0 生成写请求清单，任务 5 消费清单。守卫使用 TypeScript Compiler API，按 import alias 和调用表达式判定 HTTP 方法，不用跨行正则猜测。范围包括 `api`、`http`、`httpApi` 及项目已有的 API 包装器；只扫描应用源码，不把测试夹具当生产入口。

违规条件：

- POST/PUT/PATCH/DELETE 配置中的 `validateStatus` 对任意 `s >= 400` 返回 true；
- `validateStatus` 让 4xx/5xx 继续进入成功分支；
- catch 后仍清 dirty、升级版本或显示成功文案。

合法例外必须写成显式状态集合，例如 `s < 300 || s === 404`，并在同一调用点处理 404。GET 的 blob 错误解析和轮询兼容不因本任务一并删除。

### 11.8 测试与变异最低集合

#### 后端

- `stale_state`：指定章节/整项目年度标记、source 校验、清除 source、只 flush 不 commit；SQLite 只测纯函数/SQL 构造，PG 测 `ANY`/JSONB/事务行为；
- 真实 `DisclosureEngine.refill_sections`：值变、值不变、纯文本、resolver 失败、公式二次求值失败五类章节；不得用测试副本替换生产 `refill_sections`；
- S4：在同一事务中写公式定义、outbox 和附注 stale，回滚后三者均无持久化；投递失败只进入 outbox 重试，不清除 stale；
- 全部现算 writer 的登记闭合性和 stale 写入来源；新产生 stale 行的 source 非空率按新写入行统计为 100%；
- 变异：删除 source、把成功判据改回“值发生变化”、让公式失败章节进入清除集合、恢复任一直接 SQL/ORM stale 写入，守卫和 PG 用例均须变红。

#### 前端

- `TrialBalance.vue` 刷新后读回零值、手工重分类、`formula_detached`；不重复测试已删除的旧 `saved.data.rows` 代码；
- `writeRequestValidateStatusGuard.spec.ts`：生产写请求扫描、合法 GET 例外、别名客户端、宽放行变异；
- 至少一个 `useEditorSave` 或同类真实 composable 用例：注入 409/422/500，不显示成功、不清 dirty、不推进版本；
- stale 来源映射：已知 source、未知 source、`null` 来源未记录三态中文显示。

#### 浏览器

【测试】项目上验证：

1. 附注标记后看到来源中文文案；
2. 值不变的刷新后 stale 消失且返回 `recomputed`；
3. 失败章节仍显示过期；
4. 试算平衡表手工值保存、刷新页面、零值和断开标记仍在；
5. 写请求失败只显示错误，不显示成功 toast。

### 11.9 与 S4 的接线清单

S4 已完成的代码不在本 spec 中重新设计，但 S3 实施必须完成以下接缝：

- `formula_settings.stale_marks.mark_note_stale` 改为调用 `stale_state.mark_note_stale`；
- `formula_settings.propagation.propagate_note` 保持定义、outbox、stale 标记同一事务，不在传播 worker 中重复标记；
- S4 的 `source='formula_settings'` 通过 `StaleSource` 校验；
- S4 失败重试不能把 stale 标记提前清除；
- 公式设置相关测试加入 S3 的只候选红对比，但不改 S4 历史任务状态。

### 11.10 用户决策

| # | 事项 | 当前状态 |
|---|---|---|
| D1 | 附注权威源按章节交接：前端同步 vs 公式管理/底稿拉取 | 2026-11-04 用户拍板「按建议来」：已接「从底稿拉取 / 离屏同步」的章节由后端取数链路唯一写入，其余章节暂留前端同步，加前后端对拍守卫。可执行口径与矩阵见 §13（任务 6） |
| D2 | 历史 227 行无来源 stale 是否回填 | 默认不回填，显示「来源未记录」 |
| D3 | 试算表保存后是否要求即时 GET 反读 | 本 spec 默认不要求；页面刷新读回为验收口径 |
| D4 | `consol_note_data` 与底稿预填是否新增来源列 | 不在本 spec，另立迁移需求 |

### 11.11 本轮文档修改边界

本次重整只修改 requirements/design/tasks 三件套，未修改生产代码、迁移、INDEX 或 memory。实施阶段允许触碰的生产文件由任务 0 的现算清单生成，禁止根据旧 §1 的文件数量手工扩散。

## 12. 2026-11-01 实施与验收记录

### 12.1 实施结果

任务 0~5 与任务 7 已完成，任务 6 继续依赖 D1，不以默认意见代替拍板：

- `stale_state.py` 成为 `DisclosureNote.is_stale/stale_source` 唯一写入口；标记与清除只 flush，事务由调用方控制；
- `RefillReport` 区分 requested / changed / recomputed / failed / cleared 与章节级错误；值不变但完整成功也清 stale，公式失败章节从清除集合剔除；
- `note_writers.py` 冻结 38 个 writer 身份，并由 AST/SQL 守卫覆盖 ORM 赋值、`flag_modified`、SQLAlchemy values、原生 SQL、间接门面与动态 values 盲点；D1 前不执行唯一写方拒绝；
- TB 继续复用 `useTbSummaryPersistence → consol-worksheet-data` 的现有 CAS 链，不建设第二套持久化；端点测试钉住 `content.rows`、零值、手工 RJE 和 `formula_detached`；
- 前端 16 个宽放行写请求收紧后，全树 AST 现算 `writes=0 / wide_writes=0`；GET 兼容配置不动；`useEditorSave` 的真实 409 改从错误响应读取，422/500 不再清 dirty 或显示成功；
- `formula_push/engine.py` 因触发行数门，把状态读取/保存与失败运行记录抽到 `formula_push/state_store.py`，engine 降至 998 行，算法和事务顺序保持不变。

### 12.2 自动化证据

- 后端：S3、S4 outbox/传播、formula push 核心选集 97 passed；真实 PostgreSQL 回滚用例 1 passed。PG 用例在同一事务内创建 `【测试】S3 stale 状态机回滚` 项目与附注，验证 adjustment 标记、值不变重算清除、formula_settings 失败保留；回滚后独立会话反查项目与附注均为 0。
- 前端：父提交与候选同口径测试为 `base_failed=4 / candidate_failed=4 / common=4 / candidate_only=0`；新增写请求与 await 宿主守卫 9 passed；收尾运行时修复相关 75 passed。区域 TypeScript 用已入库的 `tsconfig._writer-ownership.json`（include 里的 `useNoteRefresh.ts` 会传递拉入 `noteHeadlessDisclosure` 及其 provider 闭包）：远端基线 151 → 候选 149（`added 0 / resolved 2`，resolved 的两条正是本轮补的 `refreshed` / `total_notes` 必填字段），`fatal_markers=0` 排除 OOM 假零；剩余 149 条分布在 28 个本轮未改文件，本 spec 触及的 39 个前端文件上 0 条，不把范围外类型债删出扫描面冒充全绿。
- 构建：Vite production build 完整转换 3804+ 模块并成功产物；构建前依次抓到并修复 `useAiNoteCapture`、D3 凭证证据、`useMountOnFirstOpen`、`useNoteSaveFlow` 四组父提交断裂。
- 变异：任务 5 的 M1~M5 全红（两处恢复 `s<600`、删除 409 分支、失败后清 dirty、吞表间审核错误），三条阴性对照全绿；每条变异后 SHA-256 字节恢复。区域 tsc 注入 `number = string` 命中 TS2322，未 OOM。
- pre-commit：gitleaks、文件行数、UTF-8 全通过。首次因 `formula_push/engine.py` 1048 行超过 998 上限而失败，未跳钩子、未抬白名单，按 12.1 拆模块后通过。

### 12.3 浏览器证据

隔离前端/后端端口为 3032/9982，使用 `【UAT】子公司A` 作为测试上下文。所有会写业务数据的请求由 Playwright 拦截，真实后端只用于登录和只读项目上下文；共享库零写。后端状态写语义另由 12.2 的真实 PG 回滚用例覆盖。

浏览器 17/17：

1. 500 写请求不显示成功且只发送一次；429 显示连续催办提示并禁用按钮；
2. stale 已知来源 `adjustment` 显示“调整分录已变化”，未知来源显示“其他数据变化”，历史 NULL 显示“来源未记录”及“过期（来源未记录）”；
3. 值不变成功回执显示“已重新计算 1 个章节，数据未变化；已清除 1 个过期标记”，随后 stale 标签消失；
4. `failed_sections` 非空时不显示“数据已是最新”，章节仍显示过期来源；
5. TB 从 `content.rows` 读回零值、手工 RJE 12.34 与 `formula_detached` 剪刀标记；
6. pageerror 0。控制台仅有测试故意注入的 HTTP 500 / 429 两条资源错误。

证据：`tmp_writer_ownership/browser_result.json` 与三张截图。临时目录在收尾后清理，不入库。

### 12.4 验收期发现并修复的父提交断裂

这些缺陷不是 S3 引入，但阻断候选运行与浏览器验收，用户拍板逐一修复：

- `6f4c5a54a` 为剪贴板 HTTP 兼容错误地整文件回退 `useAiNoteCapture.ts`：恢复 `1154b99ca` 的名称/位置确认、扁平请求体、`lastRequest` 与幂等指纹，仅保留正交 `copyText` 改动；21 个契约测试通过；
- 同提交回退 `useD3VoucherCheck.ts`：恢复 `7954c575d` 的 D3-7 行级证据位置、上传绑定与刷新，仅保留 `newUuid`；26 个测试通过；
- `useMountOnFirstOpen` 被 TrialBalance/DisclosureEditor 引用但文件从未提交：补“首次打开后永久挂载”实现与 2 个测试；
- `useNoteSaveFlow` 被 DisclosureEditor 引用但文件从未提交：补手工/自动保存差异、失败状态、保存中切章隔离与作用域清理，4 个测试；
- 附注就绪度原只识别 4 个来源且其余都显示“待刷新”：新增 16 个来源映射，与后端 `StaleSource/STALE_SOURCE_LABELS` 逐成员对拍；刷新提示接入 recomputed / failed / cleared 结果集合。

浏览器首次启动时发现的 5 个 batch-project 缺失 service 已由并发提交 `86005b6b6` 连同模型/测试正式补入，未并入 S3 提交。该提交后干净树仍有两处启动断裂，本轮按用户“逐一修复”收口：`cd0a8fe1f` 删除绕过配置驱动复核状态机的 `pm_service.BatchReviewService` 时漏删 `pm_dashboard` 旧重复端点，现移除旧端点后 `app.main` 可干净导入，运行期 `/api/projects/{project_id}/batch-review` 唯一指向 `app.routers.batch_review.batch_review`；`audit_log.py` 调用缺失的 `_redact_if_display_prefs` 导致所有非跳过写请求在审计收尾时报 NameError，现补只保留 revision + changed_fields 的脱敏函数及 3 个测试。全量 route shadow 守卫仍有 14 条父提交预存红，与本轮两处修复无关，未扩散处理。

## 13. D1 拍板后的唯一写方矩阵（任务 6，2026-11-04）

### 13.1 拍板内容与可执行口径

用户 2026-11-04 拍板 D1「按建议来」。落成以下口径（本节是 ADR-WOS-04 的执行依据，§2 原文「矩阵按拍板结论设计」即指本节）：

- **交接章节（矩阵治理域）**：`note_workpaper_sync_registry.json` 按准则登记的章节（`note_readiness_service.registry_sections`：主章节 + `{准则}_sections`）。现算上市 73、国企 73，两套章节号不相交；78 个底稿编码全部有离屏 provider，从底稿拉取覆盖全部登记章节 ⇒ 登记章节全部算「已接」。域外章节不受矩阵约束、保持现状，即「其余章节暂留前端同步」。运行时的域取自登记表，不取自矩阵文件：矩阵漏生成某章时，该章的自动写入一律被拒（fail-closed），由生成器 `--check` 守卫在 CI 先报红。
- **「后端唯一写方」的落点**：域内章节的数值格只由后端取数链路写入。链路内的分工沿用 `note-pull-header-formula-closure` ADR-2 与 `note-pull-followup-closure` ADR-3，本任务不改分工，只把它从约定变成强制：
  - 审定主表金额（附注推送规则的目标表 × 规则字段）归 `formula_push`（试算表审定数）。推送已写定的格（推送状态 `auto`、规则在用）其他自动写方不得改；推送还没写定前，该格所在容器的基础写方可以临时填写，推送一旦写定即接管（ADR-3 的交接）。
  - 底稿披露容器（`sub_table_data`；章节 `_source` 为 workpaper / workpaper_html 且至少有一张表时生效，与读时投影 `project_sub_tables` 同判据）归 `workpaper_sync`。底稿披露 Tab 自动同步与离屏同步是同一写方：同一 builder、同一端点；HTML 入口 `workpaper_html_sync` 是同一写方的另一个入口。
  - 模板容器（`_tables` / 顶层 `rows`；底稿披露容器不生效时）归 `binding_refill`（模板绑定取数）。`update_note_values`（报表更新事件）与 `generate_notes`（生成 / 重生成的合并）是同一写方的另两个触发入口。
  - 域内的非所有者：`report_sync`（报表同步附注）、`formula_runtime_apply`（公式运行）；模板身份的写方写已被底稿披露容器遮住的 `_tables` 也被拒（原来这类写入用户看不见，却计入「已更新」）。
- **底稿披露 Tab 自动同步不停用。** 它与离屏同步是同一写方，停用只会让底稿改动等到附注刷新才进附注，写方数量不变。需要停用时另行拍板。

### 13.2 矩阵

- 文件 `backend/data/note_write_ownership_matrix.json`，由 `backend/scripts/gen/gen_note_write_ownership_matrix.py` 生成；输出不含时间戳（内容不变则字节不变），`--check` 漂移时退出 2 并点名。输入是登记表章节与 `formula_push.engine.load_push_rules()` 的附注规则；推送规则目标不在登记章节内时生成器拒绝生成（与 D1 矛盾，须先拍板）。推送规则的目标不随项目变（项目层只能改公式与启停），所以矩阵可以静态生成；停用的规则在运行时不再拥有已写定的格。
- 键 `(template_type, note_section, table_key, field_key)`：
  - 基础条目每章两条：`(准则, 章节, "*", "table.sub_table_data") → workpaper_sync`、`(准则, 章节, "*", "table.rows.values") → binding_refill`；
  - 推送条目：`(准则, 章节, 规则表名, "table.cell:<字段>") → formula_push`，`scope = pushed_cells`，`rules` 列出来源规则。推送写定前，该格按所在容器的基础条目判定（基础写方可临时填写）。字段即推送规则字段：底稿披露容器里是业务键，模板容器里是按表头认出的列（`note_writer.legacy_value_keys`），两处同名。规则表名取 `resolve_table(准则)`。
  - 现算：146 章 × 2 条基础条目，加 316 条推送条目（86 条附注规则覆盖 131 章）。
- 写方身份：`workpaper_html_sync ≡ workpaper_sync`，`update_note_values ≡ generate_notes ≡ binding_refill`，登记在矩阵的 `identity` 里；守卫要求身份只能指向登记表里的 writer。

### 13.3 判定 `note_write_ownership.WriteGate`

一次写入按以下顺序判定（前一步拒绝即不往下）：

1. 单元格 `locked` 或整节人工覆盖（`_manual_override`）⇒ 拒（`locked`）；全域生效，不论章节是否在治理域。
2. 单元格 `manual` ⇒ 拒（`manual`）；`refill_sections` 修复旧生成器占位格的例外（`_is_legacy_auto_cell`）不变。
3. 写方是 `formula_push`：只能写矩阵声明的推送条目 `(章节, 规则表名, table.cell:字段)`，没有该条目 ⇒ 拒（`unknown_entry`），不论章节是否在域内（推送按标题改投到另一章、或矩阵缺行，都会落到这里）。
4. 章节不在治理域 ⇒ 放行。
5. 写模板容器而该章底稿披露容器生效 ⇒ 拒（`inactive_container`）。
6. 该格属于推送条目且已由推送写定 ⇒ 拒（`pushed_cell`，所有者 `formula_push`）。
7. 查基础条目：没有 ⇒ 拒（`unknown_entry`）；写方身份等于所有者 ⇒ 放行；否则拒（`owner_mismatch`）。

被拒的字段不写，其他字段照写。第 3~7 步的拒绝记结构化日志 `note_write_blocked`（`extra["blocked_write"]`），并进响应的 `blocked_writes[{section, table, field, writer_id, owner_id, reason_code, reason, row}]`。第 1、2 步是现有的「保留人工 / 锁定」口径，不进 `blocked_writes`（推送照旧记 `keep_manual` / `keep_locked`）。

判定用的准则取各写方本来就用来选章节的那一个，不另起口径：公式推送用取数上下文的 `template_type`；底稿披露同步用请求的 `current_standard`；HTML 入口用章节记下的 `_current_standard` / `source_template`，都没有时用项目准则；模板绑定三个入口用引擎的 `_get_active_template_type`（生成用请求的准则）；报表同步与公式运行用附注记录自己的 `_current_standard` / `source_template`（不查库）。两套准则在治理域内的章节号不相交（上市 五、N / 国企 八、N），准则取错时章节不在域内，推送全部按未登记拒绝，其余写方失去交接保护；对应的用例与磁盘变异见 §13.7。

**manual 策略（底稿披露容器接管）**：域内章节从未由底稿同步过（`table_data` 没有 `_last_sync_wp_id`）、模板表格里已有人工 / 锁定且有值的格（`note_workpaper_pull_service.manual_value_count > 0`）⇒ `workpaper_sync` 整节不写，返回 `skipped=true, reason="manual_values_never_synced"`。这与离屏同步 `sectionGuard` 是同一判据、同一组输入；原来只有离屏同步在前端拦，底稿 Tab 自动同步照写，现在后端两条路都拦。真库现算受影响 1 章（1 个项目、2 格）。

### 13.4 接入点（受限 writer 8 个）

| writer | 接入位置 | 被拒时 | 回报 |
|---|---|---|---|
| `formula_push` | `note_total_push.push_note_cell` / `push_note_total`（`_push_note` 把判定挂在定位到的表上） | 该格记 `blocked` 动作，不写 | `RunResult.blocked_writes`（进 `summary()` / `detail()`）；取数结果 `push.blocked_writes` 与逐章 `blocked` |
| `workpaper_sync` / `workpaper_html_sync` | manual 策略；`note_push_ownership.reapply_pushed_cells` 只为矩阵声明的推送条目恢复推送值 | 整节不写 / 恢复推送值 | 响应 `blocked_writes`（`push_kept` 照旧保留） |
| `binding_refill` | `refill_sections` 逐格（先算推送写定格） | 跳过该格 | `RefillReport.blocked_writes` → 三个刷新端点 |
| `update_note_values` / `generate_notes` | 三态合并之后按推送写定格恢复旧值 | 恢复旧值 | `engine.blocked_writes`；生成端点响应带上 |
| `report_sync` | `_apply_report_values` 逐格 | 跳过 | 结果 `blocked_writes` |
| `formula_runtime_apply` | `NoteMutationAdapter.apply_many` 逐目标 | 不写、不进已应用清单 | `adapter.blocked_writes` 与日志 |

### 13.5 不进矩阵的写方（登记 `role`）

- `manual`：编辑器保存、Excel HTML、三格式、切换格模式、清除公式、恢复自动、AI 采纳 / 草稿确认 / 撤销、交付件正文回写。它们经 `note_edit_gate`（归档 423 / 成员 / EQCR / `note:edit` / 合并锁）放行后写入，不受矩阵限制。
- `derived`：附注公式执行器、绑定刷新后的公式二次求值、读时修复空表。它们按表内其他格计算，不是数据来源，沿用现有规则：只写 auto 格、推送拥有格 `kept_push`、底稿投影表只补空格。
- `structural`：集团基线 / 模板下发、合并模板下推、上年导入 / 继承、离线导入、正文批量、交叉引用、模板重排、结构重对齐、准则切换、自动裁剪、公式设置物化、拉取后记来源。这些是用户发起的整批操作，各有自己的确认流程。
- `stale`：`stale_mark` / `stale_clear`（R2 状态机）。
- 守卫：每个 writer 都有 role；role 为 `automatic` 的 writer，其入口函数或入口直接调用的写函数必须引用 `note_write_ownership`（AST 判定）。

### 13.6 前后端对拍

- 后端：矩阵域与登记表章节双向相等；推送条目与附注推送规则目标双向相等；每个域内章节两条基础条目都在；生成器 `--check` 通过。
- 前后端：矩阵文件附 `manual_policy.cases`（由后端判据算出期望结果）；前端 vitest 用离屏同步的同一判据（导出的 `manualSkipMessage`）跑同一组用例，结论必须逐条一致。同一 spec 断言离屏 provider 编码集合等于矩阵各章 `wp_codes` 的并集。
- 运行时：推送写定格被拒时，回报带底稿值与保留的推送值（即 `push_kept` 的差值），前端照旧提示「以试算表审定数为准」。

### 13.7 测试与变异

- 每个受限 writer 至少一条「该字段被拒、其他字段照写」用例。
- 磁盘变异（独立 worktree，SHA-256 恢复）：矩阵删一条推送条目；判定改用错误准则；判定去掉 locked；判定去掉 manual；去掉 manual 策略。全部须红。

### 13.8 实施与验收记录（2026-11-04）

**实施**（接入点见 §13.4，补充实施中定下的细节）：

- 公式推送：判定挂在最终落笔的表上（按标题改投之后的章节、规则表名），拒写记动作 `blocked`，计入 `skipped_count`（健康度的 total = 写入 + 未变 + 保留 + 跳过仍等于项数）；`RunResult.blocked_writes` 进 `summary()` / `detail()`；取数结果带 `push.blocked` / `push.blocked_writes` 与逐章 `blocked`。真库守卫 `test_formula_push_note_skip_pg` 加类别 B（写入归属拒写，棘轮 0），对齐脚本 `realign_project_notes` 的待人工清单含 `blocked`。
- 底稿披露同步：manual 策略拒绝接管时与口径跳过同形（`skipped=true`、`reason=manual_values_never_synced`），中文原因在 `blocked_writes`；批量严格模式整批回滚时对外原因写中文；HTML 入口章节没记准则时按项目准则。
- 提示：附注页刷新提示单列一句「公式推送有 N 格不在它负责的范围，未改（如 章节 表「行」）」并按告警显示；离屏同步认 `manual_values_never_synced`；披露 Tab 自己的提示把跳过回执当成功（「已更新…0 行」），全局拦截器 `disclosureSyncPushNotice` 补一句原因与处理建议。处理建议前后端同一句（前端 `utils/noteWriteOwnership.ts` ↔ 后端 `note_write_ownership.MANUAL_TAKEOVER_ADVICE`，对拍守卫读后端源码比对）：「如需改用底稿数据，先在附注编辑器里把人工填写的格恢复为自动」。离屏同步原来的建议是「去底稿附注披露页同步」，那条路现在同样被拒，已改。

**S3 遗留红用例（本轮一并修）**：任务 1 把清过期改走 `stale_state`（一条 UPDATE + flush，不再改内存里的对象）后，11 个测试文件的 48 个用例的测试替身没跟上——`side_effect` 少一条、FakeDB 不认 UPDATE、FakeNote 缺 `year`、断言内存对象 `is_stale`；HEAD 上一直红，任务 7 的回归选集没有覆盖到。本轮只改测试替身与断言口径（改为断言统一入口的那条 UPDATE），生产代码不动；base 套同样的替身修复后 196 个节点两侧同为 1 红（`test_audit_log_contains_correct_payload`：审计日志已改走 `append_audit_log`（ADR-ALC-07/08），该用例仍 patch `AuditLogEntry`，与本 spec 无关，未改）。`integration/test_disclosure_sync.py` HEAD 已 814 行（超行数门、未登记），FakeDB 挪到 `tests/integration/_disclosure_sync_fakes.py` 后 749 行。

**验证**（候选 = 远端头 98332962c + 本任务改动；基线 = 远端头）：

- 后端逐节点（隔离库）：589 个测试文件（附注 / 披露 / 过期 / 公式推送 / 公式运行 / 离屏 / 写入归属），基线 13348 节点 341 红、候选 13387 节点 292 红，候选新增红 0，新增 39 节点全绿，修复 49（S3 遗留 48 + 写方登记守卫 1）。中途远端两次前移（ec777f0fa → 165599b60 → 98332962c，与本任务的代码文件零交集），每次移到新头重跑：165599b60 新加的 `test_note_headless_refresh_protections::test_refresh_steps_called_by_the_executor_skip_manual_cells` 用 `SimpleNamespace` 冒充 `RefillReport`、缺新字段 `blocked_writes`，改用真实 `RefillReport`；98332962c 带来的 6db64f2fa 让三态合并在明细有保留值时按合并后的明细重算合计的自动格——推送写定格在合并里按 locked 语义保留，同样触发，生成 / 报表更新两条用例的合计期初期望随之改为按明细重算（与保留的推送明细一致，正是该提交的用意）。
- 真库（只读效果）：重药安徽 2025 公式推送预演（引擎在 savepoint 里执行后回滚，外层显式 rollback），候选与 HEAD 逐项 373 条（规则、地址、动作、公式值、当前值）完全相同、拒写 0；真库守卫 3 passed。
- 前端：vitest 13 个 spec 候选新增红 0（新增 8 例）；区域 vue-tsc added 0（探针 TS2322 报出，排除 OOM 假零）；ESLint 9 个文件 0；Ruff 40 个文件新增 0；行数门 exit 0；离屏披露 Node 执行器（远端头新增）在候选上构建通过，构建清单 576 个源文件比基线多 `utils/noteWriteOwnership.ts`、新鲜度核对通过。
- 磁盘变异（独立 worktree，SHA-256 逐字节还原）：46 条全红且红在预期用例上（矩阵缺推送 / 基础条目、空章节 / 缺基础条目放行、准则对调与三个入口写死准则、去掉 locked / manual、公式运行不传格模式、manual 策略恒放行 / 判据不看同步过 / 两个入口不调、推送不查声明 / 不挂判定 / 明细与合计两条路径不判、跳过数不含拒写、容器判据、模板绑定写被遮住的容器 / 不跳推送格 / 重算推送合计、报表更新与生成合并不取推送格、合并不加保留、域内推送格一律归推送、恢复推送值不问矩阵 / 不回报 / 不带判定、报表同步与公式运行不看判定、拒写不回报、`--check` 不比对、推送目标出域不拒绝、对齐脚本漏 blocked、批量原因写代码、前后端处理建议分叉、前端判据不看同步过、刷新提示不写 / 丢行名、离屏跳过原因缺失、披露 Tab 不提示）；阴性对照 3 条（只改措辞 / 日志格式 / 取法）保持绿。
- 浏览器（候选前端 3032 → 共享后端 9980 只读，令牌按共享后端配置签发、不登录；4 个写请求全部在浏览器里拦截回模拟响应，共享库零写）：【测试】公式同步甲有限公司_2025 附注页 五、1「🔄 刷新」，推送回执 blocked=3 ⇒ 提示含「公式推送有 3 格不在它负责的范围，未改（如 五、1 货币资金「库存现金」）」且为告警；经应用里装好的全局 http 实例发非静默同步、回执 manual 策略跳过 ⇒ 全局拦截器提示原因与处理建议；pageerror 0、console error 0。截图与 JSON 是临时产物（`tmp_writer_ownership/task6/browser/`），清理后以本节摘要为准。

- 推送前复核（远端头两次前移：→ cad390dcb / v1.0.116 → 2dbc68ea0「双向回写闭环审计整改」，后者改了 125 个文件、
  其中 `workpaper_writer_inventory.json` 等写方清册与多个全仓扫描守卫）：两次 rebase 都无冲突，`git range-diff` 四条补丁
  逐条 `=`（内容逐字节未变），与远端改动文件交集为空（本任务 56 个 / 远端 125 个）。最终头上整套重跑：
  后端逐节点 676 个测试文件（附注 / 披露 / 过期 / 公式推送 / 公式运行 / 离屏 / 写入归属 589 个 + 43 个全仓扫描守卫
  + 远端新改的 44 个），基线 15934 节点 506 红、候选 15973 节点 456 红，**候选新增红 0**、新增 39 节点全绿、修复 50；
  前端 158 个 spec（本任务 13 个 + 全仓扫描类守卫 + 远端新改的 6 个）基线 3222 例 49 红、候选 3230 例 49 红，候选新增红 0、
  新增 8 例全绿；区域 vue-tsc added 0（TS2322 探针报出）；ESLint 9 文件 / Ruff 41 文件新增 0；46 条磁盘变异全红 +
  3 条阴性对照全绿、`mut_wt` 与候选逐字节一致；矩阵 `--check`、暂存树自洽 2 门、行数门 exit 0、离屏执行器重新构建后
  新鲜度核对通过；浏览器走查 6/6 复跑通过（console error 0、4 个写请求全部在浏览器拦截、共享库零写）。
- 「两边都红」不等于没变化：456 个同红用例里 52 个失败全文有差异，按「行号 / `MagicMock` id / 内存地址 / 临时目录 /
  `frozenset` 顺序 / 随机种子 / 摘要哈希 / 每次新签的 JWT / 随机 UUID」归一后 50 个属装饰性差异，剩 2 个逐条查清：
  (1) `test_wp_disclosure_sync_html_audit::test_audit_log_contains_correct_payload`——基线红在 `FakeNote` 没有 `year`
  （替身没跟上统一清过期），本轮把替身补齐后它越过这一步，露出原有的那条（审计日志已改走 `append_audit_log`、用例仍
  `patch AuditLogEntry`），仍不是本 spec 的问题；
  (2) `test_formula_push_note_skip::TestTotalRecomputeNeedsANumber` 两例——基线红在 `TypeError: 来源摘要不支持 MagicMock
  类型`，候选红在断言（`section` 为 None、合计没重算）。探针查明：用例的 `_make_rule()` 把章节 `五、22` 和表名「应交税费」
  配在一起，而真实登记里上市 `五、22` 是固定资产（`H1.note.main`）、应交税费在 `五、41` / `八、41`（`N2.note.main`）
  ——这是臆造组合，判定按「矩阵没有这一格」fail-closed 拒写，正是 R1b 要的行为；该用例在 HEAD 上本来就红（另一个原因），
  本轮不改它，修法是把用例换成已登记的组合（后续谁修那条 `MagicMock` 类型红时一并改）。
- 反向核对（不靠生成器自说自话）：按真实推送规则反查矩阵，318 个「规则 × 准则 × 字段」组合全部有 `formula_push` 条目
  且条目 `rules` 里登记了规则号，出域章节 0 个 ⇒ fail-closed 不会打到任何真实推送规则。
- 另外按本任务的专有标识（新模块名 / `WriteGate` / `blocked_write` / `manual_values_never_synced` / 新中文文案等）
  扫候选侧全部 456 条失败全文：命中 0 ⇒ 没有任何全仓清册 / 摘要类守卫因为本任务新增的文件而变红。
**合入后须知**：远端头新增的离屏披露 Node 执行器按源文件 sha256 核对构建新鲜度，本任务改了它打包的 `noteHeadlessDisclosure.ts` / `noteWorkpaperPull.ts` / `headlessFramework.ts`，各环境要按 `BUILD_HINT` 重新构建一次，否则执行器拒绝运行（设计如此，不是故障）。

**发现（未修，登记）**：

- `formula_runtime` 附注适配器的行形状与真实附注不符、`wp_formula` 0 行（实际从未执行）；`_set_cell_value` 找不到行时追加假行。
- 披露 Tab 对 `skipped` 回执当成功：提示「已更新…0 行」并记已同步表名，口径跳过（`section_not_applicable_to_report_scope`）同样如此；本轮只在全局拦截器补提示，没改 90 多个 Tab。
- 批量严格模式对口径跳过的对外原因仍是代码 `section_not_applicable_to_report_scope`（本轮只改了 manual 策略这一种）。
