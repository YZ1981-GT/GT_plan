# 合并附注标题行库 + 节点子树重新汇总 — 设计

## 1 总览

```
四版种子（单体 note_template_{soe,listed}.json 的单体口径章节 / 合并 consol_note_sections_{soe,listed}.json）
        │                          词表 note_table_header_vocabulary.json（手工维护：同义词、规则、逐表覆盖）
        ▼                                   │
note_table_header_library.py（唯一识别口径：表头路径 → 列语义键 / 续表认定 / 列对应 / 选表）
        │                     │                         │
        ▼                     ▼                         ▼
库目录生成（catalog）     映射生成器                 读取层 consol_note_standalone_reader
note_table_header_       gen_consol_standalone_     （V186 明细映射拉数）
library.json + --check   note_mapping.py
                         → consol_note_section_mapping.json（单体表名按同一选表结果）
```

请求期只用模块 + 词表；库目录是生成产物（给人看、给 CI 比对、给测试断言覆盖率），不在请求期读取。

## 2 表头路径（与展示同口径）

`column_paths(table) -> list[list[str]]`，第 0 列为标签列：

1. 合并表（有 `multi_header` ≥ 2 行或 `header_rows`）：`consol_note_headers.normalize_consol_note_section(table)["header_rows"]`（展示 / Word 导出同一函数）落格后逐列自上而下取非空文字。取代读取层的 `_multi_header_raw_paths` 启发式。
2. 单体表：`_column_groups` 两种格式都认 —— 平铺 `{group,start,span}`；投影器树形 `{group, children:[{group,start,span}|{headerIdx}]}` / `{headerIdx}`；`[]` = 显式单级。没有 `_column_groups` 时用 `columns[i].group`（「/」分层，投影器同口径）。路径 = 分组层 + 列名（列名与末级分组相同时不重复）。
3. 平表头文字里的「/」不拆段（「利得/损失」是一个列名）；只有两侧都是同一期间词时（「期末余额/本期发生额」）整体认作该期间。

## 3 列语义键

`ColumnKey(period, measure, kind, label)`：

- `kind`：第 0 列 `label`；末段命中比例规则（`比例|比率|率(|率$|%`）为 `ratio`（不加总）；其余 `amount`。
- 期间四类（词表 `periods`）：`end` 期末余额类 / `prior` 期初、年初、上年年末余额类 / `cur` 本期、本年发生额类 / `prev` 上期、上年发生额类。旧读取层把 期末 与 本期 并为一类，会让「期末账面价值 / 期末公允价值」两列都只剩「期末」而撞键；本设计先整词查表，再按最长期间前缀拆出余下的计量词（「期末账面价值」→ `end` + 「账面价值」；余下为「余额 / 数 / 金额 / 发生额」视为纯期间）。
- 表名期间（单体种子约定：三级表头的顶层期间写进表名）：只看表名最后一个括注，去掉「续：」后若是期间词即为表名期间，路径里没有期间时补上。
- `measure`：路径去掉期间段后逐段规范化（去空白 / 换行，全角括号冒号百分号转半角）+ 分组同义词（如「账面金额」→「账面余额」、「本年增加」→「本期增加」）。
- 逐表覆盖：词表 `overrides.columns`，按 `(variant, 表标识, 列号)` 直接给键，必填理由。

## 4 续表认定

- 标记：规范化表名以「续」开头，或含「（续）」「（续：…）」「（续表）」及半角写法。「续」在 永续债 / 继续涉入 / 手续费 / 存续 / 后续 / 持续 / 连续 里不算。
- 主表：同节内前面最近、基名相同（去掉续表标记与期间括注）的非续表；裸「续：」「续（1）：」取前面最近的非续表。
- 类型：去掉期间后列键相同或续表行名大多在主表里 → `columns`（列续：同一批行补期间或补列，按行名对行）；否则 `rows`（行续：同样的列补行）。
- 覆盖：`overrides.continuations`（指定主表 / 类型 / 声明不是续表），必填理由。
- 种子里的 `continuation_of_index` / `continuation_of` 不作依据（含并列表与「接在上一张后」），只在异常清单里对照。

## 5 选表与列对应

- 候选单元：单体章节每张表一个单元；非续表的单元带上它的列续表。
- 逐列对应（沿用读取层规则，改为作用在语义键上）：同期间且计量相同 → 同期间且计量为后缀（单体省略分组层）→ 同期间且计量为前缀（合并多一层说明）；强规则有命中就不再试弱规则，命中不唯一放弃，同一单体列被多列认领全部放弃。
- 选表：先按名字（映射给的单体表名、合并表标题；规范化相等 → 去期间后缀相等 → 相似度 ≥ 0.9，续表只和续表比）；名字命中的单元金额列覆盖为 0 而另有单元覆盖 ≥ 一半且唯一最高 → 按结构选中（`structure`）；名字没命中按结构兜底（同阈值）；单表章节直接用。结果写明方式 `name / structure / single_table / none`。
- 映射生成器用同一选表结果写 `standalone_table_name`；目录生成时复算，与映射不一致即漂移。

## 6 库目录 `note_table_header_library.json`

```json
{
  "version": 1, "_source": "...", "vocabulary_digest": "<sha1>",
  "variants": {
    "soe_standalone": {"tables": [{"id": "八、4#1", "name": "...", "period": "end",
        "header_rows": [[{"text","colspan","rowspan"}...]...],
        "columns": [["类别", "§label"], ["账面余额/金额", "end|账面余额|金额"], ...],
        "continuation": {"of": "八、4#0", "kind": "columns"} | null}]},
    "soe_consolidated": {"tables": [{"id": "五-4-2", ...}]}, "listed_standalone": {...}, "listed_consolidated": {...}
  },
  "correspondence": {"soe": [{"consol": "五-4-3", "standalone": "八、4#3", "via": "structure",
        "columns": {"1": "八、4#3:1", ...}, "unmatched": ["..."], "ratio": ["..."]}], "listed": [...]},
  "anomalies": [{"variant", "id", "kind", "detail"}],
  "stats": {...}
}
```

