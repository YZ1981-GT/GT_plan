# 附注表格结构、预设公式与合并拉数收口 — 设计

## 1. 现状实证（2026-10-31，探针在 `tmp_note_table_closure/probes/`）

| 事实 | 证据 |
|---|---|
| 三道模板门禁绿；D2 单体 32 张表与底稿逐表配对，白名单外差异 0 | Word 树 `--check`、`test_note_template_workpaper_alignment` |
| 国企 Word 子表标题是字面「（1）…（6）」（`numId=0` 去编号），上市 Word 子表标题样式 96 继承 heading 3 自动编号「（%3）」 | p03 / p04 |
| 单体按底稿：国企账龄单级 6 档 + 小计 / 减：坏账准备 / 合计；合并按 Word：期末数 / 期初数 × 账面余额 / 坏账准备、4 档 | p01 / p03 |
| 冒号结尾标题行当明细：「资产小计 = cell(资产：)」等，全模板 35 种标题 / 144 处 | p02 §1 |
| 上市账龄等 6 张表嵌套小计整表判不准（18 个合计行无公式） | p02 §2 |
| 纵向变动表 13 张：期末余额 = 全部行之和（转回 / 核销当加项） | p02 §3 |
| 「账龄 / 期末账龄」列判为金额列 18 处 | p02 §4 |
| 可执行预设只有合计与账面价值；比例 / 损失率无公式 | `note_formula_tables.table_preset_formulas` |
| 读时增强：期间层按表名挂、不看结构；泄漏名绕过首列校验按位置串表 | `note_period_layout.attach_display_layout`、`note_table_enrichment._align_table_to_template` |
| 推送只写主表、推送后附注公式不跑（刷新链路除外） | `formula_push.engine.notify_committed`、`note_workpaper_pull_service._apply_note_formulas` 只被 pull 调 |
| 公式管理附注节点把文字版预设（不执行）与可执行公式混排 | `noteScopeTargeting.buildNoteFormulaRows` + `mergeNoteUserFormulaRows` |
| 合并：【注意】提示让行名对不上、合计少算；账龄 6 档→4 档只能逐企业手工映射；来源独有行堆到合计前；单体账龄「合计」（净额）落到合并账面余额列 | 子代理逐表实测 + `consol_note_detail_source_service.suggest_template_for_section` |
| 合并跨口径（国企集团含上市子公司）按合并口径子表名选表：读不到 / 选错表 / 转置表 0 列仍报 found | `load_source_tables` 只传 `standalone_table_name` |
| 映射弹窗：建议目标已填的待确认行可一键确认 | `ConsolNoteMappingDialog.vue` 按钮 `:disabled="pendingCount > 0 && !allMapped"` |
| D2 四张逐项表依赖底稿里手点「带入」，离屏同步不带 | `useD2DisclosureNote.import*`；`d2HeadlessDisclosure` 只 setup / seed / build |
| 真库残留：和平药房 八、5 坏账变动表合计 = 应收账款余额（10-25 已删规则 `D2.note.subtable_7` 写入） | `formula_push_state` 只读查询 |

## 2. 架构裁决

- ADR-1 合计构成仍是唯一判定（后端 `note_total_terms` ⇄ 前端 `noteTotalTerms` ⇄ golden）。新增行类 `title`（冒号标题，等同 skip）；
  嵌套小计只认「分项小计在前、唯一「小计」在后、至多一个合计在最后」这一形态；纵向变动表期末行回原因不回构成。
- ADR-2 比例 / 损失率是「派生列」：单体走预设公式（类型 `ratio`，带 `requires` 分子格，执行器分子空即跳过）；合并在 `build_note_rows`
  末尾按同一列判定派生。判定函数一处（`note_formula_ratios.ratio_plans`），单体 / 合并共用。
- ADR-3 推送后自动运算不改推送引擎（`engine.py` 已超行数门）：新增 `formula_push/note_followup.py`，由推送的四个调用方
  （事件、公式配置传播、推送页、采纳公式值）在提交后调用；刷新链路不调（自己最后跑公式）。执行器对存储表上推送拥有的格跳过预设公式，
  避免推送后自动运算把审定数合计改成明细之和。
