# Task 30：评估 D1-6 能否用 `TransposedSheetSpec` 表达

**实施日期**：2026-09-26　**方法**：openpyxl 独立直读模板几何 + 通读前端 `useD1BusinessMode.ts`
composable + 通读框架层 `TransposedSheetSpec`（`phase5_transposed_sheet.py`）与
`static_region`（`RowTableSheetSpec.binding_kind`）两条能力边界 + 读 `contracts.py:_parse_field`
的 schema 硬约束 + 对照 D4-12（转置表先例）/ E1-11（`static_region` 先例）/ D1-4 第三区
（形似矩阵但从未被真实验证跑通的声明）。

## 一、裁决：`TransposedSheetSpec` 与 `static_region` 都表达不了，登记 `NOT_EXPRESSIBLE`

D1-6 有两个受管候选，本任务只评估其中一个：

| 候选 | 结论 |
|---|---|
| `D1-bm-basis-rows`（3 固定行） | 已判定标准 `RowTableSheetSpec`（稳定 key 固定行，D4-6 范式），不在本任务评估范围 |
| `D1-bm-qa-matrix`（4×3 真二维矩阵） | **本任务评估对象，结论：表达不了** |

## 二、几何实测（openpyxl 直读 `D/D1 应收票据.xlsx` · `应收票据业务模式分析D1-6`）

```
16 | A16='了解并观察...' B16='信用等级高的银行承兑汇票' C16='信用等级低的银行承兑汇票' D16='商业承兑汇票'
17 | A17='1.是否涉及大额且频繁的...？' B17='是' C17='是' D17='是'
18 | A18='2.持有目的是否交易性...？' B18='否' C18='是' D18='是'
19 | A19='3.未来是否预期...？' B19='否' C19='否' D19='否'
20 | A20='4.未来是否预期...？' B20='否' C20='否' D20='否'
21 | A21='确定业务模式' B21='=IF(AND(B17="是",B18="否"),...)' C21='=IF(...)' D21='=IF(...)'
22 | A22='确定报表项目' B22='=IF(B21="...","应列报为应收款项融资","")' C22='=IF(...)' D22='=IF(...)'
```

矩阵绝对坐标 = `B17:D20`（4 行×3 列），无合并单元格干扰。行 21/22 是硬编码绝对引用矩阵的
派生公式行，前端 `businessModeResults`/`reportItemResults` 同样是纯 `computed()`，非受管对象。

前端 `useD1BusinessMode.ts` 逐行读取确认：`QACell{answer:'Y'|'N'|''}`、`cells:QACell[][]`
（[4行][3列]），4 个问题、3 个组合均硬编码常量永不增删，`updateQACell` 只做越界校验、
矩阵形状永不变。独立 store 键 `D1-bm-qa-matrix`，序列化产物是 `string[][]`（3×4 answer 值）。

## 三、`TransposedSheetSpec` 判定：表达不了

`phase5_transposed_sheet.py` 的核心假设是**动态多实体 + 异构字段类型**：`field_rows`（一字段
一整行）+ `first_entity_column`/`initial_entity_column`（一列一实体，超模板末列即样式克隆
扩列）+ `identity_carrier_row`/`identity_carrier_prefix`（给每实体列打隐藏 UUID）。对照
D4-12 真实先例（`phase5_d4_12_contract.py`）：21 字段行 × N 份合同列，列数动态可扩、
`entity_noun="contract"`。

D1-6 的 3 列组合永久固定（无扩列）、12 格统一同类型枚举（非异构字段），`identity_carrier_*`
这套身份机制对写死的列头标签毫无意义——设计契约（动态多实体）与实际语义（固定网格）不匹配，
判定为**表达不了**（Requirement 5.6 定义的"能力边界不匹配"情形，非语法凑不出来）。

## 四、`static_region` 判定：**也表达不了**（本轮复核纠正了初步方向性判断）

初步方向判断曾以为 `static_region` 能表达（类比 D1-4 第三区 `SPEC_D104_NOTETYPE`）。深入核实
`contracts.py:_parse_field`（第 908-934 行）后发现这是**硬 schema 约束**，不是可绕过的实现
细节：

