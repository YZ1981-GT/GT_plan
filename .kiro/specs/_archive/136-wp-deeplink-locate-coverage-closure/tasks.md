# 实施计划：底稿深链定位覆盖收口（wp-deeplink-locate-coverage-closure）

> 证据目录：`tmp_wp_locate_cov/out/`，截图 `tmp_wp_locate_cov/screenshots/`。候选树 = 分支 `bb16db07d` + 本 spec 改动（分离头 worktree `tmp_wp_locate_cov/wt`）；归因基线 = `bb16db07d` 干净检出（`tmp_wp_locate_cov/base_wt`）。推送前远端前移到 `d2477f295`，提交重放到它之上后按新基线（`tmp_wp_locate_cov/base2_wt`）复跑，见任务 7。

- [x] 1. 目录单元格复核脚本与判定（需求 1.1~1.3）
      Files: `backend/scripts/acnr/review_cell_coordinates.py`、`backend/app/services/acnr/loaders/from_sheet_verdicts.py`、`backend/data/acnr/sources/sheet_verdicts.json`、`backend/data/t_address_registry_seed.json`
      Verify: `review_cell_coordinates.py --check` 退出 0；停用判定与新种子条数与复核结论一致；PG / 静态引用核对
      实施记录（2026-10-30）：脚本由模板现算 402 格（435 未停用格扣既有 33 格待核对）的证据并写停用判定（kind `seed_coordinate_mismatch`，`CELL_KINDS` 增此值）与新种子：69 格改指到 65 个新坐标（63 个「审计结论」标签格 + E1-14 I18 / C34），333 格指父 sheet；`--check` 退出 0。停用前核对：PG 17 个公式类列（2337 条非空文本）对这 402 格的 addr_id / formula_ref 引用 0（`pg_formula_refs.json`）；静态引用只在冻结夹具、`acknowledgements.json`（那 33 格）、生成物与测试用例里，生产代码只有 docstring 示例 `D2/D2-2/E100`（`static_refs.json`、`static_refs_files.txt`）。

- [x] 2. 重新发布目录与守卫（需求 1.4 / 1.5）
      Files: `backend/data/acnr/{global_catalog.json,catalog_report.json,catalog_snapshots/*,v2_canonical_reconcile.json}`、`backend/tests/acnr/test_cell_coordinate_review.py`、受影响的既有测试
      Verify: `generate_catalog.py --check`；`backend/tests/acnr` 全套与 `test_*_cycle_address_registry.py`；变异 V1、V2
      实施记录（2026-10-30）：新批次 `20261030063137`（上一批 `20261029075533`）：sheet 1225、单元格 539、停用 446、发布门禁 blocking 0，有效单元格 98 = 33 + 65；`v2_canonical_reconcile.json`、`fixtures/editor_save_inputs.json` 按各自生成器重算；架构文档事实表与「为 446」同步。ACNR CI 同口径检查 17 条全部 rc=0（`acnr_checks_wt.txt`）。用目录样例或计数的 13 个既有测试文件与 2 份夹具改用仍有效的格（I18 / C34 / A50 / A21 等）或停用语义，判据不放宽；新守卫 `test_cell_coordinate_review.py` 7 例（含 pg_only、文字锚点对照与 CI 接线）。`backend/tests/acnr` 1029 passed、3 skipped（数据条件：无 semantic_only 条目、计划符号表为空）、0 failed（基线 1022 passed）；acnr 外引用停用坐标的 24 个用例文件 335 passed；cycle 种子与 CI 接线 10 个文件 6 例失败（4 个循环 `test_seed_wp_codes_are_audit_sheet_type`、F 循环 `test_seed_coordinate_purposes_valid`、`test_governance_ci::test_hotspot_baseline_mode`）在基线逐条同红。V1（结论规则放宽）红 1、V2（种子改错 A1）红 4。

