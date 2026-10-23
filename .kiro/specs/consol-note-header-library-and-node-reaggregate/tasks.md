# 合并附注标题行库 + 节点子树重新汇总 — 任务

## Phase 1 标题行库

- [x] 1. 词表 `backend/data/note_table_header_vocabulary.json`：期间四类词（从读取层 `_END_WORDS/_PRIOR_WORDS` 迁入并拆分 本期 / 期末）、期间前缀与纯期间余词、分组同义词、比例列规则、续表标记规则与非续表词、逐表覆盖（初始为空，结构带理由字段）（R1.2）
  - 词表按四版种子全部表头段现扫（197 个带期间词的段）定：整词期间 / 期间开头 / 期间结尾三种写法都认（「减值准备期末余额」「期末余额（账面价值）」）
- [x] 2. 模块 `backend/app/services/note_table_header_library.py`：`column_paths`（合并表走 `normalize_consol_note_section`，单体表认平铺 / 树形分组与 `columns[].group`）、`column_keys`、`is_continuation_name`、`name_period`、`continuation_links`、`match_columns`、`choose_unit`（R1.1 / R1.4 / R1.5）
  - 行数门 800：识别（501 行）与对应 / 选表（`note_table_header_match.py`，345 行）分两个模块
  - 选表补一条「表头分不出时取有数的那张」：真库同一章节新旧模板表并存（和平 八、4 有 17 张表，「（期末数）」与无期间同名表同构）
- [x] 3. 模块单元测试：续表正反例、主表与类型、树形分组、表名期间、期间前缀拆分不撞键、「/」平表头、强弱规则与歧义放弃、三种选表方式、覆盖生效
  - `tests/test_note_table_header_library.py` 65 passed；进程内 5 个变异（续表按子串 / 去期间前缀 / 去结构排序 / 去有数优先 / 合并表只取末级）各自打红对应用例
  - 真库三种 八、4 表组合：五-4-2 都选到期末表、五-4-3 都选到「（续：期初数）」（名字精确命中的是单项计提表）
- [x] 4. 目录生成：`note_table_header_catalog.py` + `backend/scripts/seed/build_note_table_header_library.py`（`--check` 漂移 exit 2），生成 `note_table_header_library.json`（R1.3 / R1.6）
  - 四版：国企单体 252 / 国企合并 321 / 上市单体 460 / 上市合并 432 张表；对应覆盖（已选中单体表的金额列对上比例）国企 76.2%、上市 89.1%
  - 按目录审出来的规则修正（都进了模块与测试）：说明类列（原因 / 依据 / 日期 / 期限 …）不算金额列；「金额 / 余额」是计量填充词；种子「中级-叶」连字符拆层；表头尾部勾稽式注记不进计量；新增同义（坏账准备 ↔ 减值准备）、反向前后缀、单期间唯一列三条弱规则；选表打分加比例 / 说明类列一致与列数接近；一列金额都对不上时只认表名精确命中；「续」接紧挨着的上一张表（上市「应付债券（续）」原被认到同基名汇总表）
  - 异常清单 90 条（续表自指 2 / 并列表误标续表 12 / 种子续表序号与标记不符 4 / 同表两列同键 23 / 表头混入数据行 7 / 标签列表头盖到数据列 4 / 疑似新旧模板重复表 5 / 含「续」非续表 33）
- [x] 5. 目录测试：入库文件与生成结果一致、四版表数 = 种子表数、已知异常在清单、国企 五-4-3 对到「（续：期初数）」、覆盖率棘轮
  - `tests/test_note_table_header_catalog.py` 11 passed；进程内变异：词表改动未重生成 / 去掉章节异常检测 / 续表主表改按同基名优先，各自打红

## Phase 2 读取层与映射收口

