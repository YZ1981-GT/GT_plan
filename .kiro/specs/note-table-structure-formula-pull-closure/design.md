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
