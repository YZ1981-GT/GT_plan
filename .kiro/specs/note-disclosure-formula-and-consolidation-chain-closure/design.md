# 附注披露取数、公式与合并拉数闭环 — 设计

## 1. 现状实证（2026-10-29）

| 事实 | 现算证据 |
|---|---|
| 注册表 78 个 wp_code，headless 已接 67 个；11 个欠账有逐码原因 | `note_workpaper_sync_registry.json`、`noteHeadlessDisclosureCoverage.spec.ts` |
| 当前顺序为 push+note formula → headless → refill，公式早于明细 | `note_workpaper_pull_service.pull_sections`、`useNoteRefresh` |
| “生成”、重试、stale 重算和保存事件没有走完整 headless | `DisclosureEditor.onGenerate`、`useNoteRefresh` |
| G1/G10 的复数章节键被 pull/readiness/status/stale 多处忽略 | 注册表读取器现读 |
| 标准 sync 更新不清 stale；单/批 sync 与 formula push 不发 `NOTE_SECTION_SAVED` | `wp_disclosure_sync_service`、`formula_push.engine` |
| 表头库生成检查通过；单体↔底稿 161 例、合并表头/读取 363 例、Word 树 32 例通过 | 本轮实际命令 |
| 标题行库单体→合并列覆盖率 SOE 94.18%、listed 95.00% | `note_table_header_library.json.stats` |
| D2 单体国企 15 表、上市 17 表；合并映射国企 11、上市 15 | 模板、映射与既有结构守卫 |
| raw 前端投影覆盖服务端模板结构 | `useNoteTableProjection` 的 `{...metadata, ...table}` |
| note 顶部应用按钮走 report；非 note 的域也可能回落 report | `FormulaManagerDialog.onApplyFormulas/settingsDomain` |
| 合并 apply 不强制比较 bound hash；pending 叶子不阻断祖先清 stale | `consol_note_detail_apply_service`、`consol_note_subtree_reaggregate` |
| 遗留 Word 同步 phase5 按位置报 115 条假漂移；权威 Word 树门禁通过 | 两个 `--check` 本轮实跑 |

## 2. 架构裁决

### ADR-1：三类写入职责不混用

- headless builder：底稿披露明细、表名、业务列键。
- formula push：TB 审定后的主表金额、格级状态和运行记录。
- note formula：每张表内合计、账面价值、用户公式。

禁止用 TB 生成账龄、前五名等明细；禁止合并附注直接读 TB 或新增“合并披露底稿”。

### ADR-2：刷新采用两阶段 pull

`pull-from-workpapers?phase=prepare` 只返回 variant、章节、wp_id、人工格状态；浏览器运行现有 headless provider；
`phase=push` 再执行公式推送。随后现有 refresh 端点做 binding refill，并在同一后端 service 最后执行 note formulas。
未传 phase 保持旧 `all` 行为，避免破坏既有调用方。

最终顺序：

```text
prepare → headless(sync-from-workpaper) → push → refill → note formulas → fetchTree/fetchDetail
```
## 3. 后端设计

### 3.1 注册表访问

在 `note_readiness_service` 增加一个纯函数，返回某 entry/variant 的主章节与复数章节值，稳定去重。`section_workpaper_map`、
`section_sheet_map`、pull、状态查询和 stale marker 共用它。sheet 对复数章节沿用该 variant 的同一披露 sheet。

### 3.2 pull 与最终公式

`pull_sections(phase)`：

- `prepare`：不运行 push/公式，只读取 wp 与章节状态；
- `push`：运行有效 push 规则，不先运行 note formulas；
- `all`：保留旧行为（push 后运行 note formulas）。

`NoteWpMappingService.refresh_*` 在 refill 后调用现有 `_apply_note_formulas`，保证表内公式看到 headless 与 binding 的最终数据。

### 3.3 提交后事件

