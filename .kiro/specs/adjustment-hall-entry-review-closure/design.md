# 设计文档：adjustment-hall-entry-review-closure

需求见 requirements.md（事实 F1~F12）。本文只写怎么做。

## 1. 复核状态机（D1）

| 当前 | 动作 | 目标 | 端点 | 权限 |
|---|---|---|---|---|
| 草稿 / 已驳回 | 提交复核 | 待复核 | `POST /submit-review`（批量） | `adjustment:edit` |
| 待复核 | 撤回提交 | 草稿 | `POST /{gid}/withdraw-submission` | `adjustment:edit` |
| 草稿 / 待复核 | 通过 / 驳回 | 已批准 / 已驳回 | `POST /{gid}/review`（保留）、`POST /review-batch`（新） | `adjustment:review` + 合并锁 |
| 已批准 | 撤回复核 | 草稿 | `POST /{gid}/revoke-review`（保留） | `adjustment:review` + 合并锁 |
| 已驳回 | 修改明细 | 草稿 | `PUT /{gid}`（既有） | edit 级 |

- `_VALID_TRANSITIONS` 增 `rejected → pending_review`、`pending_review → draft`；后者与 `approved → draft` 一样只能走专用端点（`allow_withdraw` / `allow_approved_revoke` 开关），`/review` 传 draft 仍拒绝。
- 提交与撤回提交清空复核人、复核时间、驳回原因（历史在审计日志里）。
- `/review` 的权限不变（`test_adjustment_review_permission.py` 全部保持），提交复核改走新端点，审计员 / 质控因此能提交、仍不能审批。
- 草稿可被复核人直接通过（既有行为，链路测试依赖）保留。

## 2. 通知（D2）

新模块 `services/adjustment_hall_notify.py`：

- 类型（`notification_types.py`，前端 `notificationTypes.ts` 同步）：`adjustment.review_submitted` / `adjustment.review_approved` / `adjustment.review_rejected` / `adjustment.review_revoked` / `adjustment.approved_impact`；底稿推送沿用 `adjustment_sync_arrived`（补登记常量）。集合 `ADJ_HALL_NOTIFICATION_TYPES` 供前后端契约测试。
- 接收人：
  - 复核人候选 = 本项目未删除、启用的成员（`project_users` 级别 ≥ review）中合并权限含 `adjustment:review` 的人（项目角色权限 ∪ 系统角色权限，与 `resolve_project_context` 同口径；admin 视为有）。提交时传 `reviewer_ids` 则必须是候选子集（否则 400），不传则取全部候选；都排除操作人。
  - 编制人 = 分录组各行 `created_by` 去重。
  - 受影响底稿负责人 = 手工来源分录在通过 / 撤回复核时，`workpapers_for_account_codes(科目, include_parent=True)` → 本项目 `working_paper.assigned_to`；排除操作人与已作为编制人收到通知的人。
- 每次操作对每个接收人一条通知（批量合并列出编号，最多列 10 个）；metadata `{project_id, year, object_type: 'adjustment', object_id: 首个分录组, entry_group_ids, adjustment_nos}`。
- 写入：直接建 `Notification` 行，每条在 `begin_nested()` 保存点内 flush；失败只记 warning，不污染主事务；由路由与状态变更一起 commit。
- 跳转：`/projects/{pid}/adjustments?focus={gid}&year={year}`；大厅收到 `focus` 后定位到该行所在页、展开并高亮，然后清掉参数。

## 3. 录入（D3）

