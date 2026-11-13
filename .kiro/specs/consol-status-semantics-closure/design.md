# 合并链路状态语义收口 — 设计

需求见 `requirements.md`（R1~R6）。本文写现状落点、取舍、接口与测试，不复述需求。

## 1. 现状确认（HEAD `39777a020` 现读）

### 1.1 合并附注「待更新」的写入方

`ConsolNoteData.is_stale` 是布尔列（`consol_note_data_models.py:35`），没有原因与时间。单体附注已有同类机制：`stale_state.StaleSource` + `DisclosureNote.stale_source` + `STALE_SOURCE_LABELS`；已归档 spec `147-formula-settings-durable-outbox` design §2 记有「合并附注表没有来源列，只置标记」，本 spec 补上这一列。

| 动作 | 位置 | 现状 |
| --- | --- | --- |
| 置 True：推送开始时全项目全部行 | `consol_push_service._mark_notes_stale :212-220` | 批量 `update().values(is_stale=True)` |
| 置 True：拉数行公式值变化 | `consol_note_formula_service.py:1297-1302` | `preserve_pulled` 且快照变化 |
| 置 True：子企业单体附注已保存 | `consol_note_value_change_service.on_note_section_saved :50-58` | 逐行赋值 |
| 置 True：公式设置变化 | `formula_settings/propagation.py:178-185` | 批量 update |
| 置 True：新建显式节点行 | `consol_node_scope.save_scoped_note_record :315-337` | 无 legacy 基线时默认 True |
| 继承 | `consol_note_formula_service._copy_note_data_record :1011-1033`、`consol_note_subtree_reaggregate.py:719-733`、`consol_node_scope :326-331` | 只继承布尔值 |
| 置 False | `detail_apply :371`、`formula :1336/:1342`、`subtree_reaggregate :572`、`topn :295` | 不清其他字段（本来也没有） |
| 读取短路 | `consol_note_formula_refresh_handler.py:183-208` | 无 stale 行即跳过 |
| 死代码 | `formula_settings/stale_marks.py:83-108` | 引用不存在的 `ConsolNoteData.section_code`；`mark_in_txn` 只有测试调用 |

共享库现查（只读，2026-11-11）：`consol_note_data` 3518 行，`is_stale = true` 1 行（1 个项目）。迁移回填影响 1 行。

前端：`ConsolNoteTab.vue` 不读 `is_stale`；章节 GET（`consol_note_sections.py:367-373`）不返回它。合并页横幅只由 SSE `consol.note_stale` 置位（`ConsolidationIndex.vue:1474-1485`），刷新即消失；`consol_note_stale_handler._emit_consol_note_stale` 的 docstring 写「下次进合并页读最新 stale 态兜底」，实际没有这条读取。

### 1.2 重新汇总

- `_Run.result()`（`consol_note_subtree_reaggregate.py:752-773`）：有失败且有写入为 `partial`，有失败无写入为 `failed`，否则按是否写入为 `persisted` / `skipped`；没有 `errors` 字段。
- 四处 `_PERSISTED` 结果（拉数 `:435`、差额 `:459`、汇总 `:585`、前 N 名 `:637`）不看是否真写入了自动格。`build_note_rows`（`consol_note_table_totals.py:206-224`）对被保护格只记 `kept_value`，不记本次算出的值。
- 异步执行器（`consol_note_reaggregate_executor.py:114`）一律 `ExecutorOutcome(result_ref={"result": result})`，平台任务记 succeeded；平台终态集合 `{"succeeded","failed","cancelled"}`（`platform_job_service.py:18`）被全平台共用。
- `ConsolidationIndex.onReaggregateCompleted :1040-1062` 读 `result.errors` 恒为 0 ⇒ 恒提示成功；随后只要章节重读成功就清 `consolStale`。`ConsolNoteTab.handleReaggregate` 用 `consolNoteView.reaggregateSummary :193-214`，判定正确。

### 1.3 推送附注步骤

`_refresh_notes`（`consol_push_service.py:223-366`）在四种情况下提前返回 `note_status = "skipped"`：模板类型解析失败 `:267-271`、无启用章节 `:278-279`、无企业树 `:284-286`、上下文构建异常 `:303-305`。`_push_one` 把 skipped 记成 succeeded（`:546-549`）。其中上下文构建异常是失败被说成成功。级联刷新 `consol_cascade_refresh_service.py:311-332` 把四种都记为 skipped，同样漏掉上下文失败。`consol_push_service.py` 895 行，未登记白名单（默认上限 800）⇒ 任何改动都会被行数门拒绝，须先抽出附注步骤。

### 1.4 抵销审批

