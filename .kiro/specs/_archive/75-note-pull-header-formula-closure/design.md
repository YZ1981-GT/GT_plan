# 附注取数 / 多级表头 / 公式管理收口 — 设计

## §1 现状实证（2026-10-26）

| # | 事实 | 证据 |
|---|---|---|
| F1 | 附注「刷新 / 全部刷新 / 手动重试 / 点击重算 / 底稿保存自动刷新」最终都只跑 `DisclosureEngine.refill_sections`：按 `note_template_bindings.json` 取试算表 / `parsed_data` / 公式，**不读底稿披露表**；报表项目章节的绑定格国企 2068/2132、上市 1079/1887 是 manual 占位 | `useNoteRefresh.ts`、`disclosure_engine.py` refill_sections、探针统计 |
| F2 | 每次刷新前调用的 `pull-from-workpapers` 只给已有同步指纹的章节打 `_source` 标记，不取任何数；前端 `_silent` + catch 吞掉结果 | `disclosure_notes.py` pull_from_workpapers |
| F3 | 后端披露表 builder（spec 61/68，2026-10-22）挂在 `WORKPAPER_SAVED` 与 `refresh-from-disclosure` 上；事务回滚探针：重药安徽 D2 → 八、5 账龄期末全 0、组合计提坏账准备 0、变动表全 0，`build_and_sync` 返回 success、rows_synced 22 ⇒ **下次保存 D2 就把错数写进附注**；标准 builder 给约 70 个科目各写一张以章节标题命名的两行表，编辑器按 `sub_table_data` 投影后只显示这一张、模板表全部隐藏 | 探针 + `d2_builder.py` / `standard_builder.py` |
| F4 | 前端披露 Tab 的 `buildXSyncPayload` 是披露表的真实口径（如 D2：`useD2DisclosureNote` 由 checklist_responses + 账龄配置现算快照），只在披露 Tab「保存成功」时经 `useDisclosureAutoSync` 推附注；没打开过披露 Tab 的底稿永远不进附注（重药安徽 D2 有 500 户明细，八、5 十五张表全空） | `useDisclosureAutoSync.ts`、真库 |
| F5 | 公式推送（推送页可见、可改写、可停用）把试算表审定数推到附注主表（193 条附注规则）并清 stale，是平台唯一「可溯源 + 自动更新」的取数通道；未接到附注刷新按钮 | `formula_push/engine.py`、`formula_push_rules.json` |
| F6 | `execute_note_formulas` 只读写顶层 `rows`（`_tables[0]` 的镜像），编辑器与 Word 优先读 `_tables` ⇒ 多表章节公式结果看不见，第 2 张起的表从无预设公式；查询没排除已删除记录 | `note_formula_generator.py` |
| F7 | 附注公式弹窗「新增公式」的目标列不可编辑，保存时目标为空被后端当空行丢弃，前端仍提示「已保存」 | `NoteFormulaDialog.vue`、`note_settings.save_section` |
| F8 | 单体编辑器表头：Path B（`multi_header` ≥3 行）顶层把中间层分组整个丢掉；扁平列直接显示「/」路径；只有两层 `el-table-column` 嵌套 | `useNoteTableProjection.ts`、`DisclosureEditor.vue` |
| F9 | 单体模板为两层表头按期间拆表（国企 八、5「按坏账准备计提方法分类」拆成期末 / 期初两张 6 列表，底稿与 Word 都是一张 11 列三层表；国企组合计提、上市分类披露等每期一张、期间在最上层被丢掉）；配对结果：拆表 2 组、去掉最上层期间 29 组 | `note_template_workpaper_alignment.compare_all` 实跑 |
| F10 | Word 模板模式：样例表叶子列数 = 库内表列数才克隆表头，拆开的 6 列表对不上 11 列样例 ⇒ 回退两行表头；程序化导出也只有两行 | `note_template_block_fill.rebuild_block`、`note_word_exporter._render_table` |
| F11 | 空表判定跳过合计 / 小计行：只有合计行有数的表（公式推送合计行兜底写入 104 格）在编辑器显示「本期无此情形」、Word 导出整表省略 | `note_empty_table_detector.py` ↔ `disclosureEmptyTable.ts` |
| F12 | 合并 `_infer_row_type`：「小计」先命中合计正则 ⇒ 恒判合计；单体结构编辑 `recalcTotals` 整表求和、不分段 | `consol_note_formula_service.py`、`useNoteTableStructure.ts` |
| F13 | V204 下推：`from app.models.disclosure_note_models import DisclosureNote` 模块不存在（每家子企业必失败）；结构锁模型导自 `consol_note_mapping_models`（实际在 `consol_note_mapping_template_models`，异常被吞、锁从不生效） | importlib 实测 |
| F14 | 合并拉数：真库 3 个合并项目、明细模板 / 绑定 / 确认映射全 0 ⇒ 重新汇总叶子全按「未绑定」跳过；预览已算 `auto_confirmable` 前端不用、模糊匹配一律显示「就绪」；history 排在 fuzzy 之后 | 真库只读、`consol_note_detail_suggest.py`、`ConsolNoteMappingDialog.vue` |