- [x] 6. `consol_note_standalone_reader` 删除自带表头解析 / 同义词 / 续表判定改调模块；行续表并行、名字认不到按结构兜底并回报 `table_choice`（R2.1~R2.3）
  - 读取层只剩取表（`_tables_of`）、行类型与按「行名 + 同名序号」对行；选表 / 认列全部调 `choose_unit` / `match_columns`
  - 带合并表头时子表名与合并表标题两路命中合起来按表头比（映射子表名来自种子，种子有错名：国企 八、54 敏感性分析表叫「计划资产」）；裸「续：」标题有更具体名字时不参与
  - 无名字证据只在强命中明显领先「取自别的表」的次优者时按结构选（同构表不猜）；章节只有一张表但一列金额都对不上时不拿它凑数（多是章节映射错位）
  - 旧单表格式表头为空：复用 `note_header_projector.derive_headers_for_legacy_table` 补表头（真库宜宾临港店 17 个章节）
- [x] 7. `gen_consol_standalone_note_mapping.py` 续表判定与单体选表改调模块，重生成 `consol_note_section_mapping.json` 并逐条审变化（R1.5）
  - 只用单体口径章节的表选子表；「续：」接上一张改为按标题行库续表关系认；23 条变化逐条审过（国企 五-4-2 / 五-4-3、上市 五-4-5~8 / 五-10-3~5 等），库目录 `mapping_disagreements` 两版均为 0
- [x] 8. 回归：读取层 / 映射 / V186 / 端到端测试不回退（R2.4）
  - 合并附注相关 12 个测试文件 250 passed；`test_consol_note_formulas::test_seed_counts_on_real_templates` 2 例与 `test_consol_note_headers` 147 例失败在 HEAD 干净检出同样失败（预存，非本 spec）
  - 真库只读对比（9 个项目 × 映射章节 3228 组，新旧代码各跑一次）：2554 组完全相同；9 组换表全是 五-4-2 / 五-4-3 纠正；31 组不再取表（30 组是章节映射错位时唯一一张不相干的表、本来一列都对不上，1 组旧模板表无数）；76 个合并章节新认到表；没有任何原有非零数丢失
  - 进程内变异：两路名字证据改回子表名优先 / 去掉裸「续：」过滤 / 去掉旧单表补表头，各自打红

## Phase 3 重新汇总 = 子树逐节点更新 + 自下而上汇总

- [x] 9. 合计 / 小计重算抽成 `consol_note_table_totals.recompute_total_rows`，apply 改用（不改行为）
  - 勘误：实际抽成 `build_table_rows`（骨架行 + 逐列金额 → 写入行，含合计 / 小计重算与手工 / 锁定格保留），apply 与子树汇总共用；另有 `to_decimal` / `fmt_amount` / `existing_cell`
  - 偏离「不改行为」一处（缺陷修复）：手工 / 锁定格在来源这一格没数时原来会被清空，现在一律保留（来源有数时才回报「保留了手工值」）；`tests/test_consol_note_table_totals.py` 4 例，变异「恢复旧清空」「小计不截断」各自打红
- [x] 10. `apply_detail_refresh` 增加可选 `scope_leaves` / `template_type`（编排传入，免逐次建树）
- [x] 11. 编排服务 `consol_note_subtree_reaggregate.py`：后序遍历、章节级 SAVEPOINT、叶子拉数 / 差额公式 / 汇总求和、跳过原因、公式值快照、共用推送锁（R3.1~R3.3）
  - 树 / 模板口径 / 绑定 / 映射状态 / 各章节有效公式只装载一次；计算口径（差额与快照用）只在有公式时装载，装载失败（如合并范围未确认 409）只让差额与快照不可用，拉数与汇总照常
  - 叶子：章节未绑定明细模板 / 没有单体项目 / 未确认映射 / 映射已变 / 已排除 → 按原因跳过（后三类里需要用户处理的列入 `pending_entities`），不调 apply（只有 stale 绑定时 apply 会写一张空表）
  - 汇总：来源判定 `record_write_source`（有标记用标记；没有标记但有公式值快照 = 来源标记出现之前的「按公式填入」）；非差额下级来源是 `formula` 不计入；映射里排除的企业旧数不计入；没有绑定的章节骨架用合并附注模板行（行类型与「从来源建议模板」同一判定 `_row_type`，表内嵌子表头行原样保留，国企 五-10-5 / 五-16-6）；根节点只有项目级兼容行时先复制再写