- ADR-4 合并跨口径：映射生成器为每张合并表另算另一口径单体章节（同章节标题）的子表名，存 `standalone_table_name_by_std`；运行时按来源
  项目口径取，缺省回退原字段。
- ADR-5 D2 逐项表派生在 `buildSnapshot()` 内完成（Tab 与离屏共用），不落底稿；用户一旦录入任一行即以用户数据为准。

## 3. 模块改动

| 区域 | 文件 | 改动 |
|---|---|---|
| R1 | `note_total_terms.py`、`noteTotalTerms.ts`、`note_table_header_vocabulary.json`（`text_pattern` 加 `账龄$`）、golden、标题行库 | 见 ADR-1 |
| R2 | 新 `note_formula_ratios.py`；`note_formula_tables.table_preset_formulas` 调用；`note_formula_generator.execute_note_formulas` 认 `requires`；`consol_note_table_totals.build_note_rows` 新参数 `table` | 见 ADR-2 |
| R3 | `note_period_layout.attach_display_layout`（自身有期间层不挂 top）；`note_table_enrichment._align_table_to_template`（去泄漏名放行、位置兜底须列数相同） | |
| R4 | 新 `formula_push/note_followup.py`；`triggers.py`、`formula_settings/propagation.py`、`formula_push/panel.py`、`routers/formula_push.py` 提交后调用；新 `note_formula_push_guard.py` 被执行器调用；`note_cell_sources._decide` 推送步骤带取数口径 | 见 ADR-3 |
| R5 | `noteScopeTargeting.ts`（文字预设标「审核要点」、排在可执行公式之后）；`note_settings.list_section` 回 `preset_notes`；公式管理弹窗显示 | `FormulaManagerDialog.vue` 净增行受白名单约束 |
| R6 | `consol_note_detail_suggest`（【】去除、账龄区间）；`consol_note_row_groups`、`row_correspondence` 同键；`consol_note_detail_source_service`（来源独有行位置、跨口径子表名）；`consol_note_standalone_reader`（账龄折叠、零列报因）；`note_row_label_aliases.json`；映射生成器；映射弹窗 | 见 ADR-4 |
| R7 | `useD2DisclosureNote.buildSnapshot` | 见 ADR-5 |
| R8 | 只读脚本 `backend/scripts/analyze/report_note_orphan_push_cells.py` | 写库另行放行 |

## 4. 验证

- 后端：`test_note_total_terms`（含 golden `--check`）、附注公式 / 预设 / 执行器、读时增强、合并读取 / 建议 / apply / 汇总、标题行库 `--check`、
  Word 树 `--check`、模板↔底稿门禁、推送 triggers 相关既有用例；新用例逐条覆盖 R1~R7，并做磁盘变异（每条判据至少一个变异打红）。
- 前端：`noteTotalTerms.spec`、`noteScopeTargeting` 相关、`ConsolNoteMappingDialog.spec`、D2 披露 / 离屏用例。
- 浏览器：`http://127.0.0.1:3030` 用【测试】项目看 D2 表头与公式管理；合并写入受测试数据阻塞时如实登记。
- 回归口径：与同提交的干净 HEAD worktree 逐节点比对，新增失败 0。

## 4.1 实测结果（交付时现算）

| 项 | 结果 |
|---|---|
| 门禁 `--check` | 标题行库 + 对照表一致；`note_total_terms_golden.json` 与现算一致；四版 Word 树一致（白名单除外） |
| 合并拉数待人工确认行（探针 `p12_pull_flow`，逐表用同口径 / 跨口径单体模板合成来源） | 国企←国企 35 → 1；上市←上市 11 → 4；国企←上市 80 → 66；上市←国企 160 → 124 |
| 合并明细模板多出的行（来源独有行） | 国企←国企 88 → 69；上市←上市 97 → 78 |
| 孤儿推送格（真库只读清点） | 规则清单 268 条、附注域推送状态 333 行，规则已不存在的 18 行（4 行值非零，全在和平药房 `D2.note.subtable_0 / _7`） |
| 后端用例 | 新 `test_consol_note_pull_r6.py` 30 例；合并 / 附注 / 公式相关选集在候选 worktree 与干净 HEAD worktree 逐节点比对 |
| 前端用例 | `components/formula` 612 passed、`components/consolidation` 431 passed、D2 相关 28 passed、`vueSfcSyntax` 4 passed |