单体表标识 `章节号#表序`，合并表标识 `section_id`。每张表一行 JSON 便于看 diff；无时间戳，内容不变则字节不变。生成器 `backend/scripts/seed/build_note_table_header_library.py`（`--check` 漂移 exit 2 并列出差异）。

## 7 读取层改造

- 删除 `_norm/_canon/_END_WORDS/_PRIOR_WORDS/_SEGMENT_ALIASES/_multi_header_raw_paths/_raw_column_paths/_group_at/_rule_*/_match_columns/_is_continuation/_table_period`，改调模块；`read_source_table` / `pick_standalone_table` / `SourceTable` 签名不变，`SourceTable` 新增 `table_choice`（`name / structure / single_table`）。
- 行续表的行追加在主表行后（列按语义键对应）；列续表按「行名 + 同名序号」对行（现状）。

## 8 重新汇总编排 `consol_note_subtree_reaggregate.py`

```
reaggregate_subtree(db, project_id, year, node_key, section_ids, template_type)
  进程锁 _process_lock("target") + PG 咨询锁 _advisory_lock（复用 consol_push_service）
  树 build_tree 一次；子树后序 = reversed(list(iter_nodes(node)))
  预载：本项目全部章节的明细模板绑定（一次查询）；视图上下文 load_view_context 一次
  逐章节 SAVEPOINT：
    数据叶子：章节有模板绑定 → apply_detail_refresh(node_key=叶子, scope_leaves=[叶子])
              ApplyError（NO_BINDINGS / UNMAPPED_ROWS / SOURCE_CHANGED …）→ 跳过并记原因（这些都在写库前抛）
    差额节点：fill_by_formula(node_key=差额节点, _view_context)
    汇总节点：aggregate_children —— 读下级节点已保存行（一次查询），骨架 = 明细模板绑定版本行，没有绑定用合并模板行；
              按（规范化行名, 同名序号）逐列求和；合计 / 小计按本表重算（与 apply 共用 recompute_total_rows）；
              手工 / 锁定格保留；下级行名在骨架里找不到的列入 unplaced；没有任何非差额下级数据 → 不写。
    写入后记录本节点公式值快照 last_formula_value（叶子 / 汇总），供 §9 判断是否过期
  单章节意外异常 → 回滚该章节 SAVEPOINT，记失败，继续下一章节
  service 只 flush；路由统一 commit
```

`apply_detail_refresh` 增加可选 `scope_leaves` 参数（编排传入，免逐次重建树）。合计重算从 apply 内联代码抽出为 `consol_note_table_totals.recompute_total_rows`，apply 与汇总共用。

响应：保留 `ReaggregateResponse` 全部字段（`sections_updated` = 所选节点写入的章节数），新增 `mode="subtree"`、`nodes=[{node_key, kind, label, written, skipped, failed, reasons}]`、`pending_entities`（需确认映射的企业）；`results` 只放所选节点的逐章节结果。

## 9 后台按公式刷新不覆盖拉数结果

`fill_by_formula` / `fill_note_sections` 增加 `preserve_pulled: bool = False`；推送后刷新与试算表事件处理器传 `True`。记录来源为 `detail_mapping` / `subtree_aggregate` 时：不改行；新算的公式值快照与 `last_formula_value` 不同 → `is_stale=True` 并更新快照；返回 `status="kept_pulled"`、`stale_marked`。差额节点来源是 `formula`，照常刷新。按钮「按公式填入」不传，行为不变。

## 10 前端

`ConsolNoteTab.vue`：按钮提示改为「重新汇总：本节点下各企业按已确认映射从单体附注重新拉数，差额节点按抵销分录重算，再自下而上汇总到本节点」；完成提示 = 写入节点数 + 拉数 / 差额 / 汇总分布 + 待确认映射企业数；`consolidationApi` 补响应类型。`ConsolFormulaManagementPanel.vue` 两条取数路径说明同步改。`ConsolidationIndex.vue`（并发会话未提交改动）不改，响应字段兼容。

## 11 测试

- 模块：续表标记正反例（含 永续债 / 继续涉入 / 手续费 / 后续 / 连续 / 存续）、主表与类型、投影器树形分组、表名期间、期间前缀拆分不撞键、「/」平表头、逐列对应强弱规则与歧义放弃、选表三种方式、覆盖生效。
- 库目录：生成结果与入库文件一致（函数调用，不起子进程）；四版表数 = 种子表数；已知异常在清单（国企 八、9 #16 / 八、18 #4 自指、上市 五-9-4~7 首格跨列）；国企 五-4-3 对应到「（续：期初数）」表；覆盖率棘轮。
- 读取层：既有 18 例 + 端到端 9 例不回退；行续表并行；结构兜底选表。
- 重新汇总：SQLite 三层树（G:consol → G 差额 / G 本部无项目 / A:consol（A 差额 / A 本部 / A1）/ B）端到端：叶子拉数、差额、A 汇总 = A 本部 + A1 + A 差额、G 汇总含 A 汇总结果、合计重算、手工格保留、锁定跳过、无绑定章节跳过、只有差额不写；后台 `preserve_pulled` 不覆盖且标过期；变异逐个打红。
- 真库事务回滚探针：【测试】集团跑一次子树汇总，核对节点金额后回滚。
- 前端：ConsolNoteTab vitest、ESLint、单区域 vue-tsc + TS2322 变异。

## 12 决策