标准 sync service 成功写入时清 stale。router 在 service 已提交后按 `section_id` 发布 `NOTE_SECTION_SAVED`；批量逐结果发布。
`formula_push.run_and_commit` 在 commit 后按 `result.note_sections` 去重发布同事件，再广播原 `formula.pushed` SSE。事件失败只记录 warning。

### 3.4 结构投影

客户端 raw 重投影保留 raw `rows/columns/_source*Refs` 作为值和写回坐标；从服务端 `_tables` 覆盖结构字段：`name`、`headers`、
`multi_header`、`header_rows`、`_column_groups`、`_row_types`、`_display_layout`、`guidance`、`text_after_table`。这样即时编辑不丢，
Word/模板结构也不会被旧 builder 表头盖回去。

## 4. 公式管理设计

`FormulaManagerDialog.onApplyFormulas` 遇 note 章节时直接 POST note `apply-formulas`，刷新该章节公式列表并发出 applied；没有具体章节时明确提示。
`settingsDomain` 先认活动推送页，再认 scope：workpaper→wp、note→note、consol_note→consol_note；TB 内仍按所选节点区分 report/tb_detail/cross_check。

## 5. 合并拉数设计

- `load_source_tables` 一次查来源项目 `template_type`，每家调用 reader 时传自身 `soe/listed`；目标表仍由合并项目口径决定。
- reader 明确跳过 header/title/header_label 行。
- apply 读取来源后无条件计算当前 hash；与 `bound_source_hash` 不同的绑定改为 stale 并从 confirmed 集合移出。
- MappingRule 必须 active，且 project/section/template_version 与当前绑定一致，否则阻断。
- reaggregate 的 pending/stale/no-binding 叶子置 incomplete，祖先不在半截旧数据上写“最新”。锁定节点仍按用户明确授权保留。
- stale handler 在通过该企业任一绑定找到合并项目后，补入同一单体章节对应的前 N 名合并章节。

不在本轮自动后台执行整棵树 reaggregate。原因是映射确认、合并锁、人工/锁定格和大批事件合并都需要显式边界；本轮保证
`NOTE_SECTION_SAVED` 可靠标 stale，用户点“重新汇总”即从单体附注全链拉取，不要求重复打开或手工搬数。

## 6. Word 与底稿的关系

- Word 决定章节、表题、顺序和合并表头语义。
- 单体数字表的实际列结构若已按用户裁决改为底稿披露表，则由 `note_template_workpaper_alignment` 证明，并在 Word 树 allowlist 写明原因。
- `sync_note_templates_from_word` 的旧 phase5 位置式写标题会把续表错配。本轮将该写路径退役并指向 `note_word_tree` 门禁，避免运行正式工具反向破坏模板。

## 7. 验证

1. 重跑标题行库、Word 树、模板↔底稿、D2、公式、pull/sync、合并 reader/apply/reaggregate 既有测试。
2. 前端跑 useNoteRefresh、note projection、FormulaManager/NoteFormulaDialog、D2 builder 既有测试。
3. 在 `http://127.0.0.1:3030` 使用【测试】项目验证：D2 国企/上市刷新、表头分组、公式应用、刷新后回读；若无可用合并测试数据，明确标为环境阻塞，不伪称通过。
4. 当前工作树存在重叠并发改动，所有编辑使用定点替换；提交树另行干净复验，绝不覆盖他人修改。

## 8. 实施与验收记录（2026-10-29）

### 8.1 实际交付

- 单体刷新链已固定为 `prepare → headless → push → refill → note formulas`；刷新、全部刷新、生成、重试、stale 重算和保存事件回调共用该编排。
- 注册表复数章节、标准 sync 清 stale、提交后 `NOTE_SECTION_SAVED`、公式管理 note 端点与治理域均已接通。
- 合并读取按每个来源项目自身 `template_type` 选择国企/上市口径；确认请求中的企业项目与 hash 不再受信任，而由当前企业树和单体附注现读重建。apply 同时校验来源 hash、模板版本、规则项目/章节，pending/stale 会阻止祖先被标成最新。
- Word 同步工具的 `phase5_standalone_title` 已退役；Word 树门禁继续管理标题、顺序和多级表头。