🔴 顺带修 HEAD 预存缺陷（commit `6f4c5a54a`「内网 http 非安全上下文兼容」引入，与本 spec 无关但挡住全部浏览器验收）：
18 个文件 22 处把 `navigator.clipboard.*` 换成 `await copyText(…)` / `await copyRichText(…)` 却没给函数加 `async`，另有 5 个 `.ts`
被 `crypto.randomUUID()` → `newUuid()` 的批量替换弄坏模板字面量 ⇒ 整份 SFC / 模块编译失败，附注编辑器、试算表、合并入口、
合并附注 Tab、查账穿透、高级查询整页打不开。门禁 `vueSfcSyntax.spec.ts` 两头漏：解析脚本块时开着
`allowAwaitOutsideFunction`（为放行 `<script setup>` 顶层 await，顺带放过同步函数里的 await），且只扫 `.vue` 不扫 `.ts`。
已改为「解析仍开该开关 + 走 AST 判定每个 `AwaitExpression` 的最近一层函数必须 async」并把 `.ts` 纳入扫描，配变异自检。

## 5. 不做 / 登记

- 推送规则 `D2.note.main` 在账龄表多合计行时不兜底（10-31 起）⇒ 账龄表主表金额来自底稿披露；改规则需动 `bindings/*`（他会话在改），登记后续。
- 续表期间守卫（推送引擎）：现存子表规则无续表目标，潜在风险登记，不动 `engine.py`。
- 写真库修复见 R8，等用户放行。
- 跨口径（国企集团含上市子企业）的「转置表」仍要人工确认：固定资产 / 无形资产 / 使用权资产这类表，合并按期间分列、单体按资产
  类别分列，金额列一列都对不上（已按 R6.6 报原因），同名行只能按位置配 —— 这是两版 Word 的结构差异，不是对应规则能消掉的。
- HEAD 干净检出整个后端起不来：`app/api/users.py`（已提交）import `app.services.project_creation_grant_service`（未提交），
  `app/routers/pm_dashboard.py` import `app.services.pm_service.BatchReviewService`（不存在）⇒ 任何 `from app.main import app`
  的用例在干净检出必 ImportError（本轮回归选集因此排除 10 个这类文件）。属他会话欠账，已如实登记，未代修。

## 6. 第二轮设计（R9~R14）

### 6.1 判定

- ADR-6 孤儿推送格只删状态行、不动格里的值：值由重跑附注公式按现行口径重算（合计按本表构成、比例按派生列）。
  直接清值会把用户可能已经认可的数抹掉；删状态行后这一格不再算「推送拥有」，预设公式 / 拉数就能接管。
  （否决「把值改成 0」：0 是一个有含义的金额，不能用它表示「没人维护」。）
- ADR-7 孤儿判定只有一份：`formula_push/orphan_states.py` 同时给清点脚本、修复脚本、推送回执用。
- ADR-8 账龄表兜底按「减：…准备」行切分语义：该行之前最近的汇总行是账面余额合计（科目余额对应它），
  最终合计是账面价值。没有「减：…准备」行的多合计表（分段合计）保持不兜底 —— 那种表的段由科目决定，引擎确实不知道。
- ADR-9 engine.py 已超行数门（HEAD 1042 / 白名单 951），接线前先把附注单元格写入的三个函数原样搬进
  `formula_push/note_push_cells.py`（不改逻辑、engine 继续用同名调用），把行数降到门禁内再改 —— 不抬白名单。
- ADR-10 跨口径转置只在两侧名字集合互为子集时启用（合并列名 ⊆ 单体行名、合并行名 ⊆ 单体列名），
  避免「只对上一两个名字就整表转置」；转不成照旧报原因。

### 6.2 模块改动