- ADR-HL-001 识别口径集中在一个模块，库目录是生成产物不进请求期：请求期读大 JSON 需要随种子同步重生成，且改词表要两处生效；目录只用于审阅、CI 与测试。否决「请求期按表头签名查目录」。
- ADR-HL-002 合并表表头路径取展示用的 `multi_header_rows`：读取层自带解析与展示不一致时以展示为准（用户看到什么就按什么认列）。
- ADR-HL-003 期间分四类：并类会让同表两列撞键；拆分后 期末余额 ↔ 期末数、本期发生额 ↔ 本年金额 仍对得上。
- ADR-HL-004 选表加结构证据：只按名字会把期初续表对到同名的单项计提表（国企 五-4-3）。
- ADR-RA-001 汇总节点 = Σ 直接下级已保存附注数 + 差额，不是叶子平铺求和：中间节点的手工调整与本级差额要带到上级（与差额表 `node_measures` 同模型）。
- ADR-RA-002 后台公式刷新对拉数结果只标过期不覆盖：否则下一次试算表事件就把单体附注数换回试算表数，违背「个别数从单体附注拉」。
- ADR-RA-003 每章节一个 SAVEPOINT（不是每章节每节点）：预期内的失败都在写库前抛出，按节点捕获即可；意外异常整章节回滚，避免汇总节点用到半截下级数据，也控制子事务数量。

## 13 实施勘误与结论（2026-10-22 实施后补，以代码为准）

### 13.1 与上文设计的偏离

- §4 续表主表：实现为「紧挨着的上一张非续表」；同基名的更早一张只在续表行名与它更吻合时才取代（上市「应付债券（续）」按「同基名最近」会认到汇总表）。
- §5 选表：名字只用来收窄候选，表头结构定夺（映射子表名与合并表标题两路证据合并；有更具体名字时裸「续：」不参与）；没有名字证据时只在强命中明显领先「取自别的表」的对手时按结构选（同构表不猜）；章节只有一张表、但一列金额都对不上时不拿它凑数（多是章节映射错位，原设计「单表章节直接用」否决）。打分顺序 = 具体强命中、强命中、命中、比例 / 说明类列一致、直接对应、列数接近、有数、成员少。
- §7 读取层：`pick_standalone_table` 只按名字；旧单表格式表头为空时复用 `note_header_projector.derive_headers_for_legacy_table`。
- §8 合计重算：抽成 `consol_note_table_totals.build_table_rows`（骨架行 + 逐列金额 → 写入行），不叫 `recompute_total_rows`；顺带修一处缺陷：手工 / 锁定格在来源这一格没数时原来被清空，现在一律保留。
- §8 叶子：先看映射状态再调 apply —— 未确认 / 已变 / 已排除直接按原因跳过（只有 stale 绑定时 apply 会写一张空表）；未确认与已变列入 `pending_entities`。
- §8 汇总：下级来源判定 `record_write_source`（有 `_last_write_source` 用它；没有标记但有公式值快照 = 来源标记出现之前的「按公式填入」，同样按试算表数排除；都没有 = 手工）；映射里排除的企业旧数不计入；没有明细模板绑定的章节骨架用合并附注模板行，行类型用「从来源建议模板」同一判定 `_row_type`（公式服务的 `_infer_row_type` 把「小计」判成合计，未改动），表内嵌子表头行（国企 五-10-5 / 五-16-6）原样保留；根节点只有项目级兼容行时先复制成节点行再写（保住其中的手工格）。
- §8 新增规则（真库探针补出，ADR-RA-004）：下级出错（差额没算出、更下层没汇总成）⇒ 上级本章不汇总并逐级向上，不在半截数据上写出「不过期」的合并数；按原因跳过的下级（未绑定 / 待确认 / 锁定 / 没有公式）仍用它已保存的数。
- §8 计算口径：只在有公式的章节才装载（差额与公式值快照共用）；合并范围未确认时计算门抛 409，只让差额与快照不可用并写明原因，拉数与汇总照常（与明细映射 apply 一致，apply 本身不过计算门）。
- §9 推送后刷新先把全部附注行标「待更新」再按节点刷新：保留的拉数行推送后保持「待更新」（差额可能变了，由用户重新汇总）；试算表事件只在公式值与快照不同时才标。副作用：有拉数行时试算表事件处理器的「无 stale 行即短路」不再生效，推送后会多跑一轮只比对快照的刷新（性能，见 13.3）。
- §10 前端：完成提示收成纯函数 `consolNoteView.reaggregateSummary`；来源标签「🔄 子树汇总（N 个下级 + 差额）」，N 只数计入了数的非差额下级（`_subtree_child_count`）。

### 13.2 实测数字

- 读取层新旧对比（真库 9 个项目 × 映射章节 3228 组，只读）：2554 组完全相同；9 组换表全是 五-4-2 / 五-4-3 纠正；31 组不再取表（30 组是章节映射错位时唯一一张不相干的表、本来一列都对不上，1 组旧模板表无数）；76 个合并章节新认到表；原有非零数丢失 0。
- 库目录：国企对应覆盖 0.7727、上市 0.8932（各 27 张合并表认不到单体表）；目录与映射不一致 0；异常清单 90 条。
- 重新汇总真库事务回滚探针（事务内新建【测试】集团 + 两家子企业，复制重药控股安徽 / 重庆和平药房的单体附注与试算表，按生产链路确认合并范围、建模板、确认映射、录抵销 1000）：3 个章节叶子 = 单体附注、合并 = Σ 下级 + 差额、合计 = 本表数据行之和，独立核对 0 不符；后台按公式刷新三章都保留拉数且未误标过期；全量 321 章节 × 5 节点 4.2 秒；回滚后无残留。
- 真库现状：明细模板绑定 0、确认映射 0 ⇒ 现有项目点「重新汇总」时叶子都按「本章节未绑定明细模板」跳过，只有差额节点按公式计算 —— 需要先在「📋 明细映射」绑定模板并确认映射。