- [x] 12. 端点 `reaggregate` 改走编排，响应兼容 + 逐节点摘要（R3.4）
  - 新增 `mode` / `nodes` / `pending_entities`；`node_key` 回填所选节点（不传 = 根合并节点，不再写项目级兼容行，`legacy_null` 恒 False）；复用路由校验节点时建的树
- [x] 13. `fill_by_formula` / `fill_note_sections` 增加 `preserve_pulled`，推送后刷新与试算表事件处理器传入（R3.5）
  - 快照构造 / 比较 / 来源判定 / 章节有效公式收成公式服务公共函数（`formula_snapshot` / `snapshot_changed` / `record_write_source` / `section_formulas`），按钮与后台同一份；保留的章节 `kept_pulled` 不计入 `sections_updated`，推送统计与事件结果单列
  - 推送先把全部附注行标待更新再刷新：保留的拉数行推送后保持「待更新」（差额变了汇总就过期，由用户重新汇总）；试算表事件只在公式值变化时标
- [x] 14. 测试：SQLite 三层树端到端 + 后台不覆盖 + 端点；关键分支变异打红
  - `tests/services/test_consol_note_subtree_reaggregate.py` 14 例（全表 SQLite、生产函数全链：单体附注 → 建议模板 → 绑定 → 预览 → 确认 → 子树汇总；试算表 1002 故意与附注不同，证明个别数取自单体附注）+ 处理器 1 例 + 合计 4 例
  - 真库探针补出一条规则：差额没算出（合并范围未确认 = 计算门 409）时上级还在汇总、并标「不过期」⇒ 改为下级出错则上级本章不汇总、逐级向上；按原因跳过的下级仍用已保存数（`test_failed_elim_stops_aggregation_upward_but_not_the_pulls`）
  - 干净 worktree 磁盘变异 20 个全部打红（后序 / 公式下级排除 / 差额计入 / 只有差额不写 / 手工格 / 整节锁定 / 快照 / 待确认 / 章节 SAVEPOINT / 子表头行 / 排除企业 / preserve 失效 / 快照比较 / 无标记来源判定 / 推送与事件两处传参 / 手工格旧清空 / 小计截断 / 下级出错仍汇总 / 出错不向上传），逐字节恢复校验
  - 回归：见任务 18（干净 worktree 终验 540 passed）
- [x] 15. 真库事务回滚探针：【测试】集团子树汇总金额核对后回滚
  - 现有【测试】集团都不合用（公式同步集团子企业没有附注；附注批量集团在回收站且附注全空），改为在一个事务里新建【测试】集团 + 两家子企业，复制两家真实单体项目（重药控股安徽 / 重庆和平药房）的附注与试算表（真实项目的行只读），按生产链路确认合并范围、建明细模板、确认映射、录一笔抵销（贷 银行存款 1000）
  - 三个章节（五-1-1 有差额公式、五-91-4、五-95-4）：叶子 = 单体附注、合并 = Σ 直接下级 + 差额、合计 = 本表数据行之和，独立核对 0 处不符；差额节点 银行存款 -1000.00；后台按公式刷新三章都 `kept_pulled`、未标过期、来源标记不变
  - 全量 321 章节 × 5 节点 4.2 秒；回滚后探针项目 0 个、库内子树汇总行 0 行
  - 另跑原「附注批量」集团（事务内临时恢复）：合并范围未确认 ⇒ 57 个有公式章节差额失败、原因写明，未绑定章节全部按原因跳过，回滚后数据与删除状态不变

## Phase 4 前端

- [x] 16. `ConsolNoteTab.vue` 按钮说明与完成提示按节点汇报；`consolidationApi` 响应类型；`ConsolFormulaManagementPanel.vue` 取数路径说明（R3.6）
  - 提示文案收成纯函数 `consolNoteView.reaggregateSummary`（写入节点数 + 拉数 / 差额 / 汇总分布、所选节点没写上的原因、待确认映射企业、出错处；旧响应没有 `nodes` 时按章节计数）；当前章节重读完成后才提示（有待确认 / 未写上 / 出错用告警）
  - 来源标签新增「🔄 子树汇总（N 个下级 + 差额）」（`_subtree_child_count` 只数计入了数的非差额下级）；类型 `ConsolNoteReaggregateResult` / `ConsolNoteReaggregateNode` / `ConsolNoteReaggregateAction`
  - `ConsolidationIndex.vue`（并发会话改动中）未改：它只读 `sections_updated` / `errors`，响应字段兼容
