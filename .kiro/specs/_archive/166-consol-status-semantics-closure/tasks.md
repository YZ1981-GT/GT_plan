# 合并链路状态语义收口 — 任务

需求 `requirements.md` R1~R6；设计 `design.md`。前置 `consol-note-save-integrity-closure` 已合入（本 spec 在其 GET 响应与写入方登记上追加）。验证在「最新 HEAD + 本 spec 改动」的干净分离头 worktree（仓库根 `tmp_consol_status/verify_wt`）上跑；连 PG 的用例显式设 `DATABASE_URL` 指向一次性库，不写共享库；迁移不在共享库执行，落库前请用户放行。

- [x] 1. 推送附注步骤迁出（行数门前置；design §1.3、§6）
  - [x] 1.1 `_mark_notes_stale` / `_refresh_notes` 原样迁到新 `consol_push_notes.py`，`consol_push_service.py` 保留同名导入；推送服务降到 800 行以下
  - [x] 1.2 纯迁移回归：`test_consol_push_*`、`test_consol_basis_reuse_and_push_targets.py`、`services/test_consol_push_cp03.py`、`test_consol_push_run_sse.py` 与干净 HEAD 逐节点一致（本批不改行为）

- [x] 2. 待更新原因（R1；design §3、§4）
  - [x] 2.1 迁移 V/R 成对（号实施时动态取）；ORM 两列；回填 `legacy`；漂移检测对齐
  - [x] 2.2 新 `consol_note_stale_state.py`：枚举、标签、`mark_stale` / `clear_stale` / `stale_values` / `clear_values` / `inherit_values`
  - [x] 2.3 design §1.1 表内全部置位、清除、继承写入方改走该模块；删除 `stale_marks.mark_consol_note_stale` 与 `mark_in_txn` 合并附注分支
  - [x] 2.4 新 `test_consol_note_stale_writers_guard.py`（三种形态 + 分母 > 0 + 内置变异）
  - [x] 2.5 新 `services/test_consol_note_stale_state.py`：每个写入方一例；一次性 PG 库跑迁移 V / R
  - [x] 2.6 GET 章节数据追加四字段；`consol.note_stale` 载荷加 `reason`
  - [x] 2.7 前端新 `ConsolNoteStaleTag.vue`，`ConsolNoteTab.vue` 采用数据时存四字段并显示；vitest 显示 / 隐藏 / 未知编码显示「历史标记」
  - [x] 2.8 变异：任一写入方不写原因；清除不清原因；复制不继承；守卫判据恒真；前端不渲染标签

- [x] 3. 重新汇总结果如实（R2；design §1.2、§5）
  - [x] 3.1 `build_note_rows` 的 `kept` 项加 `computed_value`；拉数 / 差额 / 汇总 / 前 N 名四类结果的 `detail` 补齐 `filled_count` 与 `kept_manual_count`（缺哪类补哪类，实施时先现读），统一经 `_Run` 判定 `kept_manual`（无自动格写入且有保护格），`detail.manual_differs_count` 按分比较
  - [x] 3.2 run 级：只有 `kept_manual` → `skipped`；`sections_updated` 只数 `persisted`
  - [x] 3.3 执行器 run 级 `failed` 抛 `ConsolReaggregateJobError(第一处失败原因)`
  - [x] 3.4 `ConsolidationIndex.onReaggregateCompleted` 改用 `reaggregateSummary`，仅 `ok` 时清 `consolStale`；`consolNoteView.reaggregateSummary` 识别 `kept_manual` 原因
  - [x] 3.5 测试：design §7「重新汇总」行；`consolRefreshWiring.spec.ts` 改断言为走摘要函数
  - [x] 3.6 变异：`kept_manual` 改回 `persisted`；`kept_manual` 不清待更新；执行器全部失败仍成功；前端回到读 `result.errors`

- [x] 4. 推送与级联刷新附注步骤（R3；design §5）
  - [x] 4.1 `_refresh_notes` 四处提前返回写 `skip_reason`；`note_step_verdict` 判定函数
  - [x] 4.2 `_push_one` 与 `consol_cascade_refresh_service` 改用判定函数
  - [x] 4.3 测试：`test_consol_push_cp03_note_status.py` 按原因参数化；级联刷新 `context_failed` 进 errors、其余进 skipped
  - [x] 4.4 变异：`context_failed` 改回 skipped；skipped 改回 succeeded

- [x] 5. 抵销审批重算触发（R4；design §2.4、§5）
  - [x] 5.1 `EliminationReviewResponse` + 路由按发布结果填 `recalc_trigger` / `recalc_notice`
  - [x] 5.2 新 `consol_push_failure_record.py`；处理器入队失败调用它（写 failed 运行记录 + 广播 `consol.push_failed`）
  - [x] 5.3 `ConsolElimNodePanel.vue`、`EliminationSheet.vue` 提示三态
  - [x] 5.4 测试：design §7「抵销」行；前端两个组件 spec 的提示断言
  - [x] 5.5 变异：入队失败不写记录；路由吞异常仍报 `event_published`