## §2 裁决

- **ADR-1 披露表口径只有一份：前端披露 Tab 的 composable + `buildXSyncPayload`。** 后端 builder 不是同口径（F3）⇒ 从写路径摘除、模块头注明不得接入；不在后端重写 69 个 builder（与 ADR-DPA-001 一致，双写必漂移）。「不打开底稿也能取数」用**离屏同步**：附注页直接调用同一个 composable 与 payload builder（不复制逻辑），按底稿逐个接入。
- **ADR-2 附注刷新 = 公式推送 + 离屏同步 + 附注公式。** 推送负责试算表审定数（过完调整分录）→ 底稿披露项 → 附注主表，规则在公式管理「📤 公式推送」页可见可改；离屏同步负责只有披露表才有的明细（账龄、坏账、前五名……）；附注公式负责表内合计 / 跨表引用。三者都不动人工 / 锁定格。
- **ADR-3 期间层只在显示 / 导出还原，不改存储。** 依据由生成器从 `compare_all()` 配对产出 `note_table_period_layout.json`：一张底稿表被拆成几张模板表 ⇒ `side_by_side`；1:1 配对且底稿最上层是统一期间、模板没有这一层 ⇒ `top`。读时增强把提示挂到表上，编辑器与 Word 导出共用。存储仍是两层表 ⇒ 推送规则、前端 payload、合并拉数、标题行库零改动。
- **ADR-4 公式目标表维度向后兼容。** `行:列` = 第 1 张表；`t{n}:行:列` = 第 n+1 张。旧数据不迁移。
- **ADR-5 合并自动映射仍是「确认」**，只是一键批量确认可以精确判定的企业组；判不准的照旧进弹窗。

## §3 R1 设计

- `note_disclosure_refresh_service.handle_workpaper_saved` 与 `routers/disclosure_notes.refresh_from_disclosure` 删除 `build_and_sync` 调用。
- `refresh_note_section`：章节 `table_data` 没有 `_last_sync_wp_id` 且 `_source` 不是底稿来源 ⇒ `status="not_synced"`，不改任何字段。
- `disclosure_payload_builder_service` 模块头写明口径不一致、禁止接入写路径；守卫 `test_disclosure_builders_not_wired.py`（AST 扫 `backend/app`，除服务本身与 builders 包外不得 import / 调用这两个函数）。

## §4 R2 设计

