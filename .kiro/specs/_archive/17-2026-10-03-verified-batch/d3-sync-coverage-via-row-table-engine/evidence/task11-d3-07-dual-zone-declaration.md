# Task 11 证据：D3-7「预收账款检查表」双区声明

**执行日期**：2026-09-26　**任务**：Task 11（`phase5_d3_07_voucher_check.py` 声明**两个** spec）
**Requirements 3.1**　**方法**：openpyxl 直读权威模板独立复核 + 引擎构造验证 + 三判据 + 全量 D3 回归。
全程离线、未连库、未改引擎/模板。一次性探针脚本（`_tmp_d37_probe.py` / `_tmp_d37_payload_check.py`）用完即删。

---

## 一、openpyxl 独立几何复核（不盲信 Task 1 / Task 10 §5 转述）

命令：`openpyxl.load_workbook("wp_templates/D/D3 预收账款.xlsx", data_only=False)` →
sheet「预收账款检查表D3-7」（max_row=48 max_col=18），逐格扫描关键行 A..R + 合并格 + 候选空列 + 全表公式。

### 1.1 两区行段（与 Task 1 + Task 10 §5 三方一致）

| 区 | 组标题行 | 叶子行 | 数据区 | 合计行 | store 键 |
|---|---|---|---|---|---|
| 区①本期增减变动检查 | R15 | R16 | **R17-26（10 行）** | R27 `A27='合计'` `G27='=SUM(G17:G26)'` `H27='=SUM(H17:H26)'` | `D3-vc-current-rows` |
| 区②期后结转检查 | R29 | R30 | **R31-38（8 行）** | R39 `A39='合计'` `G39='=SUM(G31:G38)'` | `D3-vc-post-rows` |

两区 SUM 区间与数据区行数逐项对齐（区① 17-26 / 区② 31-38），**无 D3-6 那种 SUM 落差**、
**无 D3-5 那种 marker 缺失**（A27/A39 都是精确「合计」两字，可被 `_find_marker_row` 命中）。

### 1.2 🔴 BP-21 排版占位行末行核查（任务原文门禁要求，逐格实读）

对两区数据区末行（26 / 38）逐格读 A..R：**R26 与 R38 全格为 `None`**（不是 D3-4 那种
`A16=' ……'` / `A24='         ……'` 续行省略号占位行）。**⇒ 不命中 BP-21
`excel_typography_rows.is_typography_placeholder`，无需像 D3-4 段①末行 16→15 那样收缩，
`last_data_row` 直接用实测末行 26 / 38。** 逐行扫描区①（17-26）区②（31-38）全部 A..R，
除合并 anchor 外全为 None，是"画了外框等待填写"的纯空白占位行。

### 1.3 🔴 两级表头（本任务独立复核发现——Task 1 只记了行段没标两级）

不同于 D3-4/D3-5 的单级表头。两区各有组标题行 + 叶子行，合并跨列：

```
区① 合并：A15:A16 B15:H15(记账凭证) I15:I16 J15:N15(核对内容) O15:O16 P15:P16 Q15:Q16
区② 合并：A29:A30 B29:G29(记账凭证) H29:I30(支持性文件,🔴两行两列) J29:N29(核对内容) O29:O30 P29:P30 Q29:Q30
```

叶子行列语义（R16 / R30）：
```
区① R16: A=客户名称 B=日期 C=凭证编号 D=业务内容 E=对方科目 F=对方明细科目 G=借方金额 H=贷方金额
         I=支持性文件 J..N=核对内容(1..5) O=索引号 P=是否异常 Q=备注说明
区② R30: A=客户名称 B=日期 C=凭证编号 D=业务内容 E=对方科目 F=对方明细科目 G=贷方金额
         H:I=支持性文件(合并单列) J..N=核对内容(1..5) O=索引号 P=是否异常 Q=备注说明
```

### 1.4 🔴 两区列语义差异（不能照 D3-4 那样两区共用 field_specs）

D3-4 双区共用一份 `FIELD_SPECS_D304`（同一份单级表头）。D3-7 **不能**——两区 G/H 列语义不同：
- 区①：G=借方金额 + H=贷方金额（借贷两列分列，合计行 G27/H27 各自 SUM）
- 区②：G=贷方金额（无借方列），**H:I 合并为单列「支持性文件」**（合计行只 G39 一列 SUM）

⇒ 两区各声明一份 field_specs（`FIELD_SPECS_CURRENT` 17 字段 / `FIELD_SPECS_POST` 16 字段），
共用 `_base_spec()` 骨架（同 D3-4 手法，只是把 field_specs 也参数化）。

### 1.5 🔴 合并列 H:I 的处置（任务原文要求，参照 E1-02 合并列范式）

