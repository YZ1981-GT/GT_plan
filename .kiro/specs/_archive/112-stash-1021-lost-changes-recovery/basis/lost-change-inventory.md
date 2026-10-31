# 2026-10-21 救援 stash 丢失文件清册

## 口径与结论

- 共同基线：`dae1129f5`。事故 stash：`112bfabec`。本轮恢复基线：`origin/spec/disclosure-note-doc-upload-and-batch-fill` 的 `434e87972`（v1.0.58）。
- “完整丢失”指当前文件 blob 与共同基线相同，stash 对该文件的改动尚未回到目标分支。共 **82 个已跟踪文件**。另有 **134 个已分叉文件**，其中旧 hunk 可能部分缺失；它们不计入 82。
- stash 中有 **133 个未跟踪文件**。其中 109 个已经入库，剩余 **24 个**在下文逐项判定。
- 本清册只决定恢复优先级。本次只恢复 `[本轮恢复]` 的 AI 采纳 / 转存笔记链路；其余一律不从旧 stash 直接检出。

| 标记 | 含义 |
|---|---|
| `[本轮恢复]` | 本 spec 恢复，按三方合并并完成验证。 |
| `[重开并 rebase]` | 业务意图仍有效，但旧 patch 已被后续提交包围；由归属 spec 基于当前 HEAD 逐 hunk 迁移、测试。 |
| `[待 owner]` | 缺少可验证业务意图，或会削弱/删除现有门禁；先由原领域负责人裁决。 |
| `[不取旧版]` | 已被后续实现取代，或属于生成物；保留当前版本，必要时从当前输入重生成。 |
| `[保持当前]` | stash 记录的是删除意图；本轮不删除当前已跟踪文件。 |

### 关键实证

1. `useWorkpaperSyncBridge.descriptor` 只在 `switchToOnlyOffice()` 成功后赋值，而当前 A 循环 14 个宿主没有任何驱动调用，在线编辑会停在“正在打开同步编辑器…”。这不是可忽略的测试差异，需在 `a-cycle-online-edit-driver-closure` 重开后整体恢复。
2. 在隔离树将 82 个前端旧改动叠加后，选集失败从 103 降至 20，但 N1 路由新增 9 个失败，证明不能批量把旧 stash 当作当前 HEAD 的正确版本。
3. 当前 `wp_template_files` 已有公式设置预填接线；`startup_registry` 已注册公式设置传播 handler。相应旧 patch 若只补回调用方或测试，必须重新按当前实现判定。
4. 两个同步 generated 文件与 JSON 在当前输入下的 `--check` 已失败，旧 stash 版本不可作为权威输出。

## A. 82 个完整丢失的已跟踪文件

