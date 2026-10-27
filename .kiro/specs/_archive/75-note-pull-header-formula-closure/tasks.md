# 附注取数 / 多级表头 / 公式管理收口 — 任务

## 批 1 止损（R1）

- [x] 1. 摘除后端披露表 builder 的写路径：`handle_workpaper_saved` 与 `refresh-from-disclosure` 不再调用 `build_and_sync`；`refresh_note_section` 对未同步章节回 `not_synced` 不标待更新；模块头注明禁止接入
- [x] 2. 守卫 `test_disclosure_builders_not_wired.py`（AST）+ 刷新服务用例改写；磁盘变异（把调用加回去必须打红）
  - 证据：20 passed（单元）+ 6 passed（PG，含改写后的只读 handler 端到端）；变异 M1~M4 全部打红（handler 调回 builder / 重新订阅 / 未同步又标 stale / 端点调回 builder）

## 批 2 附注刷新取数（R2）

- [x] 3. `note_workpaper_pull_service.pull_sections`：按准则反查底稿 → 公式推送（保存点隔离、年度门、逐章节结果）；路由 `pull-from-workpapers` 接入
- [x] 4. 后端用例：推送被调用的 codes 正确、年度不符不阻断、未接入推送的底稿点名、共用章节去重
  - 证据（3~4）：`test_note_workpaper_pull_service.py` 10 + `test_pull_from_workpapers_never_synced.py` 3（夹具改为「有指纹缺来源标记」，路由漏 commit 可见）+ PG `test_note_workpaper_pull_service_pg.py`；回滚探针：重药安徽 八、5 推送 7 格跳过（规则章节标题校验，原因回传）
  - 顺带修：`test_disclosure_note_edit_stamp.py` 夹具 patch 的 `_assert_project_edit` 自 cad40da77 起不存在 ⇒ 8 例一直在 fixture 报错、从未执行；改为替换 `note_edit_gate.assert_note_edit_access`（路由函数体形态的同名导入一并替换），48 passed
  - 变异 B2-M1~M7（+M3b 真库）全部打红且红在预期断言：推全部底稿 / 推送被拒改抛出 / 刷新改同步时间 / 空 manual 格算人工 / 保留格计写入 / 路由不提交 / 未同步章节补来源标记
- [x] 5. 前端 `useNoteRefresh`：不再静默吞 `pull-from-workpapers`，提示合并推送结果与跳过原因
- [x] 6. 离屏同步框架 `noteHeadlessDisclosure.ts`（注册表 + runner）+ D2 provider（复用 `useD2DisclosureNote` / `buildD2SyncPayload`，与 Tab 共用发送函数）
- [x] 7. 刷新 / 全部刷新接入离屏同步；未接入底稿在提示中点名；覆盖清单守卫（只许变短）
- [x] 8. 前端用例：D2 provider 产出与 Tab 同一 payload、runner 失败不阻断刷新
  - 证据（5~8）：`useNoteRefresh.spec.ts` 15（新增 5：先取数后重算的调用顺序、取数失败不阻断、离屏抛错记失败、全部刷新点名未接入底稿、未选章节不发请求）+ `noteHeadlessDisclosure` / `noteWorkpaperPull` / 覆盖清单 / `d2HeadlessDisclosure`（离屏载荷与 composable 现算逐字节相同）；D2 / 账龄相关 57 个测试文件 997 passed，18 例红均不在本 spec 改动范围（D4 写死科目码 11、`GtWpRuntimeBoundary` mock 缺导出 2、并发会话未跟踪的 `d2TbReconciliationBasis` 1、账龄 property 3、`loadNoteMappingPreset` 1；收尾在 HEAD 干净检出对照）
  - 变异 B2-F1~F11 全部打红且红在预期断言：覆盖人工填写 / 未接入不点名 / provider 失败直接抛 / 不预取账龄 / 离屏不套缓存 / 提示丢失败原因 / 请求不静默 / 不先取数 / 先重算后取数 / 离屏抛错不兜底 / D2 摘出清单