区② `支持性文件` = `H:I` 合并格（合并块值只在左上角 cell H）。**值写主列 H，不把 I 声明成
独立字段**（openpyxl 合并块语义：I 在合并块内是空 anchor）。区① `支持性文件` 落在单列 I
（`I15:I16` 只跨行不跨列）⇒ 区① I 是独立字段、区② 无独立 I 字段。这是两区字段数 17 vs 16 的
唯一差异来源。

### 1.6 UUID 候选空列

R/S/T/U 在 R14-44 实测**全空**。受管业务列止于 Q（备注说明）⇒ 选最靠近数据区的候选空列：
**区① UUID=R / 区② UUID=S**（两区各异，D1-4/D3-4/D4-9 教训：同列会让行身份串区），同 D3-5 选
I、D3-6 选 K 的"最近空列"原则。

### 1.7 数据行区间内无任何公式（不传 formula_columns）

全表 19 处公式：7 处页眉引用（`A3/F3/I3/Q3/A4/F4/I4`）+ 3 处 footer SUM（`G27/H27/G39`）+
9 处比例检查块（`E/F/G 42-44`）。**逐行确认区①（17-26）区②（31-38）数据行区间内无一处公式。**
⇒ 两区 field_specs 全部业务列 editable、**不传** `formula_columns`（`formula_mask` 现算为空），
合计 SUM 属 footer 层由 `footer_carries_total_formula=True` 表达（同 D3-4 段②/D3-5 处置）。

### 1.8 note/conclusion + 比例检查块（登记，不进 field_specs）

- A40「三、审计说明：」/ A45「2.……」/ A46「四、审计结论：」落在区②合计行（39）+ 比例检查块
  （41-44）之下 ⇒ HTML-only 候选（同 D3-4/D3-5/D3-6/D4-5），不进 field_specs。
- 比例检查块 R41-44（`F42='=G27'`/`F43='=H27'`/`F44='=G39'` 引用两区合计 + `E42..44` 跨 sheet
  引用 `'预收账款明细表D3-2'!M24/N24/T24` + `G42..44 =ROUND(...)`）是**纯派生汇总**，无行维度、
  用户不可增删 ⇒ **不是**第三个受管区（对齐 Task 1 结论）。

---

## 二、两 spec 声明落地

新建 `backend/app/services/workpaper_sync/phase5_d3_07_voucher_check.py`：

- `SPEC_D307_CURRENT`：`store_item_id="D3-vc-current-rows"`、`table_key="voucher_check_current_rows"`、
  数据区 17-26、合计行 27、组标题行 15/叶子行 16、UUID 列 R、`FIELD_SPECS_CURRENT`（17 字段）。
- `SPEC_D307_POST`：`store_item_id="D3-vc-post-rows"`、`table_key="voucher_check_post_rows"`、
  数据区 31-38、合计行 39、组标题行 29/叶子行 30、UUID 列 S、`FIELD_SPECS_POST`（16 字段，无 I）。
- 共享 `SHEET_KEY_D307="d37-managed"`（两区归一契约 sheet 含两 table，同 D3-4）。
- 两区 `row_identity_key='rowId'`、`store_kind=rows`、`footer_marker="合计"`（实测精确值）、
  `footer_carries_total_formula=True`（两区合计行都真有 SUM）。
- 两级表头传 `header_group_row`/`header_leaf_row`（同 E1-02 范式），不传单级 `header_row`。

store 键逐字对照 Task 3 判据 `REAL_STORE_ITEM_IDS` 表（`D3-7-current`→`D3-vc-current-rows` /
`D3-7-post`→`D3-vc-post-rows`），非 `D3-7-*` 推演（裁决 F2）。

引擎构造验证（离线）：`managed_field_specs(SPEC_D307_CURRENT)` = 17 字段、
`managed_field_specs(SPEC_D307_POST)` = 16 字段、两区 `formula_mask` = `()`、UUID 列 R/S。

---

## 三、循环层 `phase5_d3_prepaid_receipts._expansion_sheet_row_table_payload` 两级表头兼容修复

🔴 **本任务发现并修复一处会在 D3-7 翻开关时炸的 latent bug**：Task 6/8/9 落地的 D3-6/D3-4/D3-5
都是**单级表头**（只设 `header_row`），该 payload builder 硬编码了 `spec.header_row` 三处
（`header_source_ref` / `anchor` / `header_rows=1`）。D3-7 是 D3 扩容面**首个两级表头** sheet
（`header_row=None`，设 `header_group_row`/`header_leaf_row`）——原代码会生成 `"ANone"` 锚点、
`header_source_ref` 指向 None 行、`header_rows` 恒 1（几何错误）。

修复手法与已验证的 `phase5_e1_monetary_fund._rows_table_payload(spec)` **逐字一致**（同一引擎
的两级表头范式，非新造）：
```python
leaf_row = spec.header_leaf_row or spec.header_row or spec.header_group_row
anchor_row = spec.header_group_row or spec.header_row or leaf_row
is_two_level = bool(spec.header_group_row and spec.header_leaf_row)
# header_source_ref: 有组标题的字段取叶子行、其余取组标题行；header_rows: 两级=2
```

