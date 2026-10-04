# d1-sync-row-table-engine-and-d1-coverage Task 17 交付复盘（2026-09-26 续 3）

**背景**：Task 16（D3/D6/D7）完成并被并发进程正确整合入 HEAD 后，继续推进 Task 17（D5 声明化，
design 明确其为"内联 7 元组来源家 + 无账龄组"的零改动对照）。开工前先 `git fetch` + 检查工作树，
确认 D2/D3 相关文件有并发进程正在进行中的改动，遂避开，选择未被触碰的 D5 作为下一个独立单元。

## 完成内容

D5（无账龄，最简单一家）引擎函数层收敛：

1. 新增 `SPEC_D52: RowTableSheetSpec`，`field_specs` **直接引用**原 `MANAGED_FIELD_SPECS`
   常量（因为它本来就是内联 7 元组，design 裁决 3 的基准源——不需要转换）。
2. 删 6 个引擎函数（D5 无 `_aging_field_specs`，比 D3/D6/D7 少一个）改薄转发。
3. 补齐 D5 原自带的 `_col_index` 函数体收敛（Task 5 当时只覆盖了 D2/D3/D6/D7 四家，D5 遗漏；
   本次一并补上，且发现收敛后 `_col_index` 别名已无调用方，作为死代码清理而非保留）。
4. 减少约 100 行（911→810），与 D3/D6/D7 收敛幅度一致。

## 零改动对照验证（design 明文要求的关键判据）

用真实生产模块（非合成数据）验证 `managed_field_specs(SPEC_D52) == MANAGED_FIELD_SPECS`
逐字节相等 → `True`。这是 design 反复强调的裁决 3 验证点："D5 原本就是内联 7 元组 ⇒ 它是
裁决 3 的零改动对照，若它 digest 变了说明引擎理解错了"。已补 3 条判据钉住（零改动对照本身 /
幽灵行锚点字段身份 / 无账龄声明），补在既有 `test_phase5_row_table_sheet.py` 内。

## 变异检验

把 `formula_columns` 从 4 列改成 3 列（缺 O 列），触发**契约装配层**（`contracts.py` 的
`_parse_table`）一致性校验立即 fail-closed：`ContractSchemaError: 字段 'end_audited' 的列
O 不在 formula_mask 覆盖的列跨度内 —— formula 字段必须被只读区域覆盖，否则 OO 便修改会
覆盖公式结果`。这是比"digest 不匹配"更强的信号——错误在装配阶段就被拦住，不会有机会产生
错误的公式覆盖行为。还原后零回归恢复。

## 复用 Task 16 的框架层缺口修复

D5 与 D6 是同款幽灵行防护例外（`[0]`=`category` 枚举 / `[1]`=`item_name` 才是真名称），
D5 原实现的 docstring 早已明确写"D5 首列是枚举类别，不是自由文本名称"——这佐证了 Task 16
新增的 `RowTableSheetSpec.ghost_row_anchor_index` 参数是真实需求（不是我误判的孤例），
D5 声明同样设 `ghost_row_anchor_index=1`，零额外框架层改动即可复用。

## 验收结果

- golden digest 零回归（26 个，未受 D5 改动影响）。
- 144 个相关判据全绿（新增 3 条）。
- 2 个改动文件（`phase5_d5_receivables_financing.py` + 判据文件）0 diagnostics。
- 既存 `test_ghost_row_defense.py` 2 条 D5 用例零回归。

## 尚未完成

同 Task 16：`_rows_table_payload`（契约装配）/ `publish_definitions` / `attach_adapters`
等发布编排代码尚未拆分/精简，D5 仍 810 行，远超 design 要求的 ≤150 行上限——本轮只收敛了
引擎函数层。

## 并发环境处置记录

开工前确认 `phase5_d2_01_adjudication.py` / `phase5_d2_03_bad_debt.py` / `pilot_d2_large_json.py`
/ `phase5_d3_prepaid_receipts.py`（在我之前工作基础上又被改）及新文件 `phase5_d3_expansion.py`
/ `phase5_d3_06_related_party.py` 均有并发进程未提交改动，本轮全程未触碰这些文件，只做
D5（此前无任何并发标记）。这是延续上一轮"识别热点区域、只对自己负责的文件精确 stage"的处置
原则。