| 区域 | 文件 | 改动 |
|---|---|---|
| R9 | 新 `formula_push/orphan_states.py`；新 `backend/scripts/fix/purge_orphan_push_states.py`；`report_note_orphan_push_cells.py` 改调同一判定 | 见 ADR-6 / ADR-7 |
| R10 | `formula_push/panel.py`、`routers/formula_push.py` 回执带 `orphan_push_states`；`FormulaPushPanel.vue` 显示 | 不自动清 |
| R12 | 新 `formula_push/note_total_pick.py`；`formula_push/engine.py` 接线（先抽 `note_push_cells.py`） | 见 ADR-8 / ADR-9 |
| R13 | 新 `backend/tests/test_note_authority_source_parity.py`（后端 builder vs 前端载荷对拍，D2 样板 + 清单棘轮） | |
| R14 | `consol_note_standalone_reader`（转置读取）；新 `note_table_transpose.py` | 见 ADR-10 |
| R11 | `consol_note_detail_source_service.preview_detail_refresh` 回 `auto_confirmable_count` / `suggestion_count`；弹窗与合并附注页显示；章节级一键 | |

### 6.3 第二轮交付勘误（设计 vs 实施，以代码为准）

| 设计写的 | 实际落地 | 原因 |
|---|---|---|
| R12 新 `formula_push/note_total_pick.py` | 新 `formula_push/note_total_push.py` | 该模块不只放「挑合计行」，还搬进了 `find_total_by_label` / `push_note_cell` / `push_note_total` / `note_keep_reason` 与两张标签表，名字按职责取 |
| R12 先抽 `note_push_cells.py` 再接线（ADR-9） | 直接抽成 `note_total_push.py` 一个模块 | 同一批函数抽两次没必要；engine 1042→979 行（白名单 951 / 阈值 998），门禁内 |
| R13 新 `backend/tests/test_note_authority_source_parity.py`，后端 builder vs 前端载荷逐值相等 | 新 `audit-platform/frontend/src/components/workpaper/composables/__tests__/d2NoteSubtableContract.spec.ts`，**前端生产载荷 vs 模板 JSON 逐位对拍** | 现状调研改变了判定：D2 的附注表头**不来自后端 builder**，而是前端 `columns` 推送后经投影器渲染（见 `d2NoteSectionMap.ts` 文件头）⇒ 真正的权威源是 `note_template_{listed,soe}.json`，拿后端 builder 对拍会对错东西。且平台已有共享契约 helper（`_disclosureSubtableContract.helper.ts`），D2 是**唯一没接入的披露循环**，接入即得 P1~P6 |
| R11 回 `suggestion_count` | 回 `needs_review_count`（第一轮已落地） | 用户要看的是「还要人工看几行」，不是建议总数 |
| ADR-10 转置两条启用条件 | **四条**（加名字数量下限 ≥2、加「角色必须真对调」） | 见 §6.4 真库实证 |

### 6.4 R14 真库实证（2026-11-01）

扫描 `tmp_note_table_closure/probes/p26_transpose_scan.py`：合并侧权威模板 823 张表 × 真库 1590 张
单体附注表，按同一章节号两两判定，共 **10808 对**比较。

- **第一版判定命中 1 对，且是假阳**：五、28「商誉减值测试关键假设」的行名与列名**恰好是同一组参数**
  （毛利率 / 增长率 / 折现率；列头 `资产组/业务` 本该填实际资产组名）⇒ ①②同时成立但两边本来同口径，
  转置会把数据转错位。据此加条件 ④「合并列名 ∩ 单体列名 = ∅ 且 合并行名 ∩ 单体行名 = ∅」。
- **修后重扫命中 0**。

🔴 **诚实结论**：R14 在当前真库数据上**一次都不会触发**，属**预防性兜底**，未经真实转置数据验证。
零触发本身是好事（说明现有模板两侧口径一致），且代价只在「正常认列已经失败」的路径上。
真出现转置写法时它能把「整表拉不到数」变成「拉到数」，但这一条**没有真实样本可证**。

### 6.5 R13 抓到并修的真缺陷

