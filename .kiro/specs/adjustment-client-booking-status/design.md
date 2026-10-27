# 设计文档：调整分录阶段与「客户已入账」

需求编号见 requirements.md；现状事实只在 requirements 的 F 表。迁移号写 `V{n}`，实施第一步现扫取号。

## 1. 架构决策

**ADR-CB-01 入账记录单独成表，追加不覆盖。** 新表 `adjustment_client_bookings`：`id, project_id, year, entry_group_id, action ∈ {book, revoke}, voucher_keys JSONB（凭证键数组）, booked_dataset_id, note, created_by, created_at`。当前状态 = 该组最新一条记录（`book` 为已入账）。否决在 `adjustments` 每行加状态列：一组多行要同步改、历史会丢。

**ADR-CB-02 阶段存 `adjustments.audit_phase`。** 同组各行同值（与 `review_status` 一样按组写），`VARCHAR(16) NULL`，CHECK ∈ {preliminary, final}。

**ADR-CB-03 唯一判定 = SQL 谓词构造函数。** 新模块 `backend/app/services/adjustment_client_booking.py` 提供：

```
effective_booked_groups_clause(adj_table, *, project_id, year) -> ColumnElement
  -- 返回「该分录组未被生效的入账记录排除」的条件，形如：
  NOT EXISTS (
    SELECT 1 FROM adjustment_client_bookings b
    JOIN ledger_datasets bd ON bd.id = b.booked_dataset_id
    WHERE b.entry_group_id = adj.entry_group_id
      AND b.id = (该组最新一条记录的 id) AND b.action = 'book'
      AND bd.created_at <= (SELECT created_at FROM ledger_datasets
                            WHERE project_id = :p AND year = :y AND status = 'active'))
```

`adj_net`、`adj_net_batch` 增参数 `exclude_client_booked: bool = True`（计算口径缺省排除；只有展示类调用显式传 False），`recalc_adjustments` 无条件加该条件。无 active 版本时子查询为 NULL，比较不成立，即不排除（需求 3.4）。「最新一条」用 `DISTINCT ON (entry_group_id) … ORDER BY created_at DESC, id DESC` 的子查询实现，SQLite 测试走等价写法。

**ADR-CB-04 守卫钉三处同源、无第四处。** `test_adjustment_booking_single_source.py`：AST 扫 `backend/app`，凡对 `AdjustmentEntry` / `adjustment_entries` 做 `SUM(debit/credit)` 聚合的函数，要么在豁免清单（展示类，逐条写理由），要么引用 `effective_booked_groups_clause`；豁免清单有失效条目也打红。

**ADR-CB-05 事件。** 新增 `EventType.ADJUSTMENT_CLIENT_BOOKING_CHANGED`（payload 带受影响科目），复用 `_handle_adjustment_review_event`（trigger = `client_booking_changed`）重算调整列与审定数并发 TRIAL_BALANCE_UPDATED。账套激活已有全量重算（F4）；回滚事件实施时现读确认，未订阅试算表重算则补订阅。

**ADR-CB-06 疑似建议按需计算、不落库。** `suggest_bookings(db, project_id, year) -> list[Suggestion]`：取已审批、AJE、未生效入账的分录组；把各行标准科目经项目科目映射展开成客户科目集合；在 active 账套中按 (客户科目 ∈ 集合, 借贷栏, 金额) 取候选分录（不按日期过滤，见需求 4.1）；按凭证键分组，凭证内能为该组每一行各找一条不同的匹配分录（二分图匹配，组内行数小，暴力即可）才算候选。借贷栏与凭证键用 `voucher_identity`。单项目一次计算在和平药房规模下的耗时写入验收记录，超过 3 秒则加科目与金额的预筛索引查询。

**ADR-CB-07 底稿本地数据走提示与发布门，不自动扣减。** 否决自动从底稿调整列扣掉已入账金额：底稿本地数据形态各异（F3），带入来源不落库，无法确定某个底稿数字里含不含这组调整，自动扣减可能扣两次或扣错格。做法：①新事件订阅现有 `_mark_workpapers_stale_by_account`，过期原因带分录组编号；②新接口 `GET /workpapers/{wp_id}/client-booked-adjustments` 返回涉及本底稿科目（按 `wp_account_mapping`）的生效已入账分录组，提示条挂在底稿编辑器公共外壳，不逐个底稿改；③`publish-to-tb` 在发布科目涉及生效已入账分录组、且请求不带 `booked_adjustments_ack`（分录组 id 列表）时返回 409 `BOOKED_ADJUSTMENTS_UNACKED` + 清单；前端在 http 拦截器里统一处理该错误码：弹确认框列出分录组，确认后带 ack 重发原请求（不改 86 个调用点；实施时现读确认 `http` 与 `apiProxy` 都经同一拦截器），确认写审计日志。

## 2. 改动矩阵