| # | 文件 | 归属 spec / 依据 | 结论与建议 |
|---:|---|---|---|
| 1 | `frontendSourceScan.ts` | `frontend-test-network-isolation-and-load-dedup` 的前端基线修复 | `[重开并 rebase]` 旧 patch 排除 generated `.d.ts` 扫描，意图合理；应以当前扫描器和生成物重测后迁移。 |
| 2 | `authTokenSingleSource.spec.ts` | 未见独立 spec；注释指向跨窗口会话接力 | `[重开并 rebase]` 允许 `main.ts` / `http.ts` 的同源 sessionStorage 访问，先按当前跨窗口实现复核，不能仅为消红放宽。 |
| 3 | `PlatformAiChatPanel.vue` | `ai-chat-adopt-and-note-target-picker` | `[本轮恢复]` 挂载已有的目标选择与笔记位置对话框。 |
| 4 | `components/ai/__tests__/PhaseBGateGuards.spec.ts` | `ai-chat-adopt-and-note-target-picker` | `[本轮恢复]` 与面板接线一同恢复的既有回归覆盖。 |
| 5 | `TraceSourcePopover.spec.ts` | 前端全量失败修复会话，未登记独立 spec | `[重开并 rebase]` 只迁移与当前组件响应形状仍一致的断言。 |
| 6 | `ConflictBanner.spec.ts` | 前端全量失败修复会话，未登记独立 spec | `[重开并 rebase]` 先按现行项目切换与请求竞态逻辑复核。 |
| 7 | `OnlyOfficeEditor.spec.ts` | `deliverable-writeback-and-online-edit-integrity` 相邻测试面 | `[重开并 rebase]` 当前编辑器实现已演进，旧 iframe 断言不能直接覆盖。 |
| 8 | `TbComparison.pbt.spec.ts` | 试算表对比导出测试面，未登记独立 spec | `[重开并 rebase]` 先确认当前列契约，再更新 PBT。 |
| 9 | `GtA101GovernanceCommunication.vue` | `a-cycle-online-edit-driver-closure` | `[重开并 rebase]` A 类宿主缺 driver；与其余 A 宿主一起恢复。 |
| 10 | `GtA111SubsequentEventsInquiry.vue` | `a-cycle-online-edit-driver-closure` | `[重开并 rebase]` A 类宿主缺 driver；与其余 A 宿主一起恢复。 |
| 11 | `GtA1721Kam.vue` | `a-cycle-online-edit-driver-closure` | `[重开并 rebase]` A 类宿主缺 driver；与其余 A 宿主一起恢复。 |
| 12 | `GtA1731ConsultationExecution.vue` | `a-cycle-online-edit-driver-closure` | `[重开并 rebase]` A 类宿主缺 driver；与其余 A 宿主一起恢复。 |
| 13 | `GtA173ConsultationRecord.vue` | `a-cycle-online-edit-driver-closure` | `[重开并 rebase]` A 类宿主缺 driver；与其余 A 宿主一起恢复。 |
| 14 | `GtA174DisagreementRecord.vue` | `a-cycle-online-edit-driver-closure` | `[重开并 rebase]` A 类宿主缺 driver；与其余 A 宿主一起恢复。 |
| 15 | `GtA176ClosingMeeting.vue` | `a-cycle-online-edit-driver-closure` | `[重开并 rebase]` B 类预生成宿主缺 driver；需保留预生成钩子。 |
| 16 | `GtA177IndependenceDeclaration.vue` | `a-cycle-online-edit-driver-closure` | `[重开并 rebase]` B 类预生成宿主缺 driver；需保留预生成钩子。 |
| 17 | `GtA182RegulatoryCommunication.vue` | `a-cycle-online-edit-driver-closure` | `[重开并 rebase]` A 类宿主缺 driver；与其余 A 宿主一起恢复。 |
| 18 | `GtA271ItAuditMemo.vue` | `a-cycle-online-edit-driver-closure` | `[重开并 rebase]` A 类宿主缺 driver；与其余 A 宿主一起恢复。 |
| 19 | `GtA51CashflowAudit.vue` | A 循环认证请求修复，未登记独立 spec | `[重开并 rebase]` 为原生 fetch 补鉴权头；先确认 debug 端点仍应由前端访问。 |
| 20 | `GtA81OtherInfoRepresentation.vue` | `a-cycle-online-edit-driver-closure` | `[重开并 rebase]` A 类宿主缺 driver；与其余 A 宿主一起恢复。 |
| 21 | `GtA91DeficiencyLetter.vue` | `a-cycle-online-edit-driver-closure` | `[重开并 rebase]` A 类宿主缺 driver；与其余 A 宿主一起恢复。 |
| 22 | `GtB22AControlMatrix.vue` | B 循环在线编辑容器样式，未登记独立 spec | `[重开并 rebase]` 固定 OO 容器高度是可见缺陷候选；浏览器确认后再迁移。 |
| 23 | `GtN1DeferredTaxAssets.vue` | `n1-n3-host-inline-router-and-shared-adoption` | `[不取旧版]` 10-26 的共享 N1 路由已改写；叠加旧 patch 会新增 9 个 N1 路由失败。 |
| 24 | `GtA111SubsequentEventsInquiry.spec.ts` | `a-cycle-online-edit-driver-closure` | `[重开并 rebase]` 与 A111 driver 恢复同批更新。 |
| 25 | `GtC22ItgcBundle.integration.spec.ts` | C22 ITGC 宿主链路 | `[重开并 rebase]` 比对当前 C22 子册与真实 sheet 名契约后迁移。 |
| 26 | `GtWpRuntimeBoundary.pbt.spec.ts` | 前端运行时边界，未登记独立 spec | `[重开并 rebase]` 当前 component registry 改动较多，保留 property 但重建断言。 |
| 27 | `b23ProcessControl.pbt.spec.ts`（删除） | B23 控制程序，未登记独立 spec | `[待 owner]` 当前稳定 29 红；旧 patch 删除 2,497 行用例，不能为消红直接删除。 |
| 28 | `b23ProcessControlRework.pbt.spec.ts` | B23 控制程序重写用例 | `[待 owner]` 仅与第 27 项成对裁决，确认替代 PBT 覆盖后才采纳。 |
| 29 | `b23Property7And8.pbt.spec.ts` | B23 控制程序属性用例 | `[待 owner]` 与第 27、28 项共同决定，避免删旧门禁后只留弱断言。 |
| 30 | `d2SyncHostWiring.spec.ts` | `d2-online-edit-platform-closure` | `[重开并 rebase]` 按当前双向 bridge 状态机核对后迁移。 |
| 31 | `d429BidirectionalLifecycle.spec.ts` | D4 双向生命周期 | `[重开并 rebase]` 当前 clean-close / reload 语义已变，按真实流程重建。 |
| 32 | `d4OtherGroupWriteback.spec.ts` | D4 其他业务组回写 | `[重开并 rebase]` 按当前 D4 子表和发布门契约重测。 |
| 33 | `hostSheetDispatchChain.spec.ts` | H/I 宿主 sheet 分发 | `[重开并 rebase]` 保留模板分支覆盖目标，按当前宿主结构更新。 |
| 34 | `large_component_guard.spec.ts` | 前端文件规模治理 | `[待 owner]` 旧 patch 将 `GtAuditSheet` 上限提高到 870；必须先确认是否可拆，不能以当前膨胀反向放宽。 |
| 35 | `useB22BControlMatrix.spec.ts` | B22B 控制矩阵 | `[重开并 rebase]` 以现行行数组 JSON 持久化契约重测。 |
| 36 | `useF2FormData.spec.ts` | F2 审定表回写 | `[重开并 rebase]` 旧直写端点已下线，确认发布门后更新测试。 |
| 37 | `dCycleVoucherMappedPrefixes.spec.ts` | D2 凭证抽查范围 | `[重开并 rebase]` 以 `dCycleScope` 当前单一来源重测。 |
| 38 | `e1SyncEntryRowIdentity.spec.ts` | E1 同步行身份 | `[重开并 rebase]` 旧 G1 复用诊断需按当前 entry 解析器复核。 |
| 39 | `nCycleLane2RouterAndKeys.spec.ts` | `n1-n3-host-inline-router-and-shared-adoption` | `[不取旧版]` 旧期望与 10-26 N1 共享路由冲突，作为旧基线留档。 |
| 40 | `useF5Integration.spec.ts` | F5 集成事件 | `[重开并 rebase]` 在当前 EventBus payload 下重新验证。 |
| 41 | `d4AccountScope.ts` | D4 试算表回写口径 | `[重开并 rebase]` 常量单一来源意图有效，需和当前 D4 口径一起迁移。 |
| 42 | `d4OtherGroupPushPredicates.ts` | D4 其他业务组 | `[重开并 rebase]` 依赖第 41 项，不能只拣单文件。 |
| 43 | `useD4InspectionWriteback.ts` | D4 检查回写 | `[重开并 rebase]` 依赖第 41 项，按当前发布门测试。 |
| 44 | `D4TabErpCheck.vue` | D4 ERP 核对 | `[重开并 rebase]` 依赖第 41、43 项，按当前界面走查。 |
| 45 | `D4WalkthroughTest.spec.ts` | D4 穿行测试 | `[重开并 rebase]` 结构字段变化应由当前业务模型决定。 |
| 46 | `D4IpoFindingWriteback.vue` | D4 IPO 发现回写 | `[重开并 rebase]` 依赖第 41、43 项，保留空 prop 的口径兜底。 |
| 47 | `bridgeMaterializeDriven.spec.ts` | `a-cycle-online-edit-driver-closure` | `[重开并 rebase]` 直接守住“宿主必须真正驱动 bridge”；与 9–21 同批。 |
| 48 | `workpaperEntrySyncNotice.spec.ts` | 底稿同步通知 | `[重开并 rebase]` 当前状态码和展示文本需重新对拍。 |
| 49 | `workpaperSyncEditorHostSizing.spec.ts` | 底稿同步编辑容器 | `[重开并 rebase]` 与 B22A 容器高度候选一并浏览器验证。 |
| 50 | `workpaperSyncLegacyBaseline.spec.ts` | 同步遗留基线 | `[不取旧版]` 旧统计断言已过期；先以当前生成器输出再重建最小棘轮。 |
| 51 | `workpaperSyncLegacyBaseline.generated.ts` | J 循环同步 generated 产物 | `[不取旧版]` 必须由当前 `generate_workpaper_sync_legacy_baseline.py --apply` 生成。 |
| 52 | `workpaperSyncManifest.generated.ts` | `voucher-attach-account-mapping-closure` generated 产物 | `[不取旧版]` 必须由当前 manifest 生成器在审核 mount 差异后生成。 |
| 53 | `dSalesCycleLabelGuard.spec.ts` | ACNR / D 循环标签 | `[重开并 rebase]` 旧 patch 从硬编码转 ACNR 动态标签，意图有效但需按当前地址库接口复测。 |
| 54 | `useAgingConfig.property.test.ts` | 账龄配置测试，未登记独立 spec | `[重开并 rebase]` 仅按当前 composable 属性契约迁移。 |
| 55 | `useAiCapabilities.spec.ts` | AI 能力请求测试 | `[重开并 rebase]` `isRequestCancelled` mock 缺项是真问题，按当前 http 导出面补齐。 |
| 56 | `useC24AnalyticsEngine.pbt.spec.ts` | C24 控制测试分析 | `[重开并 rebase]` 以当前引擎输出与 PBT 种子复验。 |
| 57 | `useCControlTestData.spec.ts` | C 控制测试数据 | `[重开并 rebase]` 当前数据 shape 后续已改变，重建断言。 |
| 58 | `useAgingMigration.property.test.ts` | 账龄迁移属性测试 | `[重开并 rebase]` 仅迁移当前有业务意义的性质。 |
| 59 | `useAiHostContext.ts` | `ai-chat-adopt-and-note-target-picker` | `[本轮恢复]` 恢复“只有底稿/附注可就地采纳”的前端判定。 |
| 60 | `useAiNoteCapture.ts` | `ai-chat-adopt-and-note-target-picker` | `[本轮恢复]` 恢复扁平位置 payload、会话反查和幂等键。 |
| 61 | `parseIndexRef.test.ts` | 交叉引用解析 | `[重开并 rebase]` 与第 62 项成对；确认 layer 语义后再更新断言。 |
| 62 | `parseIndexRef.ts` | 交叉引用解析 | `[重开并 rebase]` 删除旧 `isSheetRef` 分支的意图需与当前显式 `sheet:` 规则复核。 |
| 63 | `views/__tests__/composables.spec.ts` | 前端全量失败修复会话，未登记独立 spec | `[重开并 rebase]` 按当前被测 composable 的导出和 mock 迁移。 |
| 64 | `WorkpaperEditorShell.spec.ts` | 底稿编辑器测试基座 | `[重开并 rebase]` `vue-router` mock 缺 `createRouter` 是加载问题，按当前 router 依赖链补最小桩。 |
| 65 | `workpaper-list/line-budget.spec.ts` | 底稿列表规模治理 | `[待 owner]` 旧 patch 上调 Workbench 上限 1210→1765，总额 4660→5215；不得绕开瘦身决策。 |
| 66 | `frontend/tsconfig.json` | `ai-chat-adopt-and-note-target-picker` | `[本轮恢复]` 仅为已有 `findLastIndex` 类型支持升至 ES2023；区域 typecheck 决定是否保留。 |
| 67 | `backend/app/security/_bootstrap_task1_evidence.py`（删除） | `sess_39d9f181` 仓库精简，无 spec | `[保持当前]` 0 运行时引用，但本任务不执行旧清理删除。 |
| 68 | `ai_chat/access.py` | `ai-chat-adopt-and-note-target-picker` | `[本轮恢复]` 恢复项目笔记目标的角色/成员 fail-closed 授权。 |
| 69 | `ai_chat/adopt.py` | `ai-chat-adopt-and-note-target-picker` | `[本轮恢复]` 恢复跨宿主采纳的来源校验、项目边界与审计来源字段。 |
| 70 | `ai_chat/note_service.py` | `ai-chat-adopt-and-note-target-picker` | `[本轮恢复]` 接回已入库 `note_target.py` 的来源反查/位置授权。 |
| 71 | `report_excel_exporter.py` | `deliverable-trio-generation-accuracy` | `[重开并 rebase]` `load_report_rows(..., project_id=...)` 是小而明确的项目适配缺口，应单独回归后迁移。 |
| 72 | `workpaper_sync_legacy_baseline.json` | M 循环同步 generated 产物 | `[不取旧版]` 必须由当前 generator 生成，不能回灌 10-21 快照。 |
| 73 | `split_classification_wp_codes.py`（删除） | `sess_39d9f181` 清理；`acnr-foundation-defect-closure` 仍引用 | `[保持当前]` 当前 active ACNR 设计仍引用，禁止套用旧删除。 |
| 74 | `audit_d_cycle_parity.py`（删除） | `sess_39d9f181` 仓库精简，无 spec | `[保持当前]` 0 运行时引用；如需删除，另做脚本清理复核。 |
| 75 | `check_auth.py`（删除） | `sess_39d9f181` 仓库精简，无 spec | `[保持当前]` 0 运行时引用；本轮不做破坏性清理。 |
| 76 | `check_auth_coverage.py`（删除） | `sess_39d9f181` 仓库精简，无 spec | `[保持当前]` 0 运行时引用；本轮不做破坏性清理。 |
| 77 | `check_note_template_word_tree.py` | `disclosure-note-template-word-realignment` | `[不取旧版]` 旧“表格不判”变更会使当前 687 条表格白名单全部 stale；应在 spec 49 重新统一策略。 |
| 78 | `validate_i2_cross_reference.py`（删除） | `sess_39d9f181` 仓库精简，无 spec | `[保持当前]` 0 运行时引用；本轮不做破坏性清理。 |
| 79 | `test_task7_adopt_fail_closed.py` | `ai-chat-adopt-and-note-target-picker` | `[本轮恢复]` 与服务层恢复一同保留的 fail-closed 回归。 |
| 80 | `fixtures/function_support_matrix.json` | `formula-manager-runtime-integrity-closure` | `[不取旧版]` 10-22 公式治理已重写真源；回灌旧 fixture 会令 golden 对拍失败。 |
| 81 | `test_note_template_word_tree_alignment.py` | `disclosure-note-template-word-realignment` | `[不取旧版]` 绑定第 77 项旧策略；当前后续救援已另行收口。 |
| 82 | `test_startup_registry.py` | `formula-global-settings-sync` | `[重开并 rebase]` 生产已注册 formula-settings handler，仍应补适配后的测试守卫，不能直接回灌旧断言。 |