- [x] 17. vitest / ESLint / 单区域 vue-tsc + TS2322 变异
  - vitest：`consolNoteView.spec.ts` 新增 3 例 + 接线守卫，`ConsolNoteTab.spec.ts` 新增 1 例（真组件：POST 体、重读完成后的成功 / 告警文案）；合并 + 公式组件目录 72 个文件里 2 个失败（`ConsolTrialBalanceTab` / `ConsolReportBreakdownView` 6 例，请求参数多了 `signal`），在干净 worktree 把 `consolidationApi.ts` 换回 HEAD 版同样失败（预存，非本 spec）
  - ESLint 0 error（3 条 warning 是原有代码行）；单区域 vue-tsc（ConsolNoteTab / consolNoteView / consolidationApi / ConsolFormulaManagementPanel 及其依赖）0 错误，往 ts 与 vue 各注入一处 number = string 均报 TS2322

## Phase 5 收尾

- [x] 18. 行数门、design 勘误、INDEX / memory；干净 worktree 跑要提交的树；只提交本会话文件（不推送）
  - 行数门：本 spec 改动的 27 个代码 / 测试文件全过（`consol_note_formula_service.py` 1500 行在白名单基线 1470 的 +5% 内；`ConsolNoteTab.vue` 在基线内）
  - design §13 记实施偏离、实测数字、范围外 / 待拍板与 ADR-RA-004；INDEX 本 spec 一行、memory 合并附注拉数小节更新（memory 295 行）
  - 干净 worktree（HEAD `1e1d73f64` + 本会话 35 个文件 = 要提交的树；提交前 HEAD 被并发会话前移两次，两者文件零交集，按新 HEAD 重跑）：后端合并附注 / 推送相关 32 个测试文件 540 passed，3 例失败在 HEAD 同样失败；前端合并 + 公式组件目录 815 passed，6 例失败在 HEAD 同样失败；库目录 `--check` 一致，映射生成器重跑字节不变
  - 另跑鉴权 / lazy import 守卫：鉴权 3 个文件全过；`test_lazy_import_resolvability` 2 例红在 `ai_content.py` / `formula_preloader.py` / `note_section_pairing.py` 的 import（不在本 spec 文件里，HEAD 预存）

## Phase 6 其余表头识别点改调标题行库（R5，2026-10-22 用户追加）

- [x] 19. 标题行库新增逐列角色（`period_side` / `movement_kind` / `column_role` / `column_roles`）与变动表勾稽列（`rollforward_columns` / `RollForward`），变动词与余额计量词进词表，库目录重生成（R5.2）
  - 变动词命中多个取最长、同长按 增加 → 减少 → 不定；「计提减值准备」进方向不定（四版种子逐列核对：只影响 10 列，全是这一种）；期末 / 期初一侧的列不算变动
  - 勾稽列：期初 / 期末取余额列各唯一的一对，否则同一计量各唯一的一对；变动列只认两者之间的列，之间其余金额列为方向不定
  - 库目录重生成只有 `vocabulary_sha1` 一行变化
- [x] 20. `consol_note_sections`：删 `_resolve_value_columns` 与全部期间 / 变动关键词，4 个调用点改用标题行库（`_header_table` 选模板 / 平表头，`_column_view` 给列名与角色）；勾稽改用 `rollforward_columns`，方向不定列有数的行跳过；试算表校验列名取展示路径（R5.1）
  - 真库已保存合并附注 4496 行表头与国企模板逐字相同 ⇒ 审核全走模板多级表头
- [x] 21. 测试：角色 / 勾稽列单元测试 + 路由三处真实调用（全审 / 单表审核 / 下级汇总兜底）+ 变异；新旧逐列对比并归类（R5.5，design §14.4）
  - `test_note_table_header_library.py` +37 例；`test_consol_note_section_column_roles.py` 20 例（替换只测已删函数的 `test_consol_note_refresh_column_resolve.py`）
  - 干净 worktree（HEAD `cb320d128` + 本轮文件）19 个磁盘变异全打红；合并附注 / 推送 / 标题行库 33 个测试文件 568 passed，152 例失败在 HEAD 同样失败（`test_consol_note_headers.py` 147、`test_seed_counts_on_real_templates` ×2、`test_approve_push_revoke_roundtrip`、`test_note_standalone_consolidated_only_scope.py` ×2）