1. **标签列头 4 处与模板不一致**（附注里显示的就是前端自编的列头）：上市账龄 `账龄`→`账 龄`、
   上市变动表 `项目`→`项 目`、上市核销金额表 `项目`→`项  目`（两个半角空格）、国企账龄 `账龄`→`账 龄`。
   根因：`d2NoteSectionMap.ts` 文件头偏差声明第 4 条「标签列列头取「账龄」「项目」」**已过期** ——
   模板经 R8.4 批 9b-1/9b-2 按底稿披露表补齐标签列列头后，前端没跟上。该声明已改为撤销说明。
2. **上市版 9 张单级表头表既无 `group` 也无 `flat`**（国企同类表早已标 `flat`）：后端 seed 路径的
   `_infer_groups_from_headers` 会按列名前缀反猜出凭空父表头（文件头自己记过「核销金额 / 核销原因」
   被反猜出「核销」的反例）⇒ 逐表补 `flat: true`。
3. **死代码**：国企「继续涉入」被 `put` 两次（第 ⑨ 段 `is_section` 一套行结构 + 第 ⑩ 段
   `row_type: 'header_label'` 一套），后者覆盖前者 ⇒ 前者整段不可达，且两套小计 label 还不同
   （`继续涉入形成的资产小计` vs `资产小计`）。全仓无消费方引用前者。已删，并加「同名表只许 put 一次」判据。

### 6.6 第二轮验证（交付时现算）

| 项 | 结果 |
|---|---|
| R9 真库修复 | 3 个项目共 18 行孤儿状态删除（备份 `backend/backups/orphan_push_states_20261101_*.json`），`still_orphan=0`，附注状态行 333→315 |
| R13 回归 | 前端 7 文件 **156 passed** |
| R13 变异 | `p23_r13_mutate.py` **6/6 全红** + 阴性对照绿 + 源文件 sha256 恢复校验 True |
| R11 回归 | 前端 2 文件 **28 passed** |
| R11 变异 | `p25_r11_mutate.py` **6/6 全红** + 阴性对照绿 |
| R14 回归 | 后端 7 文件 **125 passed** |
| R14 变异 | `p27_r14_mutate.py` **7/7 全红** + 阴性对照绿；另如实登记 1 条**不可由行为测试区分**的防御性冗余（见下） |
| 行数门禁 | `check_file_size.py --files-from -` 全部 exit 0（`engine.py` 979 / `d2NoteSectionMap.ts` 1002 / `ConsolNoteMappingDialog.vue` 484 / `consol_note_standalone_reader.py` 368 / `note_table_transpose.py` 143） |

### 6.7 第二轮方法论教训

1. **「两道门互相兜底」会让变异整批存活**：R14 接入层三道门（`_may_be_transposed` 前置门、
   `isinstance(consol_table, dict)` 类型门、`alt.rows and alt.matched_columns` 采纳门）首轮变异
   **全部存活**，共同根因是 `looks_transposed` 判定太严、把三道门的作用全兜住了。处置分三类：
   - 前置门与类型门改**白盒 spy 判据**（断言「门真的拦住了」，而不是断言结果）+ 补「`consol_table=None`
     且认列也失败」的用例（少了类型门就会在 `None` 上 AttributeError，这才测得到）；
   - 采纳门查明为**不可由行为测试区分**的防御性冗余（`looks_transposed` 命中时两项恒非空），
     在变异脚本 `UNDISTINGUISHABLE` 清单与源码注释里**如实登记，不假装有覆盖**。
2. **真库扫描是判据正确性的唯一试金石**：R14 的假阳（对称表）在合成夹具上永远不会出现 ——
   10808 对真实比较才暴露。凡「判定某种形态」的新规则，交付前必须拿真库全量跑一遍并逐条看命中。
3. **磁盘变异脚本读源码必须统一行尾**：`read_bytes().decode()` 不做 universal newline 转换，
   LF 锚点在 CRLF 文件上 **0 命中**，而脚本会把它报成 `SETUP-FAIL` 而不是「判据无效」——
   第一轮 p23 的 M1/M2/M4 就这样假装"锚点问题"溜过去一轮。
4. **「后端回了字段」≠「前端在用」**：R11 的 `auto_confirmable_count` 第一轮就已落地，但前端
   **0 处读取**。交付「回报某个指标」类需求时，判据必须落在**消费方**（界面显示 / 回执文案），
   不能停在「接口回了」。