- 新服务 `note_workpaper_pull_service.pull_sections(db, project_id, year, sections|None, user_id)`：按项目 `template_type` 用 `note_workpaper_sync_registry.json` 反查 wp_code（共用章节逐个），过滤 `formula_push.bindings.supported_wp_codes()`，在 SAVEPOINT 里 `engine.run(trigger=MANUAL, codes=…)`；年度不符 / 推送异常 ⇒ 回滚保存点、记原因，不影响后续标记。返回 `{push: {written, kept, skipped, notes:[章节], warnings}, sections:[{section, wp_codes, pushed}]}`。原有同步指纹标记逻辑保留。
- 路由 `pull-from-workpapers` 调服务并 commit；前端 `_pullFromWorkpapers` 返回结果，`showRefreshResultMessage` 合并展示。
- 离屏同步（前端）：`views/composables/noteHeadlessDisclosure.ts` 注册表 `wp_code → provider(ctx)`；`ctx = {projectId, year, variant, wpId}`；runner 先 `GET` 解析底稿、`GET checklist-responses`，调 provider 得 payload，`POST sync-from-workpaper`。D2 provider 在 `effectScope` 里实例化 `useD2DisclosureNote`（save 置空、只读）等账龄配置加载完 → `buildSnapshot()` → `buildD2SyncPayload`；首次同步的孤儿表基线按附注现存表名播种（与 Tab 同一函数 `seedSyncedTablesFromNote`）。D2 Tab 的 `syncToDisclosureNotes` 与 provider 共用抽出的 `postD2Sync`。
- 覆盖清单 `noteHeadlessDisclosureCoverage.spec.ts`：注册表 78 个 wp_code 减去已接入 = 冻结清单，只许变短。

## §5 R3 设计

- 🔴 实施时补的实证（F6b）：真库 2042 条附注 `_formulas` / `_user_formulas` / `_check_presets` 全 0、存储行无 `account_codes`；生成器只认英文预设名（`sub_item` / `balance` / `movement` / `book_value`），模板 `check_presets` 是中文（其中项 / 余额 / 纵向 / 宽表 …）⇒ **任何附注都没有预设公式**，公式管理附注列表恒空、「应用自动运算」恒执行 0 个。
- 新模块 `note_formula_tables`：`formula_key` / `parse_formula_key`（`行:列` = 表 0，`t{n}:行:列`）、`iter_note_tables`、`total_terms`（合计构成）、`book_value_columns`、`section_preset_formulas`、严格求值 `evaluate`、表内顺序 `table_order`、`formula_targets` / `describe_target` / `target_issues`。
- 预设按每张表**当前结构现算、不落库**（按行号指格，落库后增删行会指错格）；存过 `_formulas` 的旧数据照用，「重新生成」（`apply-formulas?regenerate=true`）丢掉旧公式。合计只在判得准时生成：单合计行且上方全是明细；「其中：」标记行下是上一行的明细；「小计 / 减：X / 合计」= 小计 − 减项；含「其中：X」行内写法 / 多个合计分段 ⇒ 不生成、回原因。只加标题行库判为金额的列；账面价值 = 账面余额 − 准备（同期间各自唯一）。变动表「期末 = 期初 + 增加 − 减少」是审核勾稽，不当自动运算。模板覆盖：带合计的表 国企 153/236、上市 241/328。
- 执行器：逐表写 `_tables`、表 0 写完 `sync_first_table_mirror`；排除已删除；只写 auto 格；审核类公式不回填；引用全空 / 取不到 / 写法认不出 / 除以零 ⇒ 不写、结果带原因（原先全空写 0，会盖掉推送按审定数写入的合计）；值没变不算更新；跨表数据有引用才预载（`cross_data` 传空字典多章节共用）；`_load_cross_table_data` 每个读库语句包保存点。
- 列表 `list_section` 回 `targets`（逐表行 / 列名）与每条 `target_label`，按（表, 行, 列）数值排序；保存前 `target_problems` 校验目标（没选 / 不是单元格 / 超出表格 ⇒ 422 `FORMULA_TARGET_INVALID`）。
- `NoteFormulaDialog`：新增公式行内选表 / 行 / 列（选齐才写目标），列表显示可读目标；有公式没目标不保存；应用 / 重新生成提示写明没写入的原因。
- 刷新后执行：`pull_sections` 推送后对刷新的章节 `materialize_quietly` + 逐章节保存点 `execute_note_formulas`，回 `formulas: {updated, sections, errors}`。真库回滚探针：重药安徽全量刷新 2.5 s，八、18「小计 500000（推送写入）、合计 = 小计 − 减值准备」得 500000，其余格引用全空不写。