- [ ] 22. `note_writer.legacy_value_keys` 改调标题行库（R5.3，与用户确认接手方式后做）
- [x] 23. 收尾：行数门、干净 worktree 跑要提交的树、只提交本会话文件
  - 行数门过（路由 1157 → 1032 行，白名单基线 1116）；库目录 `--check` 一致，映射生成器重跑字节不变；鉴权基线全过，lazy import 2 例红与 HEAD 相同（`consol_lock_service` / `disclosure_source` 不存在，非本轮文件）
  - 私有索引只提交本轮 12 个文件（含删除旧测试）；note_writer 未动（task 22）

## Phase 7 V2 下线 / 种子表头 / 核销 / 单元格汇总 / 取数列 / 上年导入（R6，2026-10-22 用户追加）

- [x] 24. V2 下线（后端）：删 `consol_disclosure_service` / `note_consol_drilldown_service` / `consol_cross_template_service` / mock CSV / V2 专用汇总函数与 `resolve_consol_aggregation` / `CONSOL_CROSS_TEMPLATE_ENABLED`；路由删 create / get / integrate / save / consol-breakdown；级联刷新第 6 步改调推送同一 `_refresh_notes`（同一把锁，partial / failed 记错误）；灰度开关注释改正；只测已删代码的测试删除、其余改（R6.1）
  - 另删两处同族死代码：`consol_report_service` 里无调用方的 7 骨架附注生成器（构造的字段与 schema 不符）、只给 V2 用的 `ConsolDisclosureRow / ConsolDisclosureSection` 与 `dataset_query.bind_to_active_dataset_sync`；`consol_note_aggregation_service` 只剩 `validate_lineage_dag`；单元格取数源 9 → 8（顺带修好 HEAD 上一直红的 `test_binding_json_valid_sources_match`）
  - 一键刷新第 6 步 = `consol_push_service.refresh_notes_exclusive`（进程锁 + 事务级咨询锁 + `_refresh_notes`）；第 4 / 5 / 6 步失败先回滚本步（PG 上失败语句让事务 aborted，原来会连带后续步骤失败）
  - 端点台账（coverage ledger、两份鉴权清册、领域边界债务基线）按差量删本次端点 / 依赖边的条目，先核对计数与条目一致再改；三处历史超 800 行未登记的文件（取数源 / 模板差异 / 离线导出，本次行数只降不增）登记白名单
- [x] 25. V2 下线（前端）：删 `useNoteAggregation` / `ConsolNoteTreeEnhanced` / 附注编辑器「🔗 查看合并明细」/ 合并明细弹窗附注模式 / 单元格取数源「合并汇总」选项 / 死 API 函数与 apiPaths；`components.d.ts`、领域边界基线同步；vitest / ESLint / 单区域 vue-tsc（R6.1）
  - `ConsolBreakdownDialog` 只留报表模式（去掉 `source` 属性）；`consolidationApi` 删 9 个调已下线端点的函数与只给它们用的 7 个类型；两个 e2e 用例（V2 生成、附注右键合并明细）删除
  - vitest：合并组件目录 + 附注编辑器 / 报表相关 65 个文件 838 passed，6 例失败与 HEAD 相同（`ConsolTrialBalanceTab` / `ConsolReportBreakdownView` 请求参数多了 `signal`）；ESLint 0 error；单区域 vue-tsc 与 HEAD 同一配置的错误集合逐条对比无新增，ts / vue 各注入一处 number = string 均报 TS2322