5. **显示两个口径的同一指标必须对拍**：弹窗顶部比例用前端 `mappingRows` 自己的状态算（与表格、
   底部统计自洽），后端 count 只用来**对拍**、不一致就显式告警 —— 直接显示后端数字会在口径漂移时
   让用户看到两个打架的数，比看不到更糟。

### 6.8 第二轮回归：基线 vs 候选逐节点对比（R15）

**为什么必须建 worktree 对比**：交付期间远端又推了 `d17a1587a`（动 92 个文件、与本轮
`own_files` 重叠 13 个），主工作区 HEAD 落后 5 个提交 ⇒ 在陈旧磁盘上跑回归会得到一堆
与本轮无关的红（实测：主工作区 35 例失败，其中 22 例源于磁盘陈旧与别会话未提交文件）。

| 树 | 内容 |
|---|---|
| 基线 `tmp_note_table_closure/base_wt` | 最新远端 `d17a1587a` 干净检出 |
| 候选 `tmp_note_table_closure/cand_wt` | 基线 + 本轮我改过的 24 个文件（`engine.py` 用三方合并结果） |

`engine.py` 两侧都改过（远端把 `_load_states` / `_save_states` / `_record_failure` 抽进
`state_store.py` 并改了 stale 清除；本轮抽出 `note_total_push.py`）⇒ `git merge-file --diff3`
三方合并，**零冲突**，935 行（engine 白名单 951 / 阈值 998 内），两侧改动都在。

| 对比 | 基线 | 候选 | 差集 |
|---|---|---|---|
| 后端（62 文件选集） | 33 失败 / 1121 通过 | 33 失败 / 1168 通过 | **新增 0 / 修好 0** |
| 前端（175↔176 文件选集） | 13 失败 / 2060 通过 | 13 失败 / 2123 通过 | **新增 0 / 修好 0** |

### 6.9 回归期间抓到的真缺陷（本轮引入，已修）

`routers/formula_push.py` 的 `/run` 回执写了 `year=year`（应为 `body.year`）⇒ **`NameError`，
该端点全线 500**。首轮对比精确暴露 6 个失败（`test_formula_push_endpoints.py` 全红）。

🔴 **根因不是没有守卫，而是我的回归选集漏了守卫**：平台已有的
`tests/test_function_global_names_ratchet.py`（symtable 棘轮）把缺陷注回去后能精确点名
「`app.routers.formula_push: run_push() 用了 year`」（变异验证 `p40_verify_guard.py`：
修好后 5 passed / 注回缺陷 1 failed，端点测试同步 22 passed → 6 failed）。

选集生成器是按「被改模块的导入路径」反查测试的，而**全仓扫描型守卫不 import 任何具体模块**
（symtable / AST / 路由表 / `git ls-files` 遍历整个 `app/`）⇒ 这类守卫永远不会被反查命中。
已在 `p30_make_selection.py` 里改为**显式清单无条件纳入** 8 个此类守卫，并加「清单项必须真实
存在」校验（第一版清单就有 1 项路径写错，校验当场报出来）。
不用关键字启发式（`rglob(` 之类会把 452 个普通测试全算进来，等于没筛）。

### 6.10 浏览器实测（R15）

🔴 **后端界面实测在共享环境做不了，且与本轮无关**：`/api/health` 显示共享后端的热重载
自 `2026-11-01T05:07:11` 起持续失败 ——
`ImportError: cannot import name 'BatchReviewService' from 'app.services.pm_service'`。
归因：主工作区磁盘的 `pm_dashboard.py` 有 2 处该引用、**最新远端已删除**（0 处），即
HEAD 落后 5 个提交所致；本轮 `own_files` 不含这两个文件。旧 worker 不认任何会话的后端改动，
实测确认 `/latest` 与 `/run` 的返回里都没有 `orphan_push_states`。
⇒ 后端行为由候选树端点测试覆盖（`test_formula_push_endpoints.py` 22 passed + 注回缺陷必红）。