## §6 R4 设计

- 前端 `NoteTableCol` 改树：`{label, headerIdx?, children?}`；Path A / Path B 都产出树，Path B 递归任意层；扁平叶子标签取「/」末段。新组件 `NoteTableColumnNode.vue` 递归渲染 `el-table-column`，单元格内容走作用域插槽（编辑器单元格模板只写一份）。
- 生成器 `scripts/gen/gen_note_table_period_layout.py --write|--check` → `backend/data/note_table_period_layout.json`：`{std: {section: [{mode, tables:[表名], periods:[期间原字]}]}}`。
- 读时增强 `note_table_enrichment.attach_period_layout`：按表名挂 `_display_layout = {mode, period, partner?, order}`。
- 前端 `noteTablePeriodLayout.ts`（纯函数）：`top` ⇒ 列树外包一层期间；`side_by_side` ⇒ 两张表按行号横向合成（行名逐行一致才合成，否则不动），单元格回写坐标沿用 `_sourceCellRefs` 体系。
- 后端 `note_period_layout.apply_period_layout(tables)`（纯函数，Word 两种导出共用）：合成 / 加层后输出 `multi_header`（N 行）；`_render_table` 与 `note_template_table_look._header_rows` 支持 `multi_header` N 行表头（`fill_multi_header`）。

## §7 R5 / R6 设计要点

- `_infer_row_type`：先判小计（「小计」及「X小计」），再判合计。前端 `recalcTotals`：小计 = 上一个小计 / 合计之后到本行的数据行；合计 = 本段数据行 + 段内小计（有小计时只加小计）——与 `note_total_recalc` 对拍用例。
- 空表：合计 / 小计行在数值列（或无列定义时的数值）有非零值 ⇒ 非空；前后端镜像用例同步改。
- Word 表题：`_caption_para` 前 `strip_title_guidance`；字面编号重排只在块内模板原有表题编号从 1 连续时进行。
- 🔴 R5 实施（批 5，与上面三条的差异以此为准）：
  - 合计构成只有一份：`note_total_terms.total_terms`（单合计 / 「其中：」标记 / 「小计 − 减项」/ 多段小计 + 合计 / 标题式小计；判不准的回原因不算）。同一判定接到 7 处：附注预设（`note_formula_tables`）、生成 / 刷新回填（`disclosure_engine._backfill_totals` → `recalc_table_totals`，只写自动格、金额列、构成全空不写）、合并拉数与汇总（`consol_note_table_totals.build_table_rows`，判不准的合计写来源之和）、合并保存回填（`backfill_total_rows`）、旧派生登记（`note_formula_derivation`，展开到明细行）、前端三处（单体改单元格 `columnTotalUpdates`、结构编辑 `recalcNoteTableTotals`、合并编辑 `recalcConsolTotalRows`，`noteTotalTerms.ts`）。前后端按单体 564 / 合并 429 张模板表逐表对照 golden `note_total_terms_golden.json`（`gen_note_total_terms_golden.py --write|--check`）。
  - 实证（旧算法）：合并模板「小计」被判合计 68 行（43 张表）；合并拉数「小计 / 减：X / 合计」的合计 = 明细 + 减项（减项被加上）、「其中」表把明细重复加（合并模板逐表对照 88 张构成不同）；单体改单元格把第一个合计行写成整表之和（「其中：境外款项」「减：坏账准备」也加，明细全空写 0）；`note_total_recalc` 无生产调用方，未改。
  - 行类型（只有行名时）：以「小计」结尾 = 小计、「合计」「总计」= 合计（`label_row_type`，与合并读单体 `_source_row_type` 同口径）；汇总骨架里表内子表头标 `header`（结构行）。
  - 删行 / 加行：删最后一个明细行（不删合计 / 小计、减项、「其中：」），明细不足两行不删；加在第一个上方有明细的合计 / 小计行之前（标题式小计表加进第一组）。
  - 空表：合计 / 小计行只看数（金额列；无列定义时任意列），非零 ⇒ 非空、文字不算；同口径接到交付件判空（`table_blank_for_delivery`）与 auto_trim 判空（`note_is_empty_calc`）。真库只读：3 个项目 52 张表原先只合计行有数被判空（重药安徽 20）。
  - 表题：四版 Word 模板的表题段都没有字面编号（编号都在子标题上）⇒ 「从 1 连续」的判断落在子标题：按（级别, 上级段）分组，只重排模板里本来从 1 连续的组（上市 五、71「（7）供应商融资安排」单独一个，原先被重排成「（1）」）；续表 / 额外表按库内表名补的表题剔除指引（上市 3 个表名带「（注意：…）」「（只写…）」），表名带的「（N）」跟着所属子标题改号。
