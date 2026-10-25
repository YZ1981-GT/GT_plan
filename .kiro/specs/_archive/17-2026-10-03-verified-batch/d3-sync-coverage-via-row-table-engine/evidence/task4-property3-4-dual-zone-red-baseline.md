# Task 4 Property 3 / 4 红判据证据：D3-4 与 D3-7 是双区

**实测日期**：2026-09-26　**方法**：读取当前 HEAD 已存在的 D3 唯一 provider
`phase5_d3_prepaid_receipts.py` 的磁盘契约现算结果 + 用 `contracts.py` 数据类构造合成
`SheetSpec`/`TableSpec` 做变异检验。全程离线，未连库、未改任何生产代码。新增文件仅一个测试
文件 `backend/tests/workpaper_sync/test_d3_property3_4_dual_zone_baseline.py`。

## 一、受管区计数口径的定位

**先确认这件事没有专用统计脚本，只有一套散布全仓的遍历惯用法。**

Grep `verify_unmanaged_regions` 全仓确认：这个函数是「漂移校验」（比较 before/after 字节是否
一致），不是「受管区计数」。真正的计数口径来自已落地的姊妹判据文件
`backend/tests/workpaper_sync/test_d1_instrumentation_specs_expansion.py`
（docstring 原话：「受管区计数：1 → 2(D1-2) → 4(D1-4 前两区) → 5(+静态第三区)」）与
`test_e1_provider_and_expansion.py`（"Task 13/14：逐张开关生效、受管区按预期增长"）——
这两份文件的计数方式是调用循环层编排模块（`phase5_d1_expansion.py` /
`phase5_e1_monetary_fund.py`）暴露的 `instrumentation_specs()` 函数，取 `len(specs)`。

**D3 侧现状没有这一层编排模块**（Task 0 证据已确认：`phase5_d3_02_detail.py` 及同类拆分模块
均不存在于 HEAD，D3 目前只有一份单体 `phase5_d3_prepaid_receipts.py`，无 `_INCLUDE_*` 开关、
无 `instrumentation_specs()` 聚合函数——这层编排是 Task 6/8/9/11 才会新建的东西）。⇒ 此刻唯一
可现算的计数口径退回到更底层的**磁盘契约结构本身**：`SyncContract.sheets[].tables[]`。

全仓 grep 确认这是**唯一**的受管区遍历逻辑（无第二套竞争性定义），处处以同一个双层 for 循环
出现：

```
contracts.py:734          for sheet in contract.sheets: for table in sheet.tables:（all_fields）
published_identity_observer.py:401/458   for sheet in contract.sheets: for table in sheet.tables:
projection_first_publication.py:850/886/893  同上
merge.py:734               for sheet in contract.sheets: for table in sheet.tables:
excel_materialize.py:1141/1331/1350/2035/2099/2196/2490   同上（6 处）
excel_extract.py:957/1247   同上
excel_entry_gate.py:365/478/737   同上
```

⇒ 本任务的计数函数 `_managed_region_count(sheets) = sum(len(sheet.tables) for sheet in sheets)`
不是自造口径，是把这套全仓一致的双层遍历收成一个求和表达式，语义与
`test_d1_instrumentation_specs_expansion.py` 里 `len(specs)` 的意图完全对齐——一个 `TableSpec`
= 一个受管区，一张 sheet 可以有多个 `TableSpec`（D4-9/D4-1 的双区/三区范式）。

## 二、D3-4 / D3-7 当前受管区计数实测值

调用 `phase5_d3_prepaid_receipts.assert_contract_file_matches_source()` 取回磁盘契约（该函数
本身会先比对磁盘契约与模块现算 payload 的 digest 一致，双向锁死，不会拿到过期契约），实测：

| 项 | 实测值 |
|---|---|
| `contract.sheets` 长度 | **1**（仅 `d32-managed`，即 D3-2 明细表） |
| 该 sheet 的 `tables` 长度 | **1**（`prepaid_receipts_detail_rows`，D3-2 的单一动态行表） |
| **受管区计数合计** | **1** |
| 契约字段里含 `ana-debit`/`ana-credit`（D3-4 分析表两键） | **0 个字段命中**（尚未声明） |
| 契约字段里含 `vc-current`/`vc-post`（D3-7 检查表两键） | **0 个字段命中**（尚未声明） |

这与 design.md 记录的路线起点值「1 (D3-2 已接)」逐字一致，也与 Task 0 证据「D3 侧现状只有
D3-2 一个受管区」的判定一致。

D3-4 双区接入目标计数是 **4**（design.md「阶段 2 验收：受管区 2→4」），D3-7 双区接入目标计数是
**7**（design.md「阶段 3 验收：受管区 5→7」）。实测现状 1 < 4 且 1 < 7 ⇒ 两条红判据此刻均**必红**
（这里的"红"指"接入后应转绿的目标状态此刻确认仍是红的"，判据代码本身运行结果是 PASSED——因为
判据断言的正是"现在还没到 4/7"这件事为真）。

## 三、变异检验的构造方式与实测结果

D3-4/D3-7 的真实 `RowTableSheetSpec` 声明代码尚不存在（Task 8/11 待做，依赖 Task 6/7 先跑通
「多受管 sheet 在 D3 上成立」），故不能通过修改真实生产代码做变异（那是 Task 8/11 的工作，
本任务不越界去写）。变异检验改用**合成 `SheetSpec`/`TableSpec`**，直接调用
`contracts.py` 里已冻结的数据类构造函数，验证"只声明一个受管区"这个缺陷形态能被计数逻辑与
字段存在性检查同时捕获。

**合成契约的几何边界不是拍的**，取自 Task 1 证据文档的实测行段：