`routers/consolidation.py:262-325`：审批 commit 后 `event_bus.publish(ELIMINATION_APPROVED / REVOKED)`，发布异常只记 warning；响应只有分录。处理器 `consol_elimination_recalc_handler._push :27-62` 在独立会话 `request_operation(idempotency_key=f"elimination:{trigger}:{source_id}")` + `wake()`，入队失败只 `logger.error`。合并页已订阅 `consol.push_failed` 并弹通知（`ConsolidationIndex.vue:883-888`，取 `warnings[0]`）。前端审批 / 撤销提示「合并数将自动重算」「合并试算、报表与附注将自动推送」（`ConsolElimNodePanel.vue:290,311`、`worksheets/EliminationSheet.vue:400,435`）。

### 1.5 调整分录审批

`review-batch`（`adjustment_review.py:168-193`）返回 `{succeeded, failed, notified}`，每笔带 `tb_update_status`（`committed` / `awaiting_workpaper_publish` / `workpaper_publish_unchanged`，`adjustment_review_coordinator.py:162,214,241,277`）；`publish_review_events` 丢弃 `PublishReport`（`:71-75`；注意它投递的是全部待发 outbox 行，不只本次）。前端 `flowResultMessage`（`useAdjustmentHallActions.ts:125-138`）不读 `tb_update_status`；确认框写「相关报表与附注将在试算表更新后刷新」（`:233`）。

### 1.6 已核对、不改

- consol operation 的 `partial` 在旧刷新接口映射为 `completed`（`consol_operation_service.py:541-548`），但同一响应带 `operation_status` 与 `errors`，级联刷新路径的错误逐项进入 `errors`（`consol_operation_runner.py:270-276`），前端按错误数提示部分失败（`useConsolRefreshTracking.ts:211-215`）。推送 operation 的状态由「合并推送」面板读推送运行记录展示「部分成功」。两处都如实。
- 推送后拉数行保持「待更新」、使「无 stale 即短路」失效：已归档 spec 84 §9 / §13.3 的设计。

## 2. 取舍

### 2.1 原因放独立列，不放 `data` JSON

`data` 是用户内容，`consol-note-save-integrity-closure` 按它算 CAS 摘要；把原因写进 `data` 会让后台置待更新改变摘要，用户随后保存必然 409。独立列与单体 `stale_source` 同构，读取方不需解析 JSON。

### 2.2 `kept_manual` 清除待更新

「待更新」的含义是「行里的自动值还没按最新上游重算」。全部自动目标都被手工格保护时，重算已经做过，再跑一次结果相同；保留待更新只会让它永远亮着、并让推送后的短路判断永远失效。差异以「N 格与汇总值不同」报给用户，由用户决定是否恢复为自动。

### 2.3 任务失败只用于「全部失败」

不给平台任务加 `partial` 终态：终态集合被全平台任务共用，改动面远超本 spec。业务部分失败由结果摘要表达（合并附注页早已如此）。全部失败时让任务失败，使通用进度组件也显示失败与原因。

### 2.4 抵销审批：处理器失败上报，不在请求内入队

| 方案 | 结论 | 理由 |
| --- | --- | --- |
| A 路由 commit 后直接 `request_operation` 并在响应里带 operation id | 否 | `request_operation` 要建树与上下文快照（`_snapshot`），把重活放进审批请求；破坏 ADR-CONSOL-102「审批与推送解耦」；事件去抖本为合并连续审批 |
| B 路由回报事件是否发出；处理器入队失败写失败运行记录 + 广播 `consol.push_failed` | **采用** | 失败经已有的合并页通知与「合并推送」面板历史可见；请求路径不变重 |

### 2.5 调整审批：只报已知事实

`tb_update_status` 是同事务内已确定的事实，可以汇总；报表 / 附注刷新是 outbox 之后的异步处理，回执只能说明「事件已发出 / 投递失败待重试」，不能说「已刷新」。

## 3. 待更新原因

新文件 `backend/app/services/consol_note_stale_state.py`：

| 编码 | 中文标签 | 写入方 |
| --- | --- | --- |
| `consol_push` | 合并推送后待按最新合并数更新 | `_mark_notes_stale` |
| `formula_value_changed` | 合并数已变化，拉数数据待重新汇总 | `fill_by_formula`（`preserve_pulled` 且快照变化） |
| `standalone_note_saved` | 子企业单体附注已修改 | `on_note_section_saved` |
| `formula_settings` | 公式设置已变化 | `propagation`（consol_note 域） |
| `node_created` | 新建节点，尚未计算 | `save_scoped_note_record` 无基线的新显式节点行 |
| `legacy` | 历史标记，未记录原因 | 迁移回填；未知编码读出时也显示此标签 |