- [x] 26. 残留扫描（全仓 grep 已删符号 / 端点 / 配置）+ 相关后端套件 + lazy import / 鉴权守卫；单独提交
  - 残留只剩：报表穿透（保留）、迁移 V039 注释（不可改）、冻结的影响清单基线、断言「已下线」的测试与说明
  - 干净 worktree（HEAD `1d8600593` + 本批 64 个文件）：后端 52 个测试文件 1049 passed，89 failed + 8 error 全部在 HEAD 同样失败（附注编辑门端点 / 鉴权清册 `--check` / `_assert_project_edit` 不存在 / lazy import 2 / 种子计数 2 / 推送往返），HEAD 多红的 1 例被本批修好
- [x] 27. 「核销」= 减少：词表 + 库测试 + 库目录重生成（R6.4）
  - 词表 `movement_words.decrease` 加「核销」；`test_write_off_is_a_decrease`（期末 = 期初 + 计提 − 转回 − 核销）与最长词用例；库目录随 29 重生成（`--check` 一致）
- [x] 28. `/aggregate` 只从下级附注取数：删试算表兜底，响应 `missing_children`，前端提示；测试改为断言不取试算表（R6.5）
  - 后端用例断言 `tb_loader.assert_not_called()`、`missing_children` 点名；前端 `cellAggregateSummary` 四态（成功 / 只是这一格为空 / 有下级没附注 / 汇总失败）+ 接线守卫；合并组件目录 vitest 25 个文件 300 passed，6 例失败与 HEAD 相同（`ConsolTrialBalanceTab` / `ConsolReportBreakdownView` 请求参数多了 `signal`）；ESLint 0 error（本批新增 0 warning）；单区域 vue-tsc 0 error，ts / vue 探针各报 TS2322
- [x] 29. 种子多级表头修复：一次性脚本按 Word 替换 / 退回数据行；删 `_fix_missing_multi_header.py`；守卫测试（期望来自 Word）；Word 同步 `--check` 前后对比、库目录与映射重生成并逐条审（R6.3）
  - 表头行数判定 / 表头空白格归一改在平台 `note_word_table` 一处，Word 同步工具改调它；17 张换表头、12 张退回数据行、1 张人工定（上市 六-1-2）、全部多级表头表平表头改全路径（国企 92 / 上市 118）；国企 五-11-2 不修（同步工具按标记推章节号错一节，另立 spec）、13 张列宽不符待人工核对（design §15.3）
  - 守卫 `test_consol_note_seed_header_repair.py` 80 例（测试时解析 Word；1 例单体版无同标记表跳过）；标题行库 / 目录测试 + 守卫共 209 passed；变异 15 条全红（基线全绿）
  - 66 个相关测试文件：基线树 151 失败、本批 152 失败，多出的 1 例（推送整体状态）单跑 / 同序前缀 / 整文件重跑均过；Word 同步 dry-run 合并模板 Phase 1 只剩国企 五-11-2；修复脚本在基线种子上重放，产物与落盘种子换行归一后逐字节相同，之后删除（design §15.8）
- [x] 30. `value_column` 改调标题行库（净额 → 账面价值、毛额 → 账面余额 / 公允价值、纯期间优先、分不出写原因）；两版种子新旧逐格对比归类；真库种子与已填数据影响核对；测试 + 变异（R6.7）
  - 逐格对比（真库报表配置）：国企 60 → 55（五-23-1 固定资产净额改种账面价值列，5 格错种不再种，五-29-1 随任务 29 移到期末余额）、上市 52 → 53；补「空列名不种」「毛额行同期间有账面价值只认账面余额」（词表 `gross_measures`）；真库国企 60 条全是自动种子，重启后按新规则删 7 增 2，已保存数据只在测试项目、旧位置是 0.00 / 占位符，不迁移（design §15.8）
  - `SEED_COUNTS` 2026-10-10 起一直红：临时 worktree 逐提交跑旧代码归因到 `5914e315b`（国企表名偏移同步 + 上市续表识别），基线改为实测值并注明；`test_consol_note_formulas` / `test_consol_note_column_groups` 53 passed，变异 11 条全红；库目录随词表重生成（只变 `vocabulary_sha1`）
