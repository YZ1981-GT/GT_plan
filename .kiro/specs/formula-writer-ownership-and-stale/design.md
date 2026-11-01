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
| D1 | 附注权威源按章节交接：前端同步 vs 公式管理/底稿拉取 | 未拍板；只允许 R1a，禁止 R1b 强制 |
| D2 | 历史 227 行无来源 stale 是否回填 | 默认不回填，显示「来源未记录」 |
| D3 | 试算表保存后是否要求即时 GET 反读 | 本 spec 默认不要求；页面刷新读回为验收口径 |
| D4 | `consol_note_data` 与底稿预填是否新增来源列 | 不在本 spec，另立迁移需求 |

### 11.11 本轮文档修改边界

本次重整只修改 requirements/design/tasks 三件套，未修改生产代码、迁移、INDEX 或 memory。实施阶段允许触碰的生产文件由任务 0 的现算清单生成，禁止根据旧 §1 的文件数量手工扩散。