## 批 3 附注公式（R3）

- [x] 9. 生成器 / 执行器逐表：`t{n}:行:列` 目标、写 `_tables` 并同步顶层镜像、排除已删除记录、跳过原因
- [x] 10. `preview_records` 逐表预览；后端用例（多表章节第 2 张表的合计公式生成并写入）
  - 证据（9~10）：新模块 `note_formula_tables`（预设按当前结构现算、不落库；严格求值）；`test_note_formula_tables.py` 34 + `test_note_formula_execute_tables.py` 7（SQLite 真 ORM）+ `formula_settings/test_note_formula_table_targets.py` 3；既有公式 / 公式设置相关 41 个测试文件 1410 passed（4 红均不在本 spec 改动范围：EQCR 文案、鉴权基线 193→191 由并发会话改路由所致、合并种子计数 2 例，收尾在 HEAD 干净检出对照）
  - 实证：真库附注 `_formulas` / `_user_formulas` 全 0、生成器只认英文预设名 ⇒ 原先任何附注都没有预设公式（design §5 F6b）
- [x] 11. `NoteFormulaDialog` 目标选择器（表 / 行 / 列）+ 可读目标显示；新增未选目标不保存
  - 证据：`NoteFormulaDialog.spec.ts` 15（新增 5）+ `noteFormulaTargets.spec.ts` 3；后端保存前 422 `FORMULA_TARGET_INVALID`（`test_note_formula_save_ref_check.py` 新增 1；原用例把超出表格的目标「1:2」改为表内格）；单区域 vue-tsc 本 spec 文件 0 错（注入类型错误两处均报出）
- [x] 12. 刷新后对写入过的章节执行附注公式（保存点隔离）
  - 证据：`_apply_note_formulas` 逐章节保存点（一节失败只回滚这一节）；单元用例 + PG 用例（第 2 张表合计 / 账面价值写进 `_tables`）；回滚探针：重药安徽全量刷新 2.5 s、八、18 合计 = 小计 − 减值准备 = 500000
  - 变异 B3-M1~M16（+M13b 真库）、B3-F1~F6 全部打红且红在预期断言

## 批 4 多级表头（R4）

- [x] 13. 前端列树 + Path B 任意层 + 扁平列末段标签；`NoteTableColumnNode.vue` 递归列组件，`DisclosureEditor` 单元格模板只写一份
  - 证据：`noteColumnTree.ts`（逐列表头路径 → 列树：`multi_header` 任意层 / `_column_groups` 平铺与树形 / `columns[].group` 按「/」拆层；平表头的「/」是字面不拆，只去掉与分组路径重复的前缀；`<br/>` 去掉）；编辑器三份单元格模板合成一份（3265 → 3194 行，分组列也有了校验提示 / 批注 / 追溯图标）；`noteColumnTree.spec.ts` 5 + `NoteTableColumnNode.spec.ts` 1（三行 thead、叶子 headerIdx）+ 投影用例改为列树
- [x] 14. 生成器 `gen_note_table_period_layout.py`（`--write/--check`）+ 数据文件 + 守卫
  - 证据：`note_table_period_layout.json`（国企 4 节 10 条、上市 5 节 11 条：期间并列 2 组 = 国企 八、5「按坏账准备计提方法分类」、上市 五、10「合同资产减值准备计提情况」，其余最上层期间）；输出确定、内容不变不改文件；守卫 `test_layout_file_is_current`
- [x] 15. 读时增强挂 `_display_layout`；前端 `noteTablePeriodLayout.ts`（top / side_by_side，行名不一致不合成）+ 单元格回写坐标
  - 实施：期间层并进投影（`useNoteTableProjection` 续表合并体抽成 `appendColumns` 共用；`periodTree` / `offsetTree` / `sameRowLabels` 在 `noteColumnTree.ts`），不另起 `noteTablePeriodLayout.ts`；读时增强先清掉存进库的旧标记再按布局文件挂
  - 证据：投影用例 4（合成 + 列树、行名不一致不合成且不改源、合成表改期初列写回第 2 张源表、最上层期间）；`test_read_time_enrichment_attaches_and_replaces_stale_marks`