- 新模块 `services/adjustment_entry_rules.py`：`normalize_line_items(items) -> list`（金额按分舍入）与 `entry_rule_errors(items) -> list[str]`（需求 1.2 全部规则，中文、带行号）。`create_entry` / `update_entry` 在原借贷校验处改调它（原「借贷不平衡」文案保留为其中一条）；导入预检同调它。
- `AdjustmentCreate.adjustment_no: str | None`：去空白、≤ 30 字；同项目同年度未删除分录组已占用 ⇒ ValueError「编号 X 已被使用」。
- `_next_adjustment_no`：在原「计数 + 1」基础上，跳过未删除分录组已占用的号（自定义编号、覆盖导入钉入的编号不再与自动编号撞）。
- `get_account_dropdown(project_id, report_line_code=None, year=None)`：不传行次时返回全部标准科目，左连接已确认映射取报表项目；传 `year` 时附 `balance`（试算表审定数，按标准码）。`AccountOption` 增 `balance: Decimal | None`。

## 4. 导入（D4）

新模块 `services/adjustment_import_service.py`，`routers/import_templates._import_adjustments` 改为薄壳委托（签名与返回形状不变，既有特征测试继续守契约）。

- 行 → 分录组 `build_import_groups(rows)`（纯函数）：
  - 有编号：同编号合并（文件中位置不连续也合并）。
  - 无编号：连续无编号行累计，借贷合计相等且大于 0 时切出一笔；遇到有编号的行或文件结束时，未闭合的累计组成为一笔（报不平衡）。
  - 类型取组内首个非空值，非 AJE / RJE 报错；摘要取组内首个非空值。
  - 金额：去千分位与货币符号；无法识别 / 为负 / 同行借贷都有数 ⇒ 行级错误；按分舍入。
  - 科目解析沿用原逻辑（一级码 > 二级码归一 > 名称反查），抽成 `AccountResolver`（一次装载科目表与映射，查询顺序不变：AccountChart → AccountMapping）。
- `preview_import(db, project_id, year, rows, mode)`：逐笔给出 `{key, adjustment_no, type, description, rows, lines[{row, code, name, debit, credit}], total_debit, total_credit, action: create|replace|skip, ok, errors[]}`，不写库；错误用 `entry_rule_errors` 与科目解析结果。
- `import_rows(...)`：逐笔 `async with db.begin_nested()`；覆盖模式「删旧 + 建新 + 钉编号」在同一保存点内；失败回滚该保存点并记录原因。返回 `{imported, skipped, failed, failed_rows[, skipped_rows], created_groups}`；薄壳只透出原有键。
- 端点（新路由 `routers/adjustment_import.py`，前缀 `/api/projects/{project_id}/adjustments/import`）：`POST /preview`（readonly）与 `POST ""`（edit + 合并锁），`year` 必填、`mode=append|overwrite`、`file`。
- 旧通用端点 `/api/import-templates/{type}/import`：项目数据类型（调整分录、报表、附注、底稿、公式、试算表）带 `project_id` 时先 `assert_project_permission(edit)`；调整分录缺 `project_id` 或 `year` 时 400。
- 富模板「关注事项」改写为实际规则；sheet 名与列头不变（特征测试锁定）。
- 导出汇总：分页循环取全部分录；列头末尾加「复核状态」。

## 5. 底稿推送（D5）

- `sync_from_workpaper` 额外返回推送结果 `outcome`（created / updated / unchanged）与 `previous_status`；路由把两者并入响应。
- 通知只在 created / updated 时发，传入解析后的标准科目；补登记类型常量，metadata 加 `object_type` / `object_id` / `year`。
- 列表富化修 `StaffMember.name`，并附 `reviewer_name`、`source_wp_code`（`source_ref` 的 wp_id → `working_paper` → `wp_index.wp_code`）、`source_missing`（底稿已删除或不存在）。
- `useAdjustmentCentralSync`：请求带 `_silent`；按 outcome 提示；所有错误码显示后端 `message`。

## 6. 其余修复（D6）

- `POST /batch-delete`：`ids` 按分录组 id 处理，逐组保存点，返回逐组结果。
- 删除 `_writeback_to_source_workpaper` 与 confirm 端点里的调用；`test_lazy_import_resolvability` 基线删去对应条目。
- `related-workpapers` 改 `require_project_access("readonly")`；`conflict_guard` 三个锁端点改 `require_project_access("edit")`；`reclassification` 三个端点补项目级鉴权，`inline-submit` 改走 `AdjustmentService.create_entry`（RJE）。
- 复核 / 撤回复核 / 批量复核加 `check_consol_lock`。