- V204：两处导入改正，下推端点加 `check_consol_lock`。匹配：history 提到 fuzzy 前；`exact_id` / `history` 进可自动确认集合；弹窗 `_status` 用 `auto_confirmable`。
- 自动映射服务 `consol_note_auto_mapping.auto_map(db, project_id, year, section_ids|None, user_id)`：未绑定章节用 `suggest_template_for_section` 的合并模板骨架建明细模板并绑定；`preview_detail_refresh` 后逐结构组判定「组内全部来源行 auto_confirmable」⇒ `confirm_mapping`，否则记待确认（企业、行名）。路由 `POST /api/projects/{pid}/consol-note-detail-refresh/auto-map`（edit + 合并锁）。前端「📋 明细映射」旁加「⚡ 自动映射」。
- 🔴 R6 实施（批 6，与上两条的差异以此为准）：
  - 下推（任务 21，`consol_note_template_push_service`）：除两处导入外，原实现还有写坏子企业附注的 5 处 —— 写 `_tables[0]`（选错表）；首次下推已有行没有行身份 ⇒ 全当用户行、模板行再追加一遍（重复行）；没有章节就新建只有一列「项目」的残缺章节；映射按 soe → listed 顺序找、不按项目口径；逐家没有保存点。推送日志原生 SQL 的 `:f::jsonb` 不是绑定参数 ⇒ PG 语法错、端点必 500。只修导入会把「恒失败」变成「破坏性写入」，故写入规则一并改：
    - 章节按合并项目口径映射到单体章节（号 → 标题，取舍与拉数共用 `prefer_standalone_note`），表按 `pick_standalone_table` 选；
    - 已下推的行按 `_pushed_row_id` 认领，首次按行名 / 别名认领已有行，行名、数值、位置都不动（改名会让子企业公式推送按行名找不到行）；同名多行按顺序对应；行类型不参与比对（同名即同一行，声明类型不一致时不认领会补出重名行）；
    - 缺的模板行插在下一个已认领模板行之前（后面没有就接上一个之后），值按本表列宽补空；模板删掉的行只去下推标记，不删行、不删数；
    - 不写、记跳过并写原因：子企业没有该章节附注（不替子企业建残缺章节）、本期无此情形、由底稿披露表同步、表里没有一行明细对得上（只对上「合计」不算）、附注编辑门禁拒绝（无权限 / 归档 / 合并锁定）；
    - 每家一个保存点；写入以操作人身份盖「最近一次编辑」；结构锁只关联下推成功的企业、重推不重复；推送日志走 ORM（`failures` 列出失败与跳过）；
    - 端点加 `check_consol_lock`，每个章节下推它绑定的版本（请求里的版本只用来核对），章节级错误整单 400；
    - 不写动态行区占位行：附注编辑器、Word 导出、空表判定都不认它，会显示 / 导出成一条空行。
  - 行身份进拉数：读取层 `_rows_from` 与 `extract_source_rows` 带上 `_pushed_row_id`。原先两处都丢 ⇒ `exact_id` 在生产里从不触发；原 e2e 用例直接手造来源行，绕过了读取层。
  - 前端：结构编辑的 ➖ 行 / `deleteRow` 不删下推的固定行；恢复模板结构按行名带回行身份；下推结果弹窗列出跳过的企业与原因，请求静默（改在并发会话新建的 `consolNoteTemplatePush.ts` 上）。
  - 匹配（任务 22）：history 提到 fuzzy 前，历史目标已不在模板里 ⇒ 继续往下匹配（原先直接判手动）；可自动确认 = 有目标行 且 匹配方式 ∈ {exact_id, exact, alias, global_alias, history}（`is_auto_confirmable`，预览与自动映射共用；原条件「置信度 ≥ 0.93」漏了下推行与历史）；`needs_review_count` = 全部非自动确认（原先只数手动）；弹窗就绪用 `suggestionStatus`、改选目标即算已确认、匹配方式全中文（`consolNoteMappingLabels.ts`，原先 `exact_id` / `global_alias` / `previous_year` 显示英文代码）。
  - 自动映射（任务 23，`consol_note_auto_mapping.auto_map_sections`）：
    - 模板建议把全局别名库认得的写法并进模板行别名（「现金」→「库存现金」）；原先单列一行 ⇒ 不删就建模板时合并附注出现两行、金额各算一半；
    - 同一操作人已有该章节模板 ⇒ 追加版本（模板唯一键是 口径 + 章节 + 创建人）；一家来源都没读到 ⇒ 不建模板、记跳过；
    - 整组可自动确认才确认（规则按结构组整组生效，半组确认会让合并数少行）；已按当前结构确认的组不重复确认；用户排除的企业保持排除；每章一个保存点；
    - 企业树只建一次（扫描 / 预览 / 建议加可选 `tree` 参数）；
    - 端点 `POST /api/projects/{pid}/consol-note-detail-refresh/auto-map`（edit + 合并锁），前端「⚡ 自动映射」（全部章节 / 仅当前章节），结果弹窗列出待确认企业与对不上的行名；不写合并附注数据（之后「🔄 重新汇总」写入）。
  - 未做（登记，见 §9）：子企业编辑器对下推固定行的改名保护与可选行勾选（原设计的 `NoteTableEditor` 零挂载）；`check_structure_lock` 仍无调用方，且按合并章节号查、子企业按单体章节号保存时查不到；拉数映射按行名「一条来源行名 → 一个目标」，同名多行（多个「小计」）共用一条映射（合计 / 小计由汇总重算，影响限于同名明细行）；`_pushed_optional_active = false` 的可选行拉数照拉。
