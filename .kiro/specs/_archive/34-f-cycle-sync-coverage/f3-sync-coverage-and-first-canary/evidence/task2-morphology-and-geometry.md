# Task 2：形态判定 + 几何逐格实测（F3）

**执行**：2026-09-26　**工具**：`backend/scripts/analyze/_probe_f345_geometry.py` /
`_probe_f345_multizone_uuid.py`（openpyxl 直读，`data_only=False`）

模板：`F/F3 应付票据.xlsx`　**sha256 `06de707ba4d4f8d91534e872c7d135b9576cc3a012e3877b1f60db59ce6b3a6b`**
（79,616 B，12 sheets）—— 与 spec 记载逐字一致。

## 🔴 一、共同缺陷修正：同 sheet 多区的 `uuid_col` 必须逐区独立

框架层 `phase5_row_table_sheet.spec_to_contract_sheet_payload` 用 **`uuid_col`** 把 spec 与
contract table 一一配对，源码注释原文：「同 sheet 双区配对键……缺它 → 匹配 0 张 →
`ProviderCapabilityError`」。生产先例 D3-4 双区用 **J/K**、D3-7 双区用 **R/S** —— 逐区独立。

而 spec design 的受管区清单把 F3-7 三区的 UUID 列**全写 S**。那是不可用的声明。

实测结论（F3-7，92r × 18c，max_col=R）：

```
全空列 (8): S T U V W X Y Z        ← 候选充足
需 3 个互不相同 ⇒ 分配 S / T / U
```

⇒ **F3-7 三区改为 `S`（区①借方）/ `T`（区②贷方）/ `U`（区③期后）**。
provider 侧已加防御：`build_contract_payload()` 在同 `sheet_key` 下发现兄弟区 `uuid_col`
重复时**直接抛** `EntrySelectionError`，消息点明「须为每区实测独立空列」——
不让这类声明再静默走到 registry 才炸。

同批实测的其余多区 sheet（F4/F5 的证据文件各自记录，此处只列结论）：

| sheet | 区数 | max_col | 全空列数 | 分配 |
|---|---|---|---|---|
| F3-7 应付票据检查表 | 3 | R | 8（S~Z） | S / T / U |
| F4-7 未入账检查表 | 5 | M | 10（L~U） | L / M / N / O / P（🔴 N/O/P 超 max_col，需扩列） |
| F4-8 应付账款检查表 | 2 | R | 8（S~Z） | S / T |
| F4-1 审定表 | 2 | L | 8（M~T） | M / N |
| F5-1 营业务成本审定表 | 2 | N | 12（K~V） | K / L |

## 二、canary：`逾期票据检查F3-5`（已声明并验通）

| 项 | 实测 | 与 spec |
|---|---|---|
| 尺寸 | 29r × 15c（O） | ✅ |
| 公式总数 | **10** = 7 页眉（R3/R4 引「底稿目录」）+ 3 footer（`SUM(J/K/O 7:21)`） | ✅ |
| 表头 | **两级 R5/R6** —— 合并区实测 `C5:E5`「票据关系人」·`F5:H5`「票据期限」·`N5:O5`「抵押情况」三个横向组 + `A5:A6`/`B5:B6`/`I5:I6`/`J5:J6`/`K5:K6`/`L5:L6`/`M5:M6` 七个纵向合并 | ✅ |
| 数据区 | **R7-21** | ✅ |
| footer | **R22**，A22 逐字 = `'合计'`（纯两字**无空格**） | ✅ |
| UUID 列 | 全空列 P/Q/R/S ⇒ 取 **P**（O 是有 SUM 的业务列不可占用） | ✅ |
| `formula_columns` | **`()`** —— 数据区零公式 | ✅ |
| 数据验证 | `A7:A21`「银行承兑汇票,商业承兑汇票」· `M7:M21`「是,否」 | ✅ |

表头逐列（R5 组 / R6 叶）：
`A 票据类别 · B 票据号 · C-E 票据关系人{出票人/承兑人/收款人} · F-H 票据期限{出票日/到期日/期限} ·
I 票面利率 · J 票面金额 · K 期后支付金额 · L 借款条件 · M 是否调整 · N-O 抵押情况{物品名称/金额}`

### 🔴 修正一：FC-10 判定必须三条同时成立，不能只看 `number_format`

数据区 R7-21 里 `number_format` 含 `%` 的列实测有 **C / D / E / I** 四列，但只有 **I** 真命中：

| 列 | R6 表头（语义） | 模板格式 | 前端字段 | 判定 |
|---|---|---|---|---|
| C | 出票人 | `0.00%` | `drawer: string` | ❌ **文本列套错格式**（模板治理债） |
| D | 承兑人 | `0.00%` | `acceptor: string` | ❌ 同上 |
| E | 收款人 | `0.00%` | `payee: string` | ❌ 同上 |
| **I** | **票面利率** | `0.00%` | `interestRate: number`（标签「(%)」存百分数） | 🔴 **命中 FC-10** |

⇒ 判据是「**前端存 % 数值 ∧ 模板百分比格式 ∧ 该列语义确实是比率**」三者同时成立。
本 spec 实施中曾只看 `number_format` 误判成「四列命中」，会让 canary 白丢三个关系人字段。
判据 `TestProperty9Fc10Deferred::test_text_columns_with_percent_format_are_still_managed`
把这条钉住。M 列「是否调整」也套了数字格式 `#,##0.00_ `（枚举列），同属治理债。