```python
row_from = cell_raw.get("row_from")
if row_from == "row_identity":
    ...  # 动态行（excel_table binding）
elif isinstance(row_from, int) and row_from >= 1:
    ...  # 静态字段：cell = CellMapping(column=column, row_from="static", static_row=row_from)
else:
    raise ContractSchemaError(
        f"...cell.row_from 必须是 `row_identity` 或 >=1 的静态行号，实得 {row_from!r}"
    )
```

`row_from` **只接受单个 int 或字面量 `"row_identity"`，没有第三种「行区间」表达**。这意味着
`static_region` 的字段粒度永远是**单格**（一个 field_spec ↔ 一个绝对坐标），不存在"一个
field_spec 横跨 first_data_row..last_data_row 多行"的机制——这与 `excel_table` binding
（靠 `row_identity_key` UUID 做行区分）正好互斥，两者不能"各取所长"合成矩阵表达。

**排查了全部现存 `static_region` 真实先例**，均为"N 个字段各自一个不同绝对行"的散列单格
集合，从未出现"两个正交维度都需要被结构化表达"的矩阵：

| Provider | 形态 | 是否矩阵先例 |
|---|---|---|
| E1-11（`STATIC_CELL_ANCHORS_E111`） | 4 个互不相关的绝对坐标（承诺主体段落/日期/盖章/声明日期） | 否——`field_specs=()`，`STATIC_CELL_ANCHORS_E111` 完全在 `RowTableSheetSpec` 之外，仅供文档登记，不被引擎消费 |
| D1-4 第三区（`SPEC_D104_NOTETYPE`） | 形似矩阵（14 field_specs 共享骨架 + `first_data_row=23,last_data_row=24`） | 否——灰度开关 `_INCLUDE_D104_NOTETYPE_STATIC=False` 从未开启，全仓无任何 `_rows_table_payload` 真正把它装配成契约 JSON，现有判据只做纯 dataclass 字段校验，**从未真实跑过 extract/materialize 引擎**，不能当作"矩阵可行"的证据 |

若把 D1-6 矩阵拆成 12 个独立单格 field_specs（每格一个 stable_key，放弃"3 列共享骨架"的
简洁写法），技术上**合法**（schema 允许），但等于放弃矩阵结构本身，产出形状是 12 个散列
键值对（如 `{"B17":"是","C17":"否",...}`），需要额外手写 12 键 ↔ `cells[4][3]` 的映射表，
且前端现状（`useD1BusinessMode.ts`）从未有过这套映射、也不是本任务的登记范围。

## 五、裁决理由汇总

| 候选 | 判定 | 理由 |
|---|---|---|
| `TransposedSheetSpec` | ❌ 表达不了 | 动态多实体+异构字段类型假设，与固定 3×4 同类型枚举网格不匹配 |
| `static_region`（矩阵形态） | ❌ 表达不了 | `contracts.py:_parse_field` 的 `row_from` schema 硬约束只收单 int，无「行区间」表达 |
| `static_region`（12 单格降格） | ⚠️ 技术可行但放弃矩阵结构 | 需额外手写映射表，超出本任务范围，不在此登记为解 |

## 六、Requirement 5.6 登记

按范式（`pilot_h1.UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE`）在
`phase5_d1_06_business_mode.py` 登记模块级常量
`QA_MATRIX_NO_ROW_RANGE_CELL_MAPPING_NOT_EXPRESSIBLE`，叙述完整推理链（约束来源 /
证据出处 / 若强行绕过会丢什么 / 改选方案 / owner 建议）。

🔴 **本任务不新写任何引擎特例分支**（Requirement 5.6 明文禁止）——D1-6 QA 矩阵维持现状
（`useD1BusinessMode.ts` 纯 checklist_responses JSON 存储，不接入 Excel 双向同步契约）。
`D1-bm-basis-rows`（3 固定行）不受影响，其接入路径（标准 `RowTableSheetSpec`）由后续批次
任务决定，本任务不涉及。