前端用**独立无头浏览器**实测（共享的 chrome-devtools 页面会被别的会话关掉／导航走，本轮就被关过一次），
判据取生产函数现算值，`tmp_note_table_closure/probes/p42_browser_check.mjs`，**8/8 全过**：

| 判据 | 实测值 |
|---|---|
| listed 账龄标签列 = 模板 | `["账 龄","期末余额","上年年末余额"]`，`flat=[true,false,false]` |
| listed 变动表标签列 | `["项 目","坏账准备金额"]` |
| listed 核销金额表标签列（两个半角空格） | `["项  目","核销金额"]` |
| soe 账龄标签列 | `["账 龄","期末数","期初数"]` |
| listed 仍未表态 group/flat 的表 | `[]` |
| 自动映射回执企业覆盖 | `企业覆盖 3/4（75%），1 家仍需人工确认` |
| 自动映射回执章节覆盖（skipped 不进分母） | `章节覆盖 1/2（50%），部分确认 1` |

console error 4 条，**同一根因且与本轮无关**：
`useAiNoteCapture.ts does not provide an export named 'NOTE_NAME_MAX_LENGTH'` ——
主工作区磁盘该模块缺此导出，候选树（最新远端）有 `export const NOTE_NAME_MAX_LENGTH = 100`，
同属 HEAD 落后。

### 6.11 第二轮方法论教训（续 §6.7）

6. **「新增端点字段」必须跑端点测试，不能只跑 service 测试**：R10 的 `NameError` 之所以
   漏到基线对比，是因为我只跑了自己新写的 `test_formula_push_orphan_states.py`（直接调 service）。
   改了路由就必须跑该路由的端点测试 —— 这与「㉕新增端点必做端点级测试」是同一条，
   本轮是它的**改动既有端点**版本。
7. **全仓扫描型守卫要进每一次回归选集**：见 §6.9。推论：任何「按被改文件反查测试」的选集
   策略都有这个系统性盲区，必须用显式清单兜住，且清单要有「项仍存在」的自校验。
8. **共享开发环境的故障要先归因再下结论**：后端看不到改动时，先查 `/api/health` 的
   `reload` 字段（本轮直接给出了 ImportError 原文与时间戳），再查该错误属于谁 ——
   不要默认「我的代码没生效」而去反复改代码。
9. **PowerShell 回显不可信，输出一律让脚本自己写文件**：本轮踩了三次 ——
   `>` 重定向写 UTF-16（Python 按 utf-8 读即崩）、emoji 在 gbk 控制台 `UnicodeEncodeError`
   导致脚本写文件前就挂、PSReadLine 缓冲区被别的会话搞坏后整屏输出错乱。
10. **`Start-Process -WorkingDirectory` 会改变相对路径基准**：`node` 脚本用相对路径找不到自己；
    而脚本放在无 `node_modules` 的 `tmp_` 目录时，ESM 裸包名（`playwright`）也解析不到
    ⇒ 脚本用绝对 `file://` URL 取依赖、调用方传绝对路径。

## 7. 第三、四轮历史证据索引恢复

公式中枢批次 `85caab386` 曾删除本 spec 的 `design.md` / `requirements.md`，后续 `6640edfc4` 只恢复到第二轮版本，导致 tasks 26~35 引用的设计段落从 HEAD 消失。历史全文仍可由 `git show 7e5c08897:.kiro/specs/note-table-structure-formula-pull-closure/design.md` 复核；第三轮提交为 `7e5c08897`，写真库和迁移撞号处置完成记录为 `dcf881b39`。本段只恢复索引，不改写历史结论。

## 8. 第四轮现状与缺口矩阵（2026-11-01，基线 `85af801a0`）