## B. 24 个尚未入库的未跟踪文件

| # | 文件 | 归属 / 与当前树比较 | 结论与建议 |
|---:|---|---|---|
| U1 | `a-cycle-online-edit-driver-closure/design.md` | `_archive/55...` 同内容 | `[不取旧版]` 已归档副本，删除旧 active 副本。 |
| U2 | `a-cycle-online-edit-driver-closure/governance-handoff.md` | `_archive/55...` 同内容 | `[不取旧版]` 已归档副本。 |
| U3 | `a-cycle-online-edit-driver-closure/requirements.md` | `_archive/55...` 同内容 | `[不取旧版]` 已归档副本。 |
| U4 | `a-cycle-online-edit-driver-closure/tasks.md` | `_archive/55...` 同内容 | `[不取旧版]` 已归档副本。 |
| U5 | `ai-chat-adopt-and-note-target-picker/design.md` | 归档版多 28 行后续记录 | `[不取旧版]` 用归档版；本恢复 spec 记录事故和新结论。 |
| U6 | `ai-chat-adopt-and-note-target-picker/p0-confirm-writeback.md` | `_archive/55...` 同内容 | `[不取旧版]` 已归档副本。 |
| U7 | `ai-chat-adopt-and-note-target-picker/requirements.md` | `_archive/55...` 同内容 | `[不取旧版]` 已归档副本。 |
| U8 | `ai-chat-adopt-and-note-target-picker/tasks.md` | 归档版多 21 行后续记录 | `[不取旧版]` 用归档版；不回填旧任务。 |
| U9 | `attachment-ocr-ai-evidence-governance-hardening/release_evidence.json` | 归档版不同，stash 仍记旧 BLOCKED 状态 | `[不取旧版]` 运行时证据过期，以归档正式证据为准。 |
| U10 | `formula-global-settings-sync/.config.kiro` | `_archive/55...` 同内容 | `[不取旧版]` 已归档配置副本。 |
| U11 | `formula-global-settings-sync/design.md` | `_archive/55...` 同内容 | `[不取旧版]` 已归档副本。 |
| U12 | `formula-global-settings-sync/requirements.md` | `_archive/55...` 同内容 | `[不取旧版]` 已归档副本。 |
| U13 | `formula-global-settings-sync/tasks.md` | 归档版含后续验收记录 | `[不取旧版]` 已归档副本。 |
| U14 | `formula-global-settings-sync/tasks.meta.json` | `_archive/55...` 同内容 | `[不取旧版]` 编排元数据不单独入树。 |
| U15 | `formula-manager-runtime-integrity-closure/basis/runtime-evidence.json` | `_archive/55...` 同内容 | `[不取旧版]` 已归档证据。 |
| U16 | `formula-manager-runtime-integrity-closure/design.md` | `_archive/55...` 同内容 | `[不取旧版]` 已归档副本。 |
| U17 | `formula-manager-runtime-integrity-closure/requirements.md` | `_archive/55...` 同内容 | `[不取旧版]` 已归档副本。 |
| U18 | `formula-manager-runtime-integrity-closure/tasks.md` | `_archive/55...` 同内容 | `[不取旧版]` 已归档副本。 |
| U19 | `frontend-test-network-isolation-and-load-dedup/design.md` | `_archive/55...` 同内容 | `[不取旧版]` 已归档副本。 |
| U20 | `frontend-test-network-isolation-and-load-dedup/requirements.md` | `_archive/55...` 同内容 | `[不取旧版]` 已归档副本。 |
| U21 | `frontend-test-network-isolation-and-load-dedup/tasks.md` | `_archive/55...` 同内容 | `[不取旧版]` 已归档副本。 |
| U22 | `partner-manager-edit-permission/tasks.meta.json` | 归档版比 stash 多编排记录 | `[不取旧版]` 工具元数据不入树。 |
| U23 | `frontend/tsconfig._ai-adopt-note.json` | 旧单区域 typecheck 临时配置 | `[不取旧版]` 当前使用 `scripts/typecheck-region.mjs`。 |
| U24 | `frontend/tsconfig._formula-settings.json` | 旧单区域 typecheck 临时配置 | `[不取旧版]` 当前使用 `scripts/typecheck-region.mjs`。 |