### 13.3 范围外 / 待拍板

- 合并种子按现行四版 Word 重同步（国企 五-10 起编号错位）、上市 五-9-4~7 多级表头错一列（R4.1）。
- `formula_push/note_writer` 的期间词表（R4.2）与 `consol_note_sections._resolve_value_columns` / `_classify_header` / `_ENDING_KEYWORDS`（试算表刷新端点的第三处表头识别）改调标题行库。
- 旧 V2 汇总器、`useNoteAggregation`、无界面的 V202 端点是否下线（R4.3）。
- 「📋 明细映射」按钮的 apply 不记公式值快照：后台刷新对这类行可能多标一次「待更新」（只会多报、不会漏报）。
- 有拉数行时试算表事件处理器的短路失效（13.1 §9），可按来源标记排除拉数行后再判短路。
- 本 spec 外的预存失败（HEAD 干净检出同样失败）：`test_consol_note_formulas::test_seed_counts_on_real_templates`（soe / listed）、`test_consol_note_headers.py`、`test_consol_push::TestEndpoints::test_approve_push_revoke_roundtrip`、前端 `ConsolTrialBalanceTab.spec.ts` / `ConsolReportBreakdownView.spec.ts`（请求参数多了 `signal`）。
- ADR-RA-004 下级出错不汇总、按原因跳过不阻断：出错意味着这一级本轮的数不可信，在其上汇总会写出标「不过期」的错数；跳过是已知原因（用户可见、可处理），用已保存数并回报更有用。

## 14 其余表头识别点收口（R5，2026-10-22 追加）

### 14.1 标题行库新增：逐列角色 + 变动表勾稽列

```
period_side(period)          end / cur → current；prior / prev → previous
movement_kind(key)           计量段含词表 movement_words 的词 → increase / decrease / movement（方向不定）；
                             期间是期末 / 期初（余额类）的列不算变动（「期末余额 / 计提的利息」是期末一侧列）；
                             命中多个词取最长的，同长按 increase → decrease → movement
column_role(key)             label / closing / opening / increase / decrease / movement / None
                             closing / opening = 金额列、不是变动、计量为空或在 balance_measures（账面余额、公允价值）
column_roles(table)          column_keys(table) 逐列角色
rollforward_columns(table)   RollForward(opening, closing, increase, decrease, unknown) | None
                             期初 / 期末：余额列各唯一；否则同一计量（账面价值 / 投资金额…）期初、期末各唯一的一对；
                             变动列只认两者之间的列，之间其余金额列（方向不定 / 没有变动词）→ unknown
```

- 比例 / 说明类列、坏账准备 / 账面价值 / 已质押金额 / 终止确认金额等计量列角色为 None：不是该项目的余额，拿去和试算表审定数比只会报假告警（旧口径「首段含期末」全部当审定数列）。
- 「计提减值准备」进 movement：长期股权投资明细里它减少账面价值，减值准备变动表里是增加，词本身定不了方向；最长词优先让它不被「计提」认成增加（四版种子共 10 列受影响，全是这一种）。
- 变动表版式「期初 | 本期变动… | 期末」：期初之前的「投资成本」「预算数」、期末之后的「本期计提减值准备」「减值准备期末余额」「利息资本化累计金额」是说明列，不参与勾稽。

### 14.2 `consol_note_sections`

- 删 `_ENDING_KEYWORDS / _OPENING_KEYWORDS / _CHANGE_EXCLUDE / _header_root / _is_ending_label / _is_opening_label / _classify_header / _resolve_value_columns`，路由里不再有期间 / 变动关键词。
- `_header_table(template, headers)`：模板存在且列数与本次表头一致 → 模板（多级表头 / 分组，与展示同口径）；否则本次平表头。`_column_view(table)` 给逐列（列名, 角色），列名取展示路径（「期初余额/账面余额」；原来取平表头，分组表里常是空串）。
- 试算表交叉校验（全部审核 / 单表审核）只比 closing / opening 列；下级汇总的试算表兜底只对 closing / opening 列取下级试算表。
- 单表审核勾稽改用 `rollforward_columns(table)`；一行里 unknown 列有数就跳过该行（方向不定，没法按「增加 − 减少」算；旧逻辑当 0 算，必误报）。
- 真库核对：已保存的合并附注 4496 行表头与国企模板逐字相同 ⇒ 审核全走模板多级表头，平表头兜底现实中不走（平表头里的「/」不拆段，期间与计量混写的列不认作余额列）。

### 14.3 `note_writer`（R5.3，待确认接手方式）

期末金额列 = 本期一侧唯一纯期间列；没有时取唯一的账面价值 / 公允价值列；期初同理。旧格式整列无表头时仍按位置（与现状一致）。并发会话暂存的「六列对称兜底」按位置取前后半段，且优先顺序实际取到「账面余额」（与注释「优先账面价值」相反）—— 改调标题行库后分组表由 `_column_groups` 给出期间，不再需要按位置兜底。

### 14.4 新旧逐列对比（R5.5，两版合并模板全部表）

试算表比对用的角色（HEAD `_classify_header` vs `column_role`，2893 个数据列）：相同 2444；旧的余额列不再比 330（closing→None 176 / opening→None 154：比例 / 说明列，坏账准备 / 账面价值 / 减值准备 / 已质押 / 终止确认等计量列，以及种子平表头错位，如五-5-6 平表头把「期初数」写在「期末数/计提比例」列上）；新增比对 38（None→opening 23 / None→closing 15：分组表平表头为空串的余额列）；变动列不再当余额 13（closing→decrease 7 / closing→increase 4 / opening→increase 2）；closing→opening 1（上市五-10-5「续：」平表头写期末余额、多级表头写上年年末余额，跟展示）；其余 67 列只是变动方向变化 / 新认出的变动列，只影响勾稽。