- [x] 16. 后端 `note_period_layout.apply_period_layout` + Word 两种导出支持 N 行表头；模板模式合成表克隆 Word 表头
  - 证据：`apply_period_layout_indexed`（合成表取首张表序、全组空才算空表、单元格模式按列偏移）+ `header_defs` / `export_header_defs`（≥3 层或期间层画 N 行；两层分组照旧走原两行路径）；`_render_table` 实测 11 列 × 3 行表头、标签列跨三行、值落对列；`_note_tables` 与 `note_tables_indexed` 都走期间层；`test_note_period_layout.py` 14
- [x] 17. 模板数据：国企 八、31 t0 分组一致、八、18「发起规模」；跑模板 ↔ 底稿对齐守卫
  - 复核后不改：八、31 t0 显示分组「期初余额」与骨架「年初余额」是同义写法（用户 2026-10-24 裁决同义算一致、不改；底稿 N1 写「年初余额」）；八、18 t8「发起 / 规模」是底稿上下两格拆写，按字相连判一致；R8.4 批 9b-2（07bbbc4e1）已按底稿改结构。对齐守卫 + 标题行库 + 期间层 170 passed
  - 变异 B4-F1~F7、B4-M1~M8 全部打红且红在预期断言；前端 views / notes / formula 区 122 个测试文件 1692 passed（唯一红 = 既有 `loadNoteMappingPreset`）

## 批 5 标题行 / 序号 / 合计（R5）

- [x] 18. 合并 `_infer_row_type` 小计；前端 `recalcTotals` 分段；删行跳过结构行
  - 实施：合计构成只留一份 `note_total_terms`（新），接到附注预设、生成 / 刷新回填、合并拉数与汇总、合并保存回填、旧派生登记与前端三处（单体改单元格、结构编辑、合并编辑；`noteTotalTerms.ts` 镜像）；判不准的合计前端 / 单体不回填，合并拉数与汇总写来源同一行之和
  - 证据：前后端按单体 564 / 合并 429 张模板表逐表对照 golden（`gen_note_total_terms_golden.py --check` + `noteTotalTerms.spec.ts`）；旧算法实证：合并模板「小计」被判合计 68 行（43 张表），合并拉数逐表构成不同 88 张（减项被加上、「其中」重复加）；`test_note_total_terms.py`（新）等 10 个后端文件与 3 个前端文件全过
- [x] 19. 空表判定合计行有数即非空（前后端镜像用例）
  - 证据：合计 / 小计行只看数（金额列；无列定义时任意列），同口径接到编辑器、交付件判空与 auto_trim 判空；前端 `TOTAL_ROW_TYPES` 交叉锁；真库只读：3 个项目 52 张表原先只合计行有数被判空（重药安徽 20 张）
- [x] 20. Word 表题剔除指引 + 连续字面编号重排
  - 证据：四版 Word 模板的表题段都没有字面编号（编号在子标题上）⇒ 只重排模板里本来从 1 连续的组，上市 五、71「（7）供应商融资安排」不再改成「（1）」；续表表题跟随所属子标题改号；上市 3 个表名带编制指引，补表题时剔除（`caption_text`）
  - 变异（18~20）B5-M / B5-F 39/39 全部打红且红在预期断言；回归：后端 458 个测试文件 11585 passed / 107 failed / 7 errors，逐条对照 HEAD 干净检出（补进并发会话已暂存的模型修复 `'[]'::jsonb` → `'[]'`，否则 SQLite 建表即失败）：103 条 HEAD 同红，其余 10 条为并发会话改动所致（审计年度缺失 422 ×9、鉴权基线 193≠191 ×1：差异端点全在 procedure_row_tasks / standard_conversion / wp_template）——本批零新增；前端 202 个测试文件只有本 spec 接线用例随批 6 改写（已改），其余 9 例所在组件本 spec 未改动

