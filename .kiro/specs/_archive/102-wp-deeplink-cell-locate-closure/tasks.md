# 实施计划：底稿深链单元格定位收口（wp-deeplink-cell-locate-closure）

> 证据目录：`tmp_wp_cell_locate/out/`（选集、vitest JSON、变异、类型检查、浏览器、对账），截图 `tmp_wp_cell_locate/screenshots/`。候选树 = 分支 `c952cd60c` + 本 spec 改动（分离头 worktree `tmp_wp_cell_locate/wt`）；归因基线 = `c952cd60c` 干净检出。

- [x] 1. `useCellLocate` 范围限定、去掉行号猜测、导出高亮函数、补高亮样式（需求 2.1 / 2.2 / 3.1）
      Files: `audit-platform/frontend/src/composables/useCellLocate.ts`、`audit-platform/frontend/src/styles/global.css`、`audit-platform/frontend/src/composables/__tests__/useCellLocate.scope.spec.ts`
      Verify: `useCellLocate.scope.spec.ts`；变异 M2、M3
      实施记录（2026-10-30）：`locateCell(target, { root })` 三类策略都只在 root 内查（不传 root 仍查整个 document，LineageGraphPanel / SideStandardsTab 行为不变）；删 el-table「单元格行号 = 第 N 行」策略；导出 `highlightElement`（滚到可见 + 原幂等与 3 秒淡出）；`global.css` 补 `gt-locate-highlight`（描边 + 底色，td / 整行 / 块元素都可见）与 `gt-locate-blink`。用例 7 passed；M2（去掉 root）红 3 例、M3（恢复行号猜测）红 1 例，sha256 还原。

- [x] 2. 定位调度 `useRendererCellLocate` 与 `GtWpRenderer` 接线（需求 1.1 / 1.2 / 1.4 / 2.3 / 3.2~3.4）
      Files: `audit-platform/frontend/src/composables/useRendererCellLocate.ts`、`audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue`、`audit-platform/frontend/src/composables/__tests__/useRendererCellLocate.spec.ts`
      Verify: `useRendererCellLocate.spec.ts` + `GtWpRenderer.*.test.ts`；变异 M1、M4、M7
      实施记录（2026-10-30）：渲染配置未到时排队（只留最后一个），就绪监听用 `flush: 'sync'`（同一 tick 内先假后真时 pre 只比首尾值会漏，用例先红后改）；就绪即同步切页；重试 0 / 100 / 250 / 500 / 1000 ms，先问组件钩子、再在渲染器根元素内找，根元素为空不退回 document；新请求与卸载都作废旧重试；sheet 解析不到沿用原提示，单元格找不到提示「「{sheet}」的网页视图里没有单元格 {cell} 的对应位置」。`GtWpRenderer.onLocateCell` 改为 `request(payload)`，`initialSheet` / `initialCell` 变化时发请求；`GtWpRenderer.vue` 1514 → 1496 行。用例 13 passed，渲染器三组既有用例 22 passed（发事件后 nextTick 即切页的断言不变）；M1（未就绪直接丢）红 2、M4（不重试）红 3、M7（忽略钩子结果）红 1。

- [x] 3. 编辑器深链改走 `initial-cell`，Univer 路径事件后移（需求 1.1 / 1.3 / 1.4）
      Files: `audit-platform/frontend/src/views/WorkpaperEditor.vue`、`audit-platform/frontend/src/views/workpaper-editor/__tests__/deepLinkInitialCell.spec.ts`、`audit-platform/frontend/src/views/workpaper-editor/__tests__/line-budget.spec.ts`
      Verify: `deepLinkInitialCell.spec.ts`、`line-budget.spec.ts`、`UniverEditorCore.*.spec.ts`；变异 M6
      实施记录（2026-10-30）：`GtWpRenderer` 加 `:initial-cell`；原 onMounted 里「nextTick + 300ms 发事件」删去，改在异步块的 Univer 分支末尾发（模式判定之后），去掉不再使用的 `nextTick` 导入。`WorkpaperEditor.vue` 1361 → 1348 行，棘轮 `SHELL_RATCHET` 按测试要求同步下调为 1348。用例 3 + 11 passed，Univer 两组 6 passed；M6（HTML 路径恢复 300ms 发事件）红 1。已知限制：Univer 初始化慢于 300ms 时事件仍可能早到（Univer 只切 sheet，不在本 spec 范围）。

