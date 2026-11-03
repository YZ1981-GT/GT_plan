# 实施计划：调整分录阶段与「客户已入账」（adjustment-client-booking-status）

> 以 design.md 为准。标完成须有代码 + 测试证据 + 至少一条磁盘变异证明（备份到 `tmp_adjustment_booking/mutations/`，注入、确认红在预期处、逐字节还原核对 sha256）。环境做不到的标 `[ ]*`。约束同 `voucher-identity-writeback-and-audit-phase/tasks.md` 页头；临时产物放 `tmp_adjustment_booking/`。依赖：凭证键 `voucher_identity.py`（该 spec 任务 2）、项目当前审计阶段（该 spec 任务 8，未落地时阶段缺省 final）。

- [ ] 1. 迁移与模型（ADR-CB-01/02）
  - 现扫取号；新表 `adjustment_client_bookings` 与索引、`adjustments.audit_phase` 与 CHECK；R{n}；ORM 与 schema（`AdjustmentGroupResponse` 增两字段）
  - Verify: `MigrationRunner(...).run_pending()` 落本地库；三层一致测试。变异：ORM 漏 `audit_phase` → 三层一致用例红

- [ ] 2. 唯一判定与三处接入（需求 3.1、3.2、3.4，ADR-CB-03/04）
  - `adjustment_client_booking.effective_booked_groups_clause`；`adj_net` / `adj_net_batch` 加 `exclude_client_booked`（缺省 True，展示类调用点逐个现读后显式传 False）；`recalc_adjustments` 加条件
  - AST 守卫 `test_adjustment_booking_single_source.py` 与豁免清单
  - Files: `backend/app/services/adjustment_client_booking.py`、`adjustment_amount_source.py`、`trial_balance_service.py`、测试
  - Verify: pg_only 回滚事务内三处取数一致、回滚账套后恢复计入。变异：去掉生效时间比较 → 回滚用例红；`adj_net_batch` 缺省改 False → 一致性用例红

- [ ] 3. 标记、撤销、历史接口与事件（需求 1.1、2、3.5，ADR-CB-05）
  - 服务：标记（AJE + approved + 凭证在当前账套）/ 撤销（原因必填）/ 历史；新建分录阶段取项目当前阶段
  - 新路由 `routers/adjustment_client_booking.py` 并注册；`EventType.ADJUSTMENT_CLIENT_BOOKING_CHANGED` 与订阅；回滚事件试算表重算现读确认，缺则补订阅
  - Verify: 鉴权表驱动（edit / readonly / 跨项目 403）；RJE、未审批、凭证不存在三种拒绝带中文原因；标记后调整列重算。变异：去掉 approved 校验 → 拒绝用例红

- [ ] 4. 疑似已入账建议（需求 4，ADR-CB-06）
  - `suggest_bookings` 与 `GET …/client-booking/suggestions`
  - Verify: `test_adjustment_booking_suggestions_pg.py`（完全对应列出、改一分钱不列、多候选全列且按日期接近程度排序、借贷栏相反不列）；和平药房规模耗时记录。变异：去掉金额相等 → 用例红

- [ ] 5. 列表、筛选、导出（需求 1.2、1.3、3.3）
  - `routers/adjustments.py` 列表富化与筛选（净增 ≤ 20 行）、更新接口改阶段写审计日志；汇总导出单列「已由客户更正」
  - Verify: 列表与导出端点测试；行数门通过

- [ ] 6. 调整分录页界面（需求 5.1、5.3）
  - `Adjustments.vue` 两列与筛选（净增 ≤ 60 行）；新组件 `ClientBookingDialog.vue`、`ClientBookingSuggestionBar.vue`
  - Verify: 组件单测；ESLint；单区域 vue-tsc；浏览器打开页面无报错

- [ ] 7. 底稿调整 tab 状态标签（需求 5.2）
  - `AdjustmentCentralStatusTag.vue`；`CentralStatus` 增 `client_booking_status`；82 个 tab 内联标签脚本化替换为组件（逐文件 diff 复核），守卫禁止内联写法
  - Verify: 组件单测 + 守卫；浏览器抽查 D2、G2、K1 的调整 tab。变异：守卫清单外加回一处内联写法 → 守卫红

- [ ] 8. 底稿侧提示与发布门（需求 3.6，ADR-CB-07）
  - 新事件订阅 `_mark_workpapers_stale_by_account`（过期原因带分录组编号）；`GET /workpapers/{wp_id}/client-booked-adjustments`；底稿编辑器公共外壳提示条
  - `publish_determination_to_tb`：发布科目涉及生效已入账分录组且无 `booked_adjustments_ack` → 409 `BOOKED_ADJUSTMENTS_UNACKED` + 清单；带 ack 放行并写审计日志
  - 前端 http 拦截器统一处理该错误码（确认框 → 带 ack 重发），现读确认 `http` 与 `apiProxy` 同经此拦截器
  - Files: `routers/wp_html_save.py`、`services/event_handlers/_impl.py`、新接口所在路由、底稿编辑器外壳组件、`utils/http.ts`
  - Verify: 发布门端点测试（未确认 409、确认放行、不涉及科目照常 200）；拦截器单测（重发带 ack、取消不重发）；浏览器在 D2 发布时出现确认框。变异：发布门判断取反 → 409 用例红；拦截器重发漏带 ack → 用例红

- [ ] 9. 验收与收尾（需求 6）
  - pg_only 全流程（需求 6.1、6.2）；【测试】项目浏览器全流程（需求 6.4），清理对账
  - 变异记录汇总；干净 worktree 跑要提交的树，失败集合与 HEAD 对比；INDEX.md 登记