接口：`ConsolNoteStaleSource`（StrEnum）、`LABELS`、`label_of(code)`、`mark_stale(record, source, *, now=None)`、`clear_stale(record)`、`stale_values(source, now) -> dict`（批量 update 用）、`clear_values() -> dict`、`inherit_values(source_record) -> dict`（复制行构造参数）。推送标记后，未变化的拉数行原因保持 `consol_push`；变化的改为 `formula_value_changed`，时间取本次。

守卫 `backend/tests/test_consol_note_stale_writers_guard.py`：扫描 `backend/app` 中引用 `ConsolNoteData`（含别名导入）的模块，AST 判定三种形态 —— 属性赋值 `X.is_stale = …`、调用关键字 `values(is_stale=…)`、构造 `ConsolNoteData(..., is_stale=<非常量 False>)` 缺 `stale_reason=`；除 `consol_note_stale_state.py` 外一律打红。内置变异：临时源码各写一种形态须红；分母（被扫描的模块数）须大于 0。

## 4. 迁移

`V{n}.sql`（n 实施时取 `max(磁盘含未跟踪, 共享库已应用) + 1`，现为 269）：

```sql
ALTER TABLE consol_note_data ADD COLUMN IF NOT EXISTS stale_reason VARCHAR(40);
ALTER TABLE consol_note_data ADD COLUMN IF NOT EXISTS stale_at TIMESTAMPTZ;
UPDATE consol_note_data SET stale_reason = 'legacy' WHERE is_stale AND stale_reason IS NULL;
```

`R{n}.sql` 删两列。不加 CHECK 约束：状态一致性由写入口与守卫保证；约束失败会让后台批量置位整体失败，代价大于收益。ORM 两列可空；漂移检测随之对齐。

## 5. 接口变化

| 接口 | 变化 |
| --- | --- |
| GET 合并附注章节数据 | 追加 `is_stale`、`stale_reason`、`stale_reason_label`、`stale_at`（与 `data_digest` 同级，不进摘要） |
| SSE `consol.note_stale` | 载荷追加 `reason` |
| 重新汇总结果 | `results[].status` 新值 `kept_manual`；`detail.manual_differs_count`；run 级只有 `kept_manual` 时为 `skipped`；`sections_updated` 只数 `persisted` |
| 后台重新汇总任务 | run 级 `failed` ⇒ 抛 `ConsolReaggregateJobError(第一处失败原因)`（不可重试）；提交在抛出之前已完成，失败时无写入可回滚 |
| 附注刷新统计（推送 / 级联刷新） | 追加 `skip_reason` |
| `POST /api/consolidation/eliminations/{id}/review` | 响应模型改为 `EliminationReviewResponse(EliminationEntryResponse)`，追加 `recalc_trigger`、`recalc_notice` |
| `POST …/adjustments/review-batch` | 追加 `downstream: {published, failed}`；`succeeded[].tb_update_status` 不变，前端开始读 |

判定函数 `note_step_verdict(stats) -> (step_status, detail)` 放在新文件 `consol_push_notes.py`，推送与级联刷新共用：`persisted` → succeeded；`partial` / `failed` → 原样；`skipped` 且 `skip_reason == "context_failed"` → failed；其余 skipped → skipped（detail 带中文原因）。

## 6. 落点与行数

| 文件 | 改动 | 行数 |
| --- | --- | --- |
| `services/consol_push_notes.py`（新） | 从推送服务原样迁出 `_mark_notes_stale` / `_refresh_notes`，加 `skip_reason` 与判定函数 | ~190 / 800 |
| `services/consol_push_service.py` | 删迁出部分，保留同名导入（既有测试按 `consol_push_service._refresh_notes` 打补丁，`_push_one` 经本模块全局名调用，补丁照常生效） | 895 → ~740 / 800 |
| `services/consol_note_stale_state.py`（新） | 原因枚举与写入函数 | ~80 |
| `services/consol_push_failure_record.py`（新） | 入队失败写运行记录 + 广播 | ~50 |
| `consol_note_formula_service.py`、`consol_note_subtree_reaggregate.py`、`consol_note_detail_apply_service.py`、`consol_note_topn.py`、`consol_node_scope.py`、`consol_note_value_change_service.py`、`formula_settings/propagation.py`、`formula_settings/stale_marks.py` | 改走原因模块；死代码删除 | formula 1455 / 上限 1543；其余 < 800 |
| `consol_note_table_totals.py` | `kept` 项加 `computed_value` | 281 |
| `routers/consol_note_sections.py` | GET 追加四字段 | 1016 → ~1022 / 上限 1083（与前置 spec 合计须复核） |
| `routers/consolidation.py`、`models/consolidation_schemas.py`、`routers/adjustment_review.py` | 回执字段 | 469 / 739 / 193 |
| 前端 `components/consolidation/ConsolNoteStaleTag.vue`（新） | 章节待更新标签 | ~40 |
| `ConsolNoteTab.vue` | 引入标签、存四字段 | 3527 → +8；与前置 spec 合计 ≤ 3610 |
| `ConsolidationIndex.vue` | 完成提示改用摘要函数（净减） | HEAD 2513 / 上限 2638；工作区有他会话未提交改动，实施时在候选树上改 |
| `ConsolElimNodePanel.vue`、`EliminationSheet.vue`、`useAdjustmentHallActions.ts`、`auditPlatformApi.ts`（类型） | 提示文案与回执读取 | 均 < 1500 |

