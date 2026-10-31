# 实施计划：底稿深链定位残项收口（wp-deeplink-locate-residual-closure）

> 证据目录：`tmp_wp_locate_res/out/`，截图 `tmp_wp_locate_res/screenshots/`。候选树 = 分支 `426b30f9e`（v1.0.56）+ 本 spec 改动（分离头 worktree `tmp_wp_locate_res/wt`；起初基于 `24768860e`，与 v1.0.56 无文件重叠，重放到其上）；归因基线 = `426b30f9e` 干净检出（`tmp_wp_locate_res/base2_wt`）。提交前远端前移到 `1154b99ca`（v1.0.60，4 个提交，与本 spec 只有 INDEX.md 头部插行一处交集），重放到其上后按任务 6 末条复验。

- [x] 1. 复核脚本收口 33 格、合计行规则、删除失效豁免（需求 4.1 / 4.2 / 5.1）
      Files: `backend/scripts/acnr/review_cell_coordinates.py`、`backend/data/acnr/sources/{sheet_verdicts.json,acknowledgements.json}`、`backend/data/t_address_registry_seed.json`、`backend/app/services/acnr/{loaders/from_sheet_verdicts.py,catalog_names.py}`（文档）
      Verify: `review_cell_coordinates.py --check` 退出 0；判定 / 新坐标条数与 design §4.3 一致或按现算更正
      记录：`--write` 后本 kind 判定 435 格（改指 72、指父表 363），新坐标 68（含 G8-4 A24 `conclusion_label`、D1-3 J21 / D2-2 Q26 `total_row`），被取代的 33 条 `keep_semantic_unverified` 判定删除、豁免 `ack-seed-semantic-unverified-2026-10-27` 删除；复核范围抽成 `review_scope()`，`check_lines` 点名残留判定（design §7）。`--check` rc=0。

- [x] 2. 重新发布目录与守卫（需求 4.2 / 5.2）
      Files: `backend/data/acnr/{global_catalog.json,catalog_report.json,catalog_snapshots/*,v2_canonical_reconcile.json}`、`backend/tests/acnr/fixtures/editor_save_inputs.json`、`audit-platform/frontend/src/generated/catalogTextAnchors.ts`、`backend/tests/acnr/test_cell_coordinate_review.py` 与受影响的既有测试、架构文档事实表
      Verify: CI 同口径 17 条检查 rc=0；`backend/tests/acnr` 全套；变异（复核不纳入待核对格 / 合计行不判唯一 / 表头不判唯一列）
      记录：目录批次 20261030155451（上一批 20261030063137）：sheet 1225、单元格 542（停用 474、有效 68）、blocking 0；文字锚点 64 张表 / 64 格；v2 对账 325088 节点；editor_save_inputs 2098。CI 同口径 17 条检查 rc=0（`acnr_checks.py wt`）；`backend/tests/acnr` 1035 passed / 3 skipped（`be_acnr5.txt`，skipped 为 pg_only），其中 pg_only 的「停用坐标在 PG 公式里无引用」单独连真库跑 1 passed。既有用例样本替换见 design §7（判据不放宽）。

- [x] 3. 复合结论标题（需求 3）
      Files: `audit-platform/frontend/src/composables/textAnchorLocate.ts` 及用例
      Verify: `textAnchorLocate.spec.ts`、`useRendererCellLocate.spec.ts`；变异（不排除按钮 / 不限长度 / 不判唯一）
      记录：`textAnchorLocate.spec.ts` 19 例、`useRendererCellLocate.spec.ts` 24 例通过；变异 T1~T4 全红。浏览器：F2-18 A65 高亮「分析结论（四、审计结论）」所在卡片（二级）。

- [x] 4. 调整分录页跳来源底稿并定位分录组（需求 1）
      Files: `utils/normalizeSheetName.ts`、`views/Adjustments.vue`、`composables/adjustmentEntryGroupLocate.ts`、`components/workpaper/composables/useAdjustmentCentralSync.ts`、24 个按类型分组的 `*TabAdjustment.vue`、`composables/useRendererCellLocate.ts`、`components/workpaper/GtWpRenderer.vue` 及用例、守卫 `adjustmentEntryGroupWiring.spec.ts`
      Verify: 上述用例与渲染器 / 汇聚既有用例；变异（别名不判唯一、跳转不带别名、高亮串不校验底稿、不注销、不切类型、不还原类型、渲染器不发请求、不重试）
      记录：`adjustmentEntryGroupLocate` 5 例、`useAdjustmentCentralSync.locate` 4 例、`adjustmentEntryGroupWiring` 4 例（81 个调用点 / 24 个按类型取 item_id）、`useAdjustmentCentralSync` 24 例、`normalizeSheetName` 16 例通过；变异 A1~A13 全红。浏览器见任务 6。

- [x] 5. 底稿列表页读入口参数（需求 2）
      Files: `views/workpaper-list/{workpaperListEntryQuery.ts,useWorkpaperListLocate.ts,WorkpaperWorkbenchView.vue}`、`views/WorkpaperList.vue`、`composables/useWorkpaperListContext.ts`、`views/workpaper-editor/UniverEditorCore.vue`、`components/workpaper/ReviewLayerBadges.vue` 及用例、守卫 `workpaperListEntryQuery.spec.ts`
      Verify: 新用例、`workpaperListQueryReuse.spec.ts` 与列表页既有用例；变异（不翻页、不回落上级、签名不变也强制列表、不去掉 upload、守卫漏扫字符串路径）
      记录：另改 4 处入口与 `account` / `assigned` 两个参数（design §7）。`useWorkpaperListLocate` 7 例、`workpaperListEntryQuery` 5 例、`workpaperListQueryReuse` 14 例及列表页既有用例通过；变异 L1~L13 全红。浏览器实测抓到 `?account=` 把映射里的 13 个编码（含表级 D2-2、本项目没有的 D0）全部点名 ⇒ 改为等首次取数后只认本项目已生成的（L12 / L13 守住）。