## 7. 前端（D7）

- `services/auditPlatformApi.ts` 增：`submitAdjustmentsForReview`、`reviewAdjustmentsBatch`、`withdrawAdjustmentSubmission`、`listAdjustmentReviewers`、`previewAdjustmentImport`、`importAdjustments`、`batchDeleteAdjustments`；调用方自管提示的请求带 `_silent`。
- 新组件（`components/adjustment/`）：
  - `AdjustmentEntryDialog.vue`：新建 / 编辑 / 预填；科目下拉、编号、行校验（`adjustmentLineRules.ts`，与后端同规则）、快捷模板（`adjustmentQuickTemplates.ts`，按名称匹配）、影响预览、草稿自动保存。
  - `AdjustmentSubmitReviewDialog.vue`：所选分录、复核人多选（默认全选）、备注；返回通知结果。
  - `AdjustmentReasonDialog.vue`：驳回（统一 / 逐笔原因，必填）与撤回复核（原因可选）。
  - `AdjustmentImportDialog.vue`：模板下载（国企 / 上市）→ 选文件与模式 → 预检表 → 导入 → 结果（可一键提交复核）。
- `composables/useAdjustmentHallActions.ts`：提交、撤回提交、通过、驳回、撤回复核、删除、批量删除、转错报；统一确认、加载态、错误解析（`parseApiError`）、成功后刷新。
- `Adjustments.vue`：状态筛选与计数、按状态与权限的操作列（`canEdit` × `adjustment:edit` / `adjustment:review`）、「更多」下拉、`?focus=` 定位高亮、全部分页取数、修 F5；去批量模式；保留年度路由优先、`onContextChange`、SSE `onReconnect` 等既有守卫锁定的写法。
- `notificationTypes.ts`：新类型的标签与跳转；`adjustment_sync_arrived` 补标签。
- 手册 `adjustments-module-handbook.md` 按新流程改写。

## 8. 行数门（D8）

后端新逻辑全部放新模块；`routers/adjustments.py` 删协作回写后净减；`import_templates.py` 的导入实现迁出后净减。前端弹窗与操作逻辑迁出后 `Adjustments.vue` 目标 ≤ 1500 行，白名单条目随之删除或下调到实际值。

## 9. 风险与取舍

- 批量复核逐笔发 ADJUSTMENT_APPROVED（与单笔语义一致，事件按分录组去重），批量 N 笔会触发 N 次重算；已有 500ms 防抖，按真实规模可接受。
- 列表的循环范围过滤在分页之后执行（既有），受限用户分页取全量时可能少取；本 spec 不改，登记为已知限制。
- 81 个底稿 tab 的按钮在行为空时禁用，底稿删光分录后大厅的孤儿草稿仍需在大厅手动删除（大厅已标「来源」，手册写明）。

## 10. 实施勘误与验收记录（2026-10-31）

### 10.1 主工作树陈旧导致的误判（已撤回）

- 主工作树对 315 个文件停在 `9791805c8`，HEAD 已前移到 `6f4c5a54a`（别的会话 update-ref 前移、磁盘没跟上）。例如 `composables/adjustmentEntryGroupLocate.ts` 在 HEAD 里存在、磁盘上没有。
- 在陈旧代码上，我判断「底稿编辑器不读 `?highlight=`」，把来源跳转改成只带 `?sheet=`。实际 HEAD 的 `273604d05`（wp-deeplink-locate-residual-closure）已实现 `?sheet=@adjustment&highlight=source_ref` 定位分录组，并有守卫 `adjustmentEntryGroupWiring.spec.ts`。已恢复 HEAD 写法。
- 另一处后果：别的会话的提交把我重写后的 `Adjustments.vue` 带进了 HEAD，却没带它依赖的 7 个新模块和 `listAllAdjustments`，HEAD 上调整分录页编译不过；本 spec 推送后恢复。
- 验证一律改在候选树做（最新 HEAD + 本 spec，三方合并按每个文件的真实编辑基线；最小差异法给 `import_templates.py` 挑到旧短版本，人工更正为 HEAD）。