- 🔴 浏览器实测后补（批 7 / 批 8，【测试】公式同步集团 + 甲；与上文差异以此为准）：
  - 上市合并项目页面一律按国企版：项目详情接口只有 `template_type`、没有 `applicable_standard` ⇒ 合并页报表 / 附注模板、四栏目录按 `template_type` 取（`ConsolidationIndex.loadProjectInfo`、`ConsolCatalog` 挂载即取项目口径，它挂载晚于合并页的准则广播）。
  - 行名区间写法统一（`_label_key`：「1-2年」=「1至2年」）；来源独有行按来源出现顺序替换模板的「……」占位行（没有占位行插在首个合计前；原先按频率 / 金额排会打乱账龄顺序）。
  - 「……」占位行：模板建议标 `dynamic_zone`，自动映射建模板保留行类别；下推按行名再挡一道（修复前建的模板把它标成固定行，推进去就是子企业附注里删不掉的空行），修复前已推进去的再下推时去掉下推标记（行留原处、变回子企业自己的行）。
  - 来源结构指纹不含 `_pushed_row_id`：下推不改行名 / 行类型，映射照旧有效；含身份时每次下推都让已确认企业变成「结构已变化」、重新汇总跳过它。身份仍留在来源行里给 `exact_id`。真库：甲指纹回到确认时的 6ee71…，`stale_count` 0。
  - 标题行库：上市 五-5-6~10 组合计提表单体按底稿 D2 写「期末余额/应收账款」、合并按 Word 写「期末余额/账面余额」⇒ 词表同义计量词 `账面余额 ≡ 应收账款`；五-30-2「…上年年末互抵金额」↔ 单体「…期初互抵金额」（期间词夹在计量词中间，期间识别认不出）⇒ 计量词别名。上市对上 825 → 836、0.9375 → 0.95（棘轮上调），其余对照逐条不变。
  - 单体「🔄 恢复模板结构」恒取章节第一张表：在「组合计提项目：应收中央企业客户」上点恢复，表被换成「按账龄披露」的 3 列 12 行、金额只剩 2 格，定时自动保存随即写库。现行：前端带当前表的表名与序号，后端 `note_template_structure.pick_template_table` 按表名比较键找模板里的同一张表（同名按序号，无表名才按序号），找不到 404、不拿第一张顶；返回逐列定义（`columns` / `_column_groups`）与行类型。前端先二次确认；金额按列身份搬（列定义 key → 分组 / 列名 / 第几次出现 → 同列名，逐轮做完再降一档，弱规则不抢强规则的列；原先只按列名，期末 / 上年年末下同名列都取第一列）；行按行名依次对应（空白不计，同名多行不都取第一行），带回行类型、下推身份、单元格模式（按列映射搬）；撤销连列定义一起还原；404 静默给说明。真库修复：甲 五、5 第 6 张表按同构第 7 张表的表头 / 单元格元数据还原并带回下推身份（写前整份备份 `backend/backups/nprc_jia_5_5_combo_table_repair_20261026_143522.json`）。
  - 多级表头同名叶子点击定位：列树叶子 `column-key = h{表头序号}`，`useNoteTableInteraction.locate` 先认它（越界不定位），没有才按列名 —— 原先点上年年末「应收账款」选中、编辑的是期末那一格。
  - 定时自动保存（2 分钟）只存不打断：不跳到下一未编制章节、不退出编辑、不弹「保存成功」（`useNotePersist.onSave({ keepEditing })`）；保存后清结构撤销记录（表格对象换成了保存的副本，旧记录指向旧对象）。手工保存不变。