- [x] 6. 验证与记录（需求 6）
      前端选集回归（基线归因）、单区域 vue-tsc、磁盘变异、浏览器（【测试】项目经回收站恢复、经平台生成 D2 等底稿后测、测后放回）、写入对账
      记录：
      - 前端回归：选集 86 个文件候选 / 基线各 15 处红、候选新增 0（`fe_cmp_reg_cand.txt`；基线红含 adjustmentIeContract K13-3、workpaper-list line-budget、WorkpaperListShell「matrix」页签等，与本 spec 无关）；扫全仓类 89 个文件候选新增红 0（`fe_cmp_scan_cand3.txt`，基线 45 / 候选 39，差的 6 处在基线并行跑时红、候选通过）；收尾改动后聚焦 18 个文件 160 例全过。
      - 单区域 vue-tsc（本 spec 55 个文件）：候选 / 基线同一清单各 1178 条，新增 0、减少 0；探针 `number = string` 报 TS2322（配置确在检查）。ESLint（同 55 个文件）：候选 124 = 基线 124，新增 0。
      - 磁盘变异 38 条（A1~A13 / L1~L13 / T1~T4 / B1~B8）全红，红在预期断言上（`mutations_summary.txt`），逐条按 sha256 还原。
      - 浏览器（隔离后端 9987 + 前端 3037 跑候选树；【测试】附件小眼睛走查_2025 经回收站恢复，D2 / F2 经主树后端按模板集「精简版」只选 D2 / F2 生成，测后放回回收站；`walk2_r1/r2/r3_summary.txt`、截图 `screenshots/r1_* r2_* r3_*`）：文字锚点 G8-4 A24 / D2-5 A53 / D2-6 A21 高亮「审计结论」，F2-18 A65 二级高亮复合标题；D2-2 Q26 切到「明细表D2-2」并提示网页视图里没有该格的对应位置（合计格在网页视图没有登记位置，目录坐标供 Univer / OnlyOffice 选格与公式用）；F2-62 本项目（国企单体）显示「此底稿仅适用于 IPO/上市/新三板/重组项目」⇒ 提示，二级标题由 F2-18 与单测覆盖。调整分录跳转：D2 → 调整分录汇总表D2-4（原落审定表）、F1 → 调整分录汇总F1-3（原落程序表）、L1 AJE / RJE → 调整分录汇总L1-3 且切到对应类型、认不出的分录组提示且类型还原、别的底稿的 highlight 不误用、D4 / K3 照旧；调整分录页拦列表响应注入一条底稿来源分录后点「底稿 L1」→ L1-3 + RJE。列表页：highlight G8 / wp_code K3 / search「L1 短期借款」标出该行，D2-5 回落 D2 并提示，Z9 提示本项目没有，cycle=D 筛 D 类，assigned=unassigned 显示「未分配」，account=1122 定位 D2，upload 打开导入并去掉参数，view=lifecycle 切生命周期，手册「循环详解」点 K3 切列表并标出。
      - 写入对账（`snapdiff_r2_before_r2_after.txt`、`wp_storage_r2_*.json`）：项目行只有 deleted_at / updated_at（恢复后放回）；editing_locks +15（全部已释放）、logs +35（加锁 / 释放 / 删除项目）；wp_index、working_paper 各 +2（D2 / F2，文件 2 个在主树 `backend/wp_storage/<项目>/`，随项目留在回收站）；其余表无变化。打开 F1 时页面自动调 `/f1/import-aux-balance`（F1 明细为空时自动归集，既有行为），本项目没有辅助余额，无数据变化。
      - 走查中看到、与本 spec 无关未改：G8 页 `GET /projects/{id}/materiality` 422；生命周期视图 `GET /ai/recommend-workpapers` 405（后端是 POST）。
      - 重放到 `1154b99ca` 后复验（基线 worktree 同步移到 `1154b99ca`）：CI 同口径 17 条 rc=0；`backend/tests/acnr` 1035 passed / 3 skipped；前端选集 86 个文件候选新增红 2 处，均为扫全仓用例超时（STACK_TRACE_ERROR，三个测试进程并行时），两侧单独重跑：acnrDisplaySingleSource 两侧都过、bridgeMaterializeDriven 候选 4 红 / 基线 6 红（同一批既有红），候选新增 0；单区域 vue-tsc（上游改了 tsconfig.json）候选 / 基线各 1178、新增 0、探针 TS2322；ESLint 新增 0；行数门禁 69 个文件 rc=0；暂存树自洽门 2 道全过。

- [x] 7. 提交、推送、INDEX 登记
      暂存检查与暂存树自洽门；`.git-hooks/push_version.py` 推送
      记录：INDEX 首行登记；`acnr-foundation-defect-closure/tasks.md` 追加「后续三」；单一提交，经 `push_version.py` 推送到 `spec/disclosure-note-doc-upload-and-batch-fill`（版本标签见推送记录）。