- [x] 3. 文字锚点对照与渲染器定位一级（需求 2）
      Files: `backend/scripts/acnr/generate_cell_text_anchors.py`、`audit-platform/frontend/src/generated/catalogTextAnchors.ts`、`audit-platform/frontend/src/composables/textAnchorLocate.ts`、`useRendererCellLocate.ts`、`GtWpRenderer.vue`、`.github/workflows/governance-checks.yml` 及用例
      Verify: 生成脚本 `--check`；`textAnchorLocate.spec.ts`、`useRendererCellLocate.spec.ts`、渲染器既有用例；变异 V3、V4、V8、V9、V10、V13~V16
      实施记录（2026-10-30）：对照 63 张表 / 63 格，`--check` 接进 CI 作业 `acnr-cell-text-anchors-generated`（只依赖标准库，守卫用 YAML 解析钉住）。浏览器首轮 5 张有结论格的表全部误报「没有对应位置」，查明两个原因并修：①模板页签渲染配置不给 `sheet_code`（E1 / D4 / H3 全部页签，原因 `template_sheet_name`）⇒ 改按页签名末尾编码取（`locateSheetCode`，前端用例读目录核对 63 张表都能对回）；②D4 结论区标题比页签晚约 2.3 秒出现（`anchor_timing.json`）⇒ 登记了锚点的请求追加 1.5 / 2 / 3 秒重试，没有锚点的格仍 1.85 秒提示。组件模板普查后序号口径放宽到「2、」「2.」「（三）」「(3)」「IV.」（587 处里多认 52 处，每个文件只会 0 → 1）。用例 13 + 20 passed；V3 红 1、V4 红 2、V8 后端红 1、V9 红 1、V10 红 3、V13 红 2、V14 红 3、V15 前端红 1 + 后端红 1、V16 红 1。

- [x] 4. 定位入口统一（需求 3）
      Files: `audit-platform/frontend/src/services/openWorkpaperCell.ts`、`views/TrialBalance.vue`、`views/Misstatements.vue`、`views/ConsolidationIndex.vue`、`views/composables/useReportTrace.ts`、`components/workpaper/LineageGraphPanel.vue`、`components/dashboard/ReviewOpinionList.vue`、`composables/usePenetrate.ts` 及用例、`views/__tests__/deepLinkEntryGuard.spec.ts`
      Verify: `openWorkpaperCell.spec.ts`、守卫、各调用方既有用例；变异 V5、V6、V11
      实施记录（2026-10-30）：4 个溯源弹窗、复核意见列表、附注→底稿穿透、溯源面板跨底稿节点都经 `openWorkpaperCell`；溯源面板在编辑器里点当前底稿的节点（`wp_id` 相同或编码与「当前对象」相同）交渲染器定位。守卫 6 例（含双向样例），`cellTrace.spec.ts` 原自发事件的假用例改为调用生产 `useReportTrace`；`LineageGraphPanel` / `usePenetrate` / `ReviewOpinionList` 用例按新行为改写（14 / 11 / 11 例）。V5（编码当 id）红 12、V6（跨底稿只发事件）红 3、V11（弹窗恢复发事件）红 2。浏览器在底稿列表页用应用 router 调该函数（`entry_e1.json`）：「E1-14 + A50」回落 E1 并定位审计结论卡片、旧弹窗写法 `wpId='E1'` 定位 E1-9 结论卡片、UUID 直接打开并定位 C34、本项目没有的 Z9 返回「本项目未找到底稿 Z9（可能尚未生成）」且不跳转、无全局错误提示。

- [x] 5. Univer 就绪排队与选中单元格（需求 4）
      Files: `views/workpaper-editor/UniverEditorCore.vue`、`views/WorkpaperEditor.vue`、`views/workpaper-editor/__tests__/{UniverEditorCore.locate.spec.ts,deepLinkInitialCell.spec.ts,line-budget.spec.ts}`
      Verify: 上述用例与 Univer 既有用例；变异 V7、V12
      实施记录（2026-10-30）：`UniverEditorCore` 收 `initial-sheet` / `initial-cell`，未就绪（引擎未建 / 加载中 / 无活动工作簿）只留最后一个待办，就绪后切 sheet 并 `setActiveRange` 选中；编辑器删 300ms 定时器，`WorkpaperEditor.vue` 1348 → 1341 行（棘轮同步下调）。用例 7 + 4 + 11 passed，Univer 既有两组 6 passed；V7（未就绪直接丢）红 4、V12（恢复定时器）红 2。浏览器（【测试】项目里没有整本走 Univer 的底稿，用只读响应改写把 F4 导到 Univer 分支、工作簿用合成三张表，不请求 xlsx-to-json）：`?sheet=明细表F4-2&cell=b12`、`?sheet=F4-3&cell=C7`、`?cell=D9` 三次都在约 1.6 秒内切到目标 sheet 并选中 B12 / C7 / D9，左侧导航同步。

