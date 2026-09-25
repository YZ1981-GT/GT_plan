# d1-sync-row-table-engine-and-d1-coverage Task 16 交付复盘（2026-09-26 续 2）

**背景**：Task 10/13/14 完成、d567 阻塞解除后，继续推进 Task 16（D3/D6/D7 声明化，nested+flat
两账龄形态同批对照）。

## 完成内容

D3（nested）/ D6（flat）/ D7（nested）三家的**引擎函数层**收敛完成：

1. 各家新增 `SPEC_D{32,62,72}: RowTableSheetSpec` 作为唯一权威声明（复用现有几何/字段/账龄
   常量组装，不重新实测——常量已在 HEAD 且被 golden digest 验证过）。
2. 删除 9 个引擎函数体（`_aging_field_specs` / `stable_key_for` / `store_row_identity` /
   `iter_store_rows` / `_resolve_json_path` / `split_store_row` / `build_store_projection` /
   `_set_json_path` / `merge_projection_into_store_rows`），改为薄转发框架层
   `phase5_row_table_sheet` 同名函数。`MANAGED_FIELD_SPECS` / `FORMULA_MASK` 两个既有常量名
   保留，值从 `SPEC_D*` 派生（不改名，供既有调用方零改动）。
3. 三家各减少约 100 行（973→869 / 975→878 / 971→874）。

## 关键发现：D5/D6 的幽灵行防护锚点不是默认第 0 位（框架层缺口修复）

D6 原实现 `merge_projection_into_store_rows` 用 `MANAGED_FIELD_SPECS[1]`（`contract_name`）
判定幽灵行，**不是 `[0]`**（`seq_no`，整数序号，`0` 是合法真值不是"空"信号）。框架层原实现
硬编码 `specs[0][4]` 无法表达这条差异——直接薄转发会让 `seq_no=0` 的合法新行被误判剔除。

排查确认 D5 也是同款例外（`[0]`=`category` 枚举，`[1]`=`item_name` 才是真名称）。给
`RowTableSheetSpec` 新增 `ghost_row_anchor_index: int = 0` 字段（默认值向后兼容 D1/D2/D3/D4/D7
现状），`merge_projection_into_store_rows` 改用 `specs[spec.ghost_row_anchor_index][4]`。
D6 声明 `ghost_row_anchor_index=1`。用既存判据 `test_ghost_row_defense.py::
test_d6_ghost_row_dropped_and_seq_no_alone_is_not_enough` 验证正确（该判据非本轮编写，
独立验证）；另补 4 条新判据（含正/反两侧对照）钉住该参数的语义。

## 事故：str_replace 大块匹配截断产生孤儿代码

改 D6 的 `merge_projection_into_store_rows` 时，`str_replace` 的 `oldStr` 因原函数体比
D3/D7 略长而在中间截断匹配，导致替换后遗留了函数体尾部两行孤儿代码（`touched_rows -=
ghost_ids` + `return [...]`）引发缩进错误。`ast.parse` 立刻抓到（IndentationError）。

**教训固化**：大块代码替换后必须立刻 `ast.parse` 验证语法，不能假设"内容像是对的"就跳过——
这条纪律本次执行到位（没有把语法错误的代码带到下一步），但暴露了"复制同构改法到第三个文件
时不能machinery照抄，必须逐个读取真实边界"的操作纪律。已回查 D3/D7 的同批改动，确认那两次
`str_replace` 匹配完整（`ast.parse` 均一次通过），本次事故只影响 D6。

## 事故：golden digest 漂移排查（区分真回归 vs 基线过期 vs 脚本口径升级）

改完 D6 后过门报 `[d6] store_projection_sha256` 漂移。排查发现**三层原因交织**：

1. 并发进程同期新增了 E1（第 9 家 provider）并升级了脚本本身——加入 `sheet_digests` 逐 sheet
   粒度检测（区分"扩容新 sheet" vs "改动已有 sheet"），且脚本文件本身处于 `M`（未提交改动）
   状态，与我的改动无关。
2. 脚本的 `_synthetic_rows` 合成数据生成规则同期升级：新增 `"integer"` 类型也填数值占位
   （原来只有 `"amount"` 填数值，`"integer"` 被错误当字符串填充）。D6 有 `seq_no: integer`
   字段，D2 也有整数字段，二者的 `store_projection_sha256` 因此随口径升级而改变——**这不是
   生产代码回归**，是测试数据生成规则本身的独立改进。
3. 用 `contract_payload_sha256` 精确比对确认：D3/D6/D7 三家的 `contract`/`instrumentation`
   digest 均逐字节不变（与我改造完成时记录的值完全一致）；只有依赖 `_synthetic_rows` 口径的
   `projection` digest 因规则升级而变化，且仅影响含 `integer` 字段的 D2/D6，不影响 D3/D7。

**处置**：`--update` 重取真实当前基线（纳入 E1 + 新口径），过门确认 26 个 digest 零回归。
未回退任何我自己的改动——独立验证已确认它们无关。

**教训固化**（第二次遇到同类问题，已两次登记）：并发环境下 golden digest 门的"漂移"必须先
分类溯源（`git status` 查文件是否有非本人改动 / 对比 contract 与 projection 两段 digest 分别
定位 / 检查脚本自身逻辑是否变化），不能不假思索地假设是自己的回归就去改代码"修复"。已在脚本
的漂移提示里补充排查顺序说明（本次登记的第二条固化，第一条见 part2.md）。

## 变异检验

- Property 4（nested/flat 互不污染）：把 D6 的 `aging_layout` 从 `flat` 错改成 `nested`，
  触发框架层 `expand_aging_fields` 的一致性校验立即 fail-closed（`ValueError: 段与标签必须
  一一对应`）——在模块导入阶段就被拦住，不会产生任何错误数据。
- Property 8（stable_key_for 泛化）：延续 Task 10 的变异（此前已验证）。
- 幽灵行防护锚点参数化：4 条新判据含正反两侧对照（默认锚点=0 时 seq_no=0 被误剔除 / 改锚点=1
  后仍需名称字段有值才保留 / 双字段皆有值时正确保留 / 默认值向后兼容）。

## 验收结果

- golden digest 零回归（26 个，含新纳入的 E1）。
- 141 个相关判据全绿（新增 4 条幽灵行锚点判据）。
- 5 个改动文件（D3/D6/D7 + 框架层 phase5_row_table_sheet.py + 判据文件）0 diagnostics。
- 既存 `test_ghost_row_defense.py`（16 用例，覆盖 D1/D3/D5/D6/D7）零回归，证明薄转发未改变
  任何一家的幽灵行防护行为。

## 尚未完成

Task 15/16 的"provider ≤150 行"目标**未达成**——本轮只收敛了引擎函数层（9 个函数、约 100 行/
家），design 需求 2.1 要求的完整收敛（契约装配 `_rows_table_payload` / 发布编排 `publish_
definitions` / `attach_adapters` 等也要拆到独立文件或大幅精简）尚未开工，三家仍是 869~878 行。
真正达到 ≤150 行需要把 provider 拆成"循环层身份常量+发布编排"与"sheet 层几何+字段+契约装配"
两个文件，工作量大于本轮已完成部分，如实标注为下一步。