单表审核勾稽（两版合并模板里新旧任一会校验的 78 张表）：

| 类别 | 张数 | 说明 |
|---|---|---|
| 列完全相同 | 38 | |
| 列相同、多了方向不定列 | 7 | 应付债券 / 筹资活动负债变动：发行 / 摊销 / 偿还 / 现金流量净额 / 其他有数的行跳过（旧逻辑当 0 算，必误报） |
| 纠正 | 20 | 分组下第二、三个叶子列（其他增加 / 转销 / 其他减少 / 本期出售）补进来；期末列取对（旧「后出现的覆盖」常落在利息资本化率 / 减值准备期末余额 / 本期出售列上）；对子公司投资期末之后的「本期计提减值准备」不再当增加；种子错位挂到期末下的列改为方向不定 |
| 新增校验 | 6 | 国企五-4-6 / 五-5-7 坏账准备变动；长期股权投资明细 4 张（只有「减少投资」能判方向，其余变动列有数的行跳过） |
| 不再校验 | 7 | 优先股 / 永续债 / 其他权益工具 / 资本公积 6 张「数量 + 账面价值」两套期初期末（不唯一；旧逻辑 2 张恰好对上数量列、4 张列错位）；上市五-23-3 字母标注列（A / E=A+B−C−D；旧逻辑漏「转入固定资产 C」） |

### 14.5 测试与变异

- `tests/test_note_table_header_library.py` +37 例（期间侧、余额计量、变动方向与最长词、期末一侧不算变动、模板表头优先、词表驱动、勾稽列 8 种版式）。
- `tests/test_consol_note_section_column_roles.py` 20 例，替换只测已删函数的 `test_consol_note_refresh_column_resolve.py`：选表、平表头矩阵、真模板余额列、全部审核 / 单表审核 / 下级汇总兜底三处真实调用（附注落真实行，试算表金额打桩）。
- 干净 worktree 19 个磁盘变异全打红（库 7、词表 2、路由 10），每个由对应用例抓到。

### 14.6 范围外 / 待拍板

- `note_writer.legacy_value_keys`（R5.3）：并发会话暂存未提交，等确认接手方式。
- `consol_note_formula_service.value_column`（公式种子取数列）、上年附注导入 `_header_index`：仍各有一套识别（R5.4）；改了会变生产种子公式 / 导入行为，未动。
- 「数量 + 账面价值」两套计量的变动表按计量分别勾稽、字母标注列认作纯期间：没做（见 14.4「不再校验」）。
- 「核销」方向：坏账准备表里是减少，现按方向不定（有数的行跳过、不误报也不校验）；归减少要拍板。
- 种子多级表头错位（五-22-1 / 五-22-2「本期减少/自用房地产或存货转入」、五-13-2「期末数/本期出售」、五-29-1 商誉原值套了开发支出的子表头等）是种子问题（R4.1）。挂到期末下的错位列已按方向不定处理；五-22-1 / 五-22-2 只有「自用房地产或存货转入」有数的行仍按减少算。
- 单元格「汇总」（`/aggregate`）下级没有附注数据时用下级试算表兜底，与「只从单体附注拉数」不一致：保留原行为，只把兜底限在余额列，是否下线待拍板。

## 15 R6（2026-10-22 追加）

### 15.1 V2 汇总器 / `useNoteAggregation`：不需要，删除（R6.1）

| 事实（2026-10-22 现读 + 探针 + 真库） | 说明 |
|---|---|
| 旧生成器 `ConsolDisclosureService` 在 AsyncSession 上调 `self.db.query` | 必抛 `AttributeError`，`GET/POST /api/consolidation/notes/{pid}/{year}`、`/integrate`、`/{pid}/{year}/save` 恒 500（探针实测）；产出的是 7 个写死的骨架章节 |
| V2（`generate_full_consol_notes` 等）章节映射读 `consol_note_section_mapping.csv` | 文件头 `# is_mock=true`，章节 id 是 `section_cash` 这类假 id，对不上合并附注模板 |
| 开关 | 全局 `CONSOL_NOTES_V2_ENABLED=False`；真库 0 个项目开项目级灰度；`disclosure_notes.consolidation_breakdown` 0 行 ⇒ 生产从未跑过 |
| 事件 | `handle_consol_subsidiary_changed` 从未注册，`CONSOL_SUBSIDIARY_CHANGED` 从未发布 |
| 前端 | `useNoteAggregation` 调不存在的 `/api/disclosure-notes/{pid}/{year}/reaggregate`，唯一使用方 `ConsolNoteTreeEnhanced.vue` 无挂载点；附注编辑器「🔗 查看合并明细」只读 V2 写的 `consolidation_breakdown`（0 行）⇒ 恒「暂无合并明细」；`consolidationApi.getConsolNotes` 等 0 调用方 |

合并附注的真实链路是 V186 明细映射（单体附注拉数）+ 子树重新汇总（R3）+ 公式内核，写 `consol_note_data`；V2 是同一件事的第二条路径（还写到 `disclosure_notes`），优化它等于维护两套 ⇒ 删除。