## §8 风险与验证

- 推送接到刷新：推送本身已有逐底稿保存点、人工 / 锁定格保留、审计年度门；刷新只是多一个触发入口。验证：真库【测试】项目回滚事务探针 + 浏览器实测。
- 期间层合成只在行名逐行一致时进行；不一致保持原样（不猜）。
- 每批：相关后端 / 前端测试 + 磁盘变异（摘掉修复点须打红）+ HEAD 对照回归失败集合不新增。

## §9 其他改进建议（不在本 spec 范围，供拍板）

见交付说明；要点：
- 取数：其余 77 个底稿的离屏同步逐个接入（覆盖清单只许变短）；推送规则「子表规则」大多恒跳过需清点；附注权威源按章节交接 + 前后端对拍守卫。
- 表头：单体附注存储升级为三层表头（现只存两层 `_column_groups`，三层靠模板 `columns[].group` 的「/」）；`note_template_bindings.json` manual 占位清理；上市合并 五-5-6~10 表头左上格 Word 原样为空，界面显示「列1」。
- 公式：多合计分段（多个「合计」行）的预设；`_check_presets` 中文预设名接入生成器；`note_total_recalc` 无生产调用方，删除。
- 合并：「前五名」类表跨企业重排；同名多行映射共用一条规则；`_pushed_optional_active = false` 的可选行拉数照拉；`check_structure_lock` 无调用方且按合并章节号查；子企业下推固定行的改名保护 / 可选行勾选（`NoteTableEditor` 零挂载）；修复前建的明细模板含「……」固定行，合并附注照样显示一行「……」，写入 / 导出可跳过占位行；V202 退役；builder 模块（`disclosure_payload_builder_service`）删除。
- 编辑器：编辑态行名格与金额格共用样式而右对齐；`gt_note_auto_advance` 默认开启，手工保存即跳章，可考虑默认关。
- 工程：两份鉴权清册在 HEAD 已红（`note_write_inventory` / `edit_level_impact_inventory`）；本地库 V205 未应用（并发会话的改类型 / 删列迁移）。
