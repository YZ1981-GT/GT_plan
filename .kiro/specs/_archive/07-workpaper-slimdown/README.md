# 07 · 底稿模块瘦身系列（5 个）

围绕底稿渲染与超大单体文件瘦身的专项 spec，目标是把 Univer 单体底稿切换到 HTML 渲染器，并把超长 .vue 文件拆分为 Shell + 子组件 + composable。

| Spec | 成果 |
|------|------|
| `workpaper-html-renderer` | 1788 单体底稿从 Univer 切 HTML，9 类 componentType，40/40 tasks，413 tests |
| `workpaper-editor-slimdown` | WorkpaperEditor.vue 2748→758 行（Shell）+ 8 子 SFC + 2 composable，59/59 tasks，42 tests |
| `workpaper-list-shrink` | WorkpaperList.vue 3463→1151 行（净减 67%）+ 5 子 SFC，36 vitest + e2e |
| `workpaper-editor-shrink-phase2` | WorkpaperEditor.vue 收尾瘦身 758 行，8 子 SFC + 2 composable，42 vitest + Playwright smoke |
| `gt-c-note-table-shrink` | GtCNoteTable.vue 1803→450 行 + GtEControlTest.vue 1414→344 行；C 类拆 CNoteCell/CNoteSubTableCard/CNoteInheritanceBadge + 3 composable，E 类拆 EControlSummaryTable/SingleForm/EvalStepper/AiPanel/FieldInput + 2 composable；90 测试全绿（36 spec 零断言 + 54 新单测）+ vue-tsc 0 + file_size_whitelist 移除 GtCNoteTable；**残留 R3：Playwright C/E 目视待环境**（后端 9980/前端 3030 + 真实 schema C-D2-disclosure/E-C12/E-C12-1/E-C11-2，环境阻塞非代码缺口）|