- [x] 31. 上年导入解析：`note_word_table` 数据行取值；按块（含内容控件）切节、表名；单元测试（分组 / 续表 / 内容控件 / 上年年末）（R6.6）
  - `iter_blocks` 挪进 `note_word_table` 公开（Word 树核对改调它）、`WordTable.rows` 按逻辑列取数据行；`parse_prior_docx` 标题与上传解析同一读法、表名候选 = 表前全部段落（展示取短段落）、列键走标题行库新拆的 `path_keys`
  - 编辑器「导出 Word」三级标题原是正文样式（目录域也是空的）⇒ 上年导入 / 上传附注文档一个标题都认不出：`note_word_exporter` 设大纲级别，往返用例钉住（真库重药安徽导出 → 和平：章节对上 0 → 161）
- [x] 32. 上年导入规划 / 写入服务（标题行库对列、按表名 + 结构选表、行名 + 同名序号对行、状态与原因）；预览 / 写入端点（sha256 校验）；原端点只写自动认出的；测试（R6.6）
  - `note_prior_year_plan`（纯函数）+ 服务 `import_from_docx(mode=auto|preview|apply)`，同一端点加 `mode`，apply 重传文件校验 sha256、逐项校验确认；补三条：精确命中优先于弱规则（共享 `match_columns`，目录 `--check` 不变）、主表按「（续：期初数）」续表补对侧期间（`fill_main_period` 从合并选表抽出共用）、对不上列的候选不给可填格数
  - 真库只读核对（和平 ← 重药安徽）：编辑器导出 自动 82 / 待确认 62 / 上年没有 9，交付件 30 / 35 / 88；自动表逐张核对无认错（design §15.8）；后端用例 + 变异 9 条全红
- [x] 33. 前端 `NotePriorYearImportDialog.vue`（预览 → 逐表确认 / 改选 / 逐列指定 → 写入 → 刷新目录）+ apiPaths + 附注编辑器入口（守行数上限）；vitest / ESLint / 单区域 vue-tsc（R6.6）
  - `notePriorYearImport.ts` + 弹窗，挂 `DisclosureNoteContentTools`（同一门禁），编辑器菜单加一项（3265 行 / 上限 3281）；浏览器实测和平 2025（写入请求页面拦截应答、库里 0 行被写）
  - 同批修编辑器模板 17 处 `noteEdit.*` 未解包（`40882b2b1` 起写入口门禁恒真、「只读副本」人人可见）、已删的 `isEqcrRole`、恒假的归档判定，守卫从返回类型读 ref 字段；vitest 24 个文件 382 passed，ESLint 0 error，单区域 vue-tsc 0 error（探针报 TS2345 / TS2322），变异 17 条全红
- [x] 34. 收尾：design §15 实施记录、INDEX / memory；干净 worktree 跑要提交的树；只提交本会话文件；fetch 后推送 `spec/disclosure-note-doc-upload-and-batch-fill` 并 `ls-remote` 核对；清理探针
  - design §15.8 补任务 31~33 实施记录（规则补充、真库只读核对、浏览器实测、编辑器模板缺陷、回归与变异）；INDEX 本 spec 行与 memory 按现状改写（memory 300 行）
  - R6 四批提交（bfa0048ab / 70e718922 / 3256fc491 / e3176af66）都在干净 worktree 跑要提交的树、私有索引只提交本会话文件；并发会话把本会话文件 `git add` 进共享索引一次，已退回；推送前 fetch、推送后 `ls-remote` 核对
  - 临时引用 7 个、基线 worktree 与 2 个过期登记、单区域 tsconfig 4 个、类型探针、浏览器截图 / 上年 Word 副本已清；推送用的 worktree 与工作目录在最后一次推送后删除

## Phase 8 R7（2026-10-22 用户追加：自动刷新开关 / 导入合并锁 / 占位正文 / 同义词 / 章节重对齐 / 列宽 / 表头用例 / 勾稽）

批 8a（互不依赖的小项）

- [x] 35. 自动刷新开关：`ConsolNoteAutoRefreshSwitch.vue` + apiPaths + 合并附注工具栏挂载；vitest（读 / 写 / 失败回滚 / 全局开启不可改 / 403 原因）；ESLint / 单区域 vue-tsc；浏览器实测（R7.1，design §16.1）
  - `before-change` 里发请求、恒返回 false，显示只跟后端返回的状态走（首版「成功才返回 true」的失败分支变异是等价变异，改后用「失败也按请求值显示」钉住）；vitest 7 + 挂载 1；浏览器实测【测试】公式同步集团 2025 开 / 关各一次，请求体与库里开关值一致，已恢复为关