## C. 不计入 82、但与本轮恢复直接相关的已分叉文件

| 文件 | 当前处置 |
|---|---|
| `usePlatformAiChat.ts` | 三方合并：保留当前错误信封与 `ai-content:adopted` 事件，加入显式目标、`source_host`、无目标零请求。 |
| `useDocAiChat.ts` | 三方合并：保留当前成功事件，加入统一错误信封解析。 |
| `doc_ai_chat.py` | 三方合并：加入 `source_host`、笔记目标二选一和来源 `history` 授权；保留 SSE `get_db(scope='function')`。 |
| `auditPlatformApi.ts` | 不覆盖整文件；保留当前 `getDisclosureNoteTree(..., config?)`，仅确认目标选择的 `_silent` 可透传。 |
| `eventBus.ts` | 保留当前必带 `projectId` 的事件类型；事件仅由 `usePlatformAiChat` 成功分支、按目标项目发送一次。 |
| `AiContentPendingBanner.vue` | 保留 v1.0.57 的标签/刷新修复，不回灌旧 stash 版本。 |
| `GtA121LegalConfirmation.vue`、`GtA171AuditSummary.vue` | 与 A 类完整丢失宿主一起在后续 A-driver 重开时 rebase；不纳入本次 AI 提交。 |

## 处置汇总

- `[本轮恢复]`：9 个完整丢失文件，外加 4 个已分叉文件的最小三方合并。
- `[重开并 rebase]`：53 个完整丢失文件，绝不直接批量 checkout。
- `[待 owner]`：5 个完整丢失文件，涉及删除用例或抬高规模门槛。
- `[不取旧版]`：9 个完整丢失文件和 24 个未跟踪文件，分别是被后续实现覆盖的旧 patch、生成物或归档重复件。
- `[保持当前]`：6 个完整丢失文件；它们是旧清理会话的删除记录，本次不进行删除。