- [x] 6. 验证与记录（需求 5）
      前端选集回归（基线归因）、单区域 vue-tsc、变异、浏览器（【测试】项目经回收站恢复后测、测后放回）、写入对账；结果写进各任务实施记录
      实施记录（2026-10-30）：①前端选集（引用改动文件的 60 个用例文件）732 例：727 passed、2 failed、3 pending + `WorkpaperEditorShell.spec.ts` 整组导入失败，失败在基线逐条同红（`GtWpRuntimeBoundary.pbt` mock 缺 `resolveWorkpaperSheetContext`、Shell 的 vue-router mock 缺 `createRouter`）；全前端扫描类用例 85 个文件新增红 0（基线 38 条同红；`FrontendReferenceIntegrity`「已登记死代码零活消费方」单跑两棵树都超时，`transposeGrid` 属性测试失败种子 -2007756948 在基线重放同红）。②单区域 vue-tsc（改动与新增 25 个文件）：候选与基线都是 1230 条，差异只是联合类型成员顺序；探针报 TS2322。③磁盘变异 V1~V16 全部打红并按 sha256 还原（`mutations.json`）。④ESLint 新增 0。⑤浏览器：候选树起后端 9987（`--lifespan off`）与 Vite 3037，【测试】附件小眼睛走查_2025 与【测试】附件证据入口走查_2025 经回收站恢复后测、测后经平台删除放回；E1-14 C34 高亮比例表「银行存款÷资产总额」行、A50 与同页再次跳转都高亮审计结论卡片、I18 提示没有对应位置；E1-9 A26、E1-19 A54、H3-4 A27 高亮审计结论卡片，D4-6 A28 高亮「四、审计结论」标题（约 8.2 秒）、D4-22 A28 高亮审计意见区卡片（约 7.6 秒）；无接口错误、无页面脚本错误（`walk_w3_brief.txt`，截图 `w3_*.png`）。⑥写入对账（`snapdiff_before_final.txt`）：两个项目行 `deleted_at` / `updated_at` 更新为放回时间（`is_deleted` 仍为 true），9 份底稿行不变（未改 `file_path`），`editing_locks` +52 行全部已释放（另 3 行 10-27 的未释放锁不是本次写的，未动），`logs` +108 行（加锁 / 释放 / 恢复 / 删除）。

- [x] 7. 提交、推送、INDEX 登记
      提交前暂存检查与暂存树自洽门；按版本号流程推送（`.git-hooks/push_version.py`）
      实施记录（2026-10-30）：INDEX 登记本 spec；acnr-foundation-defect-closure 任务 16 追加「后续二」（目录坐标问题已处理）。提交在分离头 worktree 里做（不建分支）。推送前远端已前移到 `d2477f295`（v1.0.51~v1.0.54，4 个提交、618 个文件；与本 spec 交集只有 INDEX 与 `GtWpRenderer.vue` / `ConsolidationIndex.vue` / `WorkpaperEditor.vue`，改动区块不重叠；ACNR 生成输入与模板未变），提交重放到 `d2477f295` 之上（INDEX 取上游版本后重新插入本 spec 行）后复跑：ACNR 同口径检查 17 条 rc=0；`backend/tests/acnr` 1029 passed、3 skipped、0 failed；循环种子 / CI 接线 / 引用停用坐标的 14 个后端文件 6 例失败与新基线逐条同红；前端选集 62 个文件 742 例新增红 0（`DefaultLayoutNavigation.pbt`、`GtWpRuntimeBoundary.pbt` 2 例、`WorkpaperEditorShell` 导入失败与新基线同红）；扫描类 87 个文件新增红 0（39 条同红）；引用停用坐标的 24 个前端文件 285 passed；单区域 vue-tsc 候选与新基线都是 1230 条（只有联合类型成员顺序差异），探针报 TS2322；`WorkpaperEditor.vue` 上游行数未变，棘轮 1341 仍成立。提交前暂存检查与暂存树自洽门（`check_staged_tree_self_consistency.py`）通过后经 `.git-hooks/push_version.py` 推送，本提交即推送内容，版本号见对应附注标签。