🔴 **零回归证明**：对 D3-6/D3-4/D3-5（`header_group_row`/`header_leaf_row` 均 None）下式退化为
`leaf_row=anchor_row=spec.header_row`、`is_two_level=False`、`header_source_ref=header_row 行`、
`header_rows=1`，与改动前逐字节等价。golden digest **零回归**（`check_sync_provider_golden_digest.py`
75 个 digest 逐个不变）确证。

D3-7 翻开关后 payload 实测正确（monkeypatch `_INCLUDE_D307_VOUCHER_CHECK=True`）：
- 区① `anchor="A15"` `header_rows=2`；区② `anchor="A29"` `header_rows=2`。
- customer_name(A,无组)→`header_source_ref=A15/A29`（组标题行）；voucher_date(B,记账凭证组)→
  `header_source_ref=B16/B30`（叶子行）+`group_source_ref=B15/B29`；supporting_doc 区①→I15、
  区②→H29（合并列主列）。

---

## 四、灰度开关 `phase5_d3_expansion._INCLUDE_D307_VOUCHER_CHECK`

新增 `_INCLUDE_D307_VOUCHER_CHECK: Final[bool] = False`（**初始 False**）+ `managed_row_table_specs()`
追加 D3-7 两区（`SPEC_D307_CURRENT`, `SPEC_D307_POST`，按 Excel 行序）。**本任务只声明不翻**——
翻开关须同步 `generate_phase5_d3_contract.py --apply` 重生成磁盘契约 + 使 Property 4 转绿，一并
留给 Task 12（接入验收），与 Task 8/9 只声明不翻、Task 10 统一翻的处置一致（Task 10 已确立
"翻开关必同步重生成磁盘契约"纪律）。

**循环层 `_expansion_sheets_payload()` 无需业务改动**（monkeypatch 打开开关实测）：其按
`sheet_key` 分组的通用逻辑把 D3-7 两 spec 归入一个 `d37-managed` 契约 sheet 条目含两 table
（`voucher_check_current_rows` / `voucher_check_post_rows`），store id 各归其表。§三的 payload
builder 两级表头修复是**支撑**性修复（让通用分组逻辑对两级表头也产出正确 payload），非改分组逻辑本身。

---

## 五、判据结果

| 判据 | 结果 |
|---|---|
| Task 3 `test_d3_07_voucher_check_store_item_ids_both_regions` | **SKIPPED → PASSED**（15 passed），两键逐字匹配 |
| Task 4 `test_d3_property3_4_dual_zone_baseline.py` | 6 passed；`test_d3_7_dual_zone_not_yet_reaching_target_count_of_seven` **保持红基线**（count<7、D3-7 键未进契约、开关 False）——未意外提前转绿 |
| `test_d3_expansion.py` | 9 passed 零回归（开关 False 契约不变） |
| golden digest（Task 2 口径） | **零回归**：75 digest 逐个不变 |
| 全量 D3 回归 `-k "d3 or D3"` | **1 failed / 103 passed / 2 xfailed / 9085 deselected** |

### 全量回归唯一失败 = 已知基线红（非本任务引入，逐条确认）

`test_task5_d3_performance_baseline.py::test_real_registration_path_fails_before_reaching_d3`
（"DID NOT RAISE"）——该判据连真库 `async_session` 调 `register_from_manifest()` 断言其**抛错**
（因别 lane 的 entry 契约漂移），与 D3-7 声明层零关联（本任务改动仅：新建 D3-7 声明模块 +
开关 False + 循环层两级表头兼容修复，后者在开关 False 时完全 inert，golden digest 零回归已证）。
任务原文已列此为已知基线红。**本任务新增失败 = 0。**

（任务列的另两条已知红 `test_row_table_engine_core_equivalence::…[d3]` / `test_excel_row_
insertion_scope_closure::…definition_store` 在本次 `-k "d3 or D3"` 过滤集内通过或未收集，
不在本轮 104 用例的失败里——与本任务无关。）

---

## 六、结论（回应完成标准）

1. ✅ 新建 `phase5_d3_07_voucher_check.py`（两 spec）+ `phase5_d3_expansion.py` 加开关（False）。
2. ✅ 循环层两级表头兼容修复（支撑 D3-7，零回归）。
3. ✅ Property 2 D3-7 部分 SKIPPED→PASSED；Property 3-4 D3-7 保持红基线未提前转绿。
4. ✅ golden digest + expansion 零回归。全量 D3 回归新增失败 0（唯一红为已知基线）。
5. ✅ BP-21 末行核查：R26/R38 全空、非占位行、末行不收缩。合并列 H:I 值写主列 H、I 不声明独立字段。
6. 未碰引擎/模板/tasks.md 标题行/别的会话在途文件；一次性探针用完即删。