## 7. 测试与变异

| 层 | 内容 | 文件 |
| --- | --- | --- |
| 原因 | 每个写入方各一例：置位后原因与时间正确；清除后两列为空；复制继承 | 新 `backend/tests/services/test_consol_note_stale_state.py` |
| 迁移 | 一次性 PG 库跑 V / R：列存在、回填 `legacy`、回退后列消失 | `test_migration_*` 同形新例 |
| 守卫 | §3 守卫与内置变异 | 新 `test_consol_note_stale_writers_guard.py` |
| 重新汇总 | 全部手工格 → `kept_manual`、不计更新数、清待更新、差异计数；有自动格写入仍 `persisted`；run 级只有 kept_manual → `skipped`；全部失败 → 执行器抛错、任务 failed | `services/test_consol_note_subtree_reaggregate.py`、`test_consol_note_reaggregate_durable_job.py` 增例 |
| 推送 | 四种 skip_reason 各一例：`context_failed` → 步骤 failed 且 all_ok False；其余 → skipped；级联刷新同判定 | `test_consol_push_cp03_note_status.py`（`("skipped","succeeded",True)` 改为按原因参数化）、`services/test_consol_phase2_cascade_pbt.py` 增例 |
| 抵销 | 发布异常 → `recalc_trigger = event_failed`；提交 / 驳回 → `not_applicable`；处理器 `request_operation` 抛错 → 一条 failed 运行记录 + `consol.push_failed` 载荷 | `test_consolidation_chain.py`、新 `test_consol_elimination_recalc_failure.py` |
| 调整 | `downstream` 计数；三种 `tb_update_status` 汇总文案；确认框文案 | 后端 review-batch 用例、`useAdjustmentHallActions` vitest |
| 前端 | 待更新标签显示与隐藏；合并页完成提示走摘要函数（部分失败 / 待确认映射显示警告、不清横幅）；审批提示三态 | `ConsolNoteTab.spec.ts`、`consolRefreshWiring.spec.ts`（改断言：不再读 `result.errors`）、`ConsolElimNodePanel` / `EliminationSheet` 相关 spec |

变异（每条确认红在预期断言上）：任一写入方不写原因；清除时不清原因；复制不继承原因；`kept_manual` 判定改回 `persisted`；`kept_manual` 不清待更新；执行器全部失败仍成功；`context_failed` 改回 skipped；skipped 改回 succeeded；处理器入队失败不写运行记录；路由吞掉发布异常仍报 `event_published`；前端回到读 `result.errors`；守卫判据改成恒真。

浏览器实测（【测试】合并项目，写入后复原）：推送后章节显示「待更新：合并推送后待按最新合并数更新（时间）」；重新汇总后标签消失；把某章自动格全部改为手工后重新汇总，提示「全部为手工格」；用 `initScript` 拦截 XHR 实测审批回执 `event_failed` 的警告与调整审批的三类汇总文案；在 `http://192.168.20.60:3030` 复测标签显示。

## 8. 范围外与待拍板

| 项 | 处置 |
| --- | --- |
| 就绪门服务端强制可执行动作 | **已定（用户 2026-11-11 按建议）**：不强制。2026-10-27 裁决计算门只校年度；用户同日确认重复项目与关系冲突只弹窗不阻断（`consol-group-code-entry-consistency` R7）；就绪门若在服务端拒绝，会把这两类提示变相升级为阻断，与两次裁决冲突。前端按钮禁用保持不变 |
| 合并页横幅改为持久读取 | 不做：章节级标签已持久；横幅改读取需另取全项目待更新统计，与就绪条重复 |
| 就绪门附注统计含非根节点与 legacy 重复行 | 登记：`consol_readiness_service.py:413-421` 统计全部行；是否只数根节点属口径决定 |
| 平台任务 `partial` 终态 | 不做（§2.3） |
| 推送 operation 的 warnings 只在 failed 时转 errors | 不改（§1.6，面板读推送运行记录） |