## 批 6 合并附注（R6）

- [x] 21. V204 下推两处导入 + 合并锁；后端用例
  - 实施：见 design §7「R6 实施」下推一节 —— 两处导入之外，原实现另有 5 处写坏子企业附注（写 `_tables[0]`、首次下推重复行、新建残缺章节、不按项目口径找章节、没有逐家保存点），推送日志 `:f::jsonb` 不是绑定参数 ⇒ PG 上端点必 500；改为按单体章节 / 选表规则认领已有行、行名与数值不动、每家保存点、门禁拒绝记跳过；端点加 `check_consol_lock`、按章节绑定的版本下推
  - 证据：`test_consol_note_template_push.py` 21 + `test_consol_note_template_push_db.py` 18 + `test_consol_note_push_e2e.py` 6 passed；浏览器：【测试】公式同步集团 五-5 下推回执「成功 1 家，跳过 1 家：乙 …未生成章节 五、5」，甲 五、5 下推行带 `_pushed_row_id`
- [x] 22. 行匹配顺序与可自动确认集合；映射弹窗按 `auto_confirmable` 判就绪 + 中文匹配方式
  - 实施：history 提到 fuzzy 前；可自动确认 = 有目标行且匹配方式 ∈ {exact_id, exact, alias, global_alias, history}（`is_auto_confirmable`，预览与自动映射共用）；`needs_review_count` = 全部非自动确认；弹窗 `suggestionStatus` + `consolNoteMappingLabels.ts`；读取层带上 `_pushed_row_id`（原先 `exact_id` 在生产里从不触发）
  - 证据：`test_consol_note_detail_source.py` 26 + `test_consol_note_mapping_template.py` 23 + `test_consol_note_standalone_reader.py` 22 passed；浏览器：映射弹窗 7 行「下推行 100%」
- [x] 23. 自动映射服务 + 端点 + 前端按钮；后端用例（精确组自动确认、模糊组进待确认）
  - 实施：`consol_note_auto_mapping.auto_map_sections` + `POST /api/projects/{pid}/consol-note-detail-refresh/auto-map`（edit + 合并锁）+「⚡ 自动映射」（全部章节 / 仅当前章节，结果弹窗列待确认企业与对不上的行名）
  - 证据：`test_consol_note_auto_mapping_e2e.py` 27 passed（下推 → 预览 exact_id → 自动映射 → apply，生产函数逐级调用、不手造来源行）+ `test_consol_note_subtree_reaggregate.py` 16 + `consolNoteAutoMap.spec.ts` / `consolNoteTemplatePush.spec.ts`；浏览器：自动映射后「🔄 重新汇总」写入合并 五-5-6「1年以内」100.00 / 80.00
  - 变异（21~23）B6-M1~M51、B6-F1~F14 共 65 条全部打红且红在预期断言（首轮 M29「端点不提交」、F1「只有跳过也报成功」存活，补断言后打红）

## 收尾

- [x] 24. 浏览器实测（重药安徽 / 【测试】项目：刷新取数、应收账款三层表头、公式弹窗、合并自动映射）
  - 证据（独立 Vite 3041、关 HMR、隔离浏览器上下文）：甲 五、1「🔄 刷新」先 `pull-from-workpapers`（synced 1）再 `refresh-from-workpaper`（3 格，校验 350 / 350）；三层表头：甲 五、5 与重药安徽 八、5（2）只读核对（类别跨三行 / 期末数·期初数 / 账面余额·坏账准备·账面价值 / 金额·比例·预期信用损失率，`updated_at` 前后不变、控制台无错）；合并下推 / 映射 / 自动映射 / 重新汇总见任务 21~23
  - 实测抓到并已修 8 处（design §7「浏览器实测后补」）：上市合并页按国企版取模板、行名区间写法、「……」占位行、来源指纹含下推身份（已确认企业被判结构变化、重新汇总跳过）、标题行库同义 / 别名、恢复模板结构恒取第一张表、同名叶子点击定位错列、定时自动保存打断编辑；变异 B7 14 / 14、B8 29 / 29 打红
  - 真库修复：甲 五、5 第 6 张表被「恢复模板结构」换错结构后按同构表还原（写前备份 `backend/backups/nprc_jia_5_5_combo_table_repair_20261026_143522.json`）；【测试】数据保留作回归：甲 五、5 第 6 张表「1年以内」100 / 80（带下推身份）、合并 五-5-6 两个节点 100 / 80、自动映射模板 v1（修复前建，含「……」固定行）、2 条下推日志、1 条结构锁
