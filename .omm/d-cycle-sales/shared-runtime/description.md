# 共享运行时（D 循环消费方，实现在别处）

D 循环各科目**不自建**这些能力，全部由平台共享层提供；改这些等于改全平台。

## 1. 渲染与运行时边界

`GtWpRenderer.vue` 是统一渲染器，也是 **Runtime Boundary**：`provide` 全部横切能力
（`openReviewDialog` / `generateAiText` / `WorkpaperRuntimeContextKey` 内的 `version.scheduleAutoSnapshot`）。
子组件 `inject` 即用，**禁止自建 provider 或 Host**（会重复挂载）。

它也承担 `?sheet=` 深链定位（`initial-sheet` prop，精确匹配失败可按编码 endsWith/includes 兜底）
与全局「本页 AI 复核」工具栏（一处接入覆盖 A–N 全循环）。

## 2. 持久化工厂

`useChecklistPersistence` + `createChecklistFormData` 工厂：各科目 `useDxFormData` 基于它，
统一 `allResponses: Ref<Map>` + 防抖 PUT + `item_id` 强制注入（从 `responses_snapshot` 载入时若不补 `item_id`，保存会 422 静默丢数据）。

## 3. 账龄配置

`useAgingConfig(projectId, subject)` — 项目级 `wizard_state.aging_config`，
预设 `THREE_YEAR` / `FIVE_YEAR` / `CUSTOM`，段 key `within1/y1to2/y2to3/y3to4/y4to5/over3/over5`。
入口在项目设置中心「底稿配置」tab（manager+）。PUT 后 `broadcast_raw('aging-config:changed')` 刷新各表。

## 4. 抽凭引擎

`GtVoucherSamplingEngine`（`voucher-sampling/`）— 五法（随机/分层/特定/系统/MUS）+ CAS1314 泊松表 +
MUS 间隔与高值必选 + 错报推断 UML + 重抽治理 + 版本快照。
**API 契约**：`account-code`（单数）+ `phase`（仅 `preliminary|final`）+ `workpaper-id` + `year` 全 required，
emit `filled` 返回**对象** `{samples, phase, fillMode, methodology}`。

## 5. 截止测试

`useCycleCutoff` / `useCutoffAutoSampling` + **`cutoffCanonical`（跨期判定单一真源）**：
两种模式并存且语义不等价——`cutoff-boundary`（截止日两侧 XOR，D3/D7/I2/I6 用）与
`natural-month`（自然月比较，K8/K9 用）。结论 6 态状态机，缺双侧证据判「证据不完整」不判「正常」。
自动提取走 `POST /sampling/cutoff-test`（须传 `cutoff_date`，否则后端按 year-12-31 推）。

## 6. 集中调整登记

`useAdjustmentCentralSync` → `POST /adjustments/sync-from-workpaper`，幂等 `source_ref={wp_id}:{item_id}`，
`origin='workpaper'`；`trial_balance` recalc 过滤 `origin != 'workpaper'` 防与审定表回写双计；
协作接力（assign→acknowledge→contribute→confirm）期间有 `COLLABORATION_LOCKED` 锁防 re-sync 覆盖。

## 7. 错报桥

`useA13MisstatementBridge`（挂 `WorkpaperEditor.vue`）是 `a13:push-misstatement` 的**唯一消费者**：
归一 4 种 payload 形态 → `POST /api/projects/{pid}/misstatements`（`source_wp_code` 溯源，5s 去重窗口）。
各底稿只管 emit，不要自己写库。

## 8. 附注联动三件套

`noteDisclosureJump`（正向）/ `noteDisclosureReverseJump`（反向）/ `useNoteRefresh`（定向刷新），
加后端 `wp_disclosure_sync_service.sync_from_workpaper`。覆盖率有 CI 守卫
（`check_disclosure_columns_coverage.py --strict`，每个 sync 调用点必须登记 columns 构造器）。

## 9. 版本链与复核

`useWorkpaperVersionToolbar` + `GtWpVersionTrail`（保存后 `scheduleAutoSnapshot`）；
`GtReviewTrigger` + `GtReviewDot`（主入口需 `provide('getThreadDot')` / `provide('getRowDot')`，
`openReviewDialog` 由 Runtime Boundary 提供）。