### 10.2 HEAD 预存问题（不归本 spec，未改）

- 批量建项会话的 11 个服务模块（`project_creation_grant_service` / `batch_project_inventory` / `group_topology_lock` / `project_subsidiary_attachment_service` 等）未入库，而引用它们的 `api/users.py`、`project_wizard.py`、`recycle_bin.py`、`pm_dashboard.py`、`continuous_audit_service.py` 已入库：干净检出时 `app.main` 导入失败，挂 `app.main` 的路由守卫全部 setup error，lazy-import 守卫 11 条、全局名棘轮 1 条红。
- 两边都红、与本 spec 无关：`test_convert_force_bypasses_idempotency`、`test_p7_recalc_does_not_read_detail_account_code`、「仅登录不校项目」152 → 164；前端 `ReportView.vue` 切年度 3 条、K13-3 契约 1 条、`NativeLoadBearerGuard` 失效登记 1 条、`useReportExport.ts` 转译失败（`await` 不在 async 函数里）。
- ESLint 唯一 warning 在 `useAdjustmentCentralSync.ts` 的 `totalDebit` 算术，HEAD 原样存在。

### 10.3 与设计不同的实现

- 新组件 5 个，多了 `AdjustmentHallTable.vue`：`GtEditableTable` 只读时不显示勾选列（批量复核栏出不来），也不支持 row-key、展开与高亮。
- §2「定位后清掉参数」作废：本页按 fullPath 重挂，改 query 会整页重挂、把刚打开的弹窗冲掉，`?focus=` / `?highlight=` / `?group=` 每次挂载只应用一次、留在地址栏。
- 单笔与批量通过 / 驳回都走 `/review-batch`；撤回复核逐笔调 `/revoke-review`。
- 提交弹窗在有候选复核人时至少选一位（后端 `reviewer_ids` 为空 = 通知全部候选）。

### 10.4 浏览器实测（【测试】调整大厅验收_2025，admin）

录入 / 编辑（已驳回回草稿，弹窗顶部显示驳回原因）/ 差额补平 / 影响预览 / 模板匹配 → 提交复核（通知落库给复核人）→ 单笔与批量驳回（统一 + 逐笔原因）→ 修改重提 → 撤回提交 → 通过（试算表 1231 / 6702 aje +15000、1122 / 6001 −8000，底稿负责人收到影响通知）→ 批量撤回复核（审定数回退为 0）；批量栏按状态算可做数并提示跳过；状态筛选与计数；`?focus=` 直链与通知中心点击都能定位高亮；导出汇总；导出模板 + 版本不匹配确认；导入预检（来源行、逐行错因、示例行跳过）→ 导入 2 成 2 败 → 一键提交本次；覆盖模式（待复核跳过并写原因、草稿整笔替换且旧行软删）；底稿推送 created → unchanged → updated、来源列「底稿 D2」、底稿汇聚筛选、跳来源底稿；转未更正错报；删除后从通知里撤销还原；console 无 error。

实测抓到并修复：
1. 导入结果「提交复核（本次 N 笔）」弹窗摘要全是「（无摘要）」——回执只带编号。新增 `withDescriptions` 从刷新后的列表补摘要，保存后提交也走它。
2. 大厅表格：状态列被固定的操作列盖住、操作按钮折成两行。状态列改右侧固定，操作按钮单行，日期移入展开区。
3. 影响预览的报表类型显示英文枚举（`income_statement`），改为中文报表名。