| 等级 | 缺口 | 真实影响 | 证据 |
|---|---|---|---|
| P0 | 金额列全未匹配仍 `found` | 参与自动映射，apply 可把旧自动值重建成空表 | `SourceTable.to_status()` 只看 `rows`；既有测试反而断言 `found` |
| P0 | 跨口径只登记表名 | 缺另一口径章节时回退目标口径章节/表名，可能选错或静默无来源 | `load_source_tables()` 全企业共用一个 `standalone_section`；生成器只写 `standalone_table_name_by_std` |
| P1 | 行名新规则未贯穿父级 | 存量/手工行含提示、可选括号或别名时在父节点成为 `unplaced` | `row_correspondence()` / `_aggregate()` 仍用报表行 `row_name_key` |
| P1 | 无小计仍折叠准备行 | 最终合计可能是净额，却留在账面余额列 | `fold_provision_rows()` 允许 `sub is None` |
| P1 | “确认并写入”吞确认错误 | 用户看不到失败原因，apply 不执行但界面没有解释 | `handleConfirmAndApply()` 空 `catch`，注释与实际不符 |
| P0 | R4/R5 被后续公式批次回退 | 推送后不再自动算合计/比例；公式管理不再显示审核要点和未生成原因 | `85caab386` 删除 `note_followup.py` / guard / `preset_notes` / `buildNoteSectionRows`，当前生产无替代调用 |
| P1 | 附注公式加载失败伪装为空 | 网络/权限/500 被显示成“无公式”，用户无法区分 | `fetchNoteUserFormulas()` catch 后清空且无 error 状态 |

## 9. 第四轮架构裁决

- **ADR-11 来源可用性是显式状态。** `SourceTable` 保留观察到的行用于诊断，但只有 `status == found` 才向映射和 apply 暴露行；`no_amount` 明确设为 `unreadable`。preview 与 apply 调同一属性，不能一边过滤一边仍写。
- **ADR-12 跨口径映射保存来源身份三件套。** 生成器新增 `standalone_source_by_std.{soe|listed} = {note_section, section_title, table_name}`。同口径继续读旧顶层字段；跨口径必须命中新字段，否则 `no_source`。查询按每家来源口径构造项目限定的 OR 条件，不把一家企业的章节候选用于另一家。
- **ADR-13 行身份分“字面规范化”和“业务规范化”。** 新共享模块提供 `normalize_note_row_label()` 与应用全局别名后的 `canonical_note_row_label()`；建议匹配保留 match_type 语义，父级行对应使用业务规范键。结构 hash 暂不改，避免全量 stale。
- **ADR-14 折叠宁缺勿错。** 缺紧邻小计时不反推账面余额，也不折掉准备行；现有映射弹窗会把它作为待确认行展示。
- **ADR-15 公式中枢只恢复能力，不恢复旧架构。** follow-up 接在最新 `formula_push.persistence.execute_and_commit` 的统一提交边界，以回调形式在领域通知前执行；刷新专用调用显式 opt-out。附注执行器接入推送拥有格判定，并沿用最新 provenance run，而不是回退 `85caab386` 的 S5 重构。
- **ADR-16 公式管理使用可见三态。** 后端恢复 `preset_notes`；前端恢复 `buildNoteSectionRows`，同时新增加载错误状态与重试按钮。不得恢复已经退役的行内编辑器或 `FormulaParamPicker`。

## 10. 预计改动面与风险

| 交付单元 | 文件 | 风险控制 |
|---|---|---|
| 来源与跨口径 | `consol_note_standalone_reader.py`、`consol_note_detail_source_service.py`、映射生成器与 JSON | 显式状态；缺映射 fail closed；生成器 `--check`/重生成对拍 |
| 行身份与折叠 | 新 `consol_note_row_identity.py`、suggest/groups/totals/subtree、`consol_note_provision_fold.py` | 不改结构 hash；正反例覆盖 |
| 映射 UI | `ConsolNoteMappingDialog.vue` 及既有测试 | 共用错误处理，不改成功路径 |
| 公式管理 | `note_settings.py`、`noteScopeTargeting.ts`、`FormulaManagerDialog.vue` | 只移植 R5 能力到最新统一编辑器；错误不清空为假空态 |
| 推送 follow-up | `formula_push/persistence.py`、新 `note_followup.py`、`note_workpaper_pull_service.py`、`note_formula_generator.py`、推送拥有格 helper | 统一提交边界；refresh opt-out；dry-run 不执行；失败不回滚主推送 |

不新增数据库迁移，不写真实项目。若共享库没有【测试】合并集团，合并全链用回滚事务/服务夹具验证，浏览器只读走查并保留数据阻塞。