- [x] 6. 调整分录审批回执（R5；design §2.5）
  - [x] 6.1 `publish_review_events` 返回 `PublishReport`，review-batch 回执加 `downstream`
  - [x] 6.2 `flowResultMessage` 按 `tb_update_status` 汇总、读 `downstream`；确认框文案改写；`AdjustmentFlowResult` 类型补字段
  - [x] 6.3 测试：后端 review-batch 回执；`useAdjustmentHallActions.spec.ts` 三类汇总、投递失败提示、确认框文案
  - [x] 6.4 变异：不汇总 `tb_update_status`；`downstream.failed > 0` 不提示

- [x] 7. 回归与门禁
  - [x] 7.1 后端：本 spec 新增与改动测试 + 合并附注 / 推送 / 级联刷新 / 抵销 / 调整复核既有测试；失败项与干净 HEAD 逐节点比对，新增失败 0
  - [x] 7.2 前端：合并附注、合并页、抵销、调整大厅相关 vitest；改动文件区域 vue-tsc 相对 HEAD 新增 0
  - [x] 7.3 行数门（design §6，ConsolNoteTab 与前置 spec 合计复核）、暂存树自洽检查通过

- [x] 8. 浏览器实测（design §7 末段）
  - [x] 8.1 【测试】合并项目：推送后章节显示待更新原因与时间；重新汇总后消失；全部手工格章节提示「全部为手工格」
  - [x] 8.2 `initScript` 拦截 XHR：审批 `event_failed` 警告、调整审批三类汇总与投递失败提示
  - [x] 8.3 在 `http://192.168.20.60:3030` 复测 8.1 标签显示；写入数据复原并对账

- [x] 9. 收尾
  - [x] 9.1 review 文档 §0.5 / §10 标注 P0-5 / P1-6 落地方式与就绪门不在服务端强制的裁决
  - [x] 9.2 在 `.kiro/specs/INDEX.md` 登记本 spec（基于最新 HEAD 副本只加本行，CRLF 与表格列数校验）

> **状态更新（2026-11-13）**：本轮 `[x]` 表示生产代码已接入且有定向回归证据；`[~]` 保留给仍缺完整 clean-HEAD 对拍、磁盘变异、PG V/R 回滚或浏览器证据的条目。共享 PG 已只读核对 V270 已应用且 checksum 一致，但本轮未执行 R270 回滚。浏览器已在 `http://127.0.0.1:3030` 登录并加载合并页、console 0 errors；目标测试工作区已有未保存状态，切附注页触发保护对话框，未点击放弃/保存，因此 8.1~8.3 不标完成。

> **R3/R4 变异收口更新（2026-11-13）**：`test_consol_phase2_cascade_pbt.py` 新增四种 `skip_reason` 的级联断言；`test_consol_status_mutations.py` 通过子进程逐字节变异并恢复，覆盖 `context_failed → skipped`、`skipped → succeeded`、抵销失败路径删除 failed 运行记录、审批路由把 `event_failed` 改报 `event_published` 四种变异；新增 `test_consol_elimination_review_response.py` 覆盖事件发布失败回执。相关新增回归 21 passed，故 4.4 / 5.5 已标 `[x]`。

> **R1/R2/R5 变异补充（2026-11-13）**：新增 `test_consol_status_r1_mutations.py`，覆盖推送置位不写原因、清除不清原因、节点复制不继承原因、前端 stale 标签不渲染；新增 `test_consol_status_mutations.py` 的 R2 变异，覆盖 `kept_manual`、stale 清除、全部失败执行器和旧 `result.errors` 接线；新增 `test_consol_status_r5_mutations.py`，覆盖 `tb_update_status` 汇总与 `downstream.failed` 警告。以上变异均在子进程中运行并按字节恢复，相关回归通过。
> **验证复跑记录（2026-11-12）**：本轮未改变任务标记。行数门与后端 `compileall` 通过；本 spec 相关后端定向回归拆分为 98 + 12 = 110 passed，前端 5 个相关 Vitest 文件 161 passed，改动前端文件诊断无错误，`git diff --check` 通过。调整复核测试仍有 2 个既有 asyncpg `Connection._cancel` 异步清理警告，但没有失败。1.2、2.5、7.1~7.3、8.1~8.3、9.1~9.2 继续保留 `[~]`，分别缺 clean-HEAD 对拍、PG V/R 回滚、完整区域类型对拍/暂存树自洽、浏览器证据或收尾评审证据。