### 8.2 自动验证

- 最新远端分离头候选树：相关后端 **819 passed / 915 warnings**，含真 PostgreSQL `test_note_workpaper_pull_service_pg.py`、自动映射端到端和项目鉴权基线。
- 确认映射路由临时请求探针 **3 passed**：服务端会用当前企业树重建 project/hash；伪造 project 返回 422；陈旧 hash 返回 409。探针用后已删除。
- 前端相关 **99 passed**：刷新编排、pull 参数、结构投影、公式管理接线和 D2 章节映射。
- 三项生成/对齐检查全部通过：标题行库 `--check`、Word 树 `--check --summary`、四版模板同步 `--check`。
- 局部 `vue-tsc` 在最新远端基线为 **161 errors / 36 files**，候选树为 **160 errors / 35 files**。本轮最初引入的 `metadata` 两处类型错误已修；候选树没有新增类型错误，并消除基线中 `useNoteTableProjection.ts` 的 1 条错误。剩余 160 条均可在未应用本轮补丁的同一远端基线复现，不在本轮顺手改动。

### 8.3 浏览器证据

- 上市【测试】单体项目 D2 的“五、5”显示 17 张表；坏账准备分类表显示 `期末余额 → 账面余额/坏账准备/账面价值 → 金额/比例/损失率` 多层表头。
- 刷新实际按顺序请求 `phase=prepare`、`phase=push`、`五、5/refresh-from-workpaper`，三次均返回 200。
- 公式管理显示应收账款 93/93 条公式；“应用自动运算”请求当前章节 `/apply-formulas` 返回 200，并重新读取公式与章节详情。
- 国企真实项目只读抽查“八、5”，期末数/期初数多层表头正确；未执行写操作。
- 上市【测试】合并项目显示 15 张应收账款合并表、企业树、映射和重新汇总入口。重新汇总返回 200/`skipped`，明确说明下级无可汇总单体附注且本章节未绑定明细模板，没有把缺数据伪报成成功写入。
- 浏览器 console 无 error；既有 `CommentTooltip` fragment root 与 Transition non-element root warning 仍存在，另列后续治理。

### 8.4 环境与验收数据

- 验收后 `/api/health` 返回 200/healthy，PostgreSQL、Redis 正常，迁移 applied_count=219，schema drift `critical_count=0`；仍有 8 条非关键 drift，属于独立环境治理项。
- 浏览器验收通过正式端点在 `【测试】公式同步甲有限公司_2025` 创建 D2 底稿 `a544a961-e30f-4a56-a012-fd127fea42dc`。该项目名称带【测试】，本轮决定保留为后续刷新回归样本；没有改写真实项目。
- 合并真实落数仍受测试数据阻塞：当前合并测试项目的该章节没有明细模板绑定和可汇总单体来源。代码、门禁、入口、响应和阻塞提示已验证，Task 15 按 `[ ]*` 保留，待有合适测试数据后补写入验收。

## 9. 后续优化

1. 依次修复仍未接入 headless provider 的 E1/F1/G7/H1/H3/K3/L4/L5/M6/M9/M10；每码必须先修自身读回或副作用问题，再从冻结清单删除。
2. 标题行库对应覆盖率目前为 SOE 94.18%、listed 95.00%；剩余 unmatched 应逐表裁决，不能用宽松模糊匹配强行提高数字。
3. 普通同名行仍依赖 occurrence。后续可把父标题、分组路径和稳定业务键纳入行身份，降低插行/改序后的映射漂移。
4. 为 `_formulas`、`_user_formulas`、`formula_setting` 建统一的“最终生效来源”诊断视图，直接展示系统预设、项目覆盖、停用、运行结果与溯源地址。
5. 单独收口 8 条非关键 schema drift、PostgreSQL 连接容量监控，以及 `CommentTooltip`/Transition 的 fragment warning；这些问题不应混入本轮数据链修复。