- [x] 25. 回归对照 HEAD 失败集合；INDEX 登记；交付说明（含 §9 建议清单）
  - 证据：后端按改动模块选出的 229 个测试文件 6962 passed / 67 failed / 6 errors，失败逐条对照 HEAD（e36cf246d）干净检出：68 条 HEAD 同红；只在工作树红 5 条均已归因 —— ①程序裁剪 spec 的既有附注链路字节判据对本 spec 有意改动的 4 个文件恒红到提交，已按其提示在 `test_task23_zero_regression` 登记（不随提交自愈的「既有链路不 import 联动模块」判据仍绿）②鉴权基线 191 ≠ 现算 189：少的两个端点是 `project_wizard` 改上级 / 查上级变更历史补了鉴权，属并发 spec `consol-autotree-linkage-closure` R3（已于 709b21275 提交、未下调基线常量；工作树里其他会话还在补鉴权，现算已到 169）
  - 收尾修的：鉴权配方 A6 补业务桩 `pull_sections`（R2 起端点改调取数服务，推送引擎自己 commit / rollback，不打桩时第一次放行请求就回滚测试夹具 ⇒ `test_manager_to_eqcr_note_write_denied` 第二次请求成员行已不在）；行数门：`note_word_exporter` 两层分组与 N 行表头合成一条 `fill_multi_header` 路径（1797 → 1785，白名单 1706 +5% = 1791），补两层表头渲染用例 + 表头行高断言，变异 B9-M1~M5（N 行表头被丢 / 两层分组被丢 / 表头行数 / 数据起始行 / 只给首行定行高）全部打红；经运行中的后端导出【测试】甲 附注 Word（程序化导出）：293 张表、56 张多级表头，上市 五、5（2）按坏账准备计提方法分类加期间层后画三行表头（标签列跨三行），组合计提表两行表头，「1年以内」100.00 / 80.00 落在期末 / 上年年末的「应收账款」列；导出相关 35 个测试文件只在工作树红的仍是上面 4 条字节判据
  - 鉴权清册：并发提交 709b21275 按它自己的树重生了两份清册，不含本 spec 的改动 ⇒ 工作树清册与代码不一致。附注写端点清册按工作树重生（现算差异逐条核对 = 只有本 spec 3 处：新增 `consol-note-detail-refresh/auto-map`、下推端点加合并锁、`refresh-from-disclosure` 改只读）；edit 级影响清单写入「HEAD + 本 spec」那一刻的生成结果（只多本 spec 2 个门禁调用点 `api_auto_map` / `_push_to_one`；随后工作树又出现并发会话 `reports.py` 的门禁改动，未带入，提交时须按要提交的树重生）。清册检查与附注门禁两个测试文件在 HEAD 干净检出红 9 条、工作树红 7 条（同跑的另 6 个门禁文件全过），均非本 spec：edit 级已提交产物有重复键 ⇒ 检查模式恒报错、双生成按字节比（干净检出是 CRLF、必不等）、`PUT …/formula-gray` 有覆盖无配方、鉴权基线
  - 前端：本 spec 核心 17 个测试文件 167 passed；221 个相关测试文件 8 例红在 6 个文件，均为本 spec 未改动的组件 / 行数门；单区域 vue-tsc 本 spec 文件 0 新增；行数门本 spec 文件全过（余 `ReportView.vue` / `_d1_disclosure_export.py` 两处非本 spec）
  - INDEX 已登记；未做与待拍板见 design §9
