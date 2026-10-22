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