- [x] 36. 上年导入 / 继承挂合并锁（`consol_lock=True`）；附注写端点清册、edit 级影响清单、门禁配方与端点用例同步；锁定 423 用例 + 变异（R7.2，§16.2）
  - 清册两份按差量各改 2 处（生成器 `--check` 余下差异都不涉及本批）；冻结合并锁集合 13 → 15；`cross-references/update` 同类未改（需求 6.6 既定口径），已登记
- [x] 37. `note_deliverable_filter.is_placeholder_text`；上年导入（写入与预览计数）、上年继承跳过占位正文；用例 + 变异（R7.3，§16.3）
  - 复用 `_NO_BUSINESS_RE` + `note_text_plain`（HTML 正文同口径）；判定 17 例 + 导入 / 继承端点 2 例
- [x] 38. 词表同义「账面金额 → 账面余额」；库目录重生成；库测试；真库只读核对和平 ← 重药安徽（R7.4，§16.4）
  - 核实：同义词自 `2ffe0c9b7`（标题行库首个提交）就在词表里，§15.8 那句「对不上、不加同义词」是错的（已在 §16.9 勘误）；真库只读复核两种导出 八、5「（续：期初数）」三列都自动认到；补上年导入层用例，词表 / 库目录不变
- [ ] 39. 批 8a 收尾：行数门、干净 worktree 跑要提交的树、私有索引只提交本批文件、推送

批 8b（国企章节编号重对齐）

- [ ] 40. Word 同步工具身份校验：表信息带节号 / 节标题；Phase 1 / 2 / 6 / 标题漂移按节标题 + 行名核对，对不上不写并报出；新增 / 重建表共用平台构建（平表头展示全路径）；上市尾部「Word 标记缺节」登记（失效即报）；守卫 + 变异（R7.6，§16.6）
- [ ] 41. 一次性重排：国企第五章按 Word 位置重排（留哪条、结构取谁、表名、父章节规则见 §16.6）；上市尾部恢复 5 个表名、删 9 张重复表；同步工具重跑前后对比；脚本用完即删（R7.6）
- [ ] 42. 种子 ↔ Word 身份守卫：国企第五章 221 张表逐张（列数、逐列表头路径、行名、父章节、表名）；上市第五章（尾部 五、70 下 20 张按表名定位）；变异（R7.6）
- [ ] 43. 引用随改：勾稽规则 peer、续表标记；明细映射与标题行库目录重生成并逐条审；R6.3 守卫章节号、公式种子计数 / 章节断言、J1 引用、其余测试里的旧章节号（R7.6）
- [ ] 44. 已保存数据迁移工具 `backend/scripts/migrate/remap_consol_note_section_ids.py`（只读演练 / `--apply` 先备份）；测试；在两个测试项目上执行并逐行核对（R7.6）
- [ ] 45. 批 8b 收尾：回归（基线 vs 本批逐条）、干净 worktree、私有索引提交、推送

批 8c（依赖正确章节号）

- [ ] 46. 列宽：两版合并表与明细映射选中的单体表逐列比对（标题行库语义键），逐张归因，能统一的以单体侧为准改种子并迁移已保存数据，不能统一的写明原因（R7.7，§16.7）
- [ ] 47. `test_consol_note_headers.py` 按 A~F 类重写；章节详情接口返回 `template_type`；暴露的种子缺陷按 Word 修（R7.8，§16.8）
- [ ] 48. 勾稽读取改节点作用域：`check_note_cross_rules(node_key)`、端点 `node_key` + 项目实际口径、前端传当前节点；用例（真表）+ 变异（R7.5，§16.5）
- [ ] 49. 跨表 / 跨期规则逐条核对：说明成立的按标题行库语义改对两侧单元格，不成立的删除并记理由；守卫（两侧语义键可比、行存在、说明与章节一致）（R7.5）
- [ ] 50. 收尾：design §16 实施记录、INDEX / memory；干净 worktree 回归；私有索引提交、推送、`ls-remote` 核对；清理探针与临时文件