- 删除：`consol_disclosure_service.py`（2039 行）、路由 create / get / integrate / save / consol-breakdown、`note_consol_drilldown_service.py`、`consol_cross_template_service.py`、mock CSV、`consol_note_aggregation_service` 里只给 V2 用的函数、`note_source_resolvers.resolve_consol_aggregation`（注册键 `consol_aggregation`，无绑定用它）、配置 `CONSOL_CROSS_TEMPLATE_ENABLED`；前端 `useNoteAggregation.ts`、`ConsolNoteTreeEnhanced.vue`、附注编辑器「查看合并明细」、`ConsolBreakdownDialog` 的附注模式、`consolidationApi` 里的死函数与 apiPaths；只测这些的测试一并删除。
- 保留：「🔄 重新汇总」端点、`validate_lineage_dag`（重新汇总 / 应用公式在用）、`ConsolBreakdownDialog` 报表模式（`ReportDialogs.vue` 在用）、灰度开关与 `consol_note_gray_service`（只作试算表事件自动刷新 `consol_note_formula_refresh_handler` 的门控，默认关，行为不变，注释改正）。
- 级联刷新（「一键刷新」）第 6 步：原来调 V2（生产恒跳过）⇒ 改调 `consol_push_service._refresh_notes`（与合并推送同一函数：全部标待更新 → 逐节点按公式刷新、从单体附注拉来的数保留并标待更新），持推送同一把锁（进程锁 + 事务级咨询锁，与重新汇总互斥）；`note_status` 为 partial / failed 记入 `errors` 不算完成，skipped 记 `steps_skipped`。行为变化：一键刷新从此真的刷新附注，与推送一致。

### 15.2 V202：只分析，待拍板（R6.2）

`V202__consol_note_mapping_reuse_and_reference.sql` 建 4 张表（映射规则模板、结构锁定 + 锁定企业、合并附注数值确认）和 1 列（`consol_note_mapping_rule.promoted_to_template_id`），真库全 0 行；路由 `consol_note_mapping_templates.py` 有规则晋升模板 / 模板列表与删除 / 科目引用 / 数值待确认汇总 / 确认 / 确认状态 / 就绪检查 / 结构锁定加解锁；前端只有 `useConsolNoteReuse.ts`（0 调用方）与 apiPaths；数值变化时 `consol_note_value_change_service` 会把确认降级（后端已接线）。它不是第二条汇总路径，是设计好但没做界面的功能，删还是补界面要产品判断。

### 15.3 合并种子多级表头错位（R6.3）

根因：`backend/scripts/seed/_fix_missing_multi_header.py` 的 `_build_mh_and_cg`（commit d59512f33）从平表头 `headers` 反推多级表头 —— 空串当「沿用左侧」、「/」拆段 —— 与 Word 不符（如国企 五-5-1 `期末数/账面余额 | 期初数/坏账准备 | …` 把期末的坏账准备认成期初），重跑会重现。Word 生成器 `sync_note_templates_from_word.py` 按标记偏移推章节号，不能直接重跑（会动章节号与 `consol_note_data.section_id`）。

第二个根因（实施中发现）：Word 生成器自己的表头行数判定只看纵向合并 —— 两级表头「账龄」列下格留白判成一行；数据行里两格一并的空白取数格、通栏分类行（「商品价格风险」）、空白占位行又被算进表头（上面 12 张表的数据行就是这样升进表头的）。Word 表头里没合并的空白格（留白的上级）照搬进种子，种子格式把它读成「并进左边」。

修复（平台一处 + 按 Word 逐表）：

- 平台 `note_word_table`（标题行库、Word 同步工具、上年附注导入共用）：
  - 表头行数 `_header_row_count`：只有带字的合并格撑开表头、只有带字的合并格让所在行免于截断；本行起始格全空白的行（空白占位行）、首格从首列通栏的行（分类行）是数据行。
  - 表头空白格归一 `_normalize_header_gaps`：下一行子表头从空白格跨进相邻分组 ⇒ 并入那个分组；左邻是分组、右邻不是、且同一上级 ⇒ 列名属左邻分组（国企 八、4:5「本期变动情况/其他变动」、上市 五、15:3「期末余额/逾期本金」）；否则列名是独立一列、提到空白格（国企 八、11:1「原因」、上市 五、18:0「减值准备期初余额」）；左右都是分组时分不出，按独立列。四版 Word 里全部出现处逐条钉住，归一只动这些表。
  - `seed_multi_header` 输出种子格式；Word 同步工具删本地 `detect_header_row_count` / `build_multi_header` 改调它，并把多行表头表的 `leaf_headers[0]` 取为标签列表头（原取末行的空串 ⇒ 单体标题同步的「首列不匹配」保护失效）。dry-run 对比：单体标题同步少写 23 处错位表名（如上市 五、4「期末本公司已质押的应收票据」→「续：」），新提示 2 处（国企 八、64:3 / 上市 五、62:3 →「营业收入、营业成本按商品转让时间划分」，原先数据行「主营业务」被当成表头、首列判不上）。