- D3-4：段①借方 `A13`（差异公式 footer 落在"差异"标记附近）/ 段②贷方 `A22`（footer 落在
  "差异合理性分析"标记附近），与 `useD3Analysis.ts` 的 `ITEM_ID_DEBIT_ROWS='D3-ana-debit-rows'`
  / `ITEM_ID_CREDIT_ROWS='D3-ana-credit-rows'` 键名对齐。
- D3-7：区①本期 `A17`（footer "合计" 携带 SUM 公式）/ 区②期后 `A31`（同款 footer），与
  `useD3VoucherCheck.ts` 的 `ITEM_ID_CURRENT_ROWS='D3-vc-current-rows'` /
  `ITEM_ID_POST_ROWS='D3-vc-post-rows'` 键名对齐。
- 双 table 同 sheet 的结构范式参照已落地的 `phase5_d4_customer_structure.py`（D4-9，同
  `managed_sheet`、不同 `table_key`，两个各自独立的动态行 `TableSpec`）。

**三组变异，逐一验证判据有牙齿**：

1. **D3-4 只声明段①（借方）**：完整双区对照组计数 2 → 变异组计数 1，且合成字段集合里
   `D3-ana-credit-rows/label` 从存在变为不存在。断言 `assert "..." not in mutated_keys` 通过，
   证明"贷方键在 OO 视图里不可见"这个缺陷能被检出（OO 端渲染的受管字段来自契约
   `all_fields()`，缺字段 = 该 store 键对应数据在 OO canvas 上没有对应单元格）。
2. **D3-7 只声明区①（本期）**：同款验证，完整双区计数 2 → 变异组计数 1，
   `D3-vc-post-rows/customer` 从存在变为不存在。
3. **额外变体（更贴近真实容易犯的错）**：不是"整个漏声明"，而是把借贷两区**误合并成一个
   `table_key`**（命名从明确的 `analysis_debit_rows`/`analysis_credit_rows` 改成模糊的
   `analysis_rows`，design.md 明确禁止的形态）。验证即便换了个含糊的名字，`credit` 键的缺失
   依然能被检出，不会被"table_key 改名"蒙混过关。

**独立于测试文件之外的复核**（避免"测试断言恰好写对了但底层其实没变化"的假阳性）：直接在
Python REPL 里调用 `_synthetic_dual_zone_sheet` 构造对照组与变异组并打印实测值：

```
full_count= 2
mutated_count= 1
mutated_keys= {'D3-ana-debit-rows/label'}
credit_still_visible= False
```

三项数字与字段集合与测试断言内部预期完全一致，证明这不是断言写反凑巧通过，而是真实构造出的
dataclass 结构确实呈现了"退化成单区、另一键消失"的效果。

## 四、命令 + 完整输出摘录

```
$ rtk python -m pytest backend/tests/workpaper_sync/test_d3_property3_4_dual_zone_baseline.py -v --tb=short

============================= test session starts =============================
platform win32 -- Python 3.12.8, pytest-9.0.2, pluggy-1.6.0
collected 6 items
test_current_d3_managed_region_count_is_pre_expansion_baseline PASSED          [ 16%]
test_d3_4_dual_zone_not_yet_reaching_target_count_of_four PASSED               [ 33%]
test_d3_7_dual_zone_not_yet_reaching_target_count_of_seven PASSED              [ 50%]
test_mutation_d3_4_declaring_only_debit_zone_loses_credit_key_visibility PASSED [ 66%]
test_mutation_d3_7_declaring_only_current_zone_loses_post_key_visibility PASSED [ 83%]
test_mutation_merging_into_shared_table_key_still_loses_one_key PASSED        [100%]
============================== 6 passed in 1.21s ==============================
```

回归复核（确认没有破坏姊妹判据文件，计数口径与 D1/E1 的既有先例一致）：

```
$ rtk python -m pytest backend/tests/workpaper_sync/test_d3_property3_4_dual_zone_baseline.py
      backend/tests/workpaper_sync/test_d1_instrumentation_specs_expansion.py
      backend/tests/workpaper_sync/test_e1_provider_and_expansion.py -v --tb=short

collected 30 items
... 全部 30 PASSED ...
============================== 30 passed in 2.08s ==============================
```

**过程中一处需要如实记录的插曲**：首次编写合成契约时错误引用了不存在的枚举成员
`RowIdentityKind.hidden_uuid_column`，导致 3 条变异检验测试报 `AttributeError`（不是判据打红，
是测试脚手架本身的枚举名写错）。核实 `contracts.py:196` 的 `RowIdentityKind` 真实只有两个成员
`field` / `template_row_key`，D3 的隐藏 UUID 列身份属于「以字段形式暴露在 JSON payload 里」
（`json_pointer="/rows/*/rowId"`），对应 `RowIdentityKind.field`（不是"隐藏列"这个物理存储
形态本身对应一个专门枚举值——枚举描述的是行身份*来自哪里*，不是*物理上藏在哪一列*）。修正后
全部 6 条测试通过。这个插曲印证了记忆规约里"引用枚举前用代码实证核对大小写/成员名"的必要性。

## 五、结论

- D3 现状受管区计数为 **1**（仅 D3-2），D3-4 目标 4 / D3-7 目标 7，两条差距判据此刻均确认
  "现状必红"（即：断言"还没达到接入后目标值"这件事此刻为真）。
- 判据"有牙齿"：三组独立变异（D3-4 漏声明贷方区 / D3-7 漏声明期后结转区 / 借贷两区误合并成
  单一 table_key）均被判据检出，且用测试文件之外的独立 REPL 调用交叉复核过实际构造出的
  dataclass 结构，不是断言凑巧通过。
- 未修改任何生产代码；未产生任何一次性探针脚本残留。