| 位置 | 改动 | 需求 |
|---|---|---|
| 迁移 V{n} / R{n} | 新表 `adjustment_client_bookings`（索引 `(project_id, year, entry_group_id, created_at DESC)`）；`adjustments.audit_phase` 列与 CHECK | ADR-CB-01/02 |
| ORM `AdjustmentClientBooking`、`Adjustment.audit_phase`；schema `AdjustmentGroupResponse` 增 `audit_phase`、`client_booking{status, voucher_keys, booked_dataset_id, effective, created_by, created_at}` | 三层一致 | 1、2 |
| 新 `services/adjustment_client_booking.py` | 判定谓词、标记 / 撤销、历史、疑似建议 | 2、3、4 |
| `adjustment_amount_source.py` | `adj_net` / `adj_net_batch` 加 `exclude_client_booked` | 3.1、3.2 |
| `trial_balance_service.recalc_adjustments` | 加判定条件（净增约 3 行） | 3.1 |
| `adjustment_service` 新建分录 | 阶段取项目当前阶段（字段未落地缺省 final） | 1.1 |
| 新路由 `routers/adjustment_client_booking.py` | `POST …/adjustments/{entry_group_id}/client-booking`（标记）、`POST …/client-booking/revoke`、`GET …/client-booking/history`、`GET …/adjustments/client-booking/suggestions`；在 `router_registry` 注册；edit / readonly 鉴权表驱动测试 | 2、4 |
| `routers/adjustments.py` | 列表富化增阶段与入账状态（在 `_enrich_adjustment_list` 内，净增 ≤ 20 行）、按阶段与入账状态筛选、更新接口允许改阶段 | 1.2、5.1 |
| 调整分录汇总导出 | 单列「已由客户更正」区 | 3.3 |
| 事件 | 新 EventType + 订阅；回滚事件重算补订阅（若缺） | 3.5 |
| 前端 `Adjustments.vue` | 两列、筛选、操作入口、提示条（逻辑放新组件，页面净增 ≤ 60 行） | 5.1 |
| 新组件 `ClientBookingDialog.vue`、`ClientBookingSuggestionBar.vue` | 选择入账凭证（候选或按凭证键搜索）、并排对照、撤销原因 | 2.2、2.3、4.2 |
| 新组件 `AdjustmentCentralStatusTag.vue` + `useAdjustmentCentralSync` 的 `CentralStatus` 增 `client_booking_status` | 82 个底稿调整 tab 的内联标签批量替换为组件（脚本化替换，逐文件 diff 复核） | 5.2 |
| 底稿过期原因、`GET /workpapers/{wp_id}/client-booked-adjustments`、底稿编辑器公共外壳提示条 | ADR-CB-07 ①② | 3.6 |
| `routers/wp_html_save.publish_determination_to_tb` + 前端 `utils/http.ts` 拦截器 | ADR-CB-07 ③（409 + 确认重发 + 审计日志） | 3.6 |

## 3. 关键流程

标记：校验分录组为 AJE 且 approved → 校验每个入账凭证键在当前 active 账套存在 → 写 `book` 记录（`booked_dataset_id` = 当前 active）→ flush → 发 ADJUSTMENT_CLIENT_BOOKING_CHANGED（受影响科目 = 该组标准科目）→ router commit。撤销：写 `revoke` 记录 + 同一事件。服务只 flush，路由 commit。

生效计算示例：预审版本 D1（2025-10 导入）上提出 AJE；客户 12 月入账；年审导入 D2 并激活；在 D2 上标记（booked_dataset = D2）→ 生效；回滚到 D1 → D2.created_at > D1.created_at ⇒ 不生效，AJE 恢复计入；再激活 D3（更新的版本）⇒ 生效。

## 4. 测试与验收

- `test_adjustment_client_booking_pg.py`（pg_only，回滚事务）：需求 6.1 全流程；`adj_net`、`adj_net_batch`、`recalc_adjustments` 三处结果一致；RJE 与未审批组拒绝标记（400 + 中文原因）；入账凭证不在当前账套拒绝。
- `test_adjustment_booking_suggestions_pg.py`：需求 6.2；同组多个候选全部列出并按日期接近程度排序；借贷栏相反的凭证不列出。
- `test_adjustment_booking_single_source.py`：ADR-CB-04 守卫。
- 端点鉴权表驱动：标记 / 撤销 edit，历史 / 建议 readonly，跨项目 403。
- 发布门：发布科目涉及生效已入账分录组时未确认 409、带 ack 放行并写审计日志、不涉及时照常；拦截器确认后带 ack 重发、取消不重发。
- 前端：`ClientBookingDialog.spec.ts`、`AdjustmentCentralStatusTag.spec.ts`；替换后 82 个 tab 的标签守卫（不得再出现内联 `集中登记：{{ CENTRAL_STATUS_LABELS` 写法）。
- 变异：判定里去掉生效时间比较 → 回滚恢复计入用例红；`adj_net_batch` 缺省改为不排除 → 三处一致用例红；建议匹配去掉金额相等 → 改一分钱用例红；守卫豁免清单加一条不存在的函数 → 守卫红。
- 浏览器（chrome-devtools，【测试】项目）：需求 6.4。

## 5. 风险

| 风险 | 处理 |
|---|---|
| 漏掉某个直接聚合调整分录的计算点 | ADR-CB-04 AST 守卫 + 豁免清单逐条理由 |
| 客户只入账了部分金额 | 本轮只支持整组入账；部分入账请审计师调整 AJE 金额后再标记，界面写明 |
| 标记时选错凭证 | 并排对照 + 撤销留痕 |
| 82 个 tab 批量替换与并发会话冲突 | 私有 worktree 内脚本替换，动手前重读，提交只含本批文件 |
