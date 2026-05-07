# Sprint 1（P0）任务清单

## Sprint 信息
- 预计工时：1 周（5 个工作日）
- 验证方式：vue-tsc + pytest + CI lint + 手动验证 6 项

---

## Day 1：路由修复 + feedback 基础设施

- [x] Task 1：新建 `views/ConfirmationHub.vue`（stub，用 GtPageHeader + GtEmpty）
- [x] Task 2：`router/index.ts` 添加 `/confirmation` 路由（meta.developing: true）
- [ ] Task 3：验证点击侧栏"函证"跳转到 DevelopingPage
- [x] Task 4：新建 `utils/feedback.ts`（封装 ElMessage/ElNotification）
- [x] Task 5：`utils/http.ts` response interceptor 增加 5xx/超时/断网处理
- [x] Task 6：vue-tsc 验证 0 错误

## Day 2：confirm.ts 补齐 + 替换（批次 1）

- [x] Task 7：`utils/confirm.ts` 新增 7 个函数（confirmVersionConflict/confirmSignature/confirmForceReset/confirmRollback/confirmShare/confirmDuplicateAction/confirmForcePass）
- [x] Task 8：替换 10 个合并工作表组件的 ElMessageBox.confirm → confirmBatch/confirmDangerous（MinorityInterestSheet/InvestmentEquitySheet/InvestmentCostSheet/NetAssetSheet/PostElimIncomeSheet/EquitySimSheet/EliminationSheet/PostElimInvestSheet/CapitalReserveSheet/SubsidiaryInfoSheet）
- [x] Task 9：替换 ConsolNoteTab.vue 的 ElMessageBox.confirm → confirmDangerous
- [x] Task 10：vue-tsc 验证 0 错误

## Day 3：confirm.ts 替换（批次 2）

- [x] Task 11：替换 AccountImportStep.vue（2 处）→ confirmForceReset
- [x] Task 12：替换 DataImportPanel.vue（2 处）→ confirmDuplicateAction + confirmDangerous
- [x] Task 13：替换 MiddleProjectList.vue（2 处）→ confirmDelete + confirmBatch
- [x] Task 14：替换 DetailProjectPanel.vue（2 处）→ confirmForceReset + confirmDangerous
- [x] Task 15：替换 EqcrReviewNotesPanel.vue（2 处）→ confirmDelete + confirmShare
- [x] Task 16：替换 EqcrRelatedParties.vue（2 处）→ confirmDelete
- [x] Task 17：替换 WorkpaperEditor.vue（1 处）→ confirmVersionConflict
- [x] Task 18：替换 WorkpaperList.vue（1 处）→ confirmForcePass
- [x] Task 19：替换 IndependenceDeclarationForm.vue（1 处）→ confirmDangerous
- [x] Task 20：替换 StructureEditor.vue（1 处）→ confirmRollback
- [x] Task 21：替换 Adjustments.vue（2 处）→ confirmDangerous
- [x] Task 22：替换 ReportLineMappingStep.vue（1 处）→ confirmDelete
- [x] Task 23：替换 PriorYearCompareDrawer.vue（1 处）→ confirmDangerous
- [x] Task 24：CI 已有 ElMessageBox.confirm 基线检查（≤5），当前实际 0 处
- [x] Task 25：vue-tsc 验证 0 错误

## Day 4：Adjustments 转错报 + 年度 store

- [x] Task 26：`services/apiPaths.ts` adjustments 对象新增 `convertToMisstatement` 路径（已存在，R1 落地）
- [x] Task 27：`composables/usePermission.ts` ROLE_PERMISSIONS 新增 `adjustment:convert_to_misstatement`（auditor/manager/partner）
- [x] Task 28：`views/Adjustments.vue` 行操作区"转为错报"按钮补加 `v-permission="'adjustment:convert_to_misstatement'"`（按钮已存在 R1）
- [x] Task 29：`onConvertToMisstatement` 处理函数已实现（R1 Task 10 落地）
- [x] Task 30：在现有 `stores/project.ts::changeYear` 中添加 eventBus `year:changed` emit（决策：不新建 projectYear.ts 避免双真源，projectStore 已有 year/changeYear）
- [x] Task 31：GtInfoBar @year-change → 各视图 onYearChange → projectStore.changeYear → 自动 emit `year:changed`（无需改 GtInfoBar）
- [x] Task 32：TrialBalance/ReportView/DisclosureEditor 已通过 projectStore.changeYear 接入（无需改视图）
- [x] Task 33：Materiality/Adjustments/Misstatements 同样已接入
- [x] Task 34：vue-tsc 验证 0 错误

## Day 5：AI 脱敏审计 + 收尾验证

- [x] Task 35：审计 `routers/wp_ai.py`（路由层纯转发，脱敏下沉到 wp_ai_service.py::analytical_review）
- [x] Task 36：审计 `routers/note_ai.py`，3 个端点加 mask_context（generate_analysis / ai_complete×2 / ai_rewrite）
- [x] Task 37：审计 `routers/ai_unified.py`（仅健康检查+缓存统计，无 LLM prompt，跳过）
- [x] Task 38：审计 `routers/role_ai_features.py`（路由层转发，脱敏下沉到 service._llm_polish_report + _llm_generate_summary）
- [x] Task 39：新建 `backend/tests/test_ai_masking.py`（13 个测试：dict 嵌套 3 + 纯字符串 5 + 列表批量 3 + 显式金额 2）
- [x] Task 40：python -m pytest backend/tests/test_ai_masking.py 全部通过（13 passed in 0.29s）
- [x] Task 41：全量 vue-tsc 验证 0 错误
- [x] Task 42：全量 python -m pytest --collect-only 0 collection errors（2848 tests）

---

## 验收检查

- [ ] `/confirmation` 点击 → DevelopingPage
- [ ] grep `ElMessageBox\.confirm` ≤ 5 个文件
- [ ] Adjustments 被拒行有"转为错报"按钮，点击可转换
- [ ] GtInfoBar 切年度 → TrialBalance 自动 reload
- [ ] 模拟 5xx → 前端显示 ElNotification 错误提示
- [ ] AI 端点 prompt 不含未脱敏数据（测试通过）