- [x] 4. E1-14 锚点试点（需求 4）
      Files: `audit-platform/frontend/src/components/workpaper/e1/e1AnalysisCellAnchors.ts`、`e1/E1TabAnalysis.vue`、`GtE1MonetaryFund.vue`、`e1/__tests__/e1AnalysisCellAnchors.spec.ts`、`e1/__tests__/E1TabAnalysis.locate.spec.ts`、`backend/tests/test_e1_analysis_anchor_template_contract.py`
      Verify: 两个前端用例 + 后端契约；变异 M5
      实施记录（2026-10-30）：锚点表按模板登记三张表 18 行、16 个列映射与三个文字块；`E1TabAnalysis` 表格与卡片加 `data-e1-table` / `data-e1-anchor`，`defineExpose({ locateCell })` 先切区段页签再高亮；`GtE1MonetaryFund` 只在 E1-14 时转发。后端契约读模板逐格核对行标签、表头（含 H33:K33 合并）、三期日期顺序、合计行未登记、文字块前缀。用例 32 + 6 passed（真实 Element Plus 挂载：C16 高亮「银行存款 / 本期金额」、C34 切到八项比例、F15 整行、B30 切页并高亮 F3-2 提示、A50 审计结论、C10 / C18 返回 false），后端 12 passed；M5（改一行标签）后端红 1、M8（不切区段）前端红 2。

- [x] 5. 验证与记录（需求 5）
      相关前端测试与 E1 既有测试、单区域 vue-tsc（改动文件）、变异 M1~M8、浏览器 C16 / B30 / C10 各 3 次独立运行、写入对账；结果写进本文件各任务的实施记录。
      实施记录（2026-10-30）：①前端选集 27 个文件 287 例：281 passed、3 failed、3 pending；3 例失败（`GtWpRuntimeBoundary.pbt.spec.ts` 2 例 mock 缺 `resolveWorkpaperSheetContext`、`WorkpaperEditorShell.spec.ts` 整组 vue-router mock 缺 `createRouter`）在基线 `c952cd60c` 干净检出逐条同红，非本 spec 引入（`out/fe_reg1.txt`、`out/fe_base_attrib.txt`）。②单区域 vue-tsc（改动与新增 13 个文件进 include）：候选 1230 条、基线 1230 条，抹平检出路径后新增 0 / 消失 0；注入 `number = string` 的探针报 TS2322（`out/tsc_diff.json`）。③变异 8 条全部打红并按 sha256 还原（`out/mutations.json`）。④浏览器：候选树分离头 worktree 起后端 127.0.0.1:9987（`--lifespan off`、跳过启动迁移）与 Vite 3037；【测试】ACNR下钻走查_2025 经平台回收站恢复（11:32:51）后测、结束经平台删除放回（11:35:30）；无头 Chromium 每次新建上下文，未登录打开 `/workpapers/{E1}?sheet=E1-14&cell=…` → 登录 → 编辑器，9 次独立运行 redirect 均为完整短链、进入编辑器后查询串原样保留：C16 ×3 高亮构成表「银行存款 / 本期金额」单元格（描边可见）、B30 ×3 切到「其他货币资金七类」并高亮 F3-2 提示、C10 ×3 提示「「货币资金分析表E1-14」的网页视图里没有单元格 C10 的对应位置」；无接口错误、无页面脚本错误；每次运行结束释放编辑锁（DELETE 200），9 次都不是只读状态；记录器每次自检通过（`out/browser_v1.json`、`out/browser_v1_brief.txt`、截图 `v1_run{1,2,3}_{C16,B30,C10}.png`）。⑤写入对账（`out/locfix_diff.json`）：项目行 `deleted_at` / `updated_at` 更新为本次删除时间（`is_deleted` 仍为 true）；底稿行、`parsed_data`、底稿文件不变；`editing_locks` +10 行（均已释放）；窗口内 admin 写入的 `logs` 32 行：加锁 10、释放 10、恢复 1、删除 1（挂本底稿 / 项目 id），`resolve-batch` 10（不挂这两个 id）；同年度其他项目 0 行变化。验证前快照里 `tb_aux_ledger` 的摘要查询超时，验证后为 0 行，属快照查询本身的问题，不是写入。

- [x] 6. 提交、推送、INDEX 登记
      候选树干净检出复跑；按版本号流程推送（`.git-hooks/push_version.py`）。
      实施记录（2026-10-30）：INDEX 登记本 spec，acnr-foundation-defect-closure 行改写复测状态，并在其 T16 追加后续说明（目录坐标问题转交）。提交树 = 分支 `c952cd60c` + 本 spec 20 个文件，在分离头 worktree 里提交（不建分支）。提交前暂存检查：暂存集合与清单一致（20 个）、无行尾整体转换、行数门 14 个代码文件通过、无 U+FFFD、附注模板棘轮通过、gitleaks 通过；暂存树自洽门（`check_staged_tree_self_consistency.py`）rc=0。推送走 `.git-hooks/push_version.py`，本提交即推送内容，版本号见对应附注标签。