- 换成 Word 多级表头并重算分组（17 张）：国企 五-5-1、五-9-6、五-13-2、五-18-1、五-19-2、五-19-9、五-19-10、五-22-1、五-22-2、五-29-1、五-55-8；上市 五-10-8、五-11-3、五-18-1（「减值准备期初余额」提到空白格）、五-24-2、五-78-9、十六-3。
- 被误升进表头的数据行退回表体（12 张，表头行数按 Word 网格人工核定 = 平台判定）：国企 五-57-2、五-64-4；上市 九-1-27、九-1-28、五-9-4、五-9-5、五-9-6、五-9-7、五-10-1、五-11-1、五-62-4、三-重要会计政策会-1；表体 = Word 数据行（误修重复插入的行去掉）。
- 人工定 1 张：上市 六-1-2 开发支出，Word 第 0 行第 4 格空白、左右「本期增加」「本期减少」都是分组，平台按独立列；种子按语义并入「本期减少」（确认为无形资产减少开发支出余额，国企同表、上市单体同表都在「本期减少」下）。
- 平表头：全部多级表头表的 `headers` 改为展示表头逐列全路径（「/」连接，与 `ColumnKey.label`、前端「合并 headers 取最后一段」同口径；Word 留白的标签列保留原占位名）—— 国企 92 张、上市 118 张。原平表头只在分组起始列写首行文字（国企 五-24-1 `期末余额 | 期初余额 | "" …`），单读时把「期末余额/减值准备」当期初。
- 上市 五-9-4~7 保留 8 个网格列（Word 有一列死重复列），不折成 7 列（已保存数据按列号存）。
- 不修：国企 五-11-2 —— Word 同步工具按标记推章节号，国企错一节（Word 八、11 合同资产 → 种子 五-11），该表是存货跌价准备的行套了合同资产减值准备的表头；平台规则改后 dry-run 在它上面提示写入表头（P1-A），属既有错位，需另立 spec 按章节重对齐（会动 `consol_note_data.section_id`）。
- 待人工核对（Word 网格列数与种子不同，不猜）：国企 五-12-2、五-15-1、五-16-1、五-17-1、五-18-3、五-21-1、五-23-2、五-28-1、五-31-1、五-64-1、五-65-4、五-79-1，上市 九-1-3。
- 列数不变（已保存数据按列号存，不迁移）；国企 五-57-2 / 五-64-4 真库已保存 14 条全空。测试项目已保存的快照未迁移。
- 一次性修复脚本用完即删，删除 `_fix_missing_multi_header.py`；守卫测试 `test_consol_note_seed_header_repair.py` 在测试时解析 Word，逐表比对修复后的逐列路径（期望值来自 Word，不写死）。

### 15.4 核销 = 减少（R6.4）

词表 `movement_words` 把「核销」从方向不定移到减少（坏账准备变动表「本期核销」减少余额）。最长词优先不变：「转销或核销」本来就按减少。

### 15.5 单元格汇总只从下级附注取数（R6.5）

`/aggregate`（`consol_note_sections.aggregate_data`）下级没有该章节附注数据时用 `_load_tb_map` 取下级试算表审定数兜底 —— 违背「个别数从单体附注拉、不从试算表来」。改为：只汇总下级已保存的合并附注数据；没有附注数据的下级不计入，响应 `missing_children` 列出（企业名 + 原因），前端提示「以下下级没有附注数据，未计入」。

### 15.6 上年附注导入找列（R6.6）

`note_prior_year_import_service` 把上年 Word 表的期末列按行名填进本年表的期初列，分组表找不到列 / 填错的原因：

1. 本年一侧：`_header_index` 只在平表头 `headers` 里按子串找「期初 / 年初 / 上年末 / 上期末」，不看 `_column_groups` / `columns[].group` / 多级表头 / 表名期间；分组表平表头里期间只写在组首列或全是空串 ⇒ 找不到，或只找到第一列（「期初数/账面余额」找到、「期初数/坏账准备」「期初数/账面价值」漏）；「上年年末」「上期」不在词里。
2. 上年一侧：只读 Word 表第一行当表头，按原始 `w:tc` 位置取值（不按网格）⇒ 多级表头的期间在第一行、计量在第二行，横向合并单元格让列位置错开。
3. 表按位置 `zip` 配对（Word 第 i 张 ↔ 章节第 i 张），表数或顺序不同就配错；对不上返回 0，不报。
4. 解析跳过内容控件 `w:sdt` 里的内容（平台导出的交付件每节都包在内容控件里 ⇒ 整份解析为空）；表前题注被丢弃，没法按表名配对。

新做法（一条路径，旧端点与新端点共用）：

- 解析：`note_word_tree._iter_blocks`（下钻内容控件）+ `note_word_table.parse_word_table`（网格、多级表头、逻辑列）扩展数据行取值；表名 = 表前最近的非空段落。
- 对应：本年表的期初一侧金额列（`period_side=previous`）← 上年表期末一侧同计量列（期间整体平移：期末→期初、本期→上期，再走 `match_columns`）；表按表名（`base_key`，期间括注与续表标记归一，本年「（续：期初数）」对上年「（期末数）」）+ 列对上数选，唯一最优才自动；行按「行名 + 同名序号」。
- 认不出的不再静默丢：每张有期初列的本年表给出状态 `auto` / `needs_confirm` / `no_source` 与原因；预览 → 弹窗逐表确认（可改选上年表、逐列指定或不导入）→ 写入。写入时重传文件并校验 sha256（无服务端临时存储）。
- 原端点保留：只写 `auto` 的表（与弹窗默认勾选一致），响应多报待确认表数。

### 15.7 公式种子取数列 `value_column`（R6.7）

现状：`plan_seed`（a）把章节主表合计行种成 `REPORT(报表行)`，（b）把带科目码的表行按报表行公式的系数种成 `TB(...)` 组合；列由 `value_column` 定：

- 路径 A 只看顶层 `_column_groups`，组名命中「期末…」就返回该组 `start`，即组内第一个叶子列 —— 分组表里几乎都是「账面余额」（毛额）。
- 报表行常是净额：资产负债表行公式带减项（应收账款 BS-006 = 1122 − 1231，见 `row_account_terms`），净额 = 账面价值，种进「账面余额」列就是错列。
- 种子表头本身错位时（15.3，如国企 五-29-1 商誉套了开发支出的子表头）组的 `start` 也错 ⇒ 种到别的期间 / 计量列。
- `ensure_seeded` 在模板文件或报表配置变化时自动重种，人工没碰过的种子跟着规则走。

新规则（调标题行库逐列语义，`column_keys` 与展示同口径）：期间取资产负债表行「期末」、利润表行「本期」（无则取同侧另一期间，沿用「未分配利润用本期金额表头」）；该期间的金额列中 —— 纯期间列唯一 ⇒ 取它；否则报表行（b 类为该行自身公式）有减项 ⇒ 取唯一的账面价值列；否则取唯一的账面余额 / 公允价值列；都不唯一 ⇒ 不种并写原因（列出候选列）。毛额 / 坏账准备分列另种不做（报表公式里的减项常跨科目共用，拆不确定）。