### 🔴 修正二：真库载荷是 2 行「空白行」，不是可用的业务数据

spec 裁决 F3-H1 写「真库唯一有载荷的 sheet（675 B，**可做真数据往返**）」。
实测该 675 B 的内容：

```json
[{"rowId":"f3o-mrpn3xhk-ypdgcsm","seq":1,"attSlot":1,"noteType":"","ticketNo":"",
  "drawer":"","acceptor":"","payee":"","issueDate":"","dueDate":"","termDays":0,
  "overdueDays":0,"interestRate":0,"faceValue":0,"postPaymentAmount":0,
  "unpaidAmount":0,"loanConditions":"","isAdjusted":"","collateralName":"",
  "collateralAmount":0,"riskFlags":[]}, {…第二行同形…}]
```

⇒ 只有 `rowId` / `seq` / `attSlot` 有值，**全部业务字段为空/0**（用户打开过表但没录数）。
可验证的是「真行身份 + 键映射 + 投影/合并管线」，**不是**「真实数值往返」。
⇒ 表述修正为「真行身份 + 空业务值」；有意义数值的 roundtrip 与 F5 一样需要 seed。
（判据 `TestProjectionRoundtrip` 用该真载荷跑出 2 行 × 14 字段 = 28 个 `FieldValue`。）

## 三、F3-7 三区几何（逐格实测，待 Task 14 声明）

三区标题 / 表头 / 数据 / footer 全部由 A 列锚点 + footer 的 SUM 区间反推：

| 区 | 标题行 | 表头 | 数据区 | footer | footer SUM 列 | uuid_col |
|---|---|---|---|---|---|---|
| ① 本期借方金额检查 | R14 | R15/R16 | **R17-36** | R37「合计」 | F, L | **S** |
| ② 贷方金额检查 | R38 | R39/R40 | **R41-58** | R59「合计」 | F, **N** | **T** |
| ③ 资产负债表日后借方检查 | R60 | R61/R62 | **R63-79** | R80「合计」 | F, L | **U** |

与 spec 受管区清单的行号逐项一致（R17-36 / R41-58 / R63-79 ✅）。

🔴 **三区列集确实不同**（spec 需求 5.2 的结论得到实测支持）——合并区形态：

```
区①：H15:I15 + J15:L15        （两个横向组）
区②：H39:K39 + L39:N39        （组边界不同，且 footer SUM 到 N 列）
区③：H61:I61 + J61:L61        （与区① 同构）
```

⇒ 区①③ 同构、区② 独立。必须各自声明 `field_specs`，不得抽公共元组。

## 四、其余 sheet 的实测策略

F3-6 / F3-2 / F3-4 / F3-1 的逐格几何在各自声明任务（Task 13 / 15 / 16 / 19）中随实测随声明 ——
「实测即用」比先攒一份大表更不易积压漂移（本批已按此方式完成 F3-5 与 F3-7 的多区取证）。
本文件已覆盖：canary 全量 + 多区 `uuid_col` 可行性（这两项是阻塞面）。

## 五、前端三元组实证（canary）

| 维度 | 实测 |
|---|---|
| store 键 | `F3-5-rows`（`useF3OverdueCheck.ts:55 STORAGE_KEY`），**无 legacy 别名** |
| 增删行 | `addRow` / `removeRow` 各 1 处（另各 1 处出现在 return 暴露） |
| 行身份 | **`rowId`**（`F3OverdueNoteRow.rowId`；真库 2 行全带 `rowId`、0 行带 `id`） |
| 判定 | `BindingKind.excel_table` + `row_identity_key="rowId"` + `StoreKind.rows` |

🔴 F3 用 `rowId`，而 F5-2/3/5/8 用 **`id`** —— 两套惯例并存，逐 entry 按值实测（FC-4）。

🔴 数据区零公式若按「公式数阈值」判形态会被误判 `static_region`，判据
`TestProperty3Triad::test_zero_formula_data_region_is_not_static_region` 守住这一点。

store-only 字段（模板无对应列，已在声明层登记）：`seq` · `attSlot` · `overdueDays` ·
`unpaidAmount` · `riskFlags`。

## 六、模板治理债汇总（登记，不改字节）

| 位置 | 问题 |
|---|---|
| F3-5 C/D/E 列 | 文本列（出票人/承兑人/收款人）套 `0.00%` 数字格式 |
| F3-5 M 列 | 枚举列（是否调整，DV「是,否」）套 `#,##0.00_ ` 数字格式 |
| sheet 名 `应付票据实质性程序表F3A␠` | 末尾空格（宿主正则 `/(F3A\|F3-\d+)/` 恰好不受影响，但任何按 sheet 名精确匹配的新代码都会踩） |
| F3-5 DV vs 前端枚举 | 模板 `A7:A21` 只 2 枚举，前端 `F3_OVERDUE_NOTE_TYPES` 有 4 项（含供应链票据/其他）；`M7:M21` 只「是,否」而前端 `F3_YES_NO_OPTIONS` 有「不适用」⇒ 受管后 OO 侧下拉选不到多出的项（与红基线 B3 同源，归裁决 F3-H5 的降级面） |
