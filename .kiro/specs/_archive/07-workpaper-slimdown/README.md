# 07 · 底稿模块瘦身系列（6 个）

围绕底稿渲染与超大单体文件瘦身的专项 spec，目标是把 Univer 单体底稿切换到 HTML 渲染器，并把超长 .vue 文件拆分为 Shell + 子组件 + composable。

| Spec | 成果 |
|------|------|
| `workpaper-html-renderer` | 1788 单体底稿从 Univer 切 HTML，9 类 componentType，40/40 tasks，413 tests |
| `workpaper-editor-slimdown` | WorkpaperEditor.vue 2748→758 行（Shell）+ 8 子 SFC + 2 composable，59/59 tasks，42 tests |
| `workpaper-list-shrink` | WorkpaperList.vue 3463→1151 行（净减 67%）+ 5 子 SFC，36 vitest + e2e |
| `workpaper-editor-shrink-phase2` | WorkpaperEditor.vue 收尾瘦身 758 行，8 子 SFC + 2 composable，42 vitest + Playwright smoke |
| `gt-c-note-table-shrink` | GtCNoteTable.vue 1803→450 行 + GtEControlTest.vue 1414→344 行；C 类拆 CNoteCell/CNoteSubTableCard/CNoteInheritanceBadge + 3 composable，E 类拆 EControlSummaryTable/SingleForm/EvalStepper/AiPanel/FieldInput + 2 composable；90 测试全绿（36 spec 零断言 + 54 新单测）+ vue-tsc 0 + file_size_whitelist 移除 GtCNoteTable；**残留 R3：Playwright C/E 目视待环境**（后端 9980/前端 3030 + 真实 schema C-D2-disclosure/E-C12/E-C12-1/E-C11-2，环境阻塞非代码缺口）|
| `gtdform-test-and-shrink` | D 类 3 组件「先测后拆」：GtDFormReview 1670→390 / GtDFormConfirmation 1434→366 / GtDFormParagraph 878→345 行 Shell + 6 composable（useReview{StateMachine,Signature,Fields} / useConfirmation{State,Fields} / useParagraphVariables）；9/9 tasks + 116 vitest 全绿（含集成测试 + 边界/防御 + 真实 markdown/XSS）+ vue-tsc 0 + file_size_whitelist 移除 GtDFormReview；**复盘 6 改进已落地**：①边界测试 ②共享 stubs.ts 消除 Vue warn ③真实 marked/DOMPurify ④GtDForm.integration.spec.ts 父子链路 ⑤check_file_size HARD_CAPS 防退化 ⑥evalFormula 改安全递归下降解析器（消除 new Function RCE 风险）|

</content>