### 15.8 实施记录

**V2 下线（任务 24~26）**

- 删除范围比 15.1 多三处同族死代码（删前 grep 0 调用方）：`consol_report_service` 里另一份 7 骨架附注生成器（无路由、无调用方，构造 `ConsolDisclosureSection` 时传的 `content_type / summary / 中文键行` 都不是 schema 字段 ⇒ 产出空行）、`ConsolDisclosureRow / ConsolDisclosureSection`、`dataset_query.bind_to_active_dataset_sync`（只给旧生成器的同步会话用）。
- `consol_aggregation` 取数源删除后单元格取数源 9 → 8：前端单元格编辑器的「合并汇总」选项一并删；绑定 JSON 本来就只有 8 项（HEAD 上 `test_binding_json_valid_sources_match` 一直红，本批修好）；残留的旧绑定按「未识别取数源」返回 None。
- 一键刷新第 6 步：`consol_push_service.refresh_notes_exclusive` = 推送同一把锁 + `_refresh_notes`；第 4 / 5 / 6 步失败先回滚本步（PG 上失败语句让事务 aborted，原来报表步失败会连带附注步失败）。
- 台账：coverage ledger 删 5 条 HTTP 条目、附注写端点清册删 3 条、edit 级影响清单删 5 个门禁点、领域边界债务基线删 6 条已消解的依赖边 —— 都先核对计数与条目一致再按差量改。这些台账在 HEAD 上本就有别的漂移（清册 `--check` 红、ledger 缺 219 条、领域边界新增 217 条），不在本 spec 范围。
- `disclosure_notes.source_project_id / consolidation_breakdown` 两列保留（真库 0 行有值、现无读写方），删列要另起迁移。

**核销 = 减少（任务 27）**

- 词表 `movement_words.decrease` 加「核销」（原在方向不定）；坏账准备变动表「本期核销」按减少参与勾稽（期末 = 期初 + 计提 − 转回 − 核销），不再按方向不定跳过整行。库测试 `test_write_off_is_a_decrease` 与最长词用例钉住；库目录随任务 29 一并重生成。

**单元格汇总只从下级附注取数（任务 28）**

- `consol_note_sections.aggregate_data`：删 `_load_tb_map` 兜底；只汇总各下级已保存的合并附注同位置值；下级没有该章节附注数据 ⇒ 不计入，进 `missing_children`（`node_key / name / reason="没有附注数据"`）；这一格为空记 `empty_count`；`message` 拼「N 家下级这一格没有数」「N 家下级没有附注数据，未计入」。
- 前端：`consolNoteView.cellAggregateSummary` 把响应归成成功 / 普通提示（只是这一格为空）/ 告警（有下级没有附注，提示先「📋 明细映射」或「🔄 重新汇总」）/ 汇总失败（错误信封）；`ConsolNoteTab.applyCellAggregate` 按它提示。后端测试断言试算表取数器不被调用（`tb_loader.assert_not_called()`）。

**种子多级表头修复（任务 29）**

- 平台规则与逐表结果见 15.3。只去掉「撑开表头只认带字的合并格」这一侧，四版 Word 1366 张表结果不变（截断规则已覆盖全部现有表）；保留它，用合成表钉住截断规则认不出的行（首列留白 + 本行有字 + 两格一并的空白取数格）。
- 标题行库：词表加 `net_measures: ["账面价值"]`；列对应加 `period_balance` 规则 —— 一侧是纯期间列、另一侧同期间有多列时，取唯一的账面余额 / 公允价值列（另一侧有净额列则不取），两个方向都做。效果：国企 五-5-1、五-9-6 与 十一-关联方应收应付款-1 现对上 2~3 列（原先「只写了期间」的列对上同期间多列即整列放弃）。库目录覆盖率 国企 0.7774、上市 0.9015，表头异常 0；目录测试棘轮同步、异常断言改为 `header_defects == set()`。
- 生成产物重生成并逐条审：映射 `consol_note_section_mapping.json`（上市 五-11-3 → 按结构对上「持有待售资产减值准备」）、库目录、Word 目录核对白名单 749 → 721 条（只减不增）。
- Word 同步工具 dry-run（改前 / 改后）：合并模板 Phase 1 只剩国企 五-11-2 一处提示（15.3「不修」）；单体标题同步见 15.3。
- 平表头改成全路径后，旧用例 `test_template_header_rows_beat_misaligned_flat_headers` 的前提（平表头错位）不再成立：改为断言平表头与展示表头逐列同路径，并把旧式错位平表头放回副本、断言角色仍按展示表头。
- 变异 15 条全红（基线全绿）：表头行数三条（空白合并格撑开表头 / 空白合并格让数据行免于截断 / 空白行与通栏行不截断）、空白格归一三条（不归一 / 并左不看同一上级 / 左邻分组也按独立列）、标题行库三条（纯期间多列不取唯一余额列 / 不看净额列 / 词表去掉净额计量）、种子六条（六-1-2 改回平台版 / 平表头改回旧版 / 五-18-1 不上提 / 空白占位行又升进表头 / 五-11-1 表体改回 / 五-9-6 表头不归一）。
- 回归：引用本轮改动模块 / 数据的 66 个测试文件，基线树（HEAD `bb6ba02ce`）151 失败，本批 152 失败；多出的 `test_consol_push.py::TestPush::test_upper_levels_pushed_bottom_up` 单跑、同序前缀重跑、整文件重跑均通过（偶发，断言是推送整体状态）；其余 151 条两边相同（`test_consol_note_headers.py` 147 条 CP04 旧契约、种子计数 2、推送往返 1、契约锁 1，HEAD 上本就红）